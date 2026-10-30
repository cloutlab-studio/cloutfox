"""Per-launch options passed from the launcher to a runner, and what runners report back.

The runner command line stays `<name> <proxy> <os> [timezone] [locale]`; the
rest travels as JSON in one environment variable so both engines read it the
same way. The launcher also puts the proxy there and `-` on the command line,
which other OS users can read.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable

from ...models.profile import Profile

ENV = "CLOUTFOX_LAUNCH_OPTS"
# Where the subprocess finds the profile's data when it is not DATA_DIR/<name>
# (an encrypted profile unpacked into a work directory).
PROFILE_DIR_ENV = "CLOUTFOX_PROFILE_DIR"
GEO_PREFIX = "GEO:"

# Seconds a mobile proxy gets to come back after its rotate link was called.
ROTATE_SETTLE = float(os.getenv("CLOUTFOX_ROTATE_WAIT", "8"))


def encode(profile: Profile, **extra: object) -> str:
    """The profile's per-launch options, plus app-wide ones (geo_guard) in `extra`."""
    from .extensions import paths

    return json.dumps(
        {
            "start_urls": profile.start_urls,
            "proxy_rotate_url": profile.proxy_rotate_url,
            "extensions": paths(profile.extensions, profile.engine),
            **extra,
        }
    )


def profile_dir(name: str) -> str:
    """The data directory a runner or the cookie tool works in."""
    from ...core.config import DATA_DIR

    return os.environ.get(PROFILE_DIR_ENV) or os.path.join(os.getcwd(), DATA_DIR, name)


def proxy(argument: str, opts: dict) -> str:
    """The runner's proxy: from the launch options when the launcher started it."""
    value = opts.get("proxy")
    return value if isinstance(value, str) else argument


def load() -> dict:
    try:
        opts = json.loads(os.environ.get(ENV) or "{}")
    except ValueError:
        return {}
    return opts if isinstance(opts, dict) else {}


def geo_line(ip: str | None, country: str | None) -> str:
    """The stdout line telling the launcher which exit IP this launch got."""
    return GEO_PREFIX + json.dumps({"ip": ip, "country": country})


def parse_geo_line(line: str) -> dict | None:
    try:
        data = json.loads(line.removeprefix(GEO_PREFIX))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def rotate_before_launch(url: str | None, say: Callable[[str], None]) -> None:
    """Ask a mobile proxy for a new IP and give it time to reconnect (blocking)."""
    if not url:
        return
    from ..proxy.rotate import rotate_ip

    say("Requesting a new proxy IP...")
    ok, reply = rotate_ip(url)
    say(f"Proxy IP change: {'ok' if ok else 'failed'} {reply}".rstrip())
    if ok:
        time.sleep(ROTATE_SETTLE)


# Warnings that stop a launch while the geo guard is on (see geo_check.compare).
GEO_BLOCKING = {"country_mismatch", "timezone_mismatch", "hosting", "ip_differs", "locale_country"}


def geo_guard(proxy: str | None, timezone: str, locale: str, say: Callable[[str], None]) -> None:
    """Raise when Cloudflare / ipinfo / ip-api disagree with what the browser will show."""
    from ..proxy.geo_check import check_geo

    say("Geo guard: checking the exit IP...")
    result = check_geo(proxy or None, timezone or None, locale or None)
    if result.exit_ip is None:
        raise GeoGuardError(f"geo guard: exit IP unknown ({result.error})")
    # Without the IP's own country, or with every source failing, compare() has
    # nothing to compare and returns no warnings: that is a failed check, not a pass.
    if result.country is None:
        raise GeoGuardError(f"geo guard: no GeoIP country for {result.exit_ip} ({result.error})")
    if not any(s.error is None for s in result.sources):
        errors = "; ".join(f"{s.source}: {s.error}" for s in result.sources)
        raise GeoGuardError(f"geo guard: no source answered ({errors})")
    blocking = [w for w in result.warnings if w.code in GEO_BLOCKING]
    if blocking:
        raise GeoGuardError("geo guard: " + "; ".join(w.message for w in blocking))
    say(f"Geo guard: {result.exit_ip} {result.country or ''} ok")


class GeoGuardError(RuntimeError):
    pass


def check_internal_tunnel(
    timezone: str, locale: str, geo_guard_on: bool, say: Callable[[str], None]
) -> None:
    """Before launching through a WireGuard tunnel that reaches only private networks.

    There is no exit IP to take the timezone and language from, so both must be
    pinned in the profile; the geo guard has nothing to check.
    """
    if not (timezone and locale):
        raise InternalTunnelError(
            "the WireGuard tunnel has no internet exit (AllowedIPs covers only some "
            "networks), so the timezone and language cannot follow an exit IP: "
            "pin both in the profile"
        )
    if geo_guard_on:
        say("Geo guard: skipped, the tunnel has no internet exit")
    say("Exit IP: unknown, the tunnel has no internet exit; WebRTC is blocked")


class InternalTunnelError(RuntimeError):
    pass


def country_of(ip: str | None) -> str | None:
    """ISO country of an IP from Camoufox's local GeoIP database, or None."""
    if not ip:
        return None
    try:
        from camoufox.geolocation import get_geolocation

        return get_geolocation(ip).locale.region or None
    except Exception:
        return None
