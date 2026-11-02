"""Acceptance for the current Gpt artwork, held dragging and reduced settings."""
import hashlib
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtWidgets import QToolButton, QLabel, QMenu, QWidget
from PySide6.QtGui import QAction
import test_native_interactions as native
from desktop import variant_weight
from desktop_services import all_items
from status_reactions import classify

ROOT = Path(__file__).resolve().parents[1]


def pump(milliseconds):
    # Let Python decoder threads run between native event batches.
    deadline = time.monotonic()+milliseconds/1000
    while time.monotonic() < deadline:
        native.APP.processEvents()
        time.sleep(.005)


@unittest.skipIf(json.loads((ROOT/'assets/character/manifest.json').read_text(encoding='utf-8')).get('sourceFormat') == 'mp4',
                 'Legacy full-pack checks; current three-action coverage is in test_mp4_character')
class NewCharacterTests(unittest.TestCase):
    setUp = native.InteractionTests.setUp
    tearDown = native.InteractionTests.tearDown

    def pointer(self):
        press = SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton,
                                globalPosition=lambda: QPointF(200,200))
        move = SimpleNamespace(buttons=lambda: Qt.MouseButton.LeftButton,
                               globalPosition=lambda: QPointF(245,230))
        self.pet.mousePressEvent(press)
        self.pet.mouseMoveEvent(move)
        return press

    def test_new_source_inventory_and_manual_actions_cover_every_original_once(self):
        inventory = self.pet.manifest['sourceInventory']
        self.assertEqual(len(inventory),24)
        for record in inventory:
            with (ROOT/'assets/character'/record['file']).open('rb') as stream:
                self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),record['sha256'])
        # Walks only happen while she wanders; every other original is in the menu once.
        items = self.pet.role_actions()
        walks = {i['id'] for i in self.pet.manifest['moveAnimations']}
        self.assertEqual(walks,{'move-left','move-right'})
        self.assertEqual(len(items),len(inventory)-len(walks))
        self.assertEqual(len({i['playbackFile'] for i in items}),len(items))
        self.assertEqual({i['id'] for i in items},{i['id'] for i in all_items(self.pet.manifest)}-walks)

    def test_the_next_move_is_picked_before_the_idle_seam_and_decoded_ahead(self):
        p = self.pet
        variant, other, clicked = p.variants[:3]
        with patch.object(p,'roll_autonomous',return_value=('variant',variant)):
            p.plan_ahead(time.monotonic())
        self.assertEqual(p.planned,('variant',variant))
        segment = p.upcoming[1]
        self.assertTrue(segment.ready.wait(3))
        plan, p.planned = p.planned, None
        self.assertTrue(p.autonomous_boundary(time.monotonic(),plan))
        self.assertEqual(p.current['id'],variant['id'])
        self.assertIs(p.player.frames,segment.frames)
        self.assertIsNone(p.upcoming)
        # A plan overtaken by a click is dropped, not played later.
        p.gate.state='idle'; p.prepare_next(other); stale = p.upcoming[1]
        p.choose(clicked,interactive=True)
        self.assertTrue(stale.stop.is_set()); self.assertIsNone(p.upcoming)
        self.assertEqual(p.current['id'],clicked['id'])

    def test_native_idle_loop_is_cached_and_large_display_does_not_upscale_decode(self):
        p = self.pet
        p.frame_size = 512
        p.player.start(p.asset_path(p.manifest['idle']), 512, cache_loop=True)
        while True:
            raw, _, error = p.player.frames.get(timeout=5)
            if raw is None:
                self.assertIsNone(error)
                break
        self.assertEqual(p.player.loop_cache.stats()['entries'], 1)
        with patch('stream_player.Image.open', side_effect=AssertionError('repeated decode')):
            p.player.start(p.asset_path(p.manifest['idle']), 512, cache_loop=True)
            while p.player.frames.get(timeout=5)[0] is not None:
                pass
        self.assertGreater(p.player.loop_cache.stats()['hits'], 0)
        self.assertLessEqual(p.player.loop_cache.stats()['bytes'], 96*1024*1024)
        p.setFixedSize(640, 640)
        p.sync_decode_size()
        self.assertEqual(p.frame_size, 512)

    def test_a_walk_carries_her_across_the_desktop_once_and_is_never_mirrored(self):
        p = self.pet
        p.apply_settings(dict(wandering=True),save=False)
        area = p.screen().availableGeometry()
        p.move(area.left()+12,p.y())
        start = p.x()
        p.walk_direction = -1   # a facing saved by an older build
        p.start_walk()
        self.assertTrue(p.walking)
        self.assertEqual((p.current['id'],p.mode),('move-right','walk'))
        p.press_feedback = 0
        self.assertTrue(p.frame_transform(QRectF(0,0,256,256)).isIdentity())
        walk = p.current['walk']
        p.player.frame_index = (walk['start']+walk['end'])//2; p._move_frame(); middle = p.x()
        p.player.frame_index = walk['end']; p._move_frame()
        self.assertEqual(p.x()-start,p.stroll['distance'])
        self.assertGreater(p.stroll['distance'],0)
        self.assertLess(start,middle); self.assertLess(middle,p.x())
        with patch.object(p.player,'advance',return_value=(None,True)):
            p._animate_frame()
        self.assertFalse(p.walking); self.assertIsNone(p.stroll)
        self.assertEqual((p.current['id'],p.mode),('idle','idle'))

    def test_a_quick_release_still_plays_the_whole_lift_before_she_comes_down(self):
        press = self.pointer()
        p = self.pet
        self.assertTrue(p.dragging)
        self.assertEqual((p.current['id'],p.mode),('drag','drag'))
        self.assertEqual(p.player.frame_index,0)
        initial = p.player.frame_index
        p.tick.start(); pump(300)
        self.assertGreater(p.player.frame_index,initial)
        self.assertTrue(p.dragging)
        p.mouseReleaseEvent(press)
        self.assertFalse(p.dragging)
        # Let go early: the lift keeps going instead of cutting to the way down.
        self.assertEqual((p.current['id'],p.mode,p.gate.state),('drag','drag','landing'))
        self.assertGreater(p.player.frame_index,initial)
        self.assertLess(p.player.frame_index,p.current['releaseFrame'])
        self.assertFalse(p.handoff.active())
        deadline=time.monotonic()+6
        while p.mode=='drag' and time.monotonic()<deadline:pump(10)
        self.assertEqual((p.current['id'],p.mode),('drag','landing'))
        self.assertGreaterEqual(p.player.frame_index,p.current['releaseFrame'])
        # The lift ends on the release frame, so the way down is a plain cut.
        self.assertFalse(p.handoff.active())
        deadline=time.monotonic()+3
        while p.mode=='landing' and time.monotonic()<deadline:pump(20)
        self.assertEqual(p.current['id'],'idle')

    def test_catching_her_again_during_the_lift_carries_it_on(self):
        press = self.pointer()
        p = self.pet
        p.tick.start(); pump(300)
        p.mouseReleaseEvent(press)
        reached = p.player.frame_index
        self.pointer()
        self.assertTrue(p.dragging)
        self.assertEqual((p.mode,p.gate.state),('drag','drag'))
        self.assertGreaterEqual(p.player.frame_index,reached)
        self.assertFalse(p._landing_due)

    def test_long_drag_holds_the_settled_pose_without_restarting_the_lift(self):
        p = self.pet
        drag = p.manifest['dragAnimation']
        # The hold sways through the frames just before release, ending on it.
        self.assertEqual(drag['dragLoopEnd'],drag['releaseFrame'])
        self.assertLessEqual(drag['dragLoopFrames'],20)
        self.assertGreaterEqual(drag['dragLoopStart'],drag['releaseFrame']-10)
        press = self.pointer()
        p.tick.start(); pump(4450)
        self.assertTrue(p.dragging)
        self.assertEqual(p.mode,'drag')
        self.assertEqual(p.player.path.name,'drag-held.webp')
        self.assertEqual(p._drag_loop_phase,'held')
        p.mouseReleaseEvent(press)
        self.assertEqual(p.mode,'landing')
        deadline=time.monotonic()+3
        while p.mode=='landing' and time.monotonic()<deadline:pump(20)
        self.assertEqual(p.current['id'],'idle')

    def test_manual_interrupt_uses_a_short_handoff_and_event_gestures_stay_out_of_random_pool(self):
        p = self.pet
        p.choose(p.variants[0],interactive=False,manual=True)
        self.assertTrue(p.handoff.active())
        choices = {i['id']:i for i in all_items(p.manifest)}
        self.assertGreater(variant_weight(choices['01'],8),variant_weight(choices['01'],14))
        self.assertGreater(variant_weight(choices['20'],14),variant_weight(choices['21'],14))
        for key in ('18','drag','quota','work01','work02','work05'):
            self.assertEqual(variant_weight(choices[key],14),0)
        self.assertEqual(classify({'state':'thinking'},choices).action_id,'work05')
        self.assertEqual(classify({'state':'working','activity':'edit'},choices).action_id,'work02')

    def test_settings_have_two_tabs_two_navigation_buttons_and_no_removed_text(self):
        p = self.pet
        p.open_settings(); native.APP.processEvents(); p.bubble.size_transition.complete(); native.APP.processEvents()
        panel = p.settings_dialog
        self.assertEqual([panel.tabs.tabText(i) for i in range(panel.tabs.count())],['常规','动作'])
        self.assertFalse(hasattr(panel,'health_panel'))
        self.assertFalse(hasattr(panel,'draft_status'))
        self.assertFalse(hasattr(panel,'characters'))
        self.assertFalse(hasattr(panel,'import_pack'))
        self.assertFalse(hasattr(panel,'select_converter'))
        self.assertFalse({'on_top','no_move'} & set(panel.fields))
        self.assertIn('wandering',panel.fields)
        texts = [w.text() for w in panel.findChildren(QLabel)]
        self.assertFalse(any('状态卡片平时隐藏' in text or '项未保存修改' in text or '这里的偏好点击' in text or '先选择陪伴方式' in text or '思考/阅读' in text for text in texts))
        toolbar = p.bubble.findChild(QWidget,'detail_shortcuts')
        self.assertEqual(toolbar.layout().count(),2)
        buttons = toolbar.findChildren(QToolButton)
        self.assertEqual([b.text() for b in buttons],['状态','设置'])
        self.assertLessEqual(abs(buttons[0].width()-buttons[1].width()),1)
        menu = QMenu(); p.build_menu(menu)
        commands = {a.objectName() for a in menu.findChildren(QAction)}
        self.assertTrue({'command_pin','command_lock'} <= commands)


if __name__ == '__main__':
    unittest.main()
