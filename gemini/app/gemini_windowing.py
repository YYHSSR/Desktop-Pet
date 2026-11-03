"""Gemini-only foreground classification and non-activating native topmost repair."""
import ctypes
from ctypes import wintypes as w
from functools import lru_cache
import os
from pathlib import PureWindowsPath

WORKSPACE_APPS={'chatgpt.exe','claude.exe','cursor.exe','code.exe','command code.exe','explorer.exe'}
CAPTURE_APPS={'snippingtool.exe','screenclippinghost.exe','snipandsketch.exe',
              'screensketch.exe','sharex.exe','snipaste.exe','pixpin.exe'}
CAPTURE_CLASSES={'Microsoft-Windows-SnipperToolbar','Microsoft-Windows-SnipperEditor'}

def capture_overlay(info):
    """Screenshot overlays are temporary work surfaces, not fullscreen media."""
    return bool(info and (PureWindowsPath(info.get('process','')).name.casefold() in CAPTURE_APPS
                         or info.get('class') in CAPTURE_CLASSES))

def ordinary_workspace(info):
    """A maximized decorated workspace is not a fullscreen video or game."""
    if not info:return False
    name=PureWindowsPath(info.get('process','')).name.casefold()
    return capture_overlay(info) or name in WORKSPACE_APPS or bool(info.get('maximized') and info.get('style',0)&(0x00c00000|0x00040000))

class NativeWindows:
    def __init__(self):
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        u,k=self.user,self.kernel
        u.GetForegroundWindow.restype=w.HWND
        u.IsWindow.argtypes=[w.HWND];u.IsWindow.restype=w.BOOL
        u.IsWindowVisible.argtypes=[w.HWND];u.IsWindowVisible.restype=w.BOOL
        u.IsZoomed.argtypes=[w.HWND];u.IsZoomed.restype=w.BOOL
        u.GetWindowLongPtrW.argtypes=[w.HWND,ctypes.c_int];u.GetWindowLongPtrW.restype=ctypes.c_ssize_t
        u.GetWindow.argtypes=[w.HWND,w.UINT];u.GetWindow.restype=w.HWND
        u.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
        u.SetWindowPos.argtypes=[w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT]
        u.SetWindowPos.restype=w.BOOL
        k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
        k.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
        k.CloseHandle.argtypes=[w.HANDLE]

    def foreground(self):return int(self.user.GetForegroundWindow() or 0)

    def info(self,hwnd):
        if not hwnd or not self.user.IsWindow(hwnd):return None
        pid=w.DWORD();self.user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        name='';handle=self.kernel.OpenProcess(0x1000,False,pid.value)
        if handle:
            try:
                buffer=ctypes.create_unicode_buffer(32768);size=w.DWORD(len(buffer))
                if self.kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)):name=buffer.value
            finally:self.kernel.CloseHandle(handle)
        window_class=ctypes.create_unicode_buffer(256)
        self.user.GetClassNameW(hwnd,window_class,len(window_class))
        return dict(process=name,**{'class':window_class.value},style=self.user.GetWindowLongPtrW(hwnd,-16),
                    maximized=bool(self.user.IsZoomed(hwnd)))

    def topmost(self,hwnd):return bool(self.user.GetWindowLongPtrW(hwnd,-20)&8)

    def above(self,hwnd,other):
        """Check actual z-order; the TOPMOST style alone does not prove visibility."""
        if not other or hwnd==other:return True
        if not self.user.IsWindow(other):return True
        node=other
        for _ in range(4096):
            node=int(self.user.GetWindow(node,3) or 0)  # GW_HWNDPREV
            if node==hwnd:return True
            if not node:return False
        return False

    def set_topmost(self,hwnd,enabled,force=False):
        if not self.user.IsWindow(hwnd):return False
        visible=bool(self.user.IsWindowVisible(hwnd))
        if not force and visible and self.topmost(hwnd)==bool(enabled):return True
        # Preserve geometry, focus and Qt's owner order. Re-show an accidentally
        # hidden native surface without recreating its layered HWND.
        flags=1|2|0x10|0x200|0x40
        return bool(self.user.SetWindowPos(hwnd,w.HWND(-1 if enabled else -2),0,0,0,0,flags))

@lru_cache(maxsize=1)
def native_windows():
    if os.name!='nt':return None
    try:return NativeWindows()
    except (OSError,AttributeError):return None
