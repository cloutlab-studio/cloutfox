# Changelog

## [3.0.0] - 2026-10-30

The first release: https://github.com/cloutlab-studio/cloutfox

### Added
- Ready-made builds: exe and msi installers and a zip for Windows; deb and rpm packages, an AppImage, a tar.gz and an AUR recipe for Linux. Python and every dependency are bundled, so there is nothing to install first. Data lives in `%LOCALAPPDATA%\CloutFox` on Windows and in `~/.local/share/cloutfox` on Linux.
- Camoufox downloads on first launch, with progress in the log; a Camoufox profile waits for the download and then starts on its own. Only one process downloads at a time.
- `cloutfox_app.py`: starts the app from any folder on any OS with data in `CLOUTFOX_HOME`; the builds, `run.sh` and `run_cloutfox.bat` call it. `CLOUTFOX_HOME` can also be set in `.env`.
- Errors that stop the app from starting go to `logs/crash.log` in the data folder (the Windows app has no console to show them).
- English and Russian interface. It follows the system language (Russian on a Russian system, English everywhere else); `CLOUTFOX_LANG` and the switch in the panel override it.
- GitHub Actions checks on Linux and Windows: ruff, pytest, the panel and the browser stop on Windows. A release tag builds every package, installs each one on a clean system (Debian, Ubuntu, Fedora, openSUSE, Arch, Windows) and opens a draft release with `SHA256SUMS`.
- A panel in the Brutal style of the Cloutlab studio: a Qt WebEngine window (pywebview) with a Svelte interface. Pages for Profiles, Activity Log, AI agents and Settings, the profile editor next to the list, a `Ctrl+K` command palette and the `/`, `N` and Space keys, a ticker with running profiles, toasts with results, and the whole profile list without paging.
- Panel sounds (launch, stop, error, end of a warm-up or backup, an agent's request) and animations; Settings → Interface holds sound, volume, animation, cursor and language. The chosen language is remembered.
- Confirmation before removing a WireGuard tunnel, decrypting a profile, clearing the self-destruct password and removing an extension.
- Cookie warm-up: a profile visits a random part of the shared site list (or its own list) like a person, then closes. Row menu ⋮ → "Warm up cookies", a "Warm up" button for selected profiles, the site list in Settings, a counter in the profile's row, `POST`/`GET /browser/{name}/warmup`, MCP `warm_up_profile` and `warmup_status`.
- WireGuard for a profile in place of a proxy (through wireproxy 1.1.3, downloaded on first use and checked by SHA-256): row menu ⋮ → "WireGuard", "Check IP" through the tunnel, `PUT`/`DELETE /profiles/{name}/wireguard`, a `wireguard` field on the profile.
- Launching through a WireGuard tunnel into a private network with no internet exit: CloutFox recognizes such a tunnel by `AllowedIPs`, does not look for an exit IP, switches WebRTC off and skips the geo check. The timezone and language must be pinned.
- Browser extensions: a shared folder, a choice per profile, `GET /extensions`, MCP `list_extensions`, an `extensions` field on the profile. An extension belongs to an engine (Camoufox or Chrome): a profile sees and loads only its own, and the API refuses the others.
- The "Refuse a launch on geo mismatch" setting: before a launch the exit IP is checked against Cloudflare, ipinfo and ip-api.
- Scheduled backups to a chosen folder, encrypted with a master password; restore with `python -m src.services.backup restore`. The self-destruct password deletes them too.
- For agents: one-time profiles (`POST /browser/temp`, MCP `launch_temp_profile`), a per-profile log of agent actions, a request for human help (`request_human`) with a card in the app, one action in several profiles (`browser_broadcast`).
- Optional encryption: a master password with a sign-in screen and a recovery key (encrypts `profiles.json`, backups and profile keys), profile data encryption with the master password and/or a profile password, a self-destruct password.
- Settings in the side panel.
- Tags, status, notes, start pages and an IP change link per profile; filters by tag and status, search by tags and notes.
- The profile's row shows the time of the last launch, the exit IP and the country.
- "Many profiles": from a name template with a proxy pool, or from a list of `name;proxy;tags;note`.
- "Edit selected": proxies, status and tags in bulk. Cloning a profile from the row menu.
- REST: `POST /profiles/bulk`, `/profiles/import-list`, `/profiles/proxies`, `/profiles/{name}/clone`, `/profiles/{name}/rotate-ip`, `?tag=` and `?status=` filters. MCP: `create_profiles_bulk`, `clone_profile`, `set_proxies`, `rotate_proxy_ip`.
- An agent's request for help brings the CloutFox window to the front and keeps it on top until you answer, covers the panel with a card holding the request and plays a chime.
- On Linux the local proxy bridge accepts only programs of your own OS user. The WireGuard tunnel's proxy has a password, and the browser reaches it through the bridge. Proxy passwords never appear on the browser's command line, which every user of the computer can see.
- Camoufox profiles with a password-protected SOCKS5 proxy: the browser connects to a local bridge without a password, and the bridge signs in to the proxy.
- Windows: stopping a profile closes the browser cleanly, saves the tabs and packs an encrypted profile after the browser has closed.
