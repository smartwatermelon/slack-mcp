# slack-mcp

A read-only Slack MCP server for Claude Code, using cookie-based authentication.
No OAuth app required.

## How it works

Uses the same `xoxc-`/`xoxd-` tokens the Slack desktop app uses internally.
Tokens are extracted once from the local Slack installation and cached in
`~/.config/slack-mcp/credentials.json`.

## Installation

```bash
# 1. Clone and install
git clone https://github.com/smartwatermelon/slack-mcp
cd slack-mcp
pip install -e ".[setup]"   # includes slacktokens

# 2. Extract tokens (Slack must be QUIT first)
osascript -e 'quit app "Slack"'
slack-mcp-setup

# 3. Register with Claude Code
claude mcp add slack-mcp -- slack-mcp-server
```

## Tools

| Tool | Description |
|---|---|
| `list_workspaces` | List all configured workspaces |
| `list_channels` | List channels (public and/or private) |
| `get_channel_history` | Get recent messages from a channel |
| `get_thread` | Get all replies in a thread |
| `search_messages` | Full-text search across a workspace |
| `get_channel_info` | Get channel metadata |
| `get_user_info` | Get user profile by ID |
| `list_users` | List workspace members |

All tools accept an optional `workspace` parameter. If omitted, the first
configured workspace is used.

## Token refresh

Tokens expire after approximately one year. To refresh:

```bash
osascript -e 'quit app "Slack"'
slack-mcp-setup
```

## Security

`~/.config/slack-mcp/credentials.json` is written with mode `0600`.
The `xoxc-`/`xoxd-` tokens grant full Slack access equivalent to your login.
Never share or commit this file.

## Known limitations

- **macOS only** for token extraction (`slacktokens` reads the macOS keychain)
- **No write operations** — read-only by design in v1
- **Slack must be quit during setup** — LevelDB does not support concurrent access
