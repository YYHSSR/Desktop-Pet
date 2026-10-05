"""Full application tray regression entry, used only by the frozen test runner."""
import json
import os
import sys
import traceback
import ctypes
from ctypes import wintypes
from pathlib import Path

# Match the shipped entry's import order before loading test helpers.
from pet.app import AppShell, main
from pet import autostart
from pet import app as app_module, tray_controller as tray_module
from PySide6.QtCore import QPoint, QTimer
import winreg

report = Path(sys.argv[1])
if sys.argv[2] != autostart.RUN_KEY:
    autostart.RUN_KEY = sys.argv[2]
assert autostart.VALUE_NAME == sys.argv[3]
events = []
cursor = wintypes.POINT()
ctypes.windll.user32.GetCursorPos(ctypes.byref(cursor))
original_start = AppShell.start


def record(kind, **values):
    events.append(dict(kind=kind, **values))
    report.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


def start(self):
    original_start(self)
    controller = self.tray_controller
    record("start", key=autostart.RUN_KEY, name=autostart.VALUE_NAME,
           platform=sys.platform, exe=sys.executable, frozen=sys.frozen,
           same_module=app_module.autostart_mod is tray_module.autostart,
           tray_name=tray_module.autostart.VALUE_NAME, tray_key=tray_module.autostart.RUN_KEY)
    original_bubble = self.win.show_bubble

    def bubble(text, **kwargs):
        record("bubble", text=text)
        return original_bubble(text, **kwargs)

    self.win.show_bubble = bubble
    step = 0

    def close():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, autostart.VALUE_NAME)
        except FileNotFoundError:
            pass
        ctypes.windll.user32.SetCursorPos(cursor.x, cursor.y)
        self.app.quit()

    def inspect():
        nonlocal step
        try:
            expected = step % 2 == 0
            controller.menu.popup(QPoint(80, 400))
            record("after", step=step, expected=expected, actual=autostart.is_enabled(),
                   checked=controller.autostart_action.isChecked(),
                   wanted=self.config.get("autostart_wanted"))
            capture = controller.menu.grab()
            capture.save(str(report.with_name(f"tray-step-{step}.png")))
            image = capture.toImage().scaled(controller.menu.size())
            rect = controller.menu.actionGeometry(controller.autostart_action)
            blue = sum(1 for y in range(rect.top(), rect.bottom() + 1)
                       for x in range(controller.menu.width() - 30, controller.menu.width() - 10)
                       if (color := image.pixelColor(x, y)).blue() > 150 and color.red() < 60)
            record("paint", step=step, blue_pixels=blue)
            assert autostart.is_enabled() == expected, "registry did not toggle"
            assert controller.autostart_action.isChecked() == expected, "tray check did not toggle"
            assert (blue > 10) == expected, "visible check did not match registry state"
            step += 1
            if step == 4:
                record("passed")
                close()
            else:
                controller.menu.close()
                QTimer.singleShot(200, click)
        except Exception:
            record("failed", traceback=traceback.format_exc())
            close()

    def click():
        try:
            menu = controller.menu
            enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            tray_handles = []

            @enum_callback
            def find_tray(hwnd, _):
                pid = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == ctypes.windll.kernel32.GetCurrentProcessId():
                    title = ctypes.create_unicode_buffer(100)
                    ctypes.windll.user32.GetWindowTextW(hwnd, title, 100)
                    if title.value == "QTrayIconMessageWindow":
                        tray_handles.append(hwnd)
                return True

            ctypes.windll.user32.EnumWindows(find_tray, 0)
            assert len(tray_handles) == 1
            ctypes.windll.user32.SetCursorPos(100, 500)
            post = ctypes.windll.user32.PostMessageW
            post.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
            assert post(tray_handles[0], 0x8000 + 101, 100 | (500 << 16), 0x007B)
            record("before", step=step, actual=autostart.is_enabled(),
                   checked=controller.autostart_action.isChecked())

            class MouseInput(ctypes.Structure):
                _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                            ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                            ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

            class InputUnion(ctypes.Union):
                _fields_ = [("mouse", MouseInput)]

            class Input(ctypes.Structure):
                _fields_ = [("type", wintypes.DWORD), ("data", InputUnion)]

            def native_click():
                ratio = menu.devicePixelRatioF()
                current = menu.actionGeometry(controller.autostart_action).center()
                bounds = wintypes.RECT()
                get_rect = ctypes.windll.user32.GetWindowRect
                get_rect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
                assert get_rect(int(menu.winId()), ctypes.byref(bounds))
                record("native", menu_id=int(menu.winId()), same_menu=menu is controller.menu,
                       x=current.x(), y=current.y(), ratio=ratio,
                       bounds=[bounds.left,bounds.top,bounds.right,bounds.bottom])
                ctypes.windll.user32.SetCursorPos(bounds.left + round(current.x() * ratio),
                                                 bounds.top + round(current.y() * ratio))
                inputs = (Input * 2)()
                inputs[0].data.mouse.dwFlags = 0x0002
                inputs[1].data.mouse.dwFlags = 0x0004
                assert ctypes.windll.user32.SendInput(2, inputs, ctypes.sizeof(Input)) == 2
                QTimer.singleShot(int(os.environ.get("PET_TRAY_TEST_DELAY", "1000")), inspect)

            QTimer.singleShot(200, native_click)
        except Exception:
            record("failed", traceback=traceback.format_exc())
            close()

    QTimer.singleShot(2000, click)


AppShell.start = start
sys.exit(main([sys.argv[0]]))
