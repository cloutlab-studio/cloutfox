from pydantic import BaseModel, Field

_TAGS = 'Labels for filtering, e.g. ["fb", "us"]; lower-cased'
_STATUS = "Work status: one of new, warming, active, paused, banned, or empty"
_START = "http(s) pages opened on launch when there are no saved tabs"
_ROTATE = "Mobile proxy 'change IP' link, called before each launch"
_EXT = "Ids of installed extensions to load (see GET /extensions)"


class ProfileCreate(BaseModel):
    name: str
    proxy: str | None = None
    os_type: str = "windows"
    timezone: str | None = Field(
        None, description="IANA timezone, e.g. Asia/Ho_Chi_Minh. Unset = follow the IP"
    )
    locale: str | None = Field(
        None, description="language-REGION, e.g. vi-VN. Unset = follow the IP"
    )
    engine: str = Field(
        "camoufox",
        description="camoufox (Firefox) or chrome (experimental, fingerprint-chromium). "
        "Fixed once the profile is created",
    )
    tags: list[str] = Field(default_factory=list, description=_TAGS)
    notes: str = ""
    status: str = Field("", description=_STATUS)
    start_urls: list[str] = Field(default_factory=list, description=_START)
    proxy_rotate_url: str | None = Field(None, description=_ROTATE)
    extensions: list[str] = Field(default_factory=list, description=_EXT)


class ProfileUpdate(BaseModel):
    """All fields optional: only supplied fields are changed."""

    name: str | None = None
    proxy: str | None = None
    os_type: str | None = None
    timezone: str | None = Field(None, description='"" switches back to automatic')
    locale: str | None = Field(None, description='"" switches back to automatic')
    engine: str | None = Field(None, description="Cannot be changed; only the current value")
    tags: list[str] | None = Field(None, description=_TAGS)
    notes: str | None = None
    status: str | None = Field(None, description=_STATUS)
    start_urls: list[str] | None = Field(None, description=_START)
    proxy_rotate_url: str | None = Field(None, description=_ROTATE + '; "" removes it')
    extensions: list[str] | None = Field(None, description=_EXT)


class ProfileResponse(BaseModel):
    name: str
    proxy: str | None
    os_type: str
    timezone: str | None = None
    locale: str | None = None
    engine: str = "camoufox"
    tags: list[str] = []
    notes: str = ""
    status: str = ""
    start_urls: list[str] = []
    extensions: list[str] = []
    # Endpoint of the WireGuard tunnel that replaces the proxy; never the config.
    wireguard: str | None = None
    # Never the link itself: it carries the provider's key.
    has_rotate_url: bool = False
    last_launch: dict | None = None
    encrypted: bool = False
    # Encrypted with its own password that nobody entered in the app yet.
    needs_password: bool = False
    data_dir: str
    is_running: bool


class ProfileListResponse(BaseModel):
    profiles: list[ProfileResponse]
    total: int


class DataDirResponse(BaseModel):
    name: str
    data_dir: str
    exists: bool


class ExportRequest(BaseModel):
    export_dir: str
    include_data: bool = True


class ExportResponse(BaseModel):
    success: bool
    zip_path: str | None = None
    error: str | None = None


class ImportRequest(BaseModel):
    zip_path: str
    overwrite: bool = False


class ImportResponse(BaseModel):
    success: bool
    profile_name: str | None = None
    error: str | None = None


class CookieImportRequest(BaseModel):
    """Cookies as JSON (Cookie-Editor / EditThisCookie / Playwright) or Netscape text."""

    content: str


class CookieImportResponse(BaseModel):
    success: bool
    imported: int = 0
    error: str | None = None


class FingerprintResponse(BaseModel):
    name: str
    exists: bool
    os: str | None = None
    platform: str | None = None
    screen: str | None = None
    hardware_concurrency: int | None = None


class WireGuardRequest(BaseModel):
    config: str = Field(
        description="wg-quick style file ([Interface] + [Peer]); only WireGuard keys are kept"
    )


class CloneRequest(BaseModel):
    name: str = Field(description="Name of the new profile")


class BulkCreateRequest(BaseModel):
    pattern: str = Field(description="Name pattern, {n} is the number: fb-{n} -> fb-01, fb-02")
    count: int = Field(ge=1, le=500)
    start: int = Field(1, ge=0)
    os_type: str = "windows"
    engine: str = "camoufox"
    proxies: list[str] = Field(default_factory=list, description="Proxy pool; empty = direct")
    proxy_mode: str = Field("order", description="order: one each, in order; random: from pool")
    timezone: str | None = None
    locale: str | None = None
    tags: list[str] = Field(default_factory=list, description=_TAGS)
    status: str = Field("", description=_STATUS)
    start_urls: list[str] = Field(default_factory=list, description=_START)


class ImportListRequest(BaseModel):
    text: str = Field(description="One profile per line: name;proxy;tags;notes")
    os_type: str = "windows"
    engine: str = "camoufox"


class BulkCreateResponse(BaseModel):
    created: list[str]
    skipped: list[str] = Field(default_factory=list, description="Names that already existed")


class SetProxiesRequest(BaseModel):
    names: list[str]
    proxies: list[str] = Field(description="One proxy for all, a pool, or [] for direct")
    proxy_mode: str = "order"


class SetProxiesResponse(BaseModel):
    updated: list[str]


class RotateResponse(BaseModel):
    success: bool
    message: str
