# End-to-end checks

Run by hand against a real CloutFox. They are not part of `pytest`: they need a browser and the network.

| Script | Needs | Checks |
| --- | --- | --- |
| `api_e2e.py` | a running API | a lasting fingerprint, JSON and Netscape cookies, a good and a failed launch |
| `control_e2e.py` | nothing (starts a headless browser itself) | page control: navigation, snapshot, click, tabs, `file://` refused |
| `stop_e2e.py` | nothing (starts a headless browser itself) | stopping closes the browser without killing it and saves the tabs; runs in CI on Windows |
| `mcp_stdio_e2e.py` | a running API | MCP over stdio (`python -m src.mcp_server`) |
| `mcp_http_e2e.py` | a running API | MCP over HTTP at `/mcp`, 401 without a token |
| `detection_e2e.py headless headed` | the network | headless against headed on bot detection pages |

Environment variables:

```bash
CLOUTFOX_URL=http://127.0.0.1:8000     # CloutFox address
CLOUTFOX_API_TOKEN=...                 # if the API has a token
CLOUTFOX_DATA_DIR=camoufox_data        # where api_e2e reads fingerprint.json
E2E_OUT=e2e-output                     # where to save screenshots
```

The scripts create the profiles `e2e-*`, `mcp-demo`, `http-demo`, `ctl-test`. Run them with a separate data folder (`CLOUTFOX_DATA_DIR`, `CLOUTFOX_PROFILES_FILE`), never on working profiles.
