"""Git-backed Obsidian vault. The agent owns some folders, you own others."""
import os
import subprocess
from pathlib import Path

VAULT_PATH = Path(os.environ.get("VAULT_PATH", "/vault"))


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=VAULT_PATH, capture_output=True, text=True, check=False
    ).stdout.strip()


def ensure_clone() -> None:
    if (VAULT_PATH / ".git").exists():
        return
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", os.environ["VAULT_REPO"], str(VAULT_PATH)], check=True)


def pull() -> None:
    """Rebase onto remote before every session so your own edits always win."""
    _git("fetch", "origin")
    _git("rebase", "origin/HEAD")


def commit_and_push(message: str) -> bool:
    if not _git("status", "--porcelain"):
        return False
    _git("add", "-A")
    _git(
        "-c", f"user.name={os.environ.get('GIT_AUTHOR_NAME', 'tri-coach')}",
        "-c", f"user.email={os.environ.get('GIT_AUTHOR_EMAIL', 'coach@localhost')}",
        "commit", "-m", message,
    )
    _git("push", "origin", "HEAD")
    return True
