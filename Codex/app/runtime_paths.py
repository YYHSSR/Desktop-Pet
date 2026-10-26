"""Locate immutable resources in source, onedir and onefile builds."""
import sys
from pathlib import Path


def resource_root():
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]
