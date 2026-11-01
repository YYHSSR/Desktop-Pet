"""Locate immutable resources in source, onedir and onefile builds."""
import sys
from pathlib import Path


def resource_root():
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def asset_file(relative):
    """New role layout first; older frozen resource layouts remain readable."""
    root = resource_root()
    current = root/'assets'/relative
    legacy = root/'app'/relative
    return current if current.is_file() or not legacy.is_file() else legacy
