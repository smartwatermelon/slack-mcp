from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from slack_mcp.auth import Credentials, get_workspace
from slack_mcp.client import SlackClient


def _search_messages(client: SlackClient, query: str, count: int, sort: str) -> dict:
    data = client.get("search.messages", query=query, count=count, sort=sort)
    messages = data.get("messages", {})
    return {
        "total": messages.get("total", 0),
        "matches": [
            {
                "ts": m["ts"],
                "channel_id": m.get("channel", {}).get("id", ""),
                "channel_name": m.get("channel", {}).get("name", ""),
                "user": m.get("user", ""),
                "text": m.get("text", ""),
                "permalink": m.get("permalink", ""),
            }
            for m in messages.get("matches", [])
        ],
    }


def register(mcp: FastMCP, creds: Credentials) -> None:
    @mcp.tool()
    def search_messages(
        query: str, workspace: str = "", count: int = 20, sort: str = "score"
    ) -> dict:
        """Search messages in a Slack workspace."""
        with SlackClient(get_workspace(creds, workspace)) as client:
            return _search_messages(client, query, count, sort)
