import sys
from unittest.mock import MagicMock, patch

import pytest


def test_main_exits_if_slacktokens_missing(monkeypatch):
    """If slacktokens is not importable, exit 1 with instructions."""
    monkeypatch.setitem(sys.modules, "slacktokens", None)
    if "slack_mcp.setup" in sys.modules:
        del sys.modules["slack_mcp.setup"]
    from slack_mcp.setup import main

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_main_exits_if_slack_running(monkeypatch):
    """If Slack app is running (pgrep returns 0), exit 1."""
    mock_slacktokens = MagicMock()
    monkeypatch.setitem(sys.modules, "slacktokens", mock_slacktokens)
    if "slack_mcp.setup" in sys.modules:
        del sys.modules["slack_mcp.setup"]

    with patch("subprocess.run", return_value=MagicMock(returncode=0)):
        from slack_mcp import setup as setup_mod

        with pytest.raises(SystemExit) as exc:
            setup_mod.main()
    assert exc.value.code == 1


def test_main_extracts_tokens_from_leveldb(monkeypatch, tmp_path):
    """Tokens and cookie are read directly from slacktokens output (no HTTP needed)."""
    mock_slacktokens = MagicMock()
    mock_slacktokens.get_tokens_and_cookie.return_value = {
        "tokens": {
            "https://test-workspace.slack.com/": {
                "token": "xoxc-abc123",
                "name": "Test Workspace",
            }
        },
        "cookie": {"name": "d", "value": "xoxd-xyz789"},
    }
    monkeypatch.setitem(sys.modules, "slacktokens", mock_slacktokens)
    if "slack_mcp.setup" in sys.modules:
        del sys.modules["slack_mcp.setup"]

    creds_dir = tmp_path / ".config" / "slack-mcp"
    creds_dir.mkdir(parents=True)

    with (
        patch("subprocess.run", return_value=MagicMock(returncode=1)),
        patch("slack_mcp.setup._patch_pycookiecheat_for_direct_download"),
        patch(
            "slack_mcp.auth.CREDENTIALS_PATH",
            tmp_path / ".config" / "slack-mcp" / "credentials.json",
        ),
    ):
        from slack_mcp import setup as setup_mod

        setup_mod.main()

    from slack_mcp.auth import load_credentials

    with patch(
        "slack_mcp.auth.CREDENTIALS_PATH",
        tmp_path / ".config" / "slack-mcp" / "credentials.json",
    ):
        creds = load_credentials()

    assert "test-workspace" in creds.workspaces
    ws = creds.workspaces["test-workspace"]
    assert ws.token == "xoxc-abc123"
    assert ws.d_cookie == "xoxd-xyz789"


def test_main_exits_if_no_workspaces_extracted(monkeypatch):
    """If all workspaces are skipped (no tokens), exit 1."""
    mock_slacktokens = MagicMock()
    mock_slacktokens.get_tokens_and_cookie.return_value = {
        "tokens": {},
        "cookie": {"name": "d", "value": "xoxd-xyz"},
    }
    monkeypatch.setitem(sys.modules, "slacktokens", mock_slacktokens)
    if "slack_mcp.setup" in sys.modules:
        del sys.modules["slack_mcp.setup"]

    with (
        patch("subprocess.run", return_value=MagicMock(returncode=1)),
        patch("slack_mcp.setup._patch_pycookiecheat_for_direct_download"),
    ):
        from slack_mcp import setup as setup_mod

        with pytest.raises(SystemExit) as exc:
            setup_mod.main()
    assert exc.value.code == 1
