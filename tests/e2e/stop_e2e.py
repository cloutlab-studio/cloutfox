"""A stopped profile closes its browser cleanly and keeps its tabs (Windows has no SIGTERM).

Needs Camoufox (python -m camoufox fetch) and the network; runs headless with
its data in a temporary folder. Exits non-zero on failure.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

DATA = pathlib.Path(tempfile.mkdtemp(prefix="cloutfox-stop-e2e-"))
os.environ["CLOUTFOX_HEADLESS"] = "true"
os.environ["CLOUTFOX_DATA_DIR"] = str(DATA / "data")
os.environ["CLOUTFOX_PROFILES_FILE"] = str(DATA / "profiles.json")
os.environ["CLOUTFOX_LOG_DIR"] = str(DATA / "logs")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.models.profile import Profile
from src.services.browser.launcher import BrowserLauncher

NAME = "stop-e2e"


def browsers_left() -> list[str]:
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


bl = BrowserLauncher()
bl.start_thread(Profile(name=NAME, os_type="windows"), lambda m: None)
ok, error = bl.wait_for_launch(NAME, 180)
assert ok, f"launch failed: {error}"
bl.control(NAME, "navigate", {"url": "https://example.com"})
bl.control(NAME, "tab_new", {"url": "https://example.org"})
proc = bl._active_sessions[NAME]
started = time.time()
bl.stop_profile(NAME, timeout=20)
print(f"stopped in {time.time() - started:.1f}s, runner exit code {proc.returncode}")
assert proc.returncode == 0, "the runner was killed instead of closing the browser"
time.sleep(3)
left = browsers_left()
assert not left, f"browser processes left: {left}"
tabs = json.loads((DATA / "data" / NAME / "tabs.json").read_text(encoding="utf-8"))["tabs"]
print("saved tabs:", tabs)
assert any("example.org" in url for url in tabs), tabs
print("OK")
