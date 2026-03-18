from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from slack_mcp.auth import Credentials, get_workspace
from slack_mcp.client import SlackClient


def _list_workspaces(creds: Credentials) -> list[dict]:
    return [{"name": name, "url": ws.url} for name, ws in creds.workspaces.items()]


def _get_user_info(client: SlackClient, user_id: str) -> dict:
    data = client.get("users.info", user=user_id)
    u = data["user"]
    return {
        "id": u["id"],
        "name": u["name"],
        "real_name": u.get("real_name", ""),
        "display_name": u.get("profile", {}).get("display_name", ""),
        "email": u.get("profile", {}).get("email"),
        "title": u.get("profile", {}).get("title"),
        "tz": u.get("tz", ""),
    }


def _list_users(client: SlackClient, limit: int) -> list[dict]:
    members = client.get_paginated("users.list", "members", limit)
    return [
        {
            "id": u["id"],
            "name": u["name"],
            "real_name": u.get("real_name", ""),
            "is_bot": u.get("is_bot", False),
            "deleted": u.get("deleted", False),
        }
        for u in members
    ]


def register(mcp: FastMCP, creds: Credentials) -> None:
    @mcp.tool()
    def list_workspaces() -> list[dict]:
        """List all configured Slack workspaces."""
        return _list_workspaces(creds)

    @mcp.tool()
    def get_user_info(user_id: str, workspace: str = "") -> dict:
        """Get info about a Slack user by ID."""
        return _get_user_info(SlackClient(get_workspace(creds, workspace)), user_id)

    @mcp.tool()
    def list_users(workspace: str = "", limit: int = 100) -> list[dict]:
        """List users in a Slack workspace."""
        return _list_users(SlackClient(get_workspace(creds, workspace)), limit)
