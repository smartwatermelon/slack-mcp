# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`slack-mcp` is a Python MCP server that gives Claude Code read-only access to Slack workspaces using cookie-based authentication (bypassing OAuth). It uses the same `xoxc-`/`xoxd-` tokens the Slack desktop app uses internally.

**This project is currently in the spec phase.** The implementation spec is in `SPEC-slack-mcp_1.md`.

## Development Environment

Project venv lives at `.venv/`. Always use venv-qualified binaries — bare `pytest`, `python`, `pip`, and `black` are **not on PATH**.

```bash
# Install in editable mode (after creating pyproject.toml)
.venv/bin/python -m pip install -e .

# One-time token extraction (Slack app must be QUIT first)
slack-mcp-setup

# Run the MCP server manually (for debugging)
python3 -m slack_mcp.server

# Register with Claude Code
claude mcp add slack-mcp -- slack-mcp-server

# Run tests
.venv/bin/pytest

# Run a single test file
.venv/bin/pytest tests/test_client.py

# Run a single test
.venv/bin/pytest tests/test_client.py::test_rate_limiting

# Format code
.venv/bin/black .
```

For setup/install testing use a separate venv: `uv venv --python 3.11 --clear /tmp/slack-mcp-setup-venv`. Do NOT use bare `pip` — use `.venv/bin/python -m pip` or `uv` commands.

A global pre-commit config at `~/.config/pre-commit/config.yaml` runs `black` and markdownlint on every commit. If the hook auto-fixes formatting, re-add the fixed files and retry the commit.

## Project Structure (per spec)

```
slack-mcp/
├── pyproject.toml
├── setup.py              # one-time token extraction CLI
└── src/
    └── slack_mcp/
        ├── server.py         # MCP entrypoint (stdio transport only)
        ├── auth.py           # credentials file read/write (~/.config/slack-mcp/credentials.json)
        ├── client.py         # Slack API HTTP client (httpx-based)
        └── tools/
            ├── channels.py   # list_channels, get_channel_history, get_channel_info
            ├── messages.py   # get_thread
            ├── search.py     # search_messages
            └── users.py      # get_user_info, list_users
```

## Architecture

**Authentication model**: Every Slack API call requires both a workspace-specific `xoxc-` token AND its paired `xoxd-` cookie. Neither works alone. Tokens are cached in `~/.config/slack-mcp/credentials.json` (mode `0600`) after a one-time setup step.

**Credentials flow**:

1. `slack-mcp-setup` calls `slacktokens.get_tokens_and_cookie()` to read Slack's LevelDB store (requires Slack app to be quit — LevelDB doesn't support concurrent access)
2. For each workspace token, it HTTP-GETs the workspace URL with the candidate `d` cookie to extract the `xoxc-` token from embedded session state JSON
3. Results written to `~/.config/slack-mcp/credentials.json`
4. At server startup, `auth.py` reads this file — fails fast (exit 1) if missing or malformed

**Multi-workspace**: Credentials file stores all workspaces. Tools accept an optional `workspace` parameter; defaults to the first workspace in the file. Workspaces sharing the same Slack login will have identical `d_cookie` values — this is correct and expected.

**Transport**: stdio only. No HTTP server.

## Key Constraints

- **All tools are read-only** — no posting or mutations (intentional design)
- **`slacktokens` is macOS-only** (reads macOS keychain for cookie decryption). Linux support is secondary.
- **Token regex**: `xox[a-zA-Z]-[a-zA-Z0-9-]+` — used to extract `xoxc-` tokens from HTML response bodies during setup
- **Rate limiting**: On HTTP 429, wait `Retry-After` seconds and retry once, then raise
- **Pagination**: Client does NOT paginate internally — individual tools handle cursor iteration up to their `limit` parameter
- **`credentials.json` must never be committed** — add to `.gitignore` immediately

## Error Handling Conventions

| Condition | Behavior |
|---|---|
| `credentials.json` missing | Fatal exit 1 with setup instructions |
| Slack API `ok: false` | Raise `SlackAPIError(error_code)` |
| HTTP 429 | Wait `Retry-After`, retry once, then raise |
| HTTP 5xx | Raise immediately, no retry |
| `invalid_auth` | Surface error, tell user to re-run `slack-mcp-setup` |
| Slack app running during setup | Fatal exit 1, "Quit Slack first" |

## Dependencies

- `mcp>=1.0.0` — MCP Python SDK
- `httpx>=0.27` — HTTP client
- `slacktokens @ git+https://github.com/hraftery/slacktokens.git` — token extraction (pulls in `pycookiecheat`, `leveldb`)

## Security Notes

- The `xoxc-`/`xoxd-` tokens have the same privilege level as the user's Slack login — treat as passwords
- Setup script must warn: "These credentials grant full Slack access. Do not share credentials.json."
- Stale token warning: emit to stderr if `extracted_at` is older than 300 days (cookie TTL ~1 year)
- Never commit secrets, tokens, PII, or Slack credentials. Always run `git diff --cached | grep -iE 'xox[cd]-|password|secret|token'` before committing files that could contain credentials

## Git Workflow

- Never commit directly to `main` — a pre-commit hook blocks it. Always create a feature branch first: `git checkout -b claude/<name>-$(date +%s)`
- `gh pr merge <N> --squash --delete-branch` requires prior user authorization via `~/.claude/hooks/merge-lock.sh authorize <N> "reason"` — do not retry on failure, wait for the user to approve
