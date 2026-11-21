# Changelog

## [3.1.3] - 2026-11-21

### Upgrading
From 3.1.2 or earlier, update once in the way that fits your copy; after that the button and the system update do the rest.

- **Windows, setup exe for your user** (the default): **Install update** works. The setup closes CloutFox and its browsers, installs 3.1.3 and opens it again. This one time the profiles close without saving their tabs, so stop them first.
- **Windows, setup exe for all users, or the MSI**: the button in 3.1.2 cannot update these copies and does nothing. Download `CloutFox-3.1.3-setup-x64.exe` or `CloutFox-3.1.3-x64.msi` and run it once.
- **Windows zip**: close CloutFox, unpack the new zip in place of the old folder. The button in 3.1.2 would install the setup version in a separate folder instead.
- **Fedora** with the CloutFox repository already added: `sudo dnf upgrade --refresh`. The 3.1.2 packages in it were unsigned and `dnf` refused them; 3.1.3 is signed. Without the repository: **Install update** in the app, or `sudo dnf install ./cloutfox-3.1.3-1.x86_64.rpm`. Then close CloutFox and open it again: 3.1.2 does not restart itself. **openSUSE**: `sudo zypper install ./cloutfox-3.1.3-1.x86_64.rpm`, the button in 3.1.2 needs `dnf`.
- **Ubuntu, Debian**: `sudo apt update && sudo apt upgrade` if the repository is added; otherwise **Install update** or `sudo apt install ./cloutfox_3.1.3_amd64.deb`. Then close CloutFox and open it again.
- **AppImage**: **Install update** replaces the file; close CloutFox and open it again.
- **tar.gz**: download the new archive and unpack it in place of the old folder.

### Added
- "Install update" finishes the job: after a confirmation CloutFox stops the running profiles (they keep their tabs), installs the new version and opens again. On Windows the setup runs once the app has closed, for the same user or all users as the first install, and an MSI install updates through the MSI; a deb or rpm goes through `apt` or `dnf` behind the password prompt; an AppImage replaces its file. A zip or tar.gz copy gets the release page.
- Installing the .deb or .rpm adds the CloutFox repository (`software.cloutlab.studio`), so the system update and the software center bring new versions. `repo=no` in `/etc/default/cloutfox` skips it; a deleted repository file stays deleted; removing the package removes the repository.
- When the system updated CloutFox while it was open, the bar above the list says so and offers "Restart".
- The update check reads `software.cloutlab.studio/latest.json`, which carries the version and the SHA-256 of every file. The GitHub API is the fallback: it allows 60 requests an hour per address, which a provider's shared address runs out of.

### Fixed
- The rpm repository served unsigned packages, so `dnf` with `gpgcheck=1` (the command on the repository page) refused to install them, and zypper refused the repository without signed metadata. Packages and `repomd.xml` are signed now, and the workflow fails if they are not.
- The Windows setup, started from an update in 3.1.2 while CloutFox was open, now stops CloutFox and its browsers first and starts it again afterwards, instead of failing on files in use. On a copy installed for all users (the setup or the MSI) that silent per-user setup stops without installing, so no second copy appears; install 3.1.3 there by hand once.
- A panel whose renderer crashed stayed blank until the app was restarted. Since 3.1.0 the crash handler and the start watchdog were never attached to the window, so the window looked frozen while profiles kept running behind it. The panel now reloads after a crash again, and the reload limit starts over after ten quiet minutes.
- Starting CloutFox a second time (a double click on the shortcut, the menu entry while the window is still coming up) opened a second window on the same profiles. That window had no API, both wrote the same profile list, and it removed the first window's one-time profiles. Now the second start brings the open window forward and exits.
- The window now runs with the CloutFox app id, so on Wayland it groups with its menu entry and shows its own icon.
- If the API port is taken by another program, the log and the panel say so; before, the log said the API was available.
- Logging out or `kill` closes CloutFox like the window's close button on Linux: browsers stop and save their tabs, encrypted profiles are packed.
- The proxy bridge (SOCKS5 with a password, WireGuard, the Chrome engine) checks who owns a connection off its network loop, so pages no longer wait on that check, and Windows remembers the answer per browser process for 30 seconds.
- The activity log no longer shows Camoufox's warning about a custom fingerprint on every launch.

## [3.1.2] - 2026-11-16

### Added
- Updates in the app: after the first-start question, CloutFox asks GitHub once a day for a newer version and shows a bar above the profile list with "Install update". The button downloads the release file, checks its SHA-256 against `SHA256SUMS` and starts the installer: the Inno setup on Windows, `apt` or `dnf` through the polkit password prompt on Linux, and a running AppImage is replaced in place. Settings → About keeps the manual check; Settings → Interface holds the switch for the automatic one. Nothing about the computer is sent, and CloutFox never replaces itself silently.
- apt and dnf repositories on GitHub Pages at `software.cloutlab.studio`: on a published release a new workflow builds the indexes, signs them with the packages key and deploys the site, so Debian, Ubuntu, Fedora and openSUSE users get new versions with `apt upgrade` and `dnf upgrade`.

### Fixed
- A failed stop or a killed app could leave a browser holding the profile, and every later launch then failed with an unreadable error. On Linux the launcher now kills the runner's whole process tree, the browser included.

## [3.1.1] - 2026-11-15

Nothing changes in the app since 3.1.0.

### Fixed
- The Arch install check in the release workflow upgrades the whole container (`pacman -Syu`) instead of single packages. A rolling Arch refuses a partial upgrade now that openssl 4.1 breaks the image's own libarchive and pacman, which stopped the 3.1.0 draft release.

## [3.1.0] - 2026-11-15

### Added
- Folders: put profiles into folders up to three levels deep, drag a row onto a folder in the rail, or use "Move to folder" in the row menu and in the bulk bar. An empty folder stays until you delete it; deleting one moves its profiles one level up. Folders travel with a ZIP export, and the API filters with `GET /profiles?folder=`.
- Settings → About: save a diagnostics archive (version, logs, process list, settings, the panel's own numbers) with one button and open the data folder. No passwords, proxies, cookies, WireGuard configs or tokens go into it.
- The panel now says how heavy it is: the renderer's heap, node count and scaling go into the log, a window that never comes up is reloaded twice and logged, and after a renderer crash the panel says so instead of starting silently over.

### Fixed
- Windows: deleting a tree clears the read-only attribute and retries a file another process holds, so a deleted or replaced profile no longer leaves files behind.
- Windows: packing an encrypted profile retries after a stop, and a failed pack keeps the newer unpacked copy instead of deleting it.
- Windows: stopping a profile waits 15 seconds for a clean close instead of 2, so a heavy profile saves its tabs.
- Windows: the cookie tool and the browser runner no longer flash a console window from the installed app.
- Windows: the proxy bridge refuses connections from another OS account, as it already did on Linux.
- Panel: a renderer that keeps dying reloads with a growing delay, at most five times.
- Security: profile data folders and the files with proxies and keys are read-only for their owner (0700 and 0600), not for every user of the machine.

### Changed
- The checks run on every pushed branch, not only on `main`.
- The committed panel is rendered in a browser on every push: the profile list, the folder tree, the command palette, screenshots at two window sizes.
- Windows CI launches an encrypted profile with a Cyrillic name twice through a real browser and checks that its container is repacked, its tabs are kept and no process or unpacked folder is left.

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
