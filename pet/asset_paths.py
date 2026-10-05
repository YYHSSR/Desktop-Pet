"""Resolve bundled and user-selected resources for portable installations."""
from pathlib import Path


def resolve_asset(path: str | Path | None, fallback: Path) -> Path:
    fallback = Path(fallback).expanduser()
    if path is None or not str(path).strip():
        return fallback
    candidate = Path(str(path or "")).expanduser()
    if candidate.is_absolute():
        return candidate if candidate.exists() else fallback
    bundled = Path(__file__).resolve().parents[1] / candidate
    return bundled if bundled.exists() else fallback
