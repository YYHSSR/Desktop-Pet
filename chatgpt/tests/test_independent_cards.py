import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint,Qt,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from desktop import DesktopPet
from desktop_core import normalized

APP=QApplication.instance() or QApplication([])

class IndependentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.patches=[patch(module+'.'+key,root/('settings.json' if key=='CONFIG' else '')) for module in ('enhanced','desktop') for key in ('CONFIG','STATE_DIR')]
        for p in self.patches:p.start()
        self.pet=DesktopPet(monitor=False);self.pet.apply_settings(dict(wandering=False,random_actions=False));self.pet.show();APP.processEvents()
    def tearDown(self):
        self.pet.close();APP.processEvents()
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def finish(self):self.pet.bubble.size_transition.complete();self.pet.bubble.size_transition.release_landing();APP.processEvents()
    def test_card_only_pauses_decode_and_keeps_quota_status_and_notifications(self):
        p=self.pet;p.apply_settings(dict(character_visible=False));APP.processEvents()
        self.assertFalse(p.isVisible());self.assertTrue(p.bubble.isVisible());self.assertIsNone(p.bubble.parentWidget());self.assertIs(p.bubble.owner_pet(),p)
        self.assertFalse(p.tick.isActive());self.assertIsNone(p.player.thread)
        p.update_quota([dict(name='一周',remaining=63,resetsAt=None)],time.time(),'session')
        p.on_activity(dict(kind='status',session='fake',turn='one',state='thinking',active=1,text='验收状态'))
        self.assertEqual(p.bubble.windows[0]['remaining'],63);self.assertTrue(p.bubble.isVisible());self.assertIsNone(p.player.thread)
        with patch.object(p,'notify'),patch.object(p,'refresh_quota'):p.on_activity(dict(kind='complete',session='fake',turn='one',title='验收'))
        self.assertTrue(p.bubble.status_indicator.unread);self.assertFalse(p.isVisible());self.assertIsNone(p.player.thread)
        with patch('pet.Pet.play_click_sound') as sound:p.choose(p.variants[0],interactive=True,manual=True);sound.assert_not_called()
        self.assertIsNone(p.player.thread)
    def test_restore_character_and_global_hide_recover_respect_preference(self):
        p=self.pet;p.apply_settings(dict(character_visible=False));p.toggle_pet();self.assertFalse(p.bubble.isVisible())
        p.bubble.redraw();self.assertFalse(p.bubble.isVisible());p.recover();self.assertTrue(p.bubble.isVisible());self.assertFalse(p.isVisible())
        p.apply_settings(dict(character_visible=True));self.assertTrue(p.isVisible());self.assertTrue(p.tick.isActive());self.assertIsNotNone(p.player.thread)
    def test_tray_status_after_global_hide_restores_live_character(self):
        p=self.pet;p.execute_command('visible');APP.processEvents();self.assertFalse(p.isVisible())
        p.execute_command('status');APP.processEvents()
        self.assertTrue(p.isVisible());self.assertFalse(p._desktop_hidden);self.assertTrue(p.tick.isActive());self.assertTrue(p.bubble.isVisible())
        with patch('pet.Pet.play_click_sound'):p.single_click()
        self.assertEqual(p.mode,'click')
        p.execute_command('visible');p.apply_settings(dict(character_visible=False));p.execute_command('status');APP.processEvents()
        self.assertFalse(p.isVisible());self.assertTrue(p.bubble.isVisible())
    def click_pet(self):
        p=self.pet;point=QPointF(p.rect().center())
        for kind,button,buttons in ((QEvent.Type.MouseButtonPress,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseButtonRelease,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)):
            APP.sendEvent(p,QMouseEvent(kind,point,QPointF(p.mapToGlobal(point.toPoint())),button,buttons,Qt.KeyboardModifier.NoModifier))
        p.click_timer.stop();self.finish()
    def test_card_appears_only_after_pet_click_and_hides_after_delay(self):
        p=self.pet;b=p.bubble;self.finish();self.assertFalse(b.isVisible())
        b.redraw();p.position_bubble();self.assertFalse(b.isVisible())
        with patch('pet.Pet.play_click_sound'):self.click_pet()
        self.assertTrue(b.isVisible());self.assertTrue(p.card_timer.isActive());self.assertEqual(p.card_timer.interval(),10000)
        p.card_timer.timeout.emit();self.finish();self.assertFalse(b.isVisible());self.assertFalse(p._card_revealed)
        b.redraw();self.assertFalse(b.isVisible())
    def test_hover_details_and_editors_keep_revealed_card(self):
        p=self.pet;b=p.bubble;p.reveal_card();self.finish()
        with patch.object(b,'underMouse',return_value=True):p.card_timer.timeout.emit()
        self.finish();self.assertTrue(b.isVisible());self.assertTrue(p.card_timer.isActive())
        b.toggle_details();self.finish();p.card_timer.timeout.emit();self.finish();self.assertTrue(b.isVisible())
        b.collapse_to_normal();self.finish();p.open_settings();self.finish();p.card_timer.timeout.emit();self.finish()
        self.assertTrue(b.isVisible());b.return_to_status();self.finish()
        p.card_timer.timeout.emit();self.finish();self.assertFalse(b.isVisible())
    def test_completion_and_tray_reveal_card_without_click(self):
        p=self.pet;b=p.bubble;self.finish();self.assertFalse(b.isVisible())
        with patch.object(p,'notify'),patch.object(p,'refresh_quota'):p.on_activity(dict(kind='complete',session='fake',turn='one',title='验收'))
        self.finish();self.assertTrue(b.isVisible());self.assertTrue(b.status_indicator.unread)
        p.card_timer.timeout.emit();self.finish();self.assertFalse(b.isVisible())
        p.execute_command('status');self.finish();self.assertTrue(b.isVisible());self.assertFalse(b.expanded)
    def test_card_only_mode_never_auto_hides(self):
        p=self.pet;p.apply_settings(dict(character_visible=False));b=p.bubble;self.finish()
        self.assertTrue(b.isVisible());p.conceal_card();p.card_timer.timeout.emit();self.finish();self.assertTrue(b.isVisible())
    def test_drag_preserves_saved_anchor_across_sizes(self):
        p=self.pet;p.apply_settings(dict(character_visible=False));b=p.bubble;self.finish()
        target=b.pos()+QPoint(-60,-80);p.move_card(target);center=b.geometry().center().x()
        anchor=dict(p.settings['card_anchor']);b.toggle_details();self.finish()
        self.assertAlmostEqual(b.geometry().center().x(),center,delta=1)
        self.assertEqual(p.settings['card_anchor'],anchor);b.toggle_details();self.finish()
        self.assertAlmostEqual(b.geometry().center().x(),center,delta=1)
    def test_settings_draft_saves_hide_delay_even_when_current_page_is_editor(self):
        p=self.pet;p.open_settings();self.finish();s=p.settings_dialog
        s.fields['card_hide_delay'].setValue(25);s.apply();APP.processEvents()
        self.assertEqual(p.settings['card_hide_delay'],25);self.assertEqual(p.card_timer.interval(),25000)
        self.assertEqual(p.bubble.panel_page,'settings');self.assertTrue(p.bubble.isVisible())
    def test_video_ownership_and_normalization_keep_independent_card_covered(self):
        from video_yield import VideoYield
        p=self.pet
        class Holder:pet=p
        self.assertTrue(VideoYield.owned(Holder(),p.bubble))
        self.assertNotIn('bubble_mode',normalized({'bubble_mode':'minimal'}))
        self.assertEqual(normalized({'card_hide_delay':1})['card_hide_delay'],3)
        self.assertEqual(normalized({'card_hide_delay':900})['card_hide_delay'],120)

if __name__=='__main__':unittest.main()
