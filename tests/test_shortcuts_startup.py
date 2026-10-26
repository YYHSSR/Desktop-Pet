"""User-facing shortcut routing and companion launch lifecycle regressions."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication,QToolButton
from desktop import DesktopPet
from desktop_core import normalized
import codex_startup as cs
from quick_actions import website_url

APP=QApplication.instance() or QApplication([])
def settle(pet):
    for _ in range(4):APP.processEvents();pet.bubble.size_transition.complete()
    APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)

class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patches=[patch('enhanced.CONFIG',self.root/'settings.json'),patch('enhanced.STATE_DIR',self.root),
            patch('desktop.CONFIG',self.root/'settings.json'),patch('desktop.STATE_DIR',self.root),
            patch('desktop_settings.autostart_enabled',return_value=False),patch('codex_startup.enabled',return_value=False)]
        for p in self.patches:p.start()
        self.pet=DesktopPet(monitor=False);self.pet.tick.stop();self.pet.motion_timer.stop()
        self.pet.apply_settings(dict(random_actions=False,wandering=False),save=False)
        self.pet.show();self.pet.reveal_card();settle(self.pet)
    def tearDown(self):
        self.pet.close();settle(self.pet)
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def web_button(self):
        return next(w for w in self.pet.bubble.findChildren(QToolButton,'bubble_web') if w.isVisible())
    def test_default_gpt_uses_browser_without_expanding_or_changing_size(self):
        b=self.pet.bubble;size=b.size();button=self.web_button()
        self.assertEqual([w.objectName() for w in b._header_actions][2],'bubble_web')
        with patch('desktop.QDesktopServices.openUrl',return_value=True) as opened:button.click()
        self.assertEqual(opened.call_args.args[0].toString(),'https://chatgpt.com/')
        self.assertFalse(b.expanded);self.assertEqual(b.size(),size)
        self.assertFalse(b.findChildren(QToolButton,'bubble_compact'))
    def test_browser_failure_is_reported_on_the_card(self):
        with patch('desktop.QDesktopServices.openUrl',return_value=False):self.web_button().click()
        self.assertIn('浏览器',self.pet.bubble.status)
    def test_settings_draft_validates_url_and_reloads_saved_choice(self):
        self.pet.open_settings();settle(self.pet);s=self.pet.settings_dialog
        s.web_target.setCurrentIndex(s.web_target.findData('website'));s.website.setText('file:///C:/Windows/cmd.exe');s.apply()
        self.assertEqual(self.pet.settings['web_button'],'chatgpt');self.assertIn('失败',s.status.text())
        s.website.setText('https://example.org/a?lang=zh');s.apply()
        self.assertFalse(s.draft.dirty);self.assertEqual(self.pet.settings['web_button'],'website')
        self.pet.bubble.return_to_status();settle(self.pet)
        with patch('desktop.QDesktopServices.openUrl',return_value=True) as opened:self.web_button().click()
        self.assertEqual(opened.call_args.args[0].toString(),'https://example.org/a?lang=zh')
        self.assertEqual(json.loads((self.root/'settings.json').read_text(encoding='utf-8'))['web_button'],'website')
    def test_codex_link_is_separate_draft_and_failed_registration_stays_dirty(self):
        self.pet.open_settings();settle(self.pet);s=self.pet.settings_dialog
        s.codex_startup.setChecked(True)
        with patch('codex_startup.configure',side_effect=OSError('denied')):s.apply()
        self.assertIn('codex_startup',s.draft.dirty)
        with patch('codex_startup.configure') as configured:s.apply();configured.assert_called_once_with(True)
        self.assertNotIn('codex_startup',s.draft.dirty);self.assertNotIn('codex_startup',self.pet.settings)

class StartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,LOCALAPPDATA=str(self.root/'local'),APPDATA=str(self.root/'roaming'));self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def test_url_and_old_configuration_fallbacks(self):
        for bad in ('javascript:alert(1)','file:///x','cmd.exe','https://name:pw@host','https://host:bad','https://host/\ncmd'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):website_url(bad)
        self.assertEqual(normalized({'web_button':'unknown'})['web_button'],'chatgpt')
        self.assertEqual(normalized({'web_button':'website','web_url':'file:///x'})['web_button'],'chatgpt')
        old=normalized({'capsule_action':'website','capsule_website':'https://example.org/','bubble_mode':'mini'})
        self.assertEqual((old['web_button'],old['web_url']),('website','https://example.org/'))
        for key in ('capsule_action','capsule_website','bubble_mode'):self.assertNotIn(key,old)
    def test_gate_does_not_relaunch_after_pet_quit_or_unknown_presence(self):
        gate=cs.LaunchGate();first={(10,123.)}
        self.assertTrue(gate.observe(first))
        for value in (first,None,first,set(),first):self.assertFalse(gate.observe(value))
        self.assertFalse(gate.observe(first|{(20,234.)}));self.assertFalse(gate.observe({(20,234.)}))
        self.assertFalse(gate.observe(set()));self.assertFalse(gate.observe(set()))
        self.assertTrue(gate.observe({(30,345.)}));self.assertFalse(gate.observe({(30,345.)}))
        self.assertTrue(gate.observe({(40,456.)})) # restart entirely between samples
    def test_desktop_detector_excludes_cli_chatgpt_only_and_helpers(self):
        def process(pid,path,args):
            p=Mock(pid=pid,info={'name':Path(path).name});p.exe.return_value=path;p.cmdline.return_value=args;p.create_time.return_value=100.;return p
        gui=str(self.root/'OpenAI.Codex_123/app/ChatGPT.exe');cli=str(self.root/'OpenAI/Codex/bin/123/codex.exe');chat=str(self.root/'OpenAI.ChatGPT_123/ChatGPT.exe')
        values=[process(1,gui,[gui]),process(2,gui,[gui,'--type=renderer']),process(3,cli,[cli]),process(4,chat,[chat])]
        with patch.object(cs.psutil,'process_iter',return_value=values):self.assertEqual(cs.desktop_sessions(),{(1,100.)})
        values[0].exe.side_effect=cs.psutil.AccessDenied(1)
        with patch.object(cs.psutil,'process_iter',return_value=values):self.assertIsNone(cs.desktop_sessions())
    def test_enable_disable_registration_and_failed_spawn_are_reversible(self):
        exe=self.root/'program/DesktopPet.exe'
        with patch.object(cs,'spawn') as launch:
            cs.configure(True,exe);self.assertTrue(cs.enabled());self.assertIn('--watch-codex',cs.startup_path().read_text(encoding='utf-16'))
            launch.assert_called_once_with([str(exe),'--watch-codex'])
            cs.configure(False,exe);self.assertFalse(cs.enabled());self.assertFalse(cs.startup_path().exists())
        before=cs.preference_path().read_bytes()
        with patch.object(cs,'spawn',side_effect=OSError('denied')),self.assertRaises(OSError):cs.configure(True,exe)
        self.assertEqual(cs.preference_path().read_bytes(),before);self.assertFalse(cs.startup_path().exists())
    def test_corrupt_preference_does_not_crash_startup_or_enable_it(self):
        cs.atomic(cs.preference_path(),['enabled'])
        self.assertFalse(cs.enabled())

if __name__=='__main__':unittest.main()
