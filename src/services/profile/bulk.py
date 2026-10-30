"""Many profiles at once: names from a pattern, proxies from a pool, list import."""

import random
import re

from ...core.strings import get_string
from ...utils.validation import validate_profile_name, validate_proxy_format

MAX_BULK = 500
PROXY_MODES = ("order", "random")
_COUNTER = re.compile(r"\{n\}")


class BulkError(ValueError):
    """Input that cannot produce the profiles asked for; the message is for the user."""


def expand_names(pattern: str, count: int, start: int = 1) -> list[str]:
    """fb-{n} with count 3 from 1 -> fb-1, fb-2, fb-3; numbers padded to equal width.

    A pattern without {n} gets "-{n}" appended.
    """
    pattern = pattern.strip()
    if not 1 <= count <= MAX_BULK:
        raise BulkError(get_string("bulk_count_range", max=MAX_BULK))
    if start < 0:
        raise BulkError(get_string("bulk_count_range", max=MAX_BULK))
    if not _COUNTER.search(pattern):
        pattern += "-{n}"
    width = len(str(start + count - 1))
    names = [_COUNTER.sub(str(n).zfill(width), pattern) for n in range(start, start + count)]
    for name in names:
        ok, msg = validate_profile_name(name)
        if not ok:
            raise BulkError(msg)
    return names


def parse_lines(text: str) -> list[str]:
    """Non-empty lines without surrounding spaces; # starts a comment line."""
    return [s for line in text.splitlines() if (s := line.strip()) and not s.startswith("#")]


def check_proxies(proxies: list[str]) -> None:
    for proxy in proxies:
        ok, msg = validate_proxy_format(proxy)
        if not ok:
            raise BulkError(f"{proxy}: {msg}")


def assign_proxies(count: int, proxies: list[str], mode: str = "order") -> list[str]:
    """A proxy for each of `count` profiles ("" = direct).

    order: one per profile, in order; fewer proxies than profiles is an error so
    no two accounts share an address by accident. random: drawn from the pool,
    repeats allowed. A single proxy is given to every profile in either mode.
    """
    if mode not in PROXY_MODES:
        raise BulkError(f"proxy mode must be one of: {', '.join(PROXY_MODES)}")
    check_proxies(proxies)
    if not proxies:
        return [""] * count
    if len(proxies) == 1:
        return proxies * count
    if mode == "random":
        return [random.choice(proxies) for _ in range(count)]
    if len(proxies) < count:
        raise BulkError(get_string("bulk_not_enough_proxies", proxies=len(proxies), count=count))
    return proxies[:count]


def parse_profile_list(text: str) -> list[dict]:
    """Lines of name;proxy;tags;notes (only the name is required; tags comma-separated)."""
    rows = []
    for number, line in enumerate(parse_lines(text), 1):
        name, proxy, tags, notes = ([*line.split(";", 3), "", "", ""])[:4]
        name, proxy = name.strip(), proxy.strip()
        ok, msg = validate_profile_name(name)
        if not ok:
            raise BulkError(get_string("bulk_line_error", line=number, error=msg))
        ok, msg = validate_proxy_format(proxy)
        if not ok:
            raise BulkError(get_string("bulk_line_error", line=number, error=msg))
        rows.append({"name": name, "proxy": proxy, "tags": tags, "notes": notes.strip()})
    if len(rows) > MAX_BULK:
        raise BulkError(get_string("bulk_count_range", max=MAX_BULK))
    return rows
