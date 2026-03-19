from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone

TOKEN_RE = re.compile(r"xoxc-[a-zA-Z0-9-]+")


def main() -> None:
    # Step 1: Verify slacktokens is installed
    try:
        import slacktokens
    except ImportError:
        print(
            "Error: slacktokens is not installed.\n"
            "Install it with:\n"
            "  pip install git+https://github.com/hraftery/slacktokens.git",
            file=sys.stderr,
        )
        sys.exit(1)

    # Step 2: Verify Slack is not running
    result = subprocess.run(["pgrep", "-x", "Slack"], capture_output=True)
    if result.returncode == 0:
        print(
            "Error: Slack is running. Quit Slack first, then re-run 'slack-mcp-setup'.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Step 3: Extract tokens
    import httpx

    from slack_mcp.auth import Credentials, WorkspaceCredential, save_credentials

    print("Extracting Slack tokens...")
    token_data = slacktokens.get_tokens_and_cookie()
    cookie = token_data.get("cookie", "")
    tokens: dict = token_data.get("tokens", {})

    workspaces: dict[str, WorkspaceCredential] = {}

    for workspace_url, token_info in tokens.items():
        workspace_name = (
            workspace_url.removeprefix("https://")
            .removesuffix("/")
            .replace(".slack.com", "")
        )
        d_cookie = token_info.get("d_cookie") or cookie

        try:
            resp = httpx.get(
                workspace_url,
                headers={"Cookie": f"d={d_cookie}"},
                follow_redirects=True,
            )
            match = TOKEN_RE.search(resp.text)
            if not match:
                print(
                    f"Warning: could not extract xoxc- token for"
                    f" '{workspace_name}', skipping.",
                    file=sys.stderr,
                )
                continue
            xoxc_token = match.group(0)
        except Exception as e:
            print(f"Warning: failed to fetch '{workspace_url}': {e}", file=sys.stderr)
            continue

        workspaces[workspace_name] = WorkspaceCredential(
            name=workspace_name,
            url=workspace_url,
            token=xoxc_token,
            d_cookie=d_cookie,
        )

    if not workspaces:
        print(
            "Error: no workspaces extracted. Ensure Slack is quit and try again.",
            file=sys.stderr,
        )
        sys.exit(1)

    creds = Credentials(workspaces=workspaces, extracted_at=datetime.now(timezone.utc))
    save_credentials(creds)

    print(f"\nExtracted {len(workspaces)} workspace(s):")
    for name, ws in workspaces.items():
        print(f"  {name}:")
        print(f"    token  = {ws.token[:12]}...")
        print(f"    cookie = {ws.d_cookie[:12]}...")

    print(
        "\n\u26a0\ufe0f  These credentials grant full Slack access. "
        "Do not share credentials.json."
    )


if __name__ == "__main__":
    main()
