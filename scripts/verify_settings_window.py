"""Verify the Qt settings window of a background Windows smoke process."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import sys


def settings_window_exists(pid: int) -> bool:
    # Start-Process -WindowStyle Hidden creates an invisible Qt window, which
    # Process.MainWindowHandle omits. Require its title and Qt class instead.
    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    found = False

    @callback_type
    def visit(hwnd, _):
        nonlocal found
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            title = ctypes.create_unicode_buffer(256)
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, len(title))
            user32.GetClassNameW(hwnd, class_name, len(class_name))
            if title.value == "桌宠设置" and class_name.value.startswith("Qt"):
                found = True
        return True

    user32.EnumWindows(visit, 0)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=int)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("this verifier requires Windows")
    if not settings_window_exists(args.pid):
        print("SETTINGS_WINDOW_MISSING", file=sys.stderr)
        return 1
    print("SETTINGS_QT_WINDOW_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
