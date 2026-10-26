"""Cheap Windows directory-name notifications; no reader threads or log content."""
import ctypes
import os
from ctypes import wintypes


class DirectoryWatch:
    def __init__(self):
        self.handles={}
        self.api=None
        if os.name!='nt':return
        self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.FindFirstChangeNotificationW.argtypes=[wintypes.LPCWSTR,wintypes.BOOL,wintypes.DWORD]
        self.api.FindFirstChangeNotificationW.restype=wintypes.HANDLE
        self.api.FindNextChangeNotification.argtypes=[wintypes.HANDLE]
        self.api.FindNextChangeNotification.restype=wintypes.BOOL
        self.api.FindCloseChangeNotification.argtypes=[wintypes.HANDLE]
        self.api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        self.api.WaitForSingleObject.restype=wintypes.DWORD

    def changed(self,roots):
        if self.api is None:return False
        changed=False
        for root in roots:
            handle=self.handles.get(root)
            if handle is None:
                handle=self.api.FindFirstChangeNotificationW(str(root),True,0x1|0x2)
                if handle in (None,ctypes.c_void_p(-1).value):continue
                self.handles[root]=handle
                # Register before discovery, closing the creation/scan race.
                changed=True
            result=self.api.WaitForSingleObject(handle,0)
            if result==0:
                changed=True
                if self.api.FindNextChangeNotification(handle):continue
            elif result==258:continue
            self.api.FindCloseChangeNotification(handle)
            self.handles.pop(root,None)
            changed=True
        return changed

    def close(self):
        if self.api is None:return
        for handle in self.handles.values():self.api.FindCloseChangeNotification(handle)
        self.handles.clear()

    def __del__(self):
        try:self.close()
        except (AttributeError,OSError):pass
