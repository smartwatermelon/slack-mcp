import httpx
import pytest
import respx

from slack_mcp.auth import WorkspaceCredential
from slack_mcp.client import SlackClient
from slack_mcp.tools.messages import _get_thread


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
def test_get_thread(client):
    respx.post("https://slack.com/api/conversations.replies").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "messages": [
                    {"ts": "100.000", "user": "U1", "text": "parent"},
                    {"ts": "100.001", "user": "U2", "text": "reply"},
                ],
                "response_metadata": {"next_cursor": ""},
            },
        )
    )
    result = _get_thread(client, channel_id="C1", thread_ts="100.000", limit=100)
    assert len(result) == 2
    assert result[0] == {"ts": "100.000", "user": "U1", "text": "parent"}
    assert result[1]["text"] == "reply"


@respx.mock
def test_get_thread_missing_user(client):
    respx.post("https://slack.com/api/conversations.replies").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "messages": [{"ts": "100.000", "text": "bot message"}],
                "response_metadata": {"next_cursor": ""},
            },
        )
    )
    result = _get_thread(client, channel_id="C1", thread_ts="100.000", limit=100)
    assert result[0]["user"] == ""
