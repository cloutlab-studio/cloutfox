"""A profile with a Cyrillic name, encrypted, launched twice on Windows and Linux.

The Windows failure this guards against is file locking: a browser that still
holds its files makes the pack after a stop fail, and the profile then starts
from a stale copy or not at all. Needs Camoufox and the network. Exits non-zero
on failure.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

DATA = pathlib.Path(
    os.environ.get("CLOUTFOX_E2E_DIR") or tempfile.mkdtemp(prefix="cloutfox-profile-e2e-")
)
os.environ["CLOUTFOX_HEADLESS"] = "true"
os.environ["CLOUTFOX_DATA_DIR"] = str(DATA / "data")
os.environ["CLOUTFOX_ENCRYPTED_DIR"] = str(DATA / "encrypted")
os.environ["CLOUTFOX_KEYS_FILE"] = str(DATA / "keys.json")
os.environ["CLOUTFOX_VAULT_FILE"] = str(DATA / "vault.json")
os.environ["CLOUTFOX_PROFILES_FILE"] = str(DATA / "profiles.json")
os.environ["CLOUTFOX_LOG_DIR"] = str(DATA / "logs")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.models.profile import Profile  # noqa: E402
from src.services.browser.launcher import BrowserLauncher  # noqa: E402
from src.services.security.profile_data import ProfileData  # noqa: E402
from src.services.security.vault import Vault  # noqa: E402

NAME = "Профиль Тест"
PASSWORD = "e2e-password"


def processes_left() -> list[str]:
    """Browser processes still using the profile's folder."""
    if sys.platform == "win32":
        query = (
            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*"
            + str(DATA)
            + "*' -and $_.Name -notlike 'python*' -and $_.Name -ne 'powershell.exe' } | ForEach-Object { $_.Name }"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", query], capture_output=True, text=True
        ).stdout
    else:
        out = subprocess.run(["pgrep", "-af", str(DATA)], capture_output=True, text=True).stdout
        out = "\n".join(line for line in out.splitlines() if "python" not in line)
    return [line for line in out.splitlines() if line.strip()]


def log_text() -> str:
    logs = sorted((DATA / "logs").glob("*.log"))
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in logs)


vault = Vault(str(DATA / "vault.json"))
data = ProfileData(str(DATA / "data"), str(DATA / "encrypted"), str(DATA / "keys.json"), vault)
data.encrypt(NAME, PASSWORD)
data.unlock(NAME, PASSWORD)
print("encrypted:", data.is_encrypted(NAME), "size:", data.container(NAME).stat().st_size)

launcher = BrowserLauncher()
launcher.data = data
profile = Profile(name=NAME, os_type="windows")

for attempt in (1, 2):
    assert launcher.start_thread(profile, lambda m: None), "already running"
    ok, error = launcher.wait_for_launch(NAME, 180)
    assert ok, f"launch {attempt} failed: {error}"
    launcher.control(NAME, "navigate", {"url": "https://example.com"})
    launcher.control(NAME, "tab_new", {"url": "https://example.org"})
    started = time.time()
    launcher.stop_profile(NAME, timeout=20)
    print(f"attempt {attempt}: stopped in {time.time() - started:.1f}s")

    time.sleep(3)
    left = processes_left()
    assert not left, f"browser processes left after attempt {attempt}: {left}"
    assert not data.work_dir(NAME).exists(), f"unpacked data left: {data.work_dir(NAME)}"
    assert data.container(NAME).stat().st_size > 0, "the container is empty after the pack"

    # Reopening proves the container holds a profile the browser can start from.
    with data.opened(NAME) as path:
        tabs = json.loads((path / "tabs.json").read_text(encoding="utf-8"))["tabs"]
    assert any("example.org" in url for url in tabs), tabs

text = log_text()
assert "Traceback" not in text, "the log has a traceback"
print("OK")
