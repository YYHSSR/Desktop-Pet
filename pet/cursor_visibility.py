"""Read Windows cursor visibility for automatic mouse passthrough."""
import ctypes
import ctypes.wintypes
import sys

CURSOR_SHOWING = 0x00000001
CURSOR_SUPPRESSED = 0x00000002


class _CursorInfo(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_uint),
        ('flags', ctypes.c_uint),
        # ctypes.wintypes does not expose HCURSOR on every Python build;
        # HANDLE has the same pointer-sized layout.
        ('hCursor', ctypes.wintypes.HANDLE),
        ('ptScreenPos', ctypes.wintypes.POINT),
    ]


def get_cursor_visibility(user32=None) -> str:
    """Return SHOWING, HIDDEN, SUPPRESSED, or UNKNOWN without changing input."""
    if sys.platform != 'win32':
        return 'UNKNOWN'
    try:
        user32 = user32 or ctypes.windll.user32
        get_cursor_info = user32.GetCursorInfo
        get_cursor_info.argtypes = [ctypes.POINTER(_CursorInfo)]
        get_cursor_info.restype = ctypes.wintypes.BOOL
        info = _CursorInfo()
        info.cbSize = ctypes.sizeof(_CursorInfo)
        if not get_cursor_info(ctypes.byref(info)):
            return 'UNKNOWN'
        if info.flags & CURSOR_SHOWING:
            return 'SHOWING'
        if info.flags & CURSOR_SUPPRESSED:
            return 'SUPPRESSED'
        return 'HIDDEN'
    except (AttributeError, OSError, TypeError, RuntimeError):
        return 'UNKNOWN'
