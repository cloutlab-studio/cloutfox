#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# cloutfox_app.py points every data path at CLOUTFOX_HOME.
exec .venv/bin/python cloutfox_app.py "$@"
