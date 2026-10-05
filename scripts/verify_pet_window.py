"""Verify the packaged pet showed a real Qt window, not the bootloader dialog.

The default pet is a frameless Tool window (WS_EX_TOOLWINDOW). .NET
Process.MainWindowHandle skips those, so a healthy launch looks like
"no main window" and a PyInstaller Fatal Error dialog can look like success.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import sys


def is_pet_qt_window(class_name: str, _visible: bool) -> bool:
    """The pet's Qt top-level window, including one fullscreen auto-hide left up.

    Helper observers are Qt windows too, but their class name has no QWindow.
    """
    return class_name.startswith("Qt") and "QWindow" in class_name


def classify_process_windows(rows: list[tuple[str, str, bool]]) -> str:
    """Return ok, bootloader, or missing from (class, title, visible) rows."""
    if any(is_pet_qt_window(class_name, visible) for class_name, _title, visible in rows):
        return "ok"
    if any(class_name == "#32770" for class_name, _title, _visible in rows):
        return "bootloader"
    return "missing"


def pet_window_status(pid: int) -> str:
    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    rows: list[tuple[str, str, bool]] = []

    @callback_type
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            title = ctypes.create_unicode_buffer(512)
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, len(title))
            user32.GetClassNameW(hwnd, class_name, len(class_name))
            rows.append((class_name.value, title.value, bool(user32.IsWindowVisible(hwnd))))
        return True

    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows(visit, 0)
    return classify_process_windows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=int)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("this verifier requires Windows")
    status = pet_window_status(args.pid)
    if status == "ok":
        print("PET_QT_WINDOW_OK")
        return 0
    if status == "bootloader":
        print("BOOTLOADER_ERROR_DIALOG", file=sys.stderr)
        return 1
    print("PET_WINDOW_MISSING", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
