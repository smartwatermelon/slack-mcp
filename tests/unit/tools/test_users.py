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
        name="test",
        url="https://test.slack.com",
        token="xoxc-abc",
        d_cookie="xoxd-xyz",
    )


@pytest.fixture
def creds(cred):
    return Credentials(
        workspaces={"test": cred}, extracted_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def client(cred):
    return SlackClient(cred)


def test_list_workspaces(creds):
    result = _list_workspaces(creds)
    assert result == [{"name": "test", "url": "https://test.slack.com"}]


@respx.mock
def test_get_user_info(client):
    respx.post("https://slack.com/api/users.info").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "user": {
                    "id": "U123",
                    "name": "jsmith",
                    "real_name": "John Smith",
                    "profile": {
                        "display_name": "john",
                        "email": "john@example.com",
                        "title": "Engineer",
                    },
                    "tz": "America/New_York",
                },
            },
        )
    )
    result = _get_user_info(client, "U123")
    assert result["id"] == "U123"
    assert result["real_name"] == "John Smith"
    assert result["email"] == "john@example.com"
    assert result["tz"] == "America/New_York"


@respx.mock
def test_get_user_info_missing_profile_fields(client):
    respx.post("https://slack.com/api/users.info").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "user": {"id": "U1", "name": "bot", "profile": {}},
            },
        )
    )
    result = _get_user_info(client, "U1")
    assert result["email"] is None
    assert result["title"] is None


@respx.mock
def test_list_users(client):
    respx.post("https://slack.com/api/users.list").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "members": [
                    {
                        "id": "U1",
                        "name": "alice",
                        "real_name": "Alice",
                        "is_bot": False,
                        "deleted": False,
                    },
                    {
                        "id": "U2",
                        "name": "bot",
                        "real_name": "Bot",
                        "is_bot": True,
                        "deleted": False,
                    },
                ],
                "response_metadata": {"next_cursor": ""},
            },
        )
    )
    result = _list_users(client, limit=100)
    assert len(result) == 2
    assert result[0] == {
        "id": "U1",
        "name": "alice",
        "real_name": "Alice",
        "is_bot": False,
        "deleted": False,
    }
    assert result[1]["is_bot"] is True
