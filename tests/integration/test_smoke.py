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
