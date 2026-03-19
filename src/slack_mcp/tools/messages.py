from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from slack_mcp.auth import Credentials, get_workspace
from slack_mcp.client import SlackClient


def _get_thread(
    client: SlackClient, channel_id: str, thread_ts: str, limit: int
) -> list[dict]:
    replies = client.get_paginated(
        "conversations.replies", "messages", limit, channel=channel_id, ts=thread_ts
    )
    return [
        {"ts": m["ts"], "user": m.get("user", ""), "text": m.get("text", "")}
        for m in replies
    ]


def register(mcp: FastMCP, creds: Credentials) -> None:
    @mcp.tool()
    def get_thread(
        channel_id: str, thread_ts: str, workspace: str = "", limit: int = 100
    ) -> list[dict]:
        """Get all replies in a Slack thread."""
        with SlackClient(get_workspace(creds, workspace)) as client:
            return _get_thread(client, channel_id, thread_ts, limit)
