"""User journeys for settings and navigation."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication,QMenu
from desktop import DesktopPet
from settings_draft import SettingsDraft

APP=QApplication.instance() or QApplication([])


def settle(pet):
    for _ in range(4):
        APP.processEvents();pet.bubble.size_transition.complete()
    APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)


class DraftTests(unittest.TestCase):
    def test_rebase_keeps_edits_and_only_commits_changes(self):
        d=SettingsDraft(dict(a=1,b=2));d.set('a',3);d.rebase(dict(a=1,b=4))
        self.assertEqual(d.changes(),dict(a=3));self.assertEqual(d.values['b'],4)
        d.rebase(dict(a=5));self.assertEqual(d.conflicts,{'a'});self.assertEqual(d.values['a'],3)
        d.set('a',5);self.assertFalse(d.dirty);self.assertFalse(d.conflicts)
    def test_external_value_matching_draft_settles_without_conflict(self):
        d=SettingsDraft(dict(a=['one']));d.set('a',['two']);d.rebase(dict(a=['two']))
        self.assertFalse(d.dirty);self.assertFalse(d.conflicts)


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patches=[patch('enhanced.CONFIG',self.root/'settings.json'),patch('enhanced.STATE_DIR',self.root),
            patch('desktop.CONFIG',self.root/'settings.json'),patch('desktop.STATE_DIR',self.root),
            patch('desktop_settings.autostart_enabled',return_value=False),patch('desktop_settings.set_autostart')]
        for p in self.patches:p.start()
        self.startup=self.patches[-1].target.set_autostart
        self.pet=DesktopPet(monitor=False);self.pet.tick.stop();self.pet.motion_timer.stop()
        self.pet.apply_settings(dict(random_actions=False,wandering=False,card_hide_delay=120),save=False);self.pet.show();self.pet.reveal_card();settle(self.pet)
    def tearDown(self):
        self.pet.close();settle(self.pet)
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def settings(self):
        self.pet.open_settings();settle(self.pet);return self.pet.settings_dialog
    def test_external_toggle_and_cross_tab_edits_are_not_overwritten(self):
        s=self.settings();s.fields['scale'].setValue(1.2);s.fields['move_speed'].setValue(123)
        self.pet.apply_settings(dict(random_actions=True,on_top=False))
        self.assertTrue(s.fields['random_actions'].isChecked());self.assertFalse(s.fields['on_top'].isChecked())
        with patch.object(self.pet,'apply_settings',wraps=self.pet.apply_settings) as apply:
            s.apply();self.assertEqual(set(apply.call_args.args[0]),{'scale','move_speed'})
        self.assertTrue(self.pet.settings['random_actions']);self.assertFalse(self.pet.settings['on_top'])
        self.assertEqual(self.pet.settings['scale'],1.2);self.assertEqual(self.pet.settings['move_speed'],123)
        self.startup.assert_not_called();self.assertFalse(s.draft.dirty)
    def test_conflict_is_visible_and_discard_uses_current_values(self):
        s=self.settings();s.fields['scale'].setValue(1.3);self.pet.apply_settings(dict(scale=1.1))
        self.assertEqual(s.fields['scale'].value(),1.3);self.assertEqual(s.draft.conflicts,{'scale'})
        self.assertIn('外部也修改了',s.draft_status.text());s.apply();self.assertEqual(self.pet.settings['scale'],1.3)
        s.fields['scale'].setValue(1.4);self.pet.apply_settings(dict(scale=1.0));s.discard_button.click()
        self.assertEqual(s.fields['scale'].value(),1.0);self.assertFalse(s.draft.dirty)
    def test_startup_failure_does_not_block_other_settings_or_clear_draft(self):
        s=self.settings();s.startup.setChecked(True);s.fields['scale'].setValue(1.1)
        self.startup.side_effect=OSError('isolated write failure');s.apply()
        self.assertEqual(self.pet.settings['scale'],1.1);self.assertEqual(s.draft.dirty,{'startup'})
        self.assertIn('开机启动保存失败',s.status.text());self.startup.side_effect=None
        with patch.object(self.pet,'apply_settings') as apply:s.apply();apply.assert_not_called()
        self.assertFalse(s.draft.dirty);self.startup.assert_called_with(True)
    def test_failed_settings_save_restores_runtime_and_preserves_draft(self):
        s=self.settings();old=self.pet.height();s.fields['scale'].setValue(1.4)
        with patch.object(self.pet,'save_settings',side_effect=OSError('isolated save failure')):s.apply()
        self.assertEqual(self.pet.settings['scale'],1.0);self.assertEqual(self.pet.height(),old)
        self.assertEqual(s.draft.dirty,{'scale'});self.assertIn('保存失败',s.status.text())
    def test_defaults_are_per_tab_and_movement_dependencies_are_explicit(self):
        s=self.settings();s.fields['scale'].setValue(1.2);s.startup.setChecked(True);s.tabs.setCurrentIndex(1)
        s.fields['no_move'].setChecked(True);self.assertFalse(s.fields['wandering'].isEnabled())
        self.assertIn('位置已锁定',s.movement_note.text());self.assertEqual(s.fields['move_range'].value(),75)
        self.assertEqual(s.fields['status_action_interval'].decimals(),0)
        s.defaults_button.click();self.assertFalse(s.fields['no_move'].isChecked());self.assertEqual(s.fields['scale'].value(),1.2)
        self.assertTrue(s.startup.isChecked());self.startup.assert_not_called()
    def test_menus_have_separate_roles_and_share_live_settings(self):
        menu=QMenu();self.pet.build_menu(menu);self.assertEqual(len([a for a in menu.actions() if not a.isSeparator()]),7)
        tray=QMenu();self.pet.build_menu(tray,tray=True);self.assertEqual(len([a for a in tray.actions() if not a.isSeparator()]),6)
        self.assertIn('找回全部组件',[a.text() for a in tray.actions()])
        self.assertFalse([a for a in menu.findChildren(__import__('PySide6.QtGui',fromlist=['QAction']).QAction) if '穿透' in a.text() or a.objectName()=='command_through'])
        pin=next(a for a in menu.findChildren(__import__('PySide6.QtGui',fromlist=['QAction']).QAction) if a.objectName()=='command_pin')
        pin.trigger();settle(self.pet);self.assertFalse(self.pet.settings['on_top'])
        self.pet.apply_settings(dict(no_move=True));self.pet.hide();self.pet.bubble.hide()
        self.pet.build_menu(menu);walk=next(a for a in menu.actions() if a.objectName()=='command_walk')
        self.assertFalse(walk.isEnabled());self.assertIn('已锁定',walk.text())
        self.pet.execute_command('recover');self.assertTrue(self.pet.isVisible())
    def test_quota_query_is_a_silent_refresh_without_changing_preferences(self):
        self.pet.apply_settings(dict(bubble=False,quota_visible=False));current=self.pet.current
        with patch.object(self.pet,'refresh_quota') as refresh,patch('enhanced.EnhancedPet.quota') as interaction:
            self.pet.quota();refresh.assert_called_once();interaction.assert_not_called()
        self.assertIs(self.pet.current,current);self.assertFalse(self.pet.settings['bubble']);self.assertFalse(self.pet.settings['quota_visible'])
        self.assertIn(self.pet.manifest['quotaAnimation'],self.pet.action_groups()['额度回应（不刷新数据）'])
    def test_shortcut_failure_restores_state_and_gives_visible_feedback(self):
        before=self.pet.settings['on_top']
        with patch.object(self.pet,'save_settings',side_effect=OSError('isolated failure')),patch.object(self.pet,'say') as say:
            self.pet.execute_command('pin',not before)
            self.assertEqual(self.pet.settings['on_top'],before);self.assertIn('已恢复原值',say.call_args.args[0])
    def test_return_restores_origin_through_multiple_editors_and_preserves_draft(self):
        b=self.pet.bubble
        for expanded in (False,True):
            b.collapse_to_normal();settle(self.pet)
            if expanded:b.show_status(True);settle(self.pet)
            s=self.settings();s.fields['scale'].setValue(1.2);s.dismiss();settle(self.pet)
            self.assertEqual(b.panel_page,'status');self.assertEqual(b.expanded,expanded)
            self.assertEqual(s.fields['scale'].value(),1.2)
    def test_collapse_is_normal_and_queued_navigation_keeps_latest_intent(self):
        b=self.pet.bubble;b.show_status(True);settle(self.pet);self.pet.open_settings()
        b.size_transition.animation.setCurrentTime(100);native=b.geometry()
        self.pet.open_settings();b.return_to_status();self.assertEqual(b.geometry(),native);settle(self.pet)
        self.assertEqual(b.panel_page,'status');self.assertTrue(b.expanded)
        self.pet.open_settings();settle(self.pet);b.collapse_to_normal();settle(self.pet)
        self.assertEqual(b.panel_page,'status');self.assertFalse(b.expanded)
    def test_advanced_parameters_toggle_in_one_step_and_keep_drafts(self):
        s=self.settings();b=self.pet.bubble;native=b.geometry();s.tabs.setCurrentIndex(1);APP.processEvents()
        s.fields['move_speed'].setValue(123)
        for expanded in (True,False,True):
            s.advanced_button.click()
            self.assertEqual(s.advanced_card.isVisibleTo(s),expanded);self.assertEqual(b.geometry(),native)
            self.assertEqual(s.advanced_button.text(),'收起高级参数' if expanded else '展开高级参数')
        self.assertTrue(s.window().updatesEnabled());self.assertEqual(s.fields['move_speed'].value(),123);self.assertTrue(s.draft.dirty)

if __name__=='__main__':unittest.main()
