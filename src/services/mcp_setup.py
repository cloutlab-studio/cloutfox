"""Ready-to-paste MCP client configurations, shared by the desktop app and the REST API."""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import asdict, dataclass

TOKEN_PLACEHOLDER = "<CLOUTFOX_API_TOKEN>"
MCP_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "cloutfox_mcp.py"


@dataclass
class ClientConfig:
    id: str
    name: str
    where: str  # where the snippet goes: a terminal or a config file path
    language: str  # "bash" or "json", for display
    code: str


def console_python(executable: str = sys.executable) -> str:
    """The interpreter for a stdio server: the app may run under pythonw.exe,
    which has no console streams, so its python.exe sibling is used instead."""
    path = pathlib.Path(executable)
    if path.name.lower() == "pythonw.exe":
        console = path.with_name("python.exe")
        if console.exists():
            return str(console)
    return executable


def _json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def build_configs(
    mcp_url: str,
    token: str | None,
    *,
    local: bool,
    python: str | None = None,
    api_url: str | None = None,
) -> list[ClientConfig]:
    """Configs for common MCP clients.

    `token` is the real token, a placeholder, or None when the API has none.
    `local` adds a Claude Desktop config that starts CloutFox's stdio MCP
    server on this machine; otherwise Claude Desktop goes through mcp-remote.
    """
    auth = {"Authorization": f"Bearer {token}"} if token else {}
    header_flag = f' --header "Authorization: Bearer {token}"' if token else ""

    configs = [
        ClientConfig(
            id="claude-code",
            name="Claude Code",
            where="Terminal",
            language="bash",
            code=f"claude mcp add --transport http cloutfox {mcp_url}{header_flag}",
        ),
        ClientConfig(
            id="cursor",
            name="Cursor",
            where="~/.cursor/mcp.json",
            language="json",
            code=_json(
                {
                    "mcpServers": {
                        "cloutfox": {"url": mcp_url, **({"headers": auth} if auth else {})}
                    }
                },
            ),
        ),
        ClientConfig(
            id="vscode",
            name="VS Code",
            where=".vscode/mcp.json",
            language="json",
            code=_json(
                {
                    "servers": {
                        "cloutfox": {
                            "type": "http",
                            "url": mcp_url,
                            **({"headers": auth} if auth else {}),
                        },
                    },
                },
            ),
        ),
    ]

    desktop_where = (
        "%APPDATA%\\Claude\\claude_desktop_config.json"
        if sys.platform == "win32"
        else "~/Library/Application Support/Claude/claude_desktop_config.json"
    )
    if local:
        env = {"CLOUTFOX_URL": api_url or mcp_url.rsplit("/mcp", 1)[0]}
        if token:
            env["CLOUTFOX_API_TOKEN"] = token
        server = {
            "command": python or console_python(),
            "args": [str(MCP_SCRIPT)],
            "env": env,
        }
    else:
        # Claude Desktop's config file only starts local (stdio) servers;
        # mcp-remote bridges it to the HTTP endpoint.
        args = ["-y", "mcp-remote", mcp_url]
        server = {"command": "npx", "args": args}
        if token:
            args += ["--header", "Authorization:${CLOUTFOX_AUTH}"]
            server["env"] = {"CLOUTFOX_AUTH": f"Bearer {token}"}
    configs.append(
        ClientConfig(
            id="claude-desktop",
            name="Claude Desktop",
            where=desktop_where,
            language="json",
            code=_json({"mcpServers": {"cloutfox": server}}),
        ),
    )
    return configs


def as_dicts(configs: list[ClientConfig]) -> list[dict]:
    return [asdict(c) for c in configs]
