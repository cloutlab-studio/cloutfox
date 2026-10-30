"""Profile <-> stored dict, tolerant of old and hand-edited files.

profiles.json and profile.json inside export archives use the same layout. A
field that is missing or no longer valid falls back to its default instead of
dropping the whole profile.
"""

from ...models.profile import ENGINES, STATUSES, Profile
from ...utils.validation import (
    MAX_NOTES_LENGTH,
    normalize_tags,
    normalize_urls,
    valid_or_none,
    validate_http_url,
    validate_locale,
    validate_timezone,
)


def _last_launch(value: object) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("at"), str):
        return None
    return {
        "at": value["at"],
        "ip": value.get("ip") if isinstance(value.get("ip"), str) else None,
        "country": value.get("country") if isinstance(value.get("country"), str) else None,
    }


def profile_from_dict(data: dict) -> Profile:
    """A Profile from stored data; the caller has validated data["name"]."""
    notes = data.get("notes")
    status = data.get("status")
    return Profile(
        name=data["name"],
        proxy=data.get("proxy") or None,
        os_type=data.get("os_type", (data.get("config") or {}).get("os", "windows")),
        timezone=valid_or_none(data.get("timezone"), validate_timezone),
        locale=valid_or_none(data.get("locale"), validate_locale),
        engine=data.get("engine") if data.get("engine") in ENGINES else "camoufox",
        tags=normalize_tags(data.get("tags")),
        notes=notes[:MAX_NOTES_LENGTH] if isinstance(notes, str) else "",
        status=status if status in STATUSES else "",
        start_urls=normalize_urls(data.get("start_urls")),
        proxy_rotate_url=valid_or_none(data.get("proxy_rotate_url"), validate_http_url),
        last_launch=_last_launch(data.get("last_launch")),
        extensions=[e for e in data.get("extensions") or [] if isinstance(e, str)][:50],
        wireguard=data.get("wireguard") if isinstance(data.get("wireguard"), str) else None,
    )
