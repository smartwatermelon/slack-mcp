# SPEC: `slack-mcp` — Cookie-Authenticated Slack MCP Server

**Target runtime**: Claude Code CLI (stdio MCP transport)  
**Language**: Python 3.11+  
**Platform**: macOS (primary), Linux (secondary)

---

## Background and Constraints

The standard Slack API requires OAuth app installation, which is often blocked by workspace admins. This MCP server bypasses that by using the same authentication material the Slack desktop app uses:

- A **`d` cookie** (`xoxd-...`) — long-lived (~1 year TTL as of Dec 2025), shared across all workspaces belonging to the same Slack login. Multiple logins (different email addresses) each have their own distinct `d` cookie.
- A **session token** (`xoxc-...`) — one per workspace, derived by presenting the correct `d` cookie for that account to the workspace URL

Every API call must include **both**: `Authorization: Bearer xoxc-...` and `Cookie: d=xoxd-...`. Neither alone is sufficient.

**Critical operational constraint**: `slacktokens` reads Slack's LevelDB store, which does not support concurrent access. The Slack desktop app must be **quit** during token extraction. The MCP server itself never touches LevelDB directly at runtime — it reads from a cached credentials file written during a one-time setup step.

---

## Architecture

```
Claude Code CLI
    │  stdio (MCP protocol)
    ▼
slack-mcp server process
    │  reads at startup
    ▼
~/.config/slack-mcp/credentials.json   ← written once by setup script
    │
    ▼
Slack Web API (https://slack.com/api/*)
    with: Authorization: Bearer xoxc-...
          Cookie: d=xoxd-...
```

Token extraction (via `slacktokens`) is deliberately decoupled from the server runtime. The server is stateless with respect to credentials — it reads the cache file and fails fast if it's missing or stale.

---

## Project Structure

```
slack-mcp/
├── pyproject.toml
├── README.md
├── setup.py              # one-time token extraction CLI
└── src/
    └── slack_mcp/
        ├── __init__.py
        ├── server.py         # MCP server entrypoint
        ├── auth.py           # credentials file read/write
        ├── client.py         # Slack API HTTP client
        └── tools/
            ├── __init__.py
            ├── channels.py
            ├── messages.py
            ├── search.py
            └── users.py
```

---

## Setup Script (`setup.py`)

This is a standalone CLI script, **not** part of the running server. Run it once (with Slack quit) to populate the credentials cache.

### Behavior

1. Check that the Slack app process is not running (`pgrep -x Slack`). If it is, print an error and exit — do not attempt extraction with the app open.
2. Call `slacktokens.get_tokens_and_cookie()`.
3. `slacktokens` returns a `cookie` field and a `tokens` dict. Each token entry includes the workspace URL. For each workspace, identify which `d` cookie is correct by attempting the session state extraction: make an HTTP GET to the workspace URL with `Cookie: d=<value>` for each candidate cookie, and use whichever returns a valid `xoxc-` token. In practice, workspaces from the same login will share a `d` cookie, but workspaces from different logins will not — store the correct `d_cookie` value **per workspace** regardless.
4. Extract the `xoxc-` token from the `api_token` field in the session state JSON blob embedded in the HTML response. Use the regex `xox[a-zA-Z]-[a-zA-Z0-9-]+` against the raw response body.
4. Write the result to `~/.config/slack-mcp/credentials.json` with mode `0600`.
5. Print a summary: workspace names, token prefixes (first 12 chars + `...`), and cookie prefix.

### Credentials File Format

```json
{
  "workspaces": {
    "my-workspace": {
      "url": "https://my-workspace.slack.com",
      "token": "xoxc-...",
      "d_cookie": "xoxd-..."
    },
    "other-workspace": {
      "url": "https://other-workspace.slack.com",
      "token": "xoxc-...",
      "d_cookie": "xoxd-..."
    },
    "third-workspace-same-login-as-first": {
      "url": "https://third-workspace.slack.com",
      "token": "xoxc-...",
      "d_cookie": "xoxd-SAME_VALUE_AS_MY_WORKSPACE"
    }
  },
  "extracted_at": "2025-03-18T00:00:00Z"
}
```

`d_cookie` is stored per-workspace. Workspaces sharing the same Slack login will have identical `d_cookie` values; this is expected and correct. There is no deduplication. `credentials.json` must be in `.gitignore` and must never be committed.

---

## MCP Server (`server.py`)

### Transport

stdio only. Registered with Claude Code via:

```bash
claude mcp add slack-mcp -- python -m slack_mcp.server
```

Or if installed as a script entry point:

```bash
claude mcp add slack-mcp -- slack-mcp-server
```

### Startup

1. Read `~/.config/slack-mcp/credentials.json`. If missing, emit a clear error and exit with code 1 — do not silently degrade.
2. Validate that the file contains at least one workspace entry, and that every workspace entry has `token` and `d_cookie` fields present and non-empty.
3. Warn (stderr only) if `extracted_at` is older than 300 days, since the cookie TTL is ~1 year.
4. Start the MCP server loop.

### Default Workspace Selection

Many tools accept an optional `workspace` parameter. When omitted, the server uses the **first** workspace listed in the credentials file. The `list_workspaces` tool exists so Claude can discover available options.

---

## Slack API Client (`client.py`)

A thin wrapper around `httpx` (or `requests`) that:

- Accepts a workspace name to select the correct `xoxc-` token **and its paired `d_cookie`** from credentials
- Injects `Authorization: Bearer <token>` and `Cookie: d=<d_cookie>` on every request, using the values for the selected workspace
- Raises a typed `SlackAPIError` on non-OK responses (checking `response["ok"]`)
- Handles rate limiting: on HTTP 429, wait `Retry-After` seconds and retry once
- Does **not** implement pagination internally — individual tools handle cursor iteration

Base URL: `https://slack.com/api/`

---

## MCP Tools

Each tool corresponds to a Slack Web API method. All tools are **read-only** — no posting, no mutations. This is intentional: the goal is information access, not automation.

### `list_workspaces`

Returns the list of workspace names and URLs from the credentials file. No API call needed.

**Returns**: `{ workspaces: [{ name, url }] }`

---

### `list_channels`

Wraps `conversations.list`.

**Parameters**:

- `workspace` (string, optional) — workspace name; defaults to first
- `types` (string, optional) — comma-separated: `public_channel`, `private_channel`, `mpim`, `im`; defaults to `public_channel,private_channel`
- `limit` (int, optional, default 200) — max channels to return

**Returns**: array of `{ id, name, is_private, num_members, topic, purpose }`

Handles cursor-based pagination internally up to `limit`.

---

### `get_channel_history`

Wraps `conversations.history`.

**Parameters**:

- `channel_id` (string, required)
- `workspace` (string, optional)
- `limit` (int, optional, default 50)
- `oldest` (string, optional) — Unix timestamp; for time-bounded queries
- `latest` (string, optional) — Unix timestamp

**Returns**: array of `{ ts, user, text, thread_ts?, reply_count? }`

---

### `get_thread`

Wraps `conversations.replies`.

**Parameters**:

- `channel_id` (string, required)
- `thread_ts` (string, required) — the `ts` of the parent message
- `workspace` (string, optional)
- `limit` (int, optional, default 100)

**Returns**: array of `{ ts, user, text }`

---

### `search_messages`

Wraps `search.messages`. This endpoint requires a **user token** (`xoxc-`), which is exactly what we have.

**Parameters**:

- `query` (string, required)
- `workspace` (string, optional)
- `count` (int, optional, default 20)
- `sort` (string, optional) — `score` or `timestamp`; default `score`

**Returns**: `{ total, matches: [{ ts, channel_id, channel_name, user, text, permalink }] }`

---

### `get_user_info`

Wraps `users.info`.

**Parameters**:

- `user_id` (string, required)
- `workspace` (string, optional)

**Returns**: `{ id, name, real_name, display_name, email?, title?, tz }`

---

### `list_users`

Wraps `users.list`.

**Parameters**:

- `workspace` (string, optional)
- `limit` (int, optional, default 100)

**Returns**: array of `{ id, name, real_name, is_bot, deleted }`

---

### `get_channel_info`

Wraps `conversations.info`.

**Parameters**:

- `channel_id` (string, required)
- `workspace` (string, optional)

**Returns**: `{ id, name, is_private, topic, purpose, num_members, created }`

---

## Dependencies (`pyproject.toml`)

```toml
[project]
name = "slack-mcp"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "mcp>=1.0.0",          # MCP Python SDK
    "httpx>=0.27",          # HTTP client
    "slacktokens @ git+https://github.com/hraftery/slacktokens.git",
]

[project.scripts]
slack-mcp-server = "slack_mcp.server:main"
slack-mcp-setup  = "slack_mcp.setup:main"
```

Note: `slacktokens` itself depends on `pycookiecheat` (for cookie decryption from the macOS keychain) and `leveldb`. The setup step will prompt for your macOS login password once via the system keychain dialog — this is expected and required for cookie decryption.

---

## Credentials Security

- `~/.config/slack-mcp/credentials.json` — mode `0600`, owner only
- The `d` cookie and `xoxc-` tokens have the same privilege level as your Slack login. Treat them as passwords.
- The setup script should explicitly warn: **"These credentials grant full Slack access. Do not share credentials.json."**
- For your existing bash config pattern, add to `secrets.sh` only if you need to reference the path; do **not** export the token values as env vars — the credentials file is the source of truth.

---

## Error Handling

| Condition | Behavior |
|---|---|
| `credentials.json` missing | Fatal: exit 1, print setup instructions |
| Slack API `ok: false` | Raise `SlackAPIError(error_code)`, surface in tool response |
| HTTP 429 | Wait `Retry-After`, retry once, then raise |
| HTTP 5xx | Raise immediately, do not retry |
| Token expired / invalid | Surface `invalid_auth` error; tell user to re-run `slack-mcp-setup` |
| Slack app running during setup | Fatal: exit 1, print "Quit Slack first" |

---

## Installation Steps (for README)

```bash
# 1. Clone and install
cd ~/Developer
git clone https://github.com/yourname/slack-mcp
cd slack-mcp
pip install -e .

# 2. Extract tokens (Slack must be QUIT first)
osascript -e 'quit app "Slack"'
slack-mcp-setup

# 3. Verify
cat ~/.config/slack-mcp/credentials.json | python -m json.tool

# 4. Register with Claude Code
claude mcp add slack-mcp -- slack-mcp-server

# 5. Test
claude "list my Slack workspaces"
```

---

## Known Limitations

- **Slack must be quit during setup**. Once tokens are cached, the app can run normally.
- **Token refresh is manual**. When tokens expire (typically ~1 year for the cookie), re-run `slack-mcp-setup` with Slack quit.
- **No write operations by design**. Adding message-posting tools later is possible but intentionally excluded from v1 to limit blast radius.
- **No DM/IM history by default**. `list_channels` excludes `im` type by default; pass `types=im` explicitly.
- **Enterprise Grid**: the `search_messages` tool uses the per-workspace `xoxc-` token. For enterprise-level search across all workspaces, an `enterprise_api_token` would be needed — this is a future enhancement.
