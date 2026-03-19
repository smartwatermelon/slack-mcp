# slack-mcp Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a read-only Slack MCP server using cookie-based authentication that gives Claude Code access to Slack channels, messages, users, and search.

**Architecture:** FastMCP server with module-based tool registration; each domain module exposes `register(mcp, creds)`. Private helper functions (`_func`) hold the logic and are tested directly; `register()` just creates closures over `creds`. Auth, HTTP client, and tools are separate layers. Setup is a standalone CLI that extracts tokens once and caches them.

**Tech Stack:** Python 3.11+, FastMCP (`mcp>=1.0.0`), `httpx`, `respx` (HTTP mock), `pytest`, `hatchling` (build backend), GitHub Actions (CI)

---

## Tasks

### Task 1: Project scaffolding

**Files:**

- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/slack_mcp/__init__.py`
- Create: `src/slack_mcp/tools/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/tools/__init__.py`
- Create: `tests/integration/__init__.py`

**Step 1: Create `pyproject.toml`**

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

[tool.hatch.build.targets.wheel]
packages = ["src/slack_mcp"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 2: Create `.gitignore`**

```gitignore
credentials.json
__pycache__/
*.py[cod]
*.egg-info/
dist/
.venv/
.env
```

**Step 3: Create directory structure and empty init files**

```bash
mkdir -p src/slack_mcp/tools tests/unit/tools tests/integration
touch src/slack_mcp/__init__.py src/slack_mcp/tools/__init__.py
touch tests/__init__.py tests/unit/__init__.py tests/unit/tools/__init__.py
touch tests/integration/__init__.py
```

**Step 4: Install in dev mode**

```bash
pip install -e ".[dev]"
```

Expected: installs without errors. (If `slacktokens` fails due to LevelDB build issues, that's OK — it's only needed at setup time, not for tests.)

**Step 5: Verify pytest is wired up**

```bash
pytest --collect-only
```

Expected: `no tests ran` — the test directories exist and pytest finds them.

**Step 6: Commit**

```bash
git add pyproject.toml .gitignore src/ tests/
git commit -m "chore: project scaffolding — pyproject.toml, src layout, test dirs"
```

---

### Task 2: Auth module

**Files:**

- Create: `src/slack_mcp/auth.py`
- Create: `tests/unit/test_auth.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_auth.py`:

```python
import json
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from slack_mcp.auth import (
    Credentials,
    WorkspaceCredential,
    get_workspace,
    load_credentials,
    save_credentials,
)


@pytest.fixture
def cred():
    return WorkspaceCredential(
        name="test",
        url="https://test.slack.com",
        token="xoxc-abc",
        d_cookie="xoxd-xyz",
    )


@pytest.fixture
def creds(cred):
    return Credentials(
        workspaces={"test": cred},
        extracted_at=datetime.now(timezone.utc),
    )


def test_load_missing_file(tmp_path):
    with pytest.raises(SystemExit) as exc:
        load_credentials(tmp_path / "missing.json")
    assert exc.value.code == 1


def test_load_invalid_json(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text("not json")
    with pytest.raises(SystemExit) as exc:
        load_credentials(path)
    assert exc.value.code == 1


def test_load_empty_token_exits(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({
        "workspaces": {
            "test": {"url": "https://test.slack.com", "token": "", "d_cookie": "xoxd-xyz"},
        },
        "extracted_at": "2026-01-01T00:00:00+00:00",
    }))
    with pytest.raises(SystemExit) as exc:
        load_credentials(path)
    assert exc.value.code == 1


def test_load_empty_cookie_exits(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({
        "workspaces": {
            "test": {"url": "https://test.slack.com", "token": "xoxc-abc", "d_cookie": ""},
        },
        "extracted_at": "2026-01-01T00:00:00+00:00",
    }))
    with pytest.raises(SystemExit) as exc:
        load_credentials(path)
    assert exc.value.code == 1


def test_load_no_workspaces_exits(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"workspaces": {}, "extracted_at": "2026-01-01T00:00:00+00:00"}))
    with pytest.raises(SystemExit) as exc:
        load_credentials(path)
    assert exc.value.code == 1


def test_load_valid(tmp_path, creds):
    path = tmp_path / "credentials.json"
    save_credentials(creds, path)
    loaded = load_credentials(path)
    assert "test" in loaded.workspaces
    assert loaded.workspaces["test"].token == "xoxc-abc"
    assert loaded.workspaces["test"].d_cookie == "xoxd-xyz"


def test_load_stale_warns_to_stderr(tmp_path, capsys):
    path = tmp_path / "credentials.json"
    old_date = (datetime.now(timezone.utc) - timedelta(days=301)).isoformat()
    path.write_text(json.dumps({
        "workspaces": {
            "test": {"url": "https://test.slack.com", "token": "xoxc-abc", "d_cookie": "xoxd-xyz"},
        },
        "extracted_at": old_date,
    }))
    load_credentials(path)
    assert "Warning" in capsys.readouterr().err


def test_save_mode_0600(tmp_path, creds):
    path = tmp_path / "credentials.json"
    save_credentials(creds, path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_save_roundtrip(tmp_path, creds):
    path = tmp_path / "credentials.json"
    save_credentials(creds, path)
    loaded = load_credentials(path)
    assert loaded.workspaces["test"].token == "xoxc-abc"
    assert loaded.workspaces["test"].d_cookie == "xoxd-xyz"


def test_get_workspace_empty_string_returns_first(creds):
    assert get_workspace(creds, "").name == "test"


def test_get_workspace_none_returns_first(creds):
    assert get_workspace(creds, None).name == "test"


def test_get_workspace_by_name(creds):
    assert get_workspace(creds, "test").token == "xoxc-abc"


def test_get_workspace_unknown_raises(creds):
    with pytest.raises(ValueError, match="not found"):
        get_workspace(creds, "nonexistent")
```

**Step 2: Run to verify failures**

```bash
pytest tests/unit/test_auth.py -v
```

Expected: `ImportError` — `slack_mcp.auth` doesn't exist yet.

**Step 3: Implement `src/slack_mcp/auth.py`**

```python
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CREDENTIALS_PATH = Path.home() / ".config" / "slack-mcp" / "credentials.json"
STALE_DAYS = 300


@dataclass
class WorkspaceCredential:
    name: str
    url: str
    token: str
    d_cookie: str


@dataclass
class Credentials:
    workspaces: dict[str, WorkspaceCredential]
    extracted_at: datetime


def load_credentials(path: Path = CREDENTIALS_PATH) -> Credentials:
    if not path.exists():
        print(
            f"Error: credentials file not found at {path}\n"
            "Run 'slack-mcp-setup' to create it.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"Error: credentials file is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    workspaces: dict[str, WorkspaceCredential] = {}
    for name, ws in data.get("workspaces", {}).items():
        if not ws.get("token") or not ws.get("d_cookie"):
            print(
                f"Error: workspace '{name}' is missing token or d_cookie.",
                file=sys.stderr,
            )
            sys.exit(1)
        workspaces[name] = WorkspaceCredential(
            name=name,
            url=ws.get("url", ""),
            token=ws["token"],
            d_cookie=ws["d_cookie"],
        )

    if not workspaces:
        print("Error: credentials file contains no workspaces.", file=sys.stderr)
        sys.exit(1)

    raw_ts = data.get("extracted_at", "2000-01-01T00:00:00+00:00")
    extracted_at = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))

    age_days = (datetime.now(timezone.utc) - extracted_at).days
    if age_days > STALE_DAYS:
        print(
            f"Warning: credentials are {age_days} days old (>{STALE_DAYS}). "
            "Re-run 'slack-mcp-setup' to refresh.",
            file=sys.stderr,
        )

    return Credentials(workspaces=workspaces, extracted_at=extracted_at)


def save_credentials(creds: Credentials, path: Path = CREDENTIALS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "workspaces": {
            name: {"url": ws.url, "token": ws.token, "d_cookie": ws.d_cookie}
            for name, ws in creds.workspaces.items()
        },
        "extracted_at": creds.extracted_at.isoformat(),
    }
    fd, tmp_str = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp = Path(tmp_str)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def get_workspace(creds: Credentials, name: str | None) -> WorkspaceCredential:
    if not name:
        return next(iter(creds.workspaces.values()))
    if name not in creds.workspaces:
        available = ", ".join(creds.workspaces.keys())
        raise ValueError(f"Workspace '{name}' not found. Available: {available}")
    return creds.workspaces[name]
```

**Step 4: Run to verify pass**

```bash
pytest tests/unit/test_auth.py -v
```

Expected: all 13 tests pass.

**Step 5: Commit**

```bash
git add src/slack_mcp/auth.py tests/unit/test_auth.py
git commit -m "feat: auth module — credentials load/save/validate"
```

---

### Task 3: HTTP client

**Files:**

- Create: `src/slack_mcp/client.py`
- Create: `tests/unit/test_client.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_client.py`:

```python
import time

import httpx
import pytest
import respx

from slack_mcp.auth import WorkspaceCredential
from slack_mcp.client import SlackAPIError, SlackClient


@pytest.fixture
def cred():
    return WorkspaceCredential(
        name="test", url="https://test.slack.com",
        token="xoxc-abc", d_cookie="xoxd-xyz",
    )


@pytest.fixture
def client(cred):
    return SlackClient(cred)


def test_auth_header(cred):
    assert SlackClient(cred)._headers["Authorization"] == "Bearer xoxc-abc"


def test_cookie_header(cred):
    assert SlackClient(cred)._headers["Cookie"] == "d=xoxd-xyz"


@respx.mock
def test_get_success(client):
    respx.post("https://slack.com/api/users.list").mock(
        return_value=httpx.Response(200, json={"ok": True, "members": []})
    )
    assert client.get("users.list")["ok"] is True


@respx.mock
def test_get_raises_slack_api_error(client):
    respx.post("https://slack.com/api/conversations.list").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "channel_not_found"})
    )
    with pytest.raises(SlackAPIError) as exc:
        client.get("conversations.list")
    assert exc.value.error_code == "channel_not_found"


@respx.mock
def test_5xx_raises_immediately(client):
    respx.post("https://slack.com/api/users.list").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.get("users.list")


@respx.mock
def test_429_retries_once(client, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx.post("https://slack.com/api/users.list")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.Response(200, json={"ok": True, "members": []}),
    ]
    result = client.get("users.list")
    assert result["ok"] is True
    assert route.call_count == 2


@respx.mock
def test_429_twice_raises(client, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx.post("https://slack.com/api/users.list")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.Response(429, headers={"Retry-After": "1"}),
    ]
    with pytest.raises(httpx.HTTPStatusError):
        client.get("users.list")


@respx.mock
def test_paginated_follows_cursor(client):
    route = respx.post("https://slack.com/api/conversations.list")
    route.side_effect = [
        httpx.Response(200, json={
            "ok": True,
            "channels": [{"id": "C1"}],
            "response_metadata": {"next_cursor": "cursor1"},
        }),
        httpx.Response(200, json={
            "ok": True,
            "channels": [{"id": "C2"}],
            "response_metadata": {"next_cursor": ""},
        }),
    ]
    result = client.get_paginated("conversations.list", "channels", 200)
    assert [r["id"] for r in result] == ["C1", "C2"]


@respx.mock
def test_paginated_respects_limit(client):
    respx.post("https://slack.com/api/conversations.list").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "channels": [{"id": f"C{i}"} for i in range(10)],
            "response_metadata": {"next_cursor": ""},
        })
    )
    assert len(client.get_paginated("conversations.list", "channels", 3)) == 3
```

**Step 2: Run to verify failures**

```bash
pytest tests/unit/test_client.py -v
```

Expected: `ImportError` — `slack_mcp.client` doesn't exist yet.

**Step 3: Implement `src/slack_mcp/client.py`**

```python
from __future__ import annotations

import time

import httpx

from slack_mcp.auth import WorkspaceCredential


class SlackAPIError(Exception):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class SlackClient:
    BASE_URL = "https://slack.com/api/"

    def __init__(self, credential: WorkspaceCredential) -> None:
        self._headers = {
            "Authorization": f"Bearer {credential.token}",
            "Cookie": f"d={credential.d_cookie}",
        }

    def get(self, method: str, **params: object) -> dict:
        return self._request(method, params)

    def _request(self, method: str, params: dict, *, _retry: bool = True) -> dict:
        with httpx.Client() as http:
            response = http.post(
                f"{self.BASE_URL}{method}",
                data=params,
                headers=self._headers,
            )

        if response.status_code == 429:
            if _retry:
                retry_after = int(response.headers.get("Retry-After", "1"))
                time.sleep(retry_after)
                return self._request(method, params, _retry=False)
            response.raise_for_status()

        if response.status_code >= 500:
            response.raise_for_status()

        data = response.json()
        if not data.get("ok"):
            raise SlackAPIError(data.get("error", "unknown_error"))

        return data

    def get_paginated(self, method: str, key: str, limit: int, **params: object) -> list[dict]:
        results: list[dict] = []
        cursor: str | None = None

        while len(results) < limit:
            batch_limit = min(limit - len(results), 200)
            request_params: dict = {**params, "limit": batch_limit}
            if cursor:
                request_params["cursor"] = cursor

            data = self._request(method, request_params)
            results.extend(data.get(key, []))

            cursor = data.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break

        return results[:limit]
```

**Step 4: Run to verify pass**

```bash
pytest tests/unit/test_client.py -v
```

Expected: all 9 tests pass.

**Step 5: Run full suite**

```bash
pytest tests/unit/ -v
```

Expected: all tests pass (auth + client).

**Step 6: Commit**

```bash
git add src/slack_mcp/client.py tests/unit/test_client.py
git commit -m "feat: Slack HTTP client with pagination and rate limiting"
```

---

### Task 4: Users tools

**Files:**

- Create: `src/slack_mcp/tools/users.py`
- Create: `tests/unit/tools/test_users.py`

**Pattern note:** Tool modules expose private helper functions (prefixed `_`) that accept a `SlackClient` directly. Tests call these helpers with a real `SlackClient` + `respx`-mocked HTTP. The `register()` function just wires them up as MCP tools.

**Step 1: Write the failing tests**

Create `tests/unit/tools/test_users.py`:

```python
from datetime import datetime, timezone

import httpx
import pytest
import respx

from slack_mcp.auth import Credentials, WorkspaceCredential
from slack_mcp.client import SlackClient
from slack_mcp.tools.users import _get_user_info, _list_users, _list_workspaces


@pytest.fixture
def cred():
    return WorkspaceCredential(
        name="test", url="https://test.slack.com",
        token="xoxc-abc", d_cookie="xoxd-xyz",
    )


@pytest.fixture
def creds(cred):
    return Credentials(workspaces={"test": cred}, extracted_at=datetime.now(timezone.utc))


@pytest.fixture
def client(cred):
    return SlackClient(cred)


def test_list_workspaces(creds):
    result = _list_workspaces(creds)
    assert result == [{"name": "test", "url": "https://test.slack.com"}]


@respx.mock
def test_get_user_info(client):
    respx.post("https://slack.com/api/users.info").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "user": {
                "id": "U123",
                "name": "jsmith",
                "real_name": "John Smith",
                "profile": {"display_name": "john", "email": "john@example.com", "title": "Engineer"},
                "tz": "America/New_York",
            },
        })
    )
    result = _get_user_info(client, "U123")
    assert result["id"] == "U123"
    assert result["real_name"] == "John Smith"
    assert result["email"] == "john@example.com"
    assert result["tz"] == "America/New_York"


@respx.mock
def test_get_user_info_missing_profile_fields(client):
    respx.post("https://slack.com/api/users.info").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "user": {"id": "U1", "name": "bot", "profile": {}},
        })
    )
    result = _get_user_info(client, "U1")
    assert result["email"] is None
    assert result["title"] is None


@respx.mock
def test_list_users(client):
    respx.post("https://slack.com/api/users.list").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "members": [
                {"id": "U1", "name": "alice", "real_name": "Alice", "is_bot": False, "deleted": False},
                {"id": "U2", "name": "bot", "real_name": "Bot", "is_bot": True, "deleted": False},
            ],
            "response_metadata": {"next_cursor": ""},
        })
    )
    result = _list_users(client, limit=100)
    assert len(result) == 2
    assert result[0] == {"id": "U1", "name": "alice", "real_name": "Alice", "is_bot": False, "deleted": False}
    assert result[1]["is_bot"] is True
```

**Step 2: Run to verify failures**

```bash
pytest tests/unit/tools/test_users.py -v
```

Expected: `ImportError` — `slack_mcp.tools.users` doesn't exist yet.

**Step 3: Implement `src/slack_mcp/tools/users.py`**

```python
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from slack_mcp.auth import Credentials, get_workspace
from slack_mcp.client import SlackClient


def _list_workspaces(creds: Credentials) -> list[dict]:
    return [{"name": name, "url": ws.url} for name, ws in creds.workspaces.items()]


def _get_user_info(client: SlackClient, user_id: str) -> dict:
    data = client.get("users.info", user=user_id)
    u = data["user"]
    return {
        "id": u["id"],
        "name": u["name"],
        "real_name": u.get("real_name", ""),
        "display_name": u.get("profile", {}).get("display_name", ""),
        "email": u.get("profile", {}).get("email"),
        "title": u.get("profile", {}).get("title"),
        "tz": u.get("tz", ""),
    }


def _list_users(client: SlackClient, limit: int) -> list[dict]:
    members = client.get_paginated("users.list", "members", limit)
    return [
        {
            "id": u["id"],
            "name": u["name"],
            "real_name": u.get("real_name", ""),
            "is_bot": u.get("is_bot", False),
            "deleted": u.get("deleted", False),
        }
        for u in members
    ]


def register(mcp: FastMCP, creds: Credentials) -> None:
    @mcp.tool()
    def list_workspaces() -> list[dict]:
        """List all configured Slack workspaces."""
        return _list_workspaces(creds)

    @mcp.tool()
    def get_user_info(user_id: str, workspace: str = "") -> dict:
        """Get info about a Slack user by ID."""
        return _get_user_info(SlackClient(get_workspace(creds, workspace)), user_id)

    @mcp.tool()
    def list_users(workspace: str = "", limit: int = 100) -> list[dict]:
        """List users in a Slack workspace."""
        return _list_users(SlackClient(get_workspace(creds, workspace)), limit)
```

**Step 4: Run to verify pass**

```bash
pytest tests/unit/tools/test_users.py -v
```

Expected: all 4 tests pass.

**Step 5: Commit**

```bash
git add src/slack_mcp/tools/users.py tests/unit/tools/test_users.py
git commit -m "feat: users tools — list_workspaces, get_user_info, list_users"
```

---

### Task 5: Channels tools

**Files:**

- Create: `src/slack_mcp/tools/channels.py`
- Create: `tests/unit/tools/test_channels.py`

**Step 1: Write the failing tests**

Create `tests/unit/tools/test_channels.py`:

```python
from datetime import datetime, timezone

import httpx
import pytest
import respx

from slack_mcp.auth import WorkspaceCredential
from slack_mcp.client import SlackClient
from slack_mcp.tools.channels import _get_channel_history, _get_channel_info, _list_channels


@pytest.fixture
def client():
    return SlackClient(WorkspaceCredential(
        name="test", url="https://test.slack.com",
        token="xoxc-abc", d_cookie="xoxd-xyz",
    ))


@respx.mock
def test_list_channels(client):
    respx.post("https://slack.com/api/conversations.list").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "channels": [
                {"id": "C1", "name": "general", "is_private": False, "num_members": 42,
                 "topic": {"value": "Company news"}, "purpose": {"value": "General chat"}},
            ],
            "response_metadata": {"next_cursor": ""},
        })
    )
    result = _list_channels(client, types="public_channel,private_channel", limit=200)
    assert result == [{
        "id": "C1", "name": "general", "is_private": False,
        "num_members": 42, "topic": "Company news", "purpose": "General chat",
    }]


@respx.mock
def test_list_channels_missing_optional_fields(client):
    respx.post("https://slack.com/api/conversations.list").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "channels": [{"id": "C2", "name": "secret", "is_private": True}],
            "response_metadata": {"next_cursor": ""},
        })
    )
    result = _list_channels(client, types="private_channel", limit=200)
    assert result[0]["num_members"] == 0
    assert result[0]["topic"] == ""


@respx.mock
def test_get_channel_history(client):
    respx.post("https://slack.com/api/conversations.history").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "messages": [
                {"ts": "123.456", "user": "U1", "text": "hello", "thread_ts": "123.456", "reply_count": 2},
                {"ts": "124.000", "user": "U2", "text": "world"},
            ],
            "response_metadata": {"next_cursor": ""},
        })
    )
    result = _get_channel_history(client, channel_id="C1", oldest="", latest="", limit=50)
    assert len(result) == 2
    assert result[0]["reply_count"] == 2
    assert result[1]["thread_ts"] is None


@respx.mock
def test_get_channel_info(client):
    respx.post("https://slack.com/api/conversations.info").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "channel": {
                "id": "C1", "name": "general", "is_private": False,
                "topic": {"value": "News"}, "purpose": {"value": "Chat"},
                "num_members": 10, "created": 1700000000,
            },
        })
    )
    result = _get_channel_info(client, "C1")
    assert result["id"] == "C1"
    assert result["num_members"] == 10
    assert result["created"] == 1700000000
```

**Step 2: Run to verify failures**

```bash
pytest tests/unit/tools/test_channels.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/slack_mcp/tools/channels.py`**

```python
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from slack_mcp.auth import Credentials, get_workspace
from slack_mcp.client import SlackClient


def _list_channels(client: SlackClient, types: str, limit: int) -> list[dict]:
    channels = client.get_paginated("conversations.list", "channels", limit, types=types)
    return [
        {
            "id": c["id"],
            "name": c.get("name", ""),
            "is_private": c.get("is_private", False),
            "num_members": c.get("num_members", 0),
            "topic": c.get("topic", {}).get("value", ""),
            "purpose": c.get("purpose", {}).get("value", ""),
        }
        for c in channels
    ]


def _get_channel_history(
    client: SlackClient, channel_id: str, oldest: str, latest: str, limit: int
) -> list[dict]:
    params: dict = {"channel": channel_id}
    if oldest:
        params["oldest"] = oldest
    if latest:
        params["latest"] = latest
    messages = client.get_paginated("conversations.history", "messages", limit, **params)
    return [
        {
            "ts": m["ts"],
            "user": m.get("user", ""),
            "text": m.get("text", ""),
            "thread_ts": m.get("thread_ts"),
            "reply_count": m.get("reply_count"),
        }
        for m in messages
    ]


def _get_channel_info(client: SlackClient, channel_id: str) -> dict:
    data = client.get("conversations.info", channel=channel_id)
    c = data["channel"]
    return {
        "id": c["id"],
        "name": c.get("name", ""),
        "is_private": c.get("is_private", False),
        "topic": c.get("topic", {}).get("value", ""),
        "purpose": c.get("purpose", {}).get("value", ""),
        "num_members": c.get("num_members", 0),
        "created": c.get("created", 0),
    }


def register(mcp: FastMCP, creds: Credentials) -> None:
    @mcp.tool()
    def list_channels(
        workspace: str = "",
        types: str = "public_channel,private_channel",
        limit: int = 200,
    ) -> list[dict]:
        """List channels in a Slack workspace."""
        return _list_channels(SlackClient(get_workspace(creds, workspace)), types, limit)

    @mcp.tool()
    def get_channel_history(
        channel_id: str,
        workspace: str = "",
        limit: int = 50,
        oldest: str = "",
        latest: str = "",
    ) -> list[dict]:
        """Get message history for a Slack channel."""
        return _get_channel_history(
            SlackClient(get_workspace(creds, workspace)), channel_id, oldest, latest, limit
        )

    @mcp.tool()
    def get_channel_info(channel_id: str, workspace: str = "") -> dict:
        """Get info about a Slack channel."""
        return _get_channel_info(SlackClient(get_workspace(creds, workspace)), channel_id)
```

**Step 4: Run to verify pass**

```bash
pytest tests/unit/tools/test_channels.py -v
```

Expected: all 4 tests pass.

**Step 5: Commit**

```bash
git add src/slack_mcp/tools/channels.py tests/unit/tools/test_channels.py
git commit -m "feat: channels tools — list_channels, get_channel_history, get_channel_info"
```

---

### Task 6: Messages tool

**Files:**

- Create: `src/slack_mcp/tools/messages.py`
- Create: `tests/unit/tools/test_messages.py`

**Step 1: Write the failing tests**

Create `tests/unit/tools/test_messages.py`:

```python
import httpx
import pytest
import respx

from slack_mcp.auth import WorkspaceCredential
from slack_mcp.client import SlackClient
from slack_mcp.tools.messages import _get_thread


@pytest.fixture
def client():
    return SlackClient(WorkspaceCredential(
        name="test", url="https://test.slack.com",
        token="xoxc-abc", d_cookie="xoxd-xyz",
    ))


@respx.mock
def test_get_thread(client):
    respx.post("https://slack.com/api/conversations.replies").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "messages": [
                {"ts": "100.000", "user": "U1", "text": "parent"},
                {"ts": "100.001", "user": "U2", "text": "reply"},
            ],
            "response_metadata": {"next_cursor": ""},
        })
    )
    result = _get_thread(client, channel_id="C1", thread_ts="100.000", limit=100)
    assert len(result) == 2
    assert result[0] == {"ts": "100.000", "user": "U1", "text": "parent"}
    assert result[1]["text"] == "reply"


@respx.mock
def test_get_thread_missing_user(client):
    respx.post("https://slack.com/api/conversations.replies").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "messages": [{"ts": "100.000", "text": "bot message"}],
            "response_metadata": {"next_cursor": ""},
        })
    )
    result = _get_thread(client, channel_id="C1", thread_ts="100.000", limit=100)
    assert result[0]["user"] == ""
```

**Step 2: Run to verify failures**

```bash
pytest tests/unit/tools/test_messages.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/slack_mcp/tools/messages.py`**

```python
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from slack_mcp.auth import Credentials, get_workspace
from slack_mcp.client import SlackClient


def _get_thread(client: SlackClient, channel_id: str, thread_ts: str, limit: int) -> list[dict]:
    replies = client.get_paginated(
        "conversations.replies", "messages", limit, channel=channel_id, ts=thread_ts
    )
    return [
        {"ts": m["ts"], "user": m.get("user", ""), "text": m.get("text", "")}
        for m in replies
    ]


def register(mcp: FastMCP, creds: Credentials) -> None:
    @mcp.tool()
    def get_thread(
        channel_id: str, thread_ts: str, workspace: str = "", limit: int = 100
    ) -> list[dict]:
        """Get all replies in a Slack thread."""
        return _get_thread(SlackClient(get_workspace(creds, workspace)), channel_id, thread_ts, limit)
```

**Step 4: Run to verify pass**

```bash
pytest tests/unit/tools/test_messages.py -v
```

Expected: all 2 tests pass.

**Step 5: Commit**

```bash
git add src/slack_mcp/tools/messages.py tests/unit/tools/test_messages.py
git commit -m "feat: messages tool — get_thread"
```

---

### Task 7: Search tool

**Files:**

- Create: `src/slack_mcp/tools/search.py`
- Create: `tests/unit/tools/test_search.py`

**Step 1: Write the failing tests**

Create `tests/unit/tools/test_search.py`:

```python
import httpx
import pytest
import respx

from slack_mcp.auth import WorkspaceCredential
from slack_mcp.client import SlackClient
from slack_mcp.tools.search import _search_messages


@pytest.fixture
def client():
    return SlackClient(WorkspaceCredential(
        name="test", url="https://test.slack.com",
        token="xoxc-abc", d_cookie="xoxd-xyz",
    ))


@respx.mock
def test_search_messages(client):
    respx.post("https://slack.com/api/search.messages").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "messages": {
                "total": 1,
                "matches": [{
                    "ts": "123.456",
                    "channel": {"id": "C1", "name": "general"},
                    "user": "U1",
                    "text": "hello world",
                    "permalink": "https://slack.com/archives/C1/p123456",
                }],
            },
        })
    )
    result = _search_messages(client, query="hello", count=20, sort="score")
    assert result["total"] == 1
    assert result["matches"][0]["channel_id"] == "C1"
    assert result["matches"][0]["permalink"] == "https://slack.com/archives/C1/p123456"


@respx.mock
def test_search_messages_empty(client):
    respx.post("https://slack.com/api/search.messages").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "messages": {"total": 0, "matches": []},
        })
    )
    result = _search_messages(client, query="zzznomatch", count=20, sort="score")
    assert result["total"] == 0
    assert result["matches"] == []
```

**Step 2: Run to verify failures**

```bash
pytest tests/unit/tools/test_search.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/slack_mcp/tools/search.py`**

```python
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from slack_mcp.auth import Credentials, get_workspace
from slack_mcp.client import SlackClient


def _search_messages(client: SlackClient, query: str, count: int, sort: str) -> dict:
    data = client.get("search.messages", query=query, count=count, sort=sort)
    messages = data.get("messages", {})
    return {
        "total": messages.get("total", 0),
        "matches": [
            {
                "ts": m["ts"],
                "channel_id": m.get("channel", {}).get("id", ""),
                "channel_name": m.get("channel", {}).get("name", ""),
                "user": m.get("user", ""),
                "text": m.get("text", ""),
                "permalink": m.get("permalink", ""),
            }
            for m in messages.get("matches", [])
        ],
    }


def register(mcp: FastMCP, creds: Credentials) -> None:
    @mcp.tool()
    def search_messages(
        query: str, workspace: str = "", count: int = 20, sort: str = "score"
    ) -> dict:
        """Search messages in a Slack workspace."""
        return _search_messages(SlackClient(get_workspace(creds, workspace)), query, count, sort)
```

**Step 4: Run to verify pass**

```bash
pytest tests/unit/tools/test_search.py -v
```

Expected: all 2 tests pass.

**Step 5: Run full unit suite**

```bash
pytest tests/unit/ -v
```

Expected: all tests pass.

**Step 6: Commit**

```bash
git add src/slack_mcp/tools/search.py tests/unit/tools/test_search.py
git commit -m "feat: search tool — search_messages"
```

---

### Task 8: MCP server entry point

**Files:**

- Create: `src/slack_mcp/server.py`

No unit tests for `server.py` — it's pure wiring. The integration test (Task 10) covers end-to-end behavior.

**Step 1: Implement `src/slack_mcp/server.py`**

```python
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from slack_mcp.auth import load_credentials
from slack_mcp.tools import channels, messages, search, users


def main() -> None:
    creds = load_credentials()

    mcp = FastMCP("slack-mcp")

    users.register(mcp, creds)
    channels.register(mcp, creds)
    messages.register(mcp, creds)
    search.register(mcp, creds)

    mcp.run()


if __name__ == "__main__":
    main()
```

**Step 2: Verify import works**

```bash
python -c "from slack_mcp.server import main; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/slack_mcp/server.py
git commit -m "feat: MCP server entry point"
```

---

### Task 9: Setup script

**Files:**

- Create: `src/slack_mcp/setup.py`
- Create: `tests/unit/test_setup.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_setup.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# We test individual functions, not the full CLI flow (which requires slacktokens + Slack)


def test_main_exits_if_slacktokens_missing(monkeypatch):
    """If slacktokens is not importable, exit 1 with instructions."""
    monkeypatch.setitem(sys.modules, "slacktokens", None)
    from slack_mcp.setup import main
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_main_exits_if_slack_running(monkeypatch, tmp_path):
    """If Slack app is running (pgrep returns 0), exit 1."""
    import subprocess
    mock_slacktokens = MagicMock()
    monkeypatch.setitem(sys.modules, "slacktokens", mock_slacktokens)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        from importlib import reload
        import slack_mcp.setup as setup_mod
        reload(setup_mod)
        with pytest.raises(SystemExit) as exc:
            setup_mod.main()
    assert exc.value.code == 1
```

**Step 2: Run to verify failures**

```bash
pytest tests/unit/test_setup.py -v
```

Expected: `ImportError` — `slack_mcp.setup` doesn't exist yet.

**Step 3: Implement `src/slack_mcp/setup.py`**

```python
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone

TOKEN_RE = re.compile(r"xox[a-zA-Z]-[a-zA-Z0-9-]+")


def main() -> None:
    # Step 1: Verify slacktokens is installed
    try:
        import slacktokens
    except ImportError:
        print(
            "Error: slacktokens is not installed.\n"
            "Install it with:\n"
            "  pip install git+https://github.com/hraftery/slacktokens.git",
            file=sys.stderr,
        )
        sys.exit(1)

    # Step 2: Verify Slack is not running
    result = subprocess.run(["pgrep", "-x", "Slack"], capture_output=True)
    if result.returncode == 0:
        print(
            "Error: Slack is running. Quit Slack first, then re-run 'slack-mcp-setup'.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Step 3: Extract tokens via slacktokens
    import httpx

    from slack_mcp.auth import Credentials, WorkspaceCredential, save_credentials

    print("Extracting Slack tokens...")
    token_data = slacktokens.get_tokens_and_cookie()
    cookie = token_data.get("cookie", "")
    tokens: dict = token_data.get("tokens", {})

    workspaces: dict[str, WorkspaceCredential] = {}

    for workspace_url, token_info in tokens.items():
        workspace_name = (
            workspace_url.removeprefix("https://").removesuffix("/").replace(".slack.com", "")
        )
        d_cookie = token_info.get("d_cookie") or cookie

        try:
            resp = httpx.get(
                workspace_url, headers={"Cookie": f"d={d_cookie}"}, follow_redirects=True
            )
            match = TOKEN_RE.search(resp.text)
            if not match:
                print(
                    f"Warning: could not extract xoxc- token for '{workspace_name}', skipping.",
                    file=sys.stderr,
                )
                continue
            xoxc_token = match.group(0)
        except Exception as e:
            print(f"Warning: failed to fetch '{workspace_url}': {e}", file=sys.stderr)
            continue

        workspaces[workspace_name] = WorkspaceCredential(
            name=workspace_name,
            url=workspace_url,
            token=xoxc_token,
            d_cookie=d_cookie,
        )

    if not workspaces:
        print(
            "Error: no workspaces extracted. Ensure Slack is quit and try again.",
            file=sys.stderr,
        )
        sys.exit(1)

    creds = Credentials(workspaces=workspaces, extracted_at=datetime.now(timezone.utc))
    save_credentials(creds)

    print(f"\nExtracted {len(workspaces)} workspace(s):")
    for name, ws in workspaces.items():
        print(f"  {name}:")
        print(f"    token  = {ws.token[:12]}...")
        print(f"    cookie = {ws.d_cookie[:12]}...")

    print(
        "\n\u26a0\ufe0f  These credentials grant full Slack access. "
        "Do not share credentials.json."
    )


if __name__ == "__main__":
    main()
```

**Step 4: Run to verify pass**

```bash
pytest tests/unit/test_setup.py -v
```

Expected: tests pass.

**Step 5: Run full unit suite**

```bash
pytest tests/unit/ -v
```

Expected: all tests pass.

**Step 6: Commit**

```bash
git add src/slack_mcp/setup.py tests/unit/test_setup.py
git commit -m "feat: setup script — token extraction CLI"
```

---

### Task 10: Integration smoke tests

**Files:**

- Create: `tests/integration/test_smoke.py`

These are skipped in CI. Run locally with `SLACK_TEST_WORKSPACE=my-workspace pytest tests/integration/`.

**Step 1: Create `tests/integration/test_smoke.py`**

```python
"""
Integration smoke tests — require real Slack credentials.

Set SLACK_TEST_WORKSPACE to a workspace name in your credentials file to enable.

    SLACK_TEST_WORKSPACE=my-workspace pytest tests/integration/ -v
"""
from __future__ import annotations

import os

import pytest

WORKSPACE = os.getenv("SLACK_TEST_WORKSPACE", "")
pytestmark = pytest.mark.skipif(
    not WORKSPACE, reason="SLACK_TEST_WORKSPACE not set — skipping integration tests"
)


@pytest.fixture(scope="module")
def creds():
    from slack_mcp.auth import load_credentials
    return load_credentials()


@pytest.fixture(scope="module")
def client(creds):
    from slack_mcp.auth import get_workspace
    from slack_mcp.client import SlackClient
    return SlackClient(get_workspace(creds, WORKSPACE))


def test_list_workspaces(creds):
    from slack_mcp.tools.users import _list_workspaces
    result = _list_workspaces(creds)
    assert isinstance(result, list)
    assert any(ws["name"] == WORKSPACE for ws in result)


def test_list_channels_returns_results(client):
    from slack_mcp.tools.channels import _list_channels
    result = _list_channels(client, types="public_channel", limit=5)
    assert isinstance(result, list)
    assert len(result) > 0
    assert "id" in result[0]
    assert "name" in result[0]


def test_list_users_returns_results(client):
    from slack_mcp.tools.users import _list_users
    result = _list_users(client, limit=5)
    assert isinstance(result, list)
    assert len(result) > 0
    assert "id" in result[0]
```

**Step 2: Verify unit tests still pass and integration tests skip**

```bash
pytest tests/ -v
```

Expected: all unit tests pass, integration tests report `SKIPPED`.

**Step 3: Commit**

```bash
git add tests/integration/test_smoke.py
git commit -m "test: integration smoke tests (opt-in via SLACK_TEST_WORKSPACE)"
```

---

### Task 11: CI workflow

**Files:**

- Create: `.github/workflows/ci.yml`

**Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run unit tests
        run: pytest tests/unit/ -v
```

Note: `slacktokens` has a native `leveldb` dependency that may fail to build on Ubuntu. If so, add a step to install it without `slacktokens` by excluding it:

```yaml
      - name: Install dependencies (CI — skip slacktokens)
        run: pip install mcp httpx pytest respx
```

And in `pyproject.toml`, move `slacktokens` to an optional `[setup]` extra so the core package installs without it:

```toml
[project.optional-dependencies]
setup = [
    "slacktokens @ git+https://github.com/hraftery/slacktokens.git",
]
dev = [
    "pytest>=8",
    "respx>=0.21",
]
```

Then update `ci.yml` install step to `pip install -e ".[dev]"` (no slacktokens).

Verify this builds correctly before committing by checking whether `slacktokens` is a hard dependency at import time (it is only imported inside `setup.py:main()`, so the package will import fine without it installed).

**Step 2: Commit**

```bash
git add .github/workflows/ci.yml pyproject.toml
git commit -m "ci: GitHub Actions — run unit tests on Python 3.11 and 3.12"
```

---

### Task 12: README

**Files:**

- Create: `README.md`

**Step 1: Create `README.md`**

````markdown
# slack-mcp

A read-only Slack MCP server for Claude Code, using cookie-based authentication.
No OAuth app required.

## How it works

Uses the same `xoxc-`/`xoxd-` tokens the Slack desktop app uses internally.
Tokens are extracted once from the local Slack installation and cached in
`~/.config/slack-mcp/credentials.json`.

## Installation

```bash
# 1. Clone and install
git clone https://github.com/yourname/slack-mcp
cd slack-mcp
pip install -e ".[setup]"   # includes slacktokens

# 2. Extract tokens (Slack must be QUIT first)
osascript -e 'quit app "Slack"'
slack-mcp-setup

# 3. Register with Claude Code
claude mcp add slack-mcp -- slack-mcp-server
```

## Tools

| Tool | Description |
|---|---|
| `list_workspaces` | List all configured workspaces |
| `list_channels` | List channels (public and/or private) |
| `get_channel_history` | Get recent messages from a channel |
| `get_thread` | Get all replies in a thread |
| `search_messages` | Full-text search across a workspace |
| `get_channel_info` | Get channel metadata |
| `get_user_info` | Get user profile by ID |
| `list_users` | List workspace members |

All tools accept an optional `workspace` parameter. If omitted, the first
configured workspace is used.

## Token refresh

Tokens expire after approximately one year. To refresh:

```bash
osascript -e 'quit app "Slack"'
slack-mcp-setup
```

## Security

`~/.config/slack-mcp/credentials.json` is written with mode `0600`.
The `xoxc-`/`xoxd-` tokens grant full Slack access equivalent to your login.
Never share or commit this file.

## Known limitations

- **macOS only** for token extraction (`slacktokens` reads the macOS keychain)
- **No write operations** — read-only by design in v1
- **Slack must be quit during setup** — LevelDB does not support concurrent access
````

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with installation and tool reference"
```

---

### Final verification

**Run the full test suite:**

```bash
pytest tests/unit/ -v
```

Expected: all tests pass across auth, client, and all tool modules.

**Verify entry points work:**

```bash
python -c "from slack_mcp.server import main; print('server OK')"
python -c "from slack_mcp.setup import main; print('setup OK')"
```

**Verify package installs cleanly:**

```bash
pip install -e "." --dry-run
```
