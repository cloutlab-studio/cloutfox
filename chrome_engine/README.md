# Chrome engine (experimental)

CloutFox's second browser engine, next to Camoufox: a Chromium build that spoofs the fingerprint in C++ ([fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium), BSD-3, based on ungoogled-chromium). The engine does not build Chromium itself. It downloads a prebuilt release with a pinned checksum and adds what the fork lacks so far.

The engine is wired into CloutFox: a profile has an `engine` field (`camoufox` or `chrome`, set at creation and never changed). For a Chrome profile `BrowserLauncher` runs `python -m chrome_engine.runner` (the same protocol as the Camoufox runner), cookies go through `cookie_tool.py` with the `chrome` engine, and a Chrome profile's fingerprint is stored in `chrome_persona.json`.

## Install and run

```bash
python -m chrome_engine fetch            # download ~190 MB, check SHA-256, unpack into the cache
python -m chrome_engine info             # path of the installed build
python -m chrome_engine probe data/alice --timezone Europe/Berlin --locale de-DE
python -m chrome_engine open  data/alice --proxy "socks5://user:pass@host:1080" --url https://example.com
```

Default cache folder: `%LOCALAPPDATA%\cloutfox\chrome`, `~/Library/Caches/cloutfox/chrome` or `~/.cache/cloutfox/chrome`. Another folder: `CLOUTFOX_CHROME_HOME`.

```python
from chrome_engine import ChromeEngine

async with ChromeEngine("data/alice", proxy="http://u:p@1.2.3.4:8080") as context:
    page = context.pages[0]
    await page.goto("https://example.com")
```

`context` is a regular Playwright `BrowserContext`. The runner for CloutFox:

```bash
python -m chrome_engine.runner <name> <proxy|None> <windows|macos|linux> [timezone] [locale]
# prints CONTROL:<port>:<token>, BROWSER_STARTED, BROWSER_CLOSED / LAUNCH_FAILED: ...
```

## What the engine adds to the fork

| Problem in the fork or Playwright | Fix in the engine | File |
|---|---|---|
| Build 150.0.7871.186 crashes the renderer when drawing emoji on a canvas (about 50% of launches) | Pinned to 148.0.7778.215 (16 of 16 launches without a crash), with a regression test | `release.py` |
| A profile has no lasting identity | A persona (seed, OS, OS version, brand, core count, timezone, language) is stored in `chrome_persona.json` | `persona.py` |
| `--proxy-server` takes no password and cannot do SOCKS5 with a password | A loopback bridge to HTTP, HTTPS or SOCKS5 with a password; site names go to the proxy and are never resolved locally (no DNS leak) | `proxy_bridge.py` |
| Timezone and language do not follow the proxy's IP | The exit IP is found through the bridge and geo comes from Camoufox's GeoIP; if that fails, the browser **does not open** and never shows the computer's timezone | `geo.py`, `engine.py` |
| Playwright adds switches a site can see (`--enable-automation`, `--disable-popup-blocking`, `--hide-scrollbars`, `--force-color-profile=srgb`, bfcache off, throttling off, `--no-sandbox`, storage partitioning off and so on) | The switches are removed one by one, including the exact `--disable-features` string from the installed Playwright driver | `engine.py` |
| Without a window the screen is 800x600 and scrollbars are 0 px | `--screen-info`/`--window-size` 1920x1080, scrollbars kept | `engine.py` |
| WebRTC: the fork blocks all UDP, and without the block it shows the LAN IP (the fork does not hide it behind mDNS) | With a proxy, UDP is blocked. Without one, only the public IP is visible (`default_public_interface_only`); the LAN IP is never visible | `engine.py` |
| A persona of another OS contradicts itself | A compatibility table; a Linux persona on Windows or macOS is refused (WebGL shows the real graphics card anyway) | `persona.py` |
| You need to know what a site sees | The probe reads window, worker, iframe, ServiceWorker, SharedWorker and HTTP headers; `check()` lists every mismatch | `probe.py` |

## Persona and host compatibility

| Host \ Persona | Windows | macOS | Linux |
|---|---|---|---|
| Windows | yes | warning: Windows fonts show up in font probing | **refused**: WebGL shows Direct3D 11 |
| Linux | warning: Linux fonts | warning: Linux fonts | yes |
| macOS | warning: macOS fonts, 0 px scrollbars | yes | **refused**: WebGL shows the real Apple GPU |

The Windows and macOS rows were measured on real machines; the Linux row is inferred and not tested.

The fork's macOS build exists only for arm64: Intel Macs are not supported (`fetch` reports an error and does not download a build that would not run). An x86_64 Python under Rosetta on Apple Silicon is detected as arm64.

## Test results (09.10.2026, Windows 11, fingerprint-chromium 148.0.7778.215)

```bash
pytest chrome_engine/tests                 # 191 tests; browser tests are skipped until the browser is downloaded
pytest chrome_engine/tests -m "not browser"
python chrome_engine/e2e/detection_e2e.py headed headless   # needs the internet
```

- Unit tests: release, fetch (checksum, rollback, path escape), persona, the proxy bridge (HTTP and SOCKS5 with a password, a wrong password, a dead proxy, 25 parallel tunnels, a 3 MB body), probe check (every kind of mismatch is caught).
- Tests with a real browser: the fingerprint is the same with a window, headless and offscreen; Chrome and Edge brands; a macOS persona on Windows; emoji on a canvas without crashes; one seed gives one device and different seeds give different ones; cookies, localStorage and the persona survive until the next launch; HTTP and SOCKS5 with a password (no DNS leak); a wrong proxy password never falls back to a direct connection; geoip; the pop-up blocker works; storage partitioning is on; `Runtime.enable` is not visible; WebRTC goes through the proxy; 3 parallel profiles are isolated from each other.
- Runner: the `CONTROL` → `BROWSER_STARTED` order, control through the control server, saving and restoring tabs, the profile opens after the runner was killed, closing the last tab gives `BROWSER_CLOSED`.
- Public detection pages, with a window and without: sannysoft passes completely, the Cloudflare check passes, BrowserScan "Normal", CreepJS 0% headless (real Chrome under Playwright: 33% headless).

## Test results (09.10.2026, macOS 15.3, Apple M1 Pro, fingerprint-chromium 148.0.7778.215)

- `fetch`: downloads the `.dmg`, checks SHA-256, unpacks it with `hdiutil`; the ad-hoc signed arm64 binary starts.
- Tests with a real browser: 23 passed, 1 skipped (`test_macos_persona_on_windows_host` runs only on Windows).
- Probe of a macOS persona (with a window and without): 0 mismatches; WebGL shows the spoofed GPU (for example Apple M4), the real chip is not visible.
- Probe of a Windows persona: 0 px scrollbars (macOS overlay scrollbars with the "Automatically" setting); macOS fonts are visible.
- Probe of a Linux persona: WebGL shows `ANGLE Metal Renderer: Apple M1 Pro`, so this combination is refused.
- Public detection pages (with a window and without, macOS persona): sannysoft passes completely, the Cloudflare check passes, BrowserScan "Normal", CreepJS 0% headless.

## Known limits

- Fonts come from the computer. A persona of another OS shows up in font probing.
- The WebGL image (pixels) is drawn by the real GPU; only the vendor/renderer strings and parameters are spoofed.
- WebRTC has no mDNS host candidates the way real Chrome does (the fork turns them off). No IP leaks, but it is a small difference.
- `userAgentData.fullVersionList` shows the patch number the fork picked (for example 148.0.7778.97), which differs from the real build number.
- Not tested on Linux; the `.dmg` unpacks only on macOS and runs only on Apple Silicon.
- A macOS persona always reports `devicePixelRatio` 1, while real MacBooks almost always have 2 (Retina). Headless, `availHeight` equals `height` (the menu bar is not subtracted).
- A Windows persona on macOS: 0 px scrollbars. `defaults write org.chromium.Chromium AppleShowScrollBars Always` brings back 15 px (real Windows has 17 px), but the setting applies to every Chromium with the same bundle id on the computer.
- Detection by CDP response timing is not handled.
- The proxy bridge listens on `127.0.0.1` on a random port without a password (Chromium cannot pass one). A site cannot use it (it cannot send `CONNECT`, and plain requests get 400). On Linux the bridge answers only programs of your own OS user; on Windows and macOS, while a profile is open, another program on this computer can go out through the profile's proxy.
- The engine depends on an outside fork: before changing `DEFAULT_VERSION`, run all tests again (especially `test_emoji_canvas_does_not_crash`).
