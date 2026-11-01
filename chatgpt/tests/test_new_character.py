"""Acceptance for the current Gpt artwork, held dragging and reduced settings."""
import hashlib
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QToolButton, QLabel, QMenu, QWidget
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
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
        self.assertEqual(len(inventory),22)
        for record in inventory:
            with (ROOT/'assets/character'/record['file']).open('rb') as stream:
                self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),record['sha256'])
        items = self.pet.role_actions()
        self.assertEqual(len(items),len(inventory))
        self.assertEqual(len({i['playbackFile'] for i in items}),len(items))
        self.assertEqual({i['id'] for i in items},{i['id'] for i in all_items(self.pet.manifest)})

    def test_drag_pose_starts_and_advances_before_mouse_release(self):
        press = self.pointer()
        p = self.pet
        self.assertTrue(p.dragging)
        self.assertEqual((p.current['id'],p.mode),('drag','drag'))
        self.assertEqual(p.player.frame_index,p.current['dragStartFrame'])
        initial = p.player.frame_index
        p.tick.start(); pump(300)
        self.assertGreater(p.player.frame_index,initial)
        self.assertTrue(p.dragging)
        p.mouseReleaseEvent(press)
        self.assertFalse(p.dragging)
        self.assertEqual(p.current['id'],'idle')
        self.assertNotEqual(p.mode,'drag')
        self.assertTrue(p.handoff.active())

    def test_long_drag_keeps_playing_the_held_loop_without_restarting_the_lift(self):
        press = self.pointer()
        p = self.pet
        p.tick.start(); pump(4450)
        self.assertTrue(p.dragging)
        self.assertEqual(p.mode,'drag')
        self.assertEqual(p.player.path.name,'drag-held.webp')
        self.assertGreater(p.player.frame_index,0)
        p.mouseReleaseEvent(press)
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
        self.assertFalse({'on_top','no_move','wandering'} & set(panel.fields))
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
