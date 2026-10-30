# Security

CloutFox stores cookies, proxy logins and encryption keys, so security reports come first for us.

## How to report

Do not open a public issue. Contact us privately in one of these ways:

- through [GitHub Security Advisories](https://github.com/cloutlab-studio/cloutfox/security/advisories/new);
- by email to dev@cloutlab.studio with the subject "CloutFox security".

Include the version, the system, steps to reproduce and what an attacker could do. We aim to answer within a week, agree on a fix date with you and, if you like, credit you in the release notes.

## Supported versions

Fixes ship for the latest version. Update from the [latest release](https://github.com/cloutlab-studio/cloutfox/releases/latest).

## Good to know

- The API and MCP listen only on `127.0.0.1`. Without `CLOUTFOX_API_TOKEN` any program on this computer can use them; set a token if other people use the computer.
- An AI agent reads other people's pages, and a page may try to take control of it. That is why MCP cannot delete a profile, and file uploads are allowed only from chosen folders and only for media files.
- The self-destruct password wipes keys and data for good.
