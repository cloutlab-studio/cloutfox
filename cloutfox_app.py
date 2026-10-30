"""Start the CloutFox desktop app from any working directory, on any OS.

The Windows shortcut runs this file with pythonw.exe (no console window). Data
goes to CLOUTFOX_HOME, as with run.sh: by default %LOCALAPPDATA%\\CloutFox on
Windows and ~/.local/share/cloutfox elsewhere. CLOUTFOX_HOME may also be set in
the app's .env.
"""

import faulthandler
import os
import pathlib
import sys
import traceback

APP = pathlib.Path(__file__).resolve().parent

# Same layout as run.sh: CLOUTFOX_<key> -> path under CLOUTFOX_HOME.
LAYOUT = {
    "PROFILES_FILE": "profiles.json",
    "DATA_DIR": "camoufox_data",
    "LOG_DIR": "logs",
    "VAULT_FILE": "vault.json",
    "KEYS_FILE": "profile_keys.json",
    "ENCRYPTED_DIR": "encrypted_data",
    "SETTINGS_FILE": "settings.json",
    "EXTENSIONS_DIR": "extensions",
    "BIN_DIR": "bin",
}


def default_home() -> pathlib.Path:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home() / "AppData" / "Local")
        return pathlib.Path(local) / "CloutFox"
    return pathlib.Path.home() / ".local" / "share" / "cloutfox"


def apply_home(environ: dict) -> pathlib.Path:
    """Point every unset CLOUTFOX_* path at CLOUTFOX_HOME; returns the home."""
    home = pathlib.Path(environ.get("CLOUTFOX_HOME") or default_home()).expanduser()
    for key, name in LAYOUT.items():
        environ.setdefault(f"CLOUTFOX_{key}", str(home / name))
    return home


def main() -> None:
    os.chdir(APP)
    sys.path.insert(0, str(APP))
    # pythonw.exe has no console: give libraries that write to it a sink, so
    # nothing fails on a missing stream (the log file still gets everything).
    if sys.stdout is None or sys.stderr is None:
        sink = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        sys.stdout = sys.stdout or sink
        sys.stderr = sys.stderr or sink
    try:
        from dotenv import load_dotenv

        load_dotenv(APP / ".env")
    except ImportError:
        pass
    apply_home(os.environ).mkdir(parents=True, exist_ok=True)
    logs = pathlib.Path(os.environ["CLOUTFOX_LOG_DIR"])
    logs.mkdir(parents=True, exist_ok=True)
    # Without a console a failed start leaves no trace: keep tracebacks and
    # native crashes (Qt, WebEngine) in the log folder.
    crash = open(logs / "crash.log", "a", encoding="utf-8")  # noqa: SIM115
    faulthandler.enable(crash)
    try:
        from src.main import main as run

        run()
    except BaseException as error:
        if not isinstance(error, SystemExit) or error.code not in (None, 0):
            traceback.print_exc(file=crash)
            crash.flush()
        raise


if __name__ == "__main__":
    main()
