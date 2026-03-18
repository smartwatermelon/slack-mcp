import sys
from unittest.mock import MagicMock, patch

import pytest


def test_main_exits_if_slacktokens_missing(monkeypatch):
    """If slacktokens is not importable, exit 1 with instructions."""
    # Remove slacktokens from sys.modules if present, and make it unimportable
    monkeypatch.setitem(sys.modules, "slacktokens", None)
    # Re-import to get a fresh module state
    if "slack_mcp.setup" in sys.modules:
        del sys.modules["slack_mcp.setup"]
    from slack_mcp.setup import main

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_main_exits_if_slack_running(monkeypatch):
    """If Slack app is running (pgrep returns 0), exit 1."""
    # Make slacktokens importable as a mock
    mock_slacktokens = MagicMock()
    monkeypatch.setitem(sys.modules, "slacktokens", mock_slacktokens)
    if "slack_mcp.setup" in sys.modules:
        del sys.modules["slack_mcp.setup"]

    with patch("subprocess.run", return_value=MagicMock(returncode=0)):
        from slack_mcp import setup as setup_mod

        with pytest.raises(SystemExit) as exc:
            setup_mod.main()
    assert exc.value.code == 1
