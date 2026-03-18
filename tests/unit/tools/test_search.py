import httpx
import pytest
import respx

from slack_mcp.auth import WorkspaceCredential
from slack_mcp.client import SlackClient
from slack_mcp.tools.search import _search_messages


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
def test_search_messages(client):
    respx.post("https://slack.com/api/search.messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "messages": {
                    "total": 1,
                    "matches": [
                        {
                            "ts": "123.456",
                            "channel": {"id": "C1", "name": "general"},
                            "user": "U1",
                            "text": "hello world",
                            "permalink": "https://slack.com/archives/C1/p123456",
                        }
                    ],
                },
            },
        )
    )
    result = _search_messages(client, query="hello", count=20, sort="score")
    assert result["total"] == 1
    assert result["matches"][0]["channel_id"] == "C1"
    assert result["matches"][0]["permalink"] == "https://slack.com/archives/C1/p123456"


@respx.mock
def test_search_messages_empty(client):
    respx.post("https://slack.com/api/search.messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "messages": {"total": 0, "matches": []},
            },
        )
    )
    result = _search_messages(client, query="zzznomatch", count=20, sort="score")
    assert result["total"] == 0
    assert result["matches"] == []
