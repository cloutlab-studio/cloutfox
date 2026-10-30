# Product

<!-- impeccable:product-schema 1 -->

## Platform

desktop

One product: a desktop app (a Svelte panel in `frontend/` shown in a pywebview Qt WebEngine window, `src/ui/`), plus a REST API and MCP server for scripts and AI agents. The look is the Brutal universe of the CLOUTLAB studio site (cloutlab.studio). The app does not follow iOS/Android native design language.

## Users

- **MMO and ads operators** running tens to hundreds of Facebook, TikTok, Google and Shopee accounts. They open, stop and switch profiles all day, work in bulk, and care about which proxy and device each account presents.
- **Agencies managing client accounts**: several people and clients share one installation; the list must stay orderly and trustworthy.
- **Developers and automation users** who drive CloutFox through the REST API and MCP on the same machine; for them the UI is where they check state and step in by hand (log in, solve a captcha).

## Product Purpose

CloutFox is a free, open-source, self-hosted manager for anti-detect browser profiles. Each profile is a persistent identity: its own device fingerprint, cookies, proxy, timezone and locale. It replaces paid tools such as GoLogin, GPM and MoreLogin. Success means a user can create, launch, check and move many accounts quickly without an account leaking its real device, IP or a mismatched geo.

## Positioning

Open source (MIT), runs on the user's own computer, no account and no per-profile pricing. Two browser engines: Camoufox (Firefox patched at the engine level) and an experimental Chrome engine (fingerprint-chromium). Built-in REST API and MCP server so AI agents can drive the browsers.

## Operating Context

- Desktop only: `python -m src.main` on Linux or Windows; the API and MCP run alongside on `127.0.0.1:8000`. There is no server mode.
- Core tasks: create/edit a profile (name, engine, OS, proxy, timezone, locale), launch/stop, bulk launch/stop/delete, search by name or proxy, check proxy, Check IP (exit IP vs Cloudflare/ipinfo/ip-api with warnings), cookie export/import (JSON, Netscape), new fingerprint, profile ZIP export/import, connect an AI agent over MCP, read the activity log.
- Sessions are long; users scan many cards at once and repeat the same actions many times a day.

## Capabilities and Constraints

- Profile fields: name, engine (`camoufox` | `chrome`, fixed after creation), OS (`windows` | `macos` | `linux`), proxy (`[scheme://][user:pass@]host:port` or `host:port:user:pass`), optional pinned timezone (IANA) and locale.
- Cookie and fingerprint operations require the profile's browser to be stopped.
- The panel runs offline inside the app: no external scripts, fonts or requests (strict CSP).
- All UI strings live in `src/core/strings.py` (desktop) in both `ru` and `en`.

## Brand Commitments

- Name: **CloutFox**. Keep it.
- Logo: the fox icon in `src/assets/icon.png` (and `icon.ico`). Keep it.
- Language: the UI follows the system language (Russian on a Russian system, English elsewhere), with a switch in the panel.
- Terminology: Russian copy uses the words operators already say (профиль, прокси, куки, отпечаток); product and protocol names stay in English (Camoufox, Chrome, API, MCP, headless).

## Evidence on Hand

- README in English describing every feature, plus a full Russian translation (`README.ru.md`). No user testimonials, usage numbers or customer names exist; do not invent them.

## Product Principles

1. Speed for repeated work: the most frequent actions (launch, stop, find a profile) take one click and are always in the same place.
2. State at a glance: whether a profile is running, which proxy/IP and device it presents, and anything that would leak (geo mismatch, datacenter IP) must be visible without opening it.
3. Safety over convenience for destructive or leaking actions: deleting profiles, cookies and credentials needs a clear confirmation; credentials are never shown in full.
4. One vocabulary across the app, the API and MCP.
5. Honest about limits: experimental features (Chrome engine) and failures are labeled plainly, not hidden.
