import json
import stat
from datetime import datetime, timedelta, timezone
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
    path.write_text(
        json.dumps(
            {
                "workspaces": {
                    "test": {
                        "url": "https://test.slack.com",
                        "token": "",
                        "d_cookie": "xoxd-xyz",
                    },
                },
                "extracted_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )
    with pytest.raises(SystemExit) as exc:
        load_credentials(path)
    assert exc.value.code == 1


def test_load_empty_cookie_exits(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(
        json.dumps(
            {
                "workspaces": {
                    "test": {
                        "url": "https://test.slack.com",
                        "token": "xoxc-abc",
                        "d_cookie": "",
                    },
                },
                "extracted_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )
    with pytest.raises(SystemExit) as exc:
        load_credentials(path)
    assert exc.value.code == 1


def test_load_no_workspaces_exits(tmp_path):
    path = tmp_path / "credentials.json"
    ts = "2026-01-01T00:00:00+00:00"
    path.write_text(json.dumps({"workspaces": {}, "extracted_at": ts}))
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
    path.write_text(
        json.dumps(
            {
                "workspaces": {
                    "test": {
                        "url": "https://test.slack.com",
                        "token": "xoxc-abc",
                        "d_cookie": "xoxd-xyz",
                    },
                },
                "extracted_at": old_date,
            }
        )
    )
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
