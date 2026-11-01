"""Compatibility import for the shared desktop-pet implementation."""
import sys
from pathlib import Path
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from share.desktop import native_coordinates as _implementation
sys.modules[__name__] = _implementation
