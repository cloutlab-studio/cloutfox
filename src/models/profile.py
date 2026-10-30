from dataclasses import asdict, dataclass, field

# Browser engines a profile can run on. A profile keeps its engine for life:
# the two keep incompatible browser data in the same directory.
ENGINES = ("camoufox", "chrome")

# Work status an operator sets by hand; "" means none.
STATUSES = ("", "new", "warming", "active", "paused", "banned")

# Organisation, not identity: ProfileManager.set_meta changes these. Name, proxy,
# OS and geo go through update_profile, which also moves the data directory.
META_FIELDS = ("tags", "notes", "status", "start_urls", "proxy_rotate_url", "extensions")


@dataclass
class Profile:
    name: str
    proxy: str | None = None
    os_type: str = "windows"
    # None = follow the proxy's exit IP (Camoufox geoip); set to pin a value.
    timezone: str | None = None
    locale: str | None = None
    engine: str = "camoufox"
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    status: str = ""
    # Opened on launch when there are no saved tabs to restore.
    start_urls: list[str] = field(default_factory=list)
    # A mobile proxy's "change IP" link; requested before launch and on demand.
    proxy_rotate_url: str | None = None
    # {"at": ISO time, "ip": exit IP, "country": ISO code} of the last ready launch.
    last_launch: dict | None = None
    # Folder names under EXTENSIONS_DIR this profile loads.
    extensions: list[str] = field(default_factory=list)
    # Endpoint of the profile's WireGuard tunnel (its config, with the private key,
    # is wireguard.conf in the data dir); while set it replaces the proxy.
    wireguard: str | None = None
    # One-time profile: never saved, deleted with its data when its browser ends.
    temporary: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
