import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _env(key: str, default: str) -> str:
    """Read the CLOUTFOX_<key> environment variable."""
    return os.getenv(f"CLOUTFOX_{key}", default)


PROFILES_FILE = _env("PROFILES_FILE", "profiles.json")
DATA_DIR = _env("DATA_DIR", "camoufox_data")
# Encryption (all optional): the master key file, profile keys, encrypted profiles.
VAULT_FILE = _env("VAULT_FILE", "vault.json")
KEYS_FILE = _env("KEYS_FILE", "profile_keys.json")
ENCRYPTED_DIR = _env("ENCRYPTED_DIR", "encrypted_data")
# Settings toggled in the app, and the shared folder of browser extensions.
SETTINGS_FILE = _env("SETTINGS_FILE", "settings.json")
EXTENSIONS_DIR = _env("EXTENSIONS_DIR", "extensions")
# Helper programs downloaded on demand (wireproxy for WireGuard profiles).
BIN_DIR = _env("BIN_DIR", "bin")
LOG_DIR = _env("LOG_DIR", "logs")
LOG_LEVEL = _env("LOG_LEVEL", "INFO")
PROXY_CHECK_TIMEOUT = int(_env("PROXY_TIMEOUT", "10"))


def system_language() -> str:
    """Russian on a Russian system, English everywhere else."""
    if sys.platform == "win32":
        try:
            import ctypes

            primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        except (AttributeError, OSError):
            return "en"
        return "ru" if primary == 0x19 else "en"
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        if value := os.environ.get(key):
            return "ru" if value.lower().startswith("ru") else "en"
    return "en"


LANGUAGE = _env("LANG", "") or system_language()

# The API and /mcp only ever listen on loopback.
API_HOST = "127.0.0.1"
API_PORT = int(_env("API_PORT", "8000"))

# Seconds the API waits for a launched browser to report ready or failed.
LAUNCH_WAIT_TIMEOUT = int(_env("LAUNCH_TIMEOUT", "90"))

FINGERPRINT_FILE = "fingerprint.json"


# Browsers open hidden when true, for agents that need no windows.
HEADLESS = _env("HEADLESS", "false").strip().lower() in ("1", "true", "yes")

# Reopen the tabs a profile had open when it was last stopped.
RESTORE_TABS = _env("RESTORE_TABS", "true").strip().lower() in ("1", "true", "yes")

# Optional shared secret for the REST API and the MCP server: without it any
# local process can drive the browsers.
API_TOKEN = _env("API_TOKEN", "")

# Directories browser_upload may read files from (os.pathsep-separated) and the
# file types it may send. Media folders only by default: an agent reading
# untrusted pages must not be able to post documents or source code.
UPLOAD_DIRS = [
    os.path.realpath(os.path.expanduser(d))
    for d in _env("UPLOAD_DIRS", os.pathsep.join(["~/Pictures", "~/Videos"])).split(os.pathsep)
    if d.strip()
]
UPLOAD_EXTENSIONS = {
    "." + e.strip().lower().lstrip(".")
    for e in _env(
        "UPLOAD_EXTENSIONS",
        "png,jpg,jpeg,gif,webp,heic,avif,mp4,mov,webm,m4v,mp3,m4a,wav,ogg",
    ).split(",")
    if e.strip()
}
