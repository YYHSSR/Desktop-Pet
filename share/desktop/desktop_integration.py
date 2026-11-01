"""Small Windows integrations for the companions: start at login, and step aside
for fullscreen programs. Both degrade to no-ops away from Windows."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys

WINDOWS = sys.platform == 'win32'
SHELL_CLASSES = {'Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'}


# ---- start at login: one hidden-launch script in the user's Startup folder ----
def startup_folder():
    if not WINDOWS:
        return None
    buffer = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 7, None, 0, buffer) != 0:  # CSIDL_STARTUP
        return None
    return Path(buffer.value)


def startup_entry(name):
    folder = startup_folder()
    return folder/f'{name}.vbs' if folder else None


def launch_command(entry_script):
    """The program to start: the frozen exe itself, or pythonw with the entry script."""
    if getattr(sys, 'frozen', False):
        return [sys.executable]
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    return [str(pythonw if pythonw.is_file() else sys.executable), str(entry_script)]


def autostart_enabled(name):
    entry = startup_entry(name)
    return bool(entry and entry.is_file())


def set_autostart(name, enabled, command, cwd):
    entry = startup_entry(name)
    if entry is None:
        raise OSError('找不到 Windows 启动文件夹')
    if not enabled:
        if entry.is_file():
            entry.unlink()
        return
    line = ' '.join('"'+part+'"' for part in command).replace('"', '""')
    script = ('Option Explicit\nDim shell\nSet shell = CreateObject("WScript.Shell")\n'
              f'shell.CurrentDirectory = "{cwd}"\nshell.Run "{line}", 0, False\n')
    entry.parent.mkdir(parents=True, exist_ok=True)
    temporary = entry.with_suffix('.tmp')
    temporary.write_text(script, encoding='utf-16')
    os.replace(temporary, entry)


# ---- is a program running (by executable name) ----
class _ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD),
                ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD),
                ('szExeFile', wintypes.WCHAR*260)]


def running_executables():
    """Lower-case executable names of all processes; empty away from Windows."""
    if not WINDOWS:
        return set()
    kernel = ctypes.windll.kernel32
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return set()
    names = set()
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            names.add(entry.szExeFile.lower())
            ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return names


def is_running(*executables):
    names = running_executables()
    return any(name.lower() in names for name in executables)


# ---- fullscreen detection ----
class _MonitorInfo(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


def _user32():
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = wintypes.HWND
    user.MonitorFromWindow.restype = wintypes.HANDLE
    user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MonitorInfo)]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    return user


def monitor_of(hwnd):
    if not WINDOWS or not hwnd:
        return None
    return _user32().MonitorFromWindow(wintypes.HWND(int(hwnd)), 2) or None  # MONITOR_DEFAULTTONEAREST


def fullscreen_foreground():
    """(hwnd, monitor) of another program covering its whole monitor, else None."""
    if not WINDOWS:
        return None
    try:
        user = _user32()
        hwnd = user.GetForegroundWindow()
        if not hwnd or not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd):
            return None
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return None
        name = ctypes.create_unicode_buffer(64)
        user.GetClassNameW(hwnd, name, 64)
        if name.value in SHELL_CLASSES:
            return None
        rect = wintypes.RECT()
        if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        monitor = user.MonitorFromWindow(hwnd, 2)
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(_MonitorInfo)
        if not monitor or not user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        screen = info.rcMonitor
        if (rect.left <= screen.left and rect.top <= screen.top and
                rect.right >= screen.right and rect.bottom >= screen.bottom):
            return int(hwnd), monitor
    except (OSError, AttributeError, ValueError):
        return None
    return None
