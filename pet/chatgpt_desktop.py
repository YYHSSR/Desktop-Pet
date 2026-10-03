"""Locate read-only local ChatGPT Work/Codex session logs."""
import os
from pathlib import Path


def codex_sessions_dir() -> Path:
    root = os.environ.get("CODEX_HOME", "").strip()
    return (Path(root).expanduser() if root else Path.home() / ".codex") / "sessions"
