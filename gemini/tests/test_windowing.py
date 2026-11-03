"""Normal desktop workspaces must not hide a pinned Gemini character."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import test_companion as fixtures
from gemini_windowing import ordinary_workspace,capture_overlay,NativeWindows
from share.desktop import desktop_integration

class WorkspaceClassificationTests(unittest.TestCase):
    def test_capture_tools_are_not_fullscreen_media(self):
        for name in ('SnippingTool.exe','ScreenClippingHost.exe','Snipaste.exe'):
            info=dict(process=name,style=0x80000000,maximized=False)
            self.assertTrue(capture_overlay(info));self.assertTrue(ordinary_workspace(info))
        self.assertTrue(capture_overlay({'class':'Microsoft-Windows-SnipperToolbar'}))
        self.assertFalse(capture_overlay({'process':'game.exe'}))

    def test_z_order_is_checked_even_when_topmost_style_is_set(self):
        api=NativeWindows.__new__(NativeWindows)
        previous={400:300,300:200,200:0}
        api.user=SimpleNamespace(IsWindow=lambda hwnd:True,GetWindow=lambda hwnd,command:previous.get(hwnd,0))
        self.assertTrue(api.above(200,400))
        self.assertFalse(api.above(400,200))

    def test_chatgpt_and_claude_desktop_apps_do_not_trigger_fullscreen_hiding(self):
        for name in ('C:/Apps/ChatGPT.exe','C:/Apps/Claude.exe','ChatGPT.EXE'):
            self.assertTrue(ordinary_workspace(dict(process=name,style=0x80000000,maximized=False)))

    def test_maximized_decorated_window_is_not_a_fullscreen_video(self):
        self.assertTrue(ordinary_workspace(dict(process='browser.exe',style=0x00c40000,maximized=True)))
        self.assertFalse(ordinary_workspace(dict(process='game.exe',style=0x80000000,maximized=False)))
        self.assertFalse(ordinary_workspace(None))

    def test_native_topmost_repair_preserves_focus_geometry_and_owner_order(self):
        calls=[]
        api=NativeWindows.__new__(NativeWindows)
        api.user=SimpleNamespace(IsWindow=lambda hwnd:True,IsWindowVisible=lambda hwnd:False,
                                 GetWindowLongPtrW=lambda *args:0,
                                 SetWindowPos=lambda *args:calls.append(args) or True)
        self.assertTrue(api.set_topmost(123,True))
        flags=calls[0][-1]
        self.assertTrue(flags&0x10);self.assertTrue(flags&1);self.assertTrue(flags&2)
        self.assertTrue(flags&0x200);self.assertTrue(flags&0x40)

class GeminiFrontTests(unittest.TestCase):
    setUp=fixtures.AppTests.setUp
    tearDown=fixtures.AppTests.tearDown
    def fake_api(self,process='ChatGPT.exe',maximized=True):
        return SimpleNamespace(foreground=lambda:4242,
            info=lambda hwnd:dict(process=process,style=0x00c40000 if maximized else 0x80000000,maximized=maximized),
            above=lambda *args:True,
            set_topmost=lambda *args:True)

    def test_screenshot_overlay_keeps_the_action_and_drag_visible(self):
        c=self.companion;monitor=desktop_integration.monitor_of(int(c.sprite.winId()))
        c.sprite.dragging=True;c.drag_started();serial=c.sprite.serial
        with patch('companion.native_windows',return_value=self.fake_api('ScreenClippingHost.exe',False)),patch.object(desktop_integration,'fullscreen_foreground',return_value=(4242,monitor)):
            c.poll()
            self.assertFalse(c.yielded);self.assertTrue(c.sprite.isVisible())
            self.assertTrue(c._capture_active);self.assertEqual(c.sprite.serial,serial)
        with patch('companion.native_windows',return_value=self.fake_api()),patch.object(desktop_integration,'fullscreen_foreground',return_value=None):
            c.poll();self.assertFalse(c._capture_active);self.assertTrue(c.sprite.isVisible())

    def test_same_foreground_is_repaired_after_capture_reorders_windows(self):
        c=self.companion;calls=[];api=self.fake_api()
        c._last_foreground=4242
        api.above=lambda *args:False
        api.set_topmost=lambda hwnd,enabled,force:calls.append((enabled,force)) or True
        with patch('companion.native_windows',return_value=api),patch.object(desktop_integration,'fullscreen_foreground',return_value=None):
            c.poll()
        self.assertTrue(any(enabled and force for enabled,force in calls))

    def test_capture_editor_restores_topmost_after_its_fullscreen_overlay_closes(self):
        c=self.companion;calls=[];api=self.fake_api('SnippingTool.exe',False)
        c._capture_active=True;c._last_foreground=4242
        api.above=lambda *args:False
        api.set_topmost=lambda hwnd,enabled,force:calls.append((enabled,force)) or True
        with patch('companion.native_windows',return_value=api),patch.object(desktop_integration,'fullscreen_foreground',return_value=None):
            c.poll()
        self.assertFalse(c._capture_active)
        self.assertTrue(any(enabled and force for enabled,force in calls))

    def test_covered_by_a_maximized_workspace_stays_visible_and_pinned(self):
        c=self.companion;monitor=desktop_integration.monitor_of(int(c.sprite.winId()))
        with patch('companion.native_windows',return_value=self.fake_api()),patch.object(desktop_integration,'fullscreen_foreground',return_value=(4242,monitor)):
            c.poll()
            self.assertFalse(c.yielded);self.assertTrue(c.sprite.isVisible())

    def test_tray_recovery_survives_the_next_fullscreen_poll(self):
        c=self.companion;monitor=desktop_integration.monitor_of(int(c.sprite.winId()))
        with patch('companion.native_windows',return_value=self.fake_api()),patch.object(desktop_integration,'fullscreen_foreground',return_value=(4242,monitor)):
            c.yielded=True;c.sprite.hide()
            c.recover();c.poll()
            self.assertFalse(c.yielded);self.assertTrue(c.sprite.isVisible())
            self.assertFalse(c.sprite.player.stop.is_set())

    def test_true_borderless_fullscreen_can_still_yield_and_recover(self):
        c=self.companion;monitor=desktop_integration.monitor_of(int(c.sprite.winId()))
        with patch('companion.native_windows',return_value=self.fake_api('game.exe',False)),patch.object(desktop_integration,'fullscreen_foreground',return_value=(4242,monitor)):
            c.poll();self.assertTrue(c.yielded);self.assertFalse(c.sprite.isVisible())
        c.poll();self.assertFalse(c.yielded);self.assertTrue(c.sprite.isVisible())

if __name__=='__main__':unittest.main()
