"""Mobile proxies' "change IP" links: an HTTP GET that makes the modem reconnect."""

import urllib.error
import urllib.request

from ...core.logging import get_logger

logger = get_logger("proxy.rotate")

TIMEOUT = 20


def rotate_ip(url: str, timeout: float = TIMEOUT) -> tuple[bool, str]:
    """Call the rotate link directly (not through the proxy). Returns (ok, short reply).

    The link carries the provider's key, so it is never logged.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "CloutFox"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(300).decode("utf-8", "replace")
            return True, " ".join(body.split())[:160]
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        logger.info("IP rotation failed: %s", reason)
        return False, str(reason)[:160]
