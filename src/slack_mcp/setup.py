from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone

# Account names used by pycookiecheat to look up the Slack decryption key.
# App Store Slack uses "Slack App Store Key"; direct-download uses "Slack Key".
_SLACK_KEYCHAIN_ACCOUNTS = ["Slack App Store Key", "Slack Key"]


def _patch_pycookiecheat_for_direct_download() -> None:
    """Patch pycookiecheat to try both Slack keychain account names.

    pycookiecheat hardcodes "Slack App Store Key", which fails for
    direct-download Slack installs that use "Slack Key" instead.
    """
    try:
        import keyring
        import pycookiecheat.chrome as _pc
        from pathlib import Path
        from pycookiecheat.chrome import BrowserType
    except ImportError:
        return  # pycookiecheat not installed; slacktokens will surface its own error

    _orig = _pc.get_macos_config

    def _patched(browser: BrowserType) -> dict:
        try:
            return _orig(browser)
        except ValueError:
            if browser is not BrowserType.SLACK:
                raise
            # Try alternative keychain account names for direct-download Slack
            for account in _SLACK_KEYCHAIN_ACCOUNTS:
                key_material = keyring.get_password("Slack Safe Storage", account)
                if key_material is not None:
                    cookie_file = (
                        Path.home() / "Library/Application Support/Slack/Cookies"
                    )
                    if not cookie_file.exists():
                        cookie_file = (
                            Path.home()
                            / "Library/Containers/com.tinyspeck.slackmacgap"
                            / "Data/Library/Application Support/Slack/Cookies"
                        )
                    return {
                        "key_material": key_material,
                        "iterations": 1003,
                        "cookie_file": cookie_file,
                    }
            raise  # no account name worked; surface the original error

    _pc.get_macos_config = _patched


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
    from slack_mcp.auth import Credentials, WorkspaceCredential, save_credentials

    # pycookiecheat hardcodes "Slack App Store Key" as the keychain account name,
    # but direct-download Slack uses "Slack Key". Patch it to try both.
    _patch_pycookiecheat_for_direct_download()

    print("Extracting Slack tokens...")
    token_data = slacktokens.get_tokens_and_cookie()
    # cookie is returned as {'name': 'd', 'value': 'xoxd-...'}
    d_cookie: str = token_data.get("cookie", {}).get("value", "")
    tokens: dict = token_data.get("tokens", {})

    workspaces: dict[str, WorkspaceCredential] = {}

    for workspace_url, token_info in tokens.items():
        workspace_name = (
            workspace_url.removeprefix("https://")
            .removesuffix("/")
            .replace(".slack.com", "")
        )
        # slacktokens extracts the xoxc- token directly from LevelDB localStorage
        xoxc_token: str = token_info.get("token", "")
        if not xoxc_token:
            print(
                f"Warning: no token found for '{workspace_name}', skipping.",
                file=sys.stderr,
            )
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
