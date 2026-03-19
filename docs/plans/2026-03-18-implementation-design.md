# slack-mcp Implementation Design

Date: 2026-03-18

## Decisions

- **MCP framework**: FastMCP (decorator-based) with module-based tool registration
- **Tool registration**: Each domain module exposes `register(mcp, creds)`; `server.py` calls all at startup
- **HTTP client**: `httpx` (async-capable, modern API)
- **Testing**: Unit tests (mocked HTTP via `respx`) + opt-in integration smoke tests
- **CI**: GitHub Actions, Python 3.11 and 3.12, unit tests only

## Project Structure

```
slack-mcp/
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   └── slack_mcp/
│       ├── __init__.py
│       ├── server.py          # FastMCP app + registers all tool modules
│       ├── auth.py            # credentials file read/validate
│       ├── client.py          # httpx wrapper (SlackClient, SlackAPIError)
│       ├── setup.py           # one-time token extraction CLI
│       └── tools/
│           ├── __init__.py
│           ├── channels.py    # list_channels, get_channel_history, get_channel_info
│           ├── messages.py    # get_thread
│           ├── search.py      # search_messages
│           └── users.py       # get_user_info, list_users, list_workspaces
├── tests/
│   ├── unit/
│   │   ├── test_auth.py
│   │   ├── test_client.py
│   │   └── tools/
│   │       ├── test_channels.py
│   │       ├── test_messages.py
│   │       ├── test_search.py
│   │       └── test_users.py
│   └── integration/
│       └── test_smoke.py
├── pyproject.toml
├── .gitignore
└── README.md
```

## Auth (`auth.py`)

```python
@dataclass
class WorkspaceCredential:
    name: str
    url: str
    token: str      # xoxc-...
    d_cookie: str   # xoxd-...

@dataclass
class Credentials:
    workspaces: dict[str, WorkspaceCredential]
    extracted_at: datetime
```

- `load_credentials()` — reads `~/.config/slack-mcp/credentials.json`, exits 1 if missing/invalid, warns stderr if >300 days old
- `save_credentials(creds)` — atomic write (temp file → rename), mode `0600`
- `get_workspace(creds, name)` — `None`/`""` returns first workspace; unknown name raises `ValueError`

## HTTP Client (`client.py`)

```python
class SlackAPIError(Exception):
    def __init__(self, error_code: str): ...

class SlackClient:
    BASE_URL = "https://slack.com/api/"

    def __init__(self, credential: WorkspaceCredential): ...
    def get(self, method: str, **params) -> dict: ...
    def get_paginated(self, method: str, key: str, limit: int, **params) -> list[dict]: ...
```

- POST + `application/x-www-form-urlencoded` for all Slack API calls
- HTTP 429: wait `Retry-After`, retry once, then raise
- HTTP 5xx: raise immediately
- `ok: false`: raise `SlackAPIError(response["error"])`
- `get_paginated`: cursor iteration up to `limit`; tools do not implement pagination

## Server (`server.py`)

```python
def main():
    creds = load_credentials()
    mcp = FastMCP("slack-mcp")
    channels.register(mcp, creds)
    messages.register(mcp, creds)
    search.register(mcp, creds)
    users.register(mcp, creds)
    mcp.run()  # stdio transport
```

Each tool module pattern:

```python
def register(mcp: FastMCP, creds: Credentials) -> None:
    @mcp.tool()
    def list_channels(workspace: str = "", ...) -> list[dict]:
        cred = get_workspace(creds, workspace)
        client = SlackClient(cred)
        ...
```

Adding a v2 write tool: add a decorated function to the relevant module. No changes to `server.py` unless it's a new domain.

## Setup Script (`setup.py`)

Entry point: `slack-mcp-setup`

1. `import slacktokens` — if `ImportError`, print install instructions and exit 1
2. `pgrep -x Slack` — if running, print "Quit Slack first" and exit 1
3. Call `slacktokens.get_tokens_and_cookie()`
4. For each workspace token, HTTP GET workspace URL with candidate `d` cookie; extract `xoxc-` token via regex `xox[a-zA-Z]-[a-zA-Z0-9-]+`
5. If workspace URL fetch fails: warn and skip (don't abort)
6. If no workspaces extracted: exit 1
7. `save_credentials()` (atomic, mode 0600)
8. Print summary with token/cookie prefixes only (first 12 chars + `...`)
9. Print: "These credentials grant full Slack access. Do not share credentials.json."

## Testing

**Unit** (`tests/unit/`): `respx` mocks for all HTTP; no credentials required.

- `test_auth.py`: load/save/validate, stale warning, missing file, bad schema, workspace resolution
- `test_client.py`: 429 retry, 5xx immediate raise, `ok:false` → `SlackAPIError`, pagination, headers
- `tools/test_*.py`: correct Slack method, params, response shape, error surfacing

**Integration** (`tests/integration/test_smoke.py`): skipped unless `SLACK_TEST_WORKSPACE` env var is set. Calls `list_workspaces`, `list_channels` (limit=5), `get_user_info`. Validates response shape only.

## CI (`.github/workflows/ci.yml`)

- Trigger: push and PR
- Matrix: Python 3.11, 3.12
- Steps: checkout → setup-python → `pip install -e ".[dev]"` → `pytest tests/unit/`
- Integration tests not run in CI

## `pyproject.toml` sketch

```toml
[project]
name = "slack-mcp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.27",
    "slacktokens @ git+https://github.com/hraftery/slacktokens.git",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "respx>=0.21",
]

[project.scripts]
slack-mcp-server = "slack_mcp.server:main"
slack-mcp-setup  = "slack_mcp.setup:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
```
