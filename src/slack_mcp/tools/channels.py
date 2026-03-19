from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from slack_mcp.auth import Credentials, get_workspace
from slack_mcp.client import SlackClient


def _list_channels(client: SlackClient, types: str, limit: int) -> list[dict]:
    channels = client.get_paginated(
        "conversations.list", "channels", limit, types=types
    )
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
    messages = client.get_paginated(
        "conversations.history", "messages", limit, **params
    )
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
        with SlackClient(get_workspace(creds, workspace)) as client:
            return _list_channels(client, types, limit)

    @mcp.tool()
    def get_channel_history(
        channel_id: str,
        workspace: str = "",
        limit: int = 50,
        oldest: str = "",
        latest: str = "",
    ) -> list[dict]:
        """Get message history for a Slack channel."""
        with SlackClient(get_workspace(creds, workspace)) as client:
            return _get_channel_history(client, channel_id, oldest, latest, limit)

    @mcp.tool()
    def get_channel_info(channel_id: str, workspace: str = "") -> dict:
        """Get info about a Slack channel."""
        with SlackClient(get_workspace(creds, workspace)) as client:
            return _get_channel_info(client, channel_id)
