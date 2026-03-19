from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from slack_mcp.auth import load_credentials
from slack_mcp.tools import channels, messages, search, users


def main() -> None:
    creds = load_credentials()

    mcp = FastMCP("slack-mcp")

    users.register(mcp, creds)
    channels.register(mcp, creds)
    messages.register(mcp, creds)
    search.register(mcp, creds)

    mcp.run()


if __name__ == "__main__":
    main()
