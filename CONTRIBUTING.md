# Contributing to CloutFox

Thanks for helping. This page has what you need to get a change merged quickly.

## Bugs and ideas

- Report a bug in an [issue](https://github.com/cloutlab-studio/cloutfox/issues/new/choose) using the template: version, system, what you did, what you expected and what happened, lines from the log (`logs/cloutfox_YYYYMMDD.log` in the data folder).
- Before sending, remove your proxies, logins, IPs and account names from the log.
- Do not post security issues in public issues: see [SECURITY.md](SECURITY.md).

## Code changes

1. Fork the repository and branch from `main`.
2. Install the development dependencies and check that everything passes before your change:

   ```bash
   python -m venv .venv
   .venv/bin/pip install -r requirements-dev.txt
   .venv/bin/ruff check src tests chrome_engine packaging docs cloutfox_app.py cloutfox_mcp.py
   .venv/bin/python -m pytest
   ```

3. Make the change and add a test that fails without it.
4. Add interface strings to `src/core/strings.py` in both English and Russian.
5. If you changed the panel (`frontend/`), rebuild it (`cd frontend && npm ci && npm run build`) and commit `src/ui/dist`.
6. Write commit messages following [Conventional Commits](https://www.conventionalcommits.org/): `fix: …`, `feat: …`, `docs: …`.
7. Open a pull request and describe what changed, why, and how you tested it.

The code layout is described in [CLAUDE.md](CLAUDE.md), the panel's design rules in [DESIGN.md](DESIGN.md).

## Data in examples

Tests, examples and screenshots use made-up data only: IPs from `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, logins like `user:pass`, invented profile names.

## License

By submitting a change you agree that it is released under the MIT license, like the rest of CloutFox.
