# slack-mcp

Ask Claude about your Slack — without setting up an OAuth app.

`slack-mcp` is a read-only [MCP](https://modelcontextprotocol.io/) server that gives
Claude Code access to your Slack workspaces using the same session tokens the Slack
desktop app uses internally. One-time setup, no app approval process, no OAuth dance.

## What you can do

Once installed, ask Claude things like:

- *"What channels am I in on the acme workspace?"*
- *"Search for messages about the Q3 launch in #general"*
- *"Summarize the last 50 messages in #engineering"*
- *"Who posted in that thread from yesterday?"*
- *"List everyone in the design workspace"*

All reads. No posting, no mutations — read-only by design.

## How it works

Slack's desktop app stores session tokens (`xoxc-`) in a local LevelDB database and
a paired cookie (`xoxd-`) in the system keychain. `slack-mcp-setup` extracts both
once and caches them in `~/.config/slack-mcp/credentials.json`. The MCP server reads
that file at startup and uses the tokens directly for every API call.

No Slack app registration required. No OAuth. Tokens are scoped to your own account.

## Requirements

- **macOS** (token extraction uses the macOS keychain; Linux not supported in v1)
- **Python 3.11** — required for both setup and the server (`slacktokens` requires `<3.12`)
- **Claude Code** — the MCP server registers as a local stdio server
- **Slack desktop app** installed (tokens are read from its local storage)

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/smartwatermelon/slack-mcp
cd slack-mcp

# 2. Create a Python 3.11 environment (required — slacktokens does not support 3.12+)
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install with setup extras (pulls in slacktokens + leveldb)
pip install -e ".[setup]"

# 4. Quit Slack, then extract tokens
#    (LevelDB does not support concurrent access — Slack must be fully quit)
osascript -e 'quit app "Slack"'
slack-mcp-setup

# 5. Register with Claude Code
claude mcp add slack-mcp -- /path/to/slack-mcp/.venv/bin/slack-mcp-server

# 6. Restart Slack
open -a Slack
```

After step 5, restart your Claude Code session. The server connects automatically at startup.

### Getting Python 3.11

If you don't have Python 3.11:

```bash
# Using Homebrew
brew install python@3.11

# Using uv
uv python install 3.11
uv venv --python 3.11 .venv
```

### Multiple workspaces

`slack-mcp-setup` extracts tokens for **all** workspaces your Slack app is signed into.
Tools default to the first workspace; pass `workspace="name"` to target a specific one:

*"List channels in the acme workspace"* — Claude will pass `workspace="acme"` automatically.

## Tools

| Tool | Parameters | Description |
|---|---|---|
| `list_workspaces` | — | List all configured workspaces |
| `list_channels` | `workspace`, `types`, `limit` | List channels (public and/or private) |
| `get_channel_history` | `channel_id`, `workspace`, `limit`, `oldest`, `latest` | Get messages from a channel |
| `get_thread` | `channel_id`, `thread_ts`, `workspace`, `limit` | Get all replies in a thread |
| `search_messages` | `query`, `workspace`, `count`, `sort` | Full-text search |
| `get_channel_info` | `channel_id`, `workspace` | Channel metadata |
| `get_user_info` | `user_id`, `workspace` | User profile by ID |
| `list_users` | `workspace`, `limit` | List workspace members |

## Token refresh

Tokens are valid for approximately one year. When they expire, re-run setup:

```bash
osascript -e 'quit app "Slack"'
slack-mcp-setup
open -a Slack
```

The server will pick up the new tokens on next restart.

## Security

- `~/.config/slack-mcp/credentials.json` is written with mode `0600` (owner read/write only)
- The `xoxc-`/`xoxd-` tokens grant full Slack access equivalent to your login
- **Never share or commit `credentials.json`** — treat it like a password
- The server is read-only: no Slack API write operations are exposed

## Troubleshooting

**"Slack is running" error during setup**
Slack must be fully quit — `Cmd+Q`, not just closing the window. Use
`osascript -e 'quit app "Slack"'` to ensure it exits.

**"Could not find a password for Slack Safe Storage" error**
Your Slack install (App Store vs. direct download) uses a different keychain account
name than `slacktokens` expects. This is handled automatically since v1.1. If you see
this on an older install, update to the latest version.

**Server shows only one workspace / wrong workspace**
Re-run `slack-mcp-setup` to refresh credentials, then restart your Claude Code session.

**Tokens expired / "invalid_auth" errors**
Re-run `slack-mcp-setup` (see Token refresh above).

## Credits

This project builds on two pieces of prior work:

- **[slacktokens](https://github.com/hraftery/slacktokens)** by Heath Raftery — extracts
  Slack session tokens and cookies from the desktop app's local storage. `slack-mcp-setup`
  uses this library directly.

- **[Retrieving and Using Slack Cookies for Authentication](https://www.papermtn.co.uk/retrieving-and-using-slack-cookies-for-authentication/)**
  by PaperMtn — the original research documenting how Slack's `xoxc-`/`xoxd-` token pair
  works and how to extract it. The technique this project depends on is explained there.

## Known limitations

- **macOS only** — `slacktokens` reads the macOS keychain; Linux support is not planned for v1
- **Python 3.11 required** — `slacktokens` does not support Python 3.12+
- **No write operations** — read-only by design in v1
- **Slack must be quit during setup** — LevelDB does not support concurrent access
