import functools
import re
import zoneinfo
from collections.abc import Callable
from urllib.parse import urlparse

from ..core.strings import get_string
from .proxy_parser import normalize_proxy

_INVALID_CHARS = '<>:"/\\|?*'
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_PROXY_PATTERN = re.compile(
    r"^(?:(?P<scheme>https?|socks[45])://)?"
    r"(?:(?P<user>[^:@]+):(?P<pass>[^@]+)@)?"
    r"(?P<host>[a-zA-Z0-9.-]+|\d{1,3}(?:\.\d{1,3}){3}|\[(?:[a-fA-F0-9:]+)\])"
    r":(?P<port>\d{1,5})$",
)
# language[-Script]-REGION, e.g. vi-VN, zh-Hant-TW, es-419
_LOCALE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?-(?:[A-Z]{2}|\d{3})$")


def validate_profile_name(name: str) -> tuple[bool, str]:
    if not name:
        return False, get_string("validation_empty_name")

    if len(name) > 64:
        return False, get_string("validation_name_too_long")

    found_invalid = [c for c in name if c in _INVALID_CHARS]
    if found_invalid:
        return False, get_string("validation_invalid_chars", chars=", ".join(found_invalid))

    # Reject control characters (ASCII < 32 or DEL=127): they cause mkdir to fail
    found_control = [repr(c) for c in name if ord(c) < 32 or ord(c) == 127]
    if found_control:
        return False, get_string("validation_invalid_chars", chars=", ".join(found_control))

    if name != name.strip():
        return False, get_string("validation_name_spaces")

    # The name becomes a directory under DATA_DIR: "." and ".." would resolve
    # to DATA_DIR or its parent (and deleting the profile would delete them),
    # and Windows silently strips trailing dots.
    if name.endswith("."):
        return False, get_string("validation_trailing_dot")

    if name.upper() in _RESERVED_NAMES:
        return False, get_string("validation_reserved_name", name=name)

    return True, ""


def validate_proxy_format(proxy_str: str) -> tuple[bool, str]:
    if not proxy_str:
        return True, ""

    match = _PROXY_PATTERN.match(normalize_proxy(proxy_str))
    if not match:
        return False, get_string("validation_invalid_proxy")

    port = int(match.group("port"))
    if not 1 <= port <= 65535:
        return False, get_string("validation_invalid_port", port=port)

    # RFC 1035/1123: a hostname must not exceed 253 characters.  Strip IPv6
    # brackets before measuring so "[::1]" does not count as 5 chars.
    host = match.group("host").strip("[]")
    if len(host) > 253:
        return False, get_string("validation_invalid_proxy")

    return True, ""


def validate_timezone(value: str) -> tuple[bool, str]:
    """An IANA timezone such as Asia/Ho_Chi_Minh; empty means automatic."""
    if not value:
        return True, ""
    if value not in _timezones():
        return False, get_string("validation_invalid_timezone", value=value)
    return True, ""


def validate_locale(value: str) -> tuple[bool, str]:
    """A language-region locale such as vi-VN; empty means automatic."""
    if not value:
        return True, ""
    if not _LOCALE_PATTERN.match(value):
        return False, get_string("validation_invalid_locale", value=value)
    try:
        from camoufox.locales import normalize_locale

        normalize_locale(value)
    except ImportError:
        pass
    except Exception:
        return False, get_string("validation_invalid_locale", value=value)
    return True, ""


def valid_or_none(value: object, validate: Callable[[str], tuple[bool, str]]) -> str | None:
    """A stored timezone/locale if it is still usable, else None (= automatic)."""
    if not isinstance(value, str) or not value or not validate(value)[0]:
        return None
    return value


@functools.cache
def _timezones() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


MAX_TAGS = 20
MAX_TAG_LENGTH = 32
MAX_NOTES_LENGTH = 2000
MAX_START_URLS = 20


def normalize_tags(value: object) -> list[str]:
    """Tags from a list or a comma-separated string: trimmed, lower-case, unique."""
    if isinstance(value, str):
        items: list[object] = list(value.split(","))
    elif isinstance(value, list | tuple):
        items = list(value)
    else:
        return []
    tags: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        tag = " ".join(item.split()).lower()[:MAX_TAG_LENGTH]
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:MAX_TAGS]


def validate_http_url(value: str) -> tuple[bool, str]:
    """An absolute http(s) URL; empty is allowed."""
    if not value:
        return True, ""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or " " in value:
        return False, get_string("validation_invalid_url", value=value)
    return True, ""


def normalize_urls(value: object) -> list[str]:
    """http(s) URLs from a list or one-per-line text; invalid ones are dropped."""
    if isinstance(value, str):
        items: list[object] = list(value.splitlines())
    elif isinstance(value, list | tuple):
        items = list(value)
    else:
        return []
    urls: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        url = item.strip()
        if url and validate_http_url(url)[0] and url not in urls:
            urls.append(url)
    return urls[:MAX_START_URLS]


def validate_urls(value: str | list[str]) -> tuple[bool, str]:
    """Every non-empty line (or item) is an http(s) URL, and there are not too many."""
    items = value.splitlines() if isinstance(value, str) else value
    urls = [u.strip() for u in items if u.strip()]
    for url in urls:
        ok, msg = validate_http_url(url)
        if not ok:
            return ok, msg
    if len(urls) > MAX_START_URLS:
        return False, get_string("validation_too_many_urls", max=MAX_START_URLS)
    return True, ""
