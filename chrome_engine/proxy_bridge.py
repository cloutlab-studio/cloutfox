"""A loopback proxy that lets Chromium use proxies with credentials.

Chromium cannot take proxy credentials on the command line, and it cannot
authenticate to SOCKS5 proxies at all. The bridge listens on 127.0.0.1 without
authentication, Chromium is pointed at it as a plain HTTP proxy, and the bridge
opens every connection through the real upstream proxy with its credentials.

Target hostnames are always passed to the upstream (HTTP CONNECT or SOCKS5
domain addressing), never resolved here, so DNS does not leak past the proxy.

The bridge has no password, so it serves only connections from its own OS user:
on Linux the socket owner comes from /proc/net/tcp, on Windows the owning PID and
its user SID from GetExtendedTcpTable and the process token. Other users of the
machine cannot borrow the proxy while a profile runs.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import ipaddress
import os
import ssl
import struct
import sys
from collections import deque
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

_HEAD_LIMIT = 64 * 1024
_BUFFER = 64 * 1024
CONNECT_TIMEOUT = 20.0
_HOP_HEADERS = {"proxy-authorization", "proxy-connection", "connection", "keep-alive"}


class UpstreamError(Exception):
    """The upstream proxy refused or failed a connection."""


@dataclass(frozen=True)
class Upstream:
    scheme: str  # http, https, socks5
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    @classmethod
    def parse(cls, proxy: str) -> Upstream:
        """Parse scheme://user:pass@host:port or host:port:user:pass (http by default)."""
        from src.utils.proxy_parser import normalize_proxy

        text = normalize_proxy(proxy.strip())
        if "://" not in text:
            text = "http://" + text
        parts = urlsplit(text)
        scheme = parts.scheme.lower()
        if scheme == "socks5h":
            scheme = "socks5"
        if scheme not in ("http", "https", "socks5"):
            raise ValueError(f"Unsupported proxy scheme {parts.scheme!r} (http, https, socks5)")
        try:
            port = parts.port
        except ValueError:
            port = None
        if not parts.hostname or not port:
            raise ValueError("Proxy must include a host and a port")
        return cls(
            scheme=scheme,
            host=parts.hostname,
            port=port,
            username=unquote(parts.username) if parts.username else None,
            password=unquote(parts.password) if parts.password else None,
        )

    @property
    def display(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    def basic_auth(self) -> str | None:
        if not self.username:
            return None
        raw = f"{self.username}:{self.password or ''}".encode()
        return "Basic " + base64.b64encode(raw).decode()


def _proc_address(text: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, int]:
    """An address from /proc/net/tcp{,6}: hex words in host byte order, then the port."""
    host, port = text.split(":")
    raw = b"".join(struct.pack("=I", int(host[i : i + 8], 16)) for i in range(0, len(host), 8))
    ip = ipaddress.ip_address(raw)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip, int(port, 16)


def socket_owner(local: tuple, remote: tuple, tables: tuple[str, ...] | None = None) -> int | None:
    """The UID owning the TCP socket local -> remote (Linux), or None if not listed."""
    want = (
        (ipaddress.ip_address(local[0]), local[1]),
        (ipaddress.ip_address(remote[0]), remote[1]),
    )
    for table in tables or ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(table, encoding="ascii") as f:
                lines = f.readlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 8:
                continue
            try:
                if (_proc_address(fields[1]), _proc_address(fields[2])) == want:
                    return int(fields[7])
            except ValueError:
                continue
    return None


def _same_user_default() -> int | None:
    return os.getuid() if sys.platform.startswith("linux") else None


# --- Windows: who owns the client socket ----------------------------------------------
#
# Loopback is not per-user on Windows: any account on the machine can reach the
# bridge's port. The browser runs as this user, so the client's socket must belong
# to a process of this user. Windows offers no /proc: the owning PID comes from
# GetExtendedTcpTable, the user from the process token (a SID string).

_TCP_TABLE_OWNER_PID_ALL = 5
_AF_INET = 2


def _net_port(value: int) -> int:
    """A port from a table row: stored in network byte order in the low two bytes."""
    return ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)


def _windows_socket_pid(peer_port: int, local_port: int) -> int | None:
    """The PID owning the client's TCP connection to this bridge, or None."""
    import ctypes
    from ctypes import wintypes

    class Row(ctypes.Structure):
        _fields_ = [
            ("state", wintypes.DWORD),
            ("local_addr", wintypes.DWORD),
            ("local_port", wintypes.DWORD),
            ("remote_addr", wintypes.DWORD),
            ("remote_port", wintypes.DWORD),
            ("pid", wintypes.DWORD),
        ]

    iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
    size = wintypes.DWORD(0)
    iphlpapi.GetExtendedTcpTable(
        None, ctypes.byref(size), False, _AF_INET, _TCP_TABLE_OWNER_PID_ALL, 0
    )
    if not size.value:
        return None
    buffer = ctypes.create_string_buffer(size.value)
    result = iphlpapi.GetExtendedTcpTable(
        buffer, ctypes.byref(size), False, _AF_INET, _TCP_TABLE_OWNER_PID_ALL, 0
    )
    if result != 0:
        return None
    count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD))[0]
    rows = ctypes.cast(ctypes.byref(buffer, ctypes.sizeof(wintypes.DWORD)), ctypes.POINTER(Row))
    for i in range(count):
        row = rows[i]
        # The client's socket: its local end is the peer we see, its remote end ours.
        if _net_port(row.local_port) == peer_port and _net_port(row.remote_port) == local_port:
            return int(row.pid)
    return None


def _windows_process_sid(pid: int) -> str | None:
    """The SID of a process's user as a string, or None when Windows refuses."""
    import ctypes
    from ctypes import wintypes

    TOKEN_QUERY = 0x8
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    TOKEN_USER = 1
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return None
    token = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
            return None
        size = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, TOKEN_USER, None, 0, ctypes.byref(size))
        if not size.value:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(token, TOKEN_USER, buffer, size, ctypes.byref(size)):
            return None
        # TOKEN_USER starts with SID_AND_ATTRIBUTES, whose first member is the SID pointer.
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(ctypes.c_void_p(sid), ctypes.byref(text)):
            return None
        try:
            return text.value
        finally:
            kernel32.LocalFree(text)
    finally:
        if token:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(process)


def own_sid() -> str | None:
    """This process's user SID on Windows, or None elsewhere."""
    if sys.platform != "win32":
        return None
    try:
        return _windows_process_sid(os.getpid())
    except Exception:  # a machine without the API: the check is simply off
        return None


def windows_socket_owner(peer: tuple, local: tuple) -> tuple[bool, str | None]:
    """(the connection was found in the table, the SID of the user who owns it)."""
    try:
        pid = _windows_socket_pid(peer[1], local[1])
    except Exception:
        return False, None
    if pid is None:
        return False, None
    try:
        return True, _windows_process_sid(pid)
    except Exception:
        return True, None


async def _read_head(reader: asyncio.StreamReader) -> bytes:
    try:
        return await reader.readuntil(b"\r\n\r\n")
    except asyncio.LimitOverrunError as e:
        raise UpstreamError("Header too large") from e


def _split_host_port(authority: str, default_port: int) -> tuple[str, int]:
    if authority.startswith("["):
        host, _, rest = authority[1:].partition("]")
        port = rest[1:] if rest.startswith(":") else ""
    else:
        host, _, port = authority.rpartition(":") if ":" in authority else (authority, "", "")
    return host, int(port) if port else default_port


async def open_tunnel(
    upstream: Upstream, host: str, port: int
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """A byte stream to host:port through the upstream proxy."""
    use_tls = ssl.create_default_context() if upstream.scheme == "https" else None
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(
            upstream.host,
            upstream.port,
            ssl=use_tls,
            server_hostname=upstream.host if use_tls else None,
            limit=_HEAD_LIMIT,
        ),
        CONNECT_TIMEOUT,
    )
    try:
        if upstream.scheme == "socks5":
            await asyncio.wait_for(
                _socks5_connect(reader, writer, upstream, host, port), CONNECT_TIMEOUT
            )
        else:
            await asyncio.wait_for(
                _http_connect(reader, writer, upstream, host, port), CONNECT_TIMEOUT
            )
    except BaseException:
        writer.close()
        raise
    return reader, writer


def _authority(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


async def _http_connect(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    upstream: Upstream,
    host: str,
    port: int,
) -> None:
    target = _authority(host, port)
    lines = [f"CONNECT {target} HTTP/1.1", f"Host: {target}"]
    auth = upstream.basic_auth()
    if auth:
        lines.append(f"Proxy-Authorization: {auth}")
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode())
    await writer.drain()
    head = await _read_head(reader)
    status = head.split(b"\r\n", 1)[0].decode("latin-1")
    parts = status.split(" ", 2)
    if len(parts) < 2 or parts[1] != "200":
        raise UpstreamError(f"Upstream refused CONNECT {target}: {status}")


_SOCKS_REPLIES = {
    1: "general failure",
    2: "connection not allowed",
    3: "network unreachable",
    4: "host unreachable",
    5: "connection refused",
    6: "TTL expired",
    7: "command not supported",
    8: "address type not supported",
}


async def _socks5_connect(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    upstream: Upstream,
    host: str,
    port: int,
) -> None:
    methods = b"\x00\x02" if upstream.username else b"\x00"
    writer.write(b"\x05" + bytes([len(methods)]) + methods)
    await writer.drain()
    version, method = await reader.readexactly(2)
    if version != 5:
        raise UpstreamError("Upstream is not a SOCKS5 proxy")
    if method == 0x02:
        user = (upstream.username or "").encode()
        password = (upstream.password or "").encode()
        if len(user) > 255 or len(password) > 255:
            raise UpstreamError("SOCKS5 credentials are limited to 255 bytes")
        writer.write(b"\x01" + bytes([len(user)]) + user + bytes([len(password)]) + password)
        await writer.drain()
        _, status = await reader.readexactly(2)
        if status != 0:
            raise UpstreamError("SOCKS5 authentication failed")
    elif method != 0x00:
        raise UpstreamError("SOCKS5 proxy requires an authentication method we do not have")

    try:
        ip = ipaddress.ip_address(host)
        address = (b"\x01" if ip.version == 4 else b"\x04") + ip.packed
    except ValueError:
        name = host.encode("idna")
        address = b"\x03" + bytes([len(name)]) + name
    writer.write(b"\x05\x01\x00" + address + port.to_bytes(2, "big"))
    await writer.drain()
    _, rep, _, atyp = await reader.readexactly(4)
    if atyp == 1:
        await reader.readexactly(4 + 2)
    elif atyp == 4:
        await reader.readexactly(16 + 2)
    elif atyp == 3:
        (length,) = await reader.readexactly(1)
        await reader.readexactly(length + 2)
    if rep != 0:
        raise UpstreamError(
            f"SOCKS5 connect to {host}:{port} failed: {_SOCKS_REPLIES.get(rep, rep)}"
        )


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(_BUFFER):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError, asyncio.IncompleteReadError):
        pass
    finally:
        with contextlib.suppress(Exception):
            if writer.can_write_eof():
                writer.write_eof()


async def _close(writer: asyncio.StreamWriter) -> None:
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()


def _rewrite_request(head: bytes, origin_form: bool, auth: str | None) -> bytes:
    """Drop hop-by-hop proxy headers, force Connection: close, optionally add auth."""
    lines = head.decode("latin-1").split("\r\n")
    method, target, version = lines[0].split(" ", 2)
    if origin_form:
        parts = urlsplit(target)
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
    out = [f"{method} {target} {version}"]
    for line in lines[1:]:
        if not line:
            continue
        name = line.split(":", 1)[0].strip().lower()
        if name not in _HOP_HEADERS:
            out.append(line)
    if auth:
        out.append(f"Proxy-Authorization: {auth}")
    out.append("Connection: close")
    return ("\r\n".join(out) + "\r\n\r\n").encode("latin-1")


class ProxyBridge:
    """Loopback HTTP proxy forwarding through an authenticated upstream proxy."""

    def __init__(
        self, upstream: Upstream, host: str = "127.0.0.1", only_uid: int | None = -1
    ) -> None:
        self.upstream = upstream
        self.host = host
        # Serve only this OS user's connections; -1: this process's user on Linux,
        # None: anyone (no socket owners to check on other systems).
        self.only_uid = _same_user_default() if only_uid == -1 else only_uid
        # Windows has no UIDs: the same rule is kept by the client's user SID.
        self.only_sid = own_sid() if only_uid == -1 else None
        self.port = 0
        self.connections = 0
        self.refused = 0
        self.errors: deque[str] = deque(maxlen=20)
        self._server: asyncio.base_events.Server | None = None
        self._clients: set[asyncio.Task] = set()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def start(self) -> ProxyBridge:
        self._server = await asyncio.start_server(self._accept, self.host, 0, limit=_HEAD_LIMIT)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            for task in list(self._clients):
                task.cancel()
            await asyncio.gather(*self._clients, return_exceptions=True)
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    async def __aenter__(self) -> ProxyBridge:
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task:
            self._clients.add(task)
        try:
            if not self._allowed(writer):
                self.refused += 1
                writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                return
            await self._handle(reader, writer)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # one bad connection must not stop the bridge
            self.errors.append(f"{type(e).__name__}: {e}")
        finally:
            await _close(writer)
            if task:
                self._clients.discard(task)

    def _allowed(self, writer: asyncio.StreamWriter) -> bool:
        if self.only_uid is None and self.only_sid is None:
            return True
        peer = writer.get_extra_info("peername")
        local = writer.get_extra_info("sockname")
        if not peer or not local:
            return True
        if self.only_uid is not None:
            owner = socket_owner(peer[:2], local[:2])
            if owner != self.only_uid:
                self.errors.append(f"refused a connection from UID {owner} (not this user)")
                return False
            return True
        found, sid = windows_socket_owner(peer[:2], local[:2])
        if not found:
            # The connection closed between accepting it and the lookup.
            return True
        if sid == self.only_sid:
            return True
        # Another account, or a process whose user Windows would not tell us:
        # the browser runs as this user, so it always resolves.
        self.errors.append(f"refused a connection from another user ({sid or 'unknown'})")
        return False

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await _read_head(reader)
        except (asyncio.IncompleteReadError, ConnectionError):
            return
        request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
        parts = request_line.split(" ")
        if len(parts) != 3:
            writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            return
        method, target, _ = parts
        self.connections += 1

        connect = method.upper() == "CONNECT"
        try:
            if connect:
                host, port = _split_host_port(target, 443)
            else:
                url = urlsplit(target)
                if url.scheme != "http" or not url.hostname:
                    raise ValueError("not an absolute http:// URL")
                host, port = url.hostname, url.port or 80
            if not 0 < port < 65536:
                raise ValueError("port out of range")
        except ValueError:
            writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            return

        up_writer: asyncio.StreamWriter | None = None
        try:
            try:
                if not connect and self.upstream.scheme in ("http", "https"):
                    # Plain HTTP through an HTTP proxy: forward the absolute-form request.
                    up_reader, up_writer = await self._open_upstream_raw()
                    prefix = _rewrite_request(
                        head, origin_form=False, auth=self.upstream.basic_auth()
                    )
                else:
                    up_reader, up_writer = await open_tunnel(self.upstream, host, port)
                    prefix = b"" if connect else _rewrite_request(head, True, None)
            except (OSError, UpstreamError, asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
                message = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                self.errors.append(f"{host}:{port}: {message}")
                writer.write(
                    b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n"
                    + message.encode("utf-8", "replace")
                )
                return

            if connect:
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                up_writer.write(prefix)
                await up_writer.drain()
            await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))
        finally:
            if up_writer is not None:
                await _close(up_writer)

    async def _open_upstream_raw(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        use_tls = ssl.create_default_context() if self.upstream.scheme == "https" else None
        return await asyncio.wait_for(
            asyncio.open_connection(
                self.upstream.host,
                self.upstream.port,
                ssl=use_tls,
                server_hostname=self.upstream.host if use_tls else None,
            ),
            CONNECT_TIMEOUT,
        )
