from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CREDENTIALS_PATH = Path.home() / ".config" / "slack-mcp" / "credentials.json"
STALE_DAYS = 300


@dataclass
class WorkspaceCredential:
    name: str
    url: str
    token: str
    d_cookie: str


@dataclass
class Credentials:
    workspaces: dict[str, WorkspaceCredential]
    extracted_at: datetime


def load_credentials(path: Path = CREDENTIALS_PATH) -> Credentials:
    if not path.exists():
        print(
            f"Error: credentials file not found at {path}\n"
            "Run 'slack-mcp-setup' to create it.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(
            f"Error: credentials file is not valid JSON: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    workspaces: dict[str, WorkspaceCredential] = {}
    for name, ws in data.get("workspaces", {}).items():
        if not ws.get("token") or not ws.get("d_cookie"):
            print(
                f"Error: workspace '{name}' is missing token or d_cookie.",
                file=sys.stderr,
            )
            sys.exit(1)
        workspaces[name] = WorkspaceCredential(
            name=name,
            url=ws.get("url", ""),
            token=ws["token"],
            d_cookie=ws["d_cookie"],
        )

    if not workspaces:
        print(
            "Error: credentials file contains no workspaces.",
            file=sys.stderr,
        )
        sys.exit(1)

    raw_ts = data.get("extracted_at", "2000-01-01T00:00:00+00:00")
    extracted_at = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))

    age_days = (datetime.now(timezone.utc) - extracted_at).days
    if age_days > STALE_DAYS:
        print(
            f"Warning: credentials are {age_days} days old (>{STALE_DAYS}). "
            "Re-run 'slack-mcp-setup' to refresh.",
            file=sys.stderr,
        )

    return Credentials(workspaces=workspaces, extracted_at=extracted_at)


def save_credentials(
    creds: Credentials,
    path: Path = CREDENTIALS_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "workspaces": {
            name: {
                "url": ws.url,
                "token": ws.token,
                "d_cookie": ws.d_cookie,
            }
            for name, ws in creds.workspaces.items()
        },
        "extracted_at": creds.extracted_at.isoformat(),
    }
    fd, tmp_str = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp = Path(tmp_str)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def get_workspace(creds: Credentials, name: str | None) -> WorkspaceCredential:
    if not name:
        return next(iter(creds.workspaces.values()))
    if name not in creds.workspaces:
        available = ", ".join(creds.workspaces.keys())
        msg = f"Workspace '{name}' not found. Available: {available}"
        raise ValueError(msg)
    return creds.workspaces[name]
