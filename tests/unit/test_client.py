import time

import httpx
import pytest
import respx

from slack_mcp.auth import WorkspaceCredential
from slack_mcp.client import SlackAPIError, SlackClient


@pytest.fixture
def cred():
    return WorkspaceCredential(
        name="test",
        url="https://test.slack.com",
        token="xoxc-abc",
        d_cookie="xoxd-xyz",
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
        return_value=httpx.Response(
            200, json={"ok": False, "error": "channel_not_found"}
        )
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
        httpx.Response(
            200,
            json={
                "ok": True,
                "channels": [{"id": "C1"}],
                "response_metadata": {"next_cursor": "cursor1"},
            },
        ),
        httpx.Response(
            200,
            json={
                "ok": True,
                "channels": [{"id": "C2"}],
                "response_metadata": {"next_cursor": ""},
            },
        ),
    ]
    result = client.get_paginated("conversations.list", "channels", 200)
    assert [r["id"] for r in result] == ["C1", "C2"]


@respx.mock
def test_paginated_respects_limit(client):
    respx.post("https://slack.com/api/conversations.list").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "channels": [{"id": f"C{i}"} for i in range(10)],
                "response_metadata": {"next_cursor": ""},
            },
        )
    )
    assert len(client.get_paginated("conversations.list", "channels", 3)) == 3
