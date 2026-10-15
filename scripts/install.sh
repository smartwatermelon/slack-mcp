#!/usr/bin/env bash
# Install slack-mcp into ./.venv, extract tokens, register with Claude Code.
# Usage: scripts/install.sh [--refresh-tokens]
set -euo pipefail

# CDPATH='' stops cd from echoing the resolved path into REPO_DIR when the
# caller's shell exports CDPATH.
REPO_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_DIR}/.venv"
SERVER_BIN="${VENV_DIR}/bin/slack-mcp-server"
SETUP_BIN="${VENV_DIR}/bin/slack-mcp-setup"
CREDS_FILE="${HOME}/.config/slack-mcp/credentials.json"

refresh_tokens=0
for arg in "$@"; do
  case "${arg}" in
    --refresh-tokens) refresh_tokens=1 ;;
    -h | --help)
      sed -n '2,3p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown argument: ${arg}" >&2
      exit 2
      ;;
  esac
done

die() {
  echo "ERROR: $*" >&2
  exit 1
}

# 1. Preflight
[[ "${OSTYPE}" == darwin* ]] || die "macOS only (slacktokens reads the macOS keychain)."
command -v uv >/dev/null 2>&1 || die "uv not found. Install it: brew install uv"
command -v claude >/dev/null 2>&1 || die "claude CLI not found. Install Claude Code first."

# 2. Python 3.11 venv (slacktokens does not support 3.12+)
# uv-managed, not Homebrew: a brew upgrade dangles the venv's python symlink.
echo "==> Creating ${VENV_DIR} with uv-managed Python 3.11"
uv python install 3.11
uv venv --managed-python --python 3.11 --clear "${VENV_DIR}"

# 3. Install the package with setup extras
echo "==> Installing slack-mcp"
uv pip install --python "${VENV_DIR}/bin/python" -e "${REPO_DIR}[setup]"
[[ -x "${SERVER_BIN}" ]] || die "Install finished but ${SERVER_BIN} is missing."

# 4. Extract tokens (needs Slack quit; LevelDB does not allow concurrent access)
if [[ ! -f "${CREDS_FILE}" || "${refresh_tokens}" -eq 1 ]]; then
  echo "==> Extracting Slack tokens. Slack must be quit for this step."
  if pgrep -xq Slack; then
    read -r -p "Quit Slack now? [y/N] " reply
    [[ "${reply}" =~ ^[Yy]$ ]] || die "Quit Slack, then re-run this script."
    osascript -e 'quit app "Slack"'
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      pgrep -xq Slack || break
      sleep 1
    done
    pgrep -xq Slack && die "Slack is still running. Quit it with Cmd+Q and re-run."
    reopen_slack=1
  fi
  "${SETUP_BIN}"
  if [[ "${reopen_slack:-0}" -eq 1 ]]; then
    open -a Slack
  fi
else
  echo "==> Credentials found at ${CREDS_FILE}; skipping token extraction (use --refresh-tokens to redo)."
fi

# 5. Register with Claude Code (user scope, so it works in every project)
if claude mcp get slack-mcp 2>/dev/null | grep -qF "Command: ${SERVER_BIN}"; then
  echo "==> slack-mcp already registered with Claude Code at ${SERVER_BIN}"
elif claude mcp get slack-mcp >/dev/null 2>&1; then
  echo "==> slack-mcp is registered with a different command. To replace it, run:"
  echo "      claude mcp remove slack-mcp && claude mcp add -s user slack-mcp -- ${SERVER_BIN}"
else
  echo "==> Registering slack-mcp with Claude Code"
  claude mcp add -s user slack-mcp -- "${SERVER_BIN}"
fi

echo "Done. Restart your Claude Code session to load the server."
