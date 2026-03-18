import httpx
import pytest
import respx

from slack_mcp.auth import WorkspaceCredential
from slack_mcp.client import SlackClient
from slack_mcp.tools.channels import (
    _get_channel_history,
    _get_channel_info,
    _list_channels,
)


@pytest.fixture
def client():
    return SlackClient(
        WorkspaceCredential(
            name="test",
            url="https://test.slack.com",
            token="xoxc-abc",
            d_cookie="xoxd-xyz",
        )
    )


@respx.mock
def test_list_channels(client):
    respx.post("https://slack.com/api/conversations.list").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "channels": [
                    {
                        "id": "C1",
                        "name": "general",
                        "is_private": False,
                        "num_members": 42,
                        "topic": {"value": "Company news"},
                        "purpose": {"value": "General chat"},
                    },
                ],
                "response_metadata": {"next_cursor": ""},
            },
        )
    )
    result = _list_channels(client, types="public_channel,private_channel", limit=200)
    assert result == [
        {
            "id": "C1",
            "name": "general",
            "is_private": False,
            "num_members": 42,
            "topic": "Company news",
            "purpose": "General chat",
        }
    ]


@respx.mock
def test_list_channels_missing_optional_fields(client):
    respx.post("https://slack.com/api/conversations.list").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "channels": [{"id": "C2", "name": "secret", "is_private": True}],
                "response_metadata": {"next_cursor": ""},
            },
        )
    )
    result = _list_channels(client, types="private_channel", limit=200)
    assert result[0]["num_members"] == 0
    assert result[0]["topic"] == ""


@respx.mock
def test_get_channel_history(client):
    respx.post("https://slack.com/api/conversations.history").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "messages": [
                    {
                        "ts": "123.456",
                        "user": "U1",
                        "text": "hello",
                        "thread_ts": "123.456",
                        "reply_count": 2,
                    },
                    {"ts": "124.000", "user": "U2", "text": "world"},
                ],
                "response_metadata": {"next_cursor": ""},
            },
        )
    )
    result = _get_channel_history(
        client, channel_id="C1", oldest="", latest="", limit=50
    )
    assert len(result) == 2
    assert result[0]["reply_count"] == 2
    assert result[1]["thread_ts"] is None


@respx.mock
def test_get_channel_info(client):
    respx.post("https://slack.com/api/conversations.info").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "channel": {
                    "id": "C1",
                    "name": "general",
                    "is_private": False,
                    "topic": {"value": "News"},
                    "purpose": {"value": "Chat"},
                    "num_members": 10,
                    "created": 1700000000,
                },
            },
        )
    )
    result = _get_channel_info(client, "C1")
    assert result["id"] == "C1"
    assert result["num_members"] == 10
    assert result["created"] == 1700000000
