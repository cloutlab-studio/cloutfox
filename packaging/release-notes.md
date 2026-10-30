<p align="center">
  <img src="{repo}/raw/v{ver}/docs/images/banner.png" alt="CloutFox: open-source anti-detect profiles" width="100%">
</p>

**CloutFox {ver}**: a free, open-source anti-detect browser profile manager on Camoufox. Every profile gets its own fingerprint, cookies, proxy or WireGuard tunnel, timezone and language. AI agents drive the profiles through MCP and the REST API. No subscription, no cloud: your data stays on your computer.

## Download

| System | Download |
| --- | --- |
| **Windows 10, 11** | [![Installer](https://img.shields.io/badge/Windows-Installer%20.exe-ffe14d?style=for-the-badge&labelColor=0a0a0a)]({download}/CloutFox-{ver}-setup-x64.exe) |
| Windows, for admins | [![MSI](https://img.shields.io/badge/Windows-MSI-ffffff?style=for-the-badge&labelColor=0a0a0a)]({download}/CloutFox-{ver}-x64.msi) |
| Windows, portable | [![Portable](https://img.shields.io/badge/Windows-Portable%20.zip-ffffff?style=for-the-badge&labelColor=0a0a0a)]({download}/CloutFox-{ver}-windows-x64.zip) |
| **Ubuntu 22.04+, Debian 12+**, Mint | [![deb](https://img.shields.io/badge/Ubuntu%20%C2%B7%20Debian-.deb-ff5c8a?style=for-the-badge&labelColor=0a0a0a)]({download}/cloutfox_{ver}_amd64.deb) |
| **Fedora**, RHEL 9+, openSUSE | [![rpm](https://img.shields.io/badge/Fedora%20%C2%B7%20openSUSE-.rpm-3d7bff?style=for-the-badge&labelColor=0a0a0a)]({download}/cloutfox-{ver}-1.x86_64.rpm) |
| Any Linux | [![AppImage](https://img.shields.io/badge/Linux-AppImage-ffe14d?style=for-the-badge&labelColor=0a0a0a)]({download}/CloutFox-{ver}-x86_64.AppImage) [![tar.gz](https://img.shields.io/badge/Linux-.tar.gz-ffffff?style=for-the-badge&labelColor=0a0a0a)]({download}/cloutfox-{ver}-linux-x86_64.tar.gz) |
| Source code | [![Source](https://img.shields.io/badge/Source-.tar.gz-ffffff?style=for-the-badge&labelColor=0a0a0a)]({download}/cloutfox-{ver}-src.tar.gz) |

x86_64 only. Checksums: [`SHA256SUMS`]({download}/SHA256SUMS).

## First start

- **Camoufox downloads once** on the first launch (about 700 MB); the progress is in the Activity Log.
- **Windows SmartScreen**: the builds are not code-signed yet. Click "More info" → "Run anyway".
- **Install commands**: `sudo apt install ./cloutfox_{ver}_amd64.deb`, `sudo dnf install ./cloutfox-{ver}-1.x86_64.rpm`, or `chmod +x CloutFox-*.AppImage` and run it.
- **AI agents**: while CloutFox runs, `claude mcp add --transport http cloutfox http://127.0.0.1:8000/mcp`.

Full guide: [README]({repo}#readme) · По-русски: [README.ru.md]({repo}/blob/main/README.ru.md)

<details>
<summary><b>Everything in {ver}</b></summary>

{changes}

</details>
