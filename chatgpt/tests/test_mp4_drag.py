"""A mouse drag completes its lift, holds the supplied pose, then lands once."""
from unittest.mock import patch
import unittest
from types import SimpleNamespace
from PySide6.QtCore import Qt, QPointF
from PySide6.QtTest import QTest
from desktop import PRESS_HOLD_MS
import test_native_interactions as native
import time


class DragPolicyTests(unittest.TestCase):
    setUp = native.InteractionTests.setUp
    tearDown = native.InteractionTests.tearDown
    drag = native.InteractionTests.drag

    def test_quick_click_and_tiny_pointer_jitter_do_not_start_the_drag_animation(self):
        p = self.pet
        press = SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton,
                                globalPosition=lambda: QPointF(200, 200))
        tiny_move = SimpleNamespace(buttons=lambda: Qt.MouseButton.LeftButton,
                                    globalPosition=lambda: QPointF(202, 201))
        p.mousePressEvent(press)
        prepared = p.upcoming[1]
        p.mouseMoveEvent(tiny_move)
        self.assertFalse(p.dragging)
        self.assertEqual(p.current['id'], 'idle')
        p.mouseReleaseEvent(press)
        self.assertIsNone(p.upcoming)
        self.assertTrue(prepared.stop.is_set())
        QTest.qWait(PRESS_HOLD_MS+40)
        self.assertFalse(p.dragging)
        self.assertNotEqual(p.current['id'], 'drag')

    def test_sustained_stationary_press_starts_drag_and_preserves_the_window_position(self):
        p = self.pet
        position = p.pos()
        press = SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton,
                                globalPosition=lambda: QPointF(200, 200))
        p.mousePressEvent(press)
        QTest.qWait(PRESS_HOLD_MS+40)
        self.assertTrue(p.dragging)
        self.assertEqual((p.current['id'], p.mode), ('drag', 'drag'))
        self.assertEqual(p.player.range_start, p.current['dragStartFrame'])
        self.assertEqual(p.player.frame_index, p.current['sourceFrameOffset']+27)
        self.assertEqual(p.pos(), position)
        p.mouseReleaseEvent(press)
        self.assertTrue(p._landing_due)

    def test_released_or_cancelled_old_hold_timer_does_not_affect_a_new_press(self):
        p = self.pet
        press = SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton,
                                globalPosition=lambda: QPointF(200, 200))
        p.mousePressEvent(press)
        stale = p._pointer_epoch
        p.mouseReleaseEvent(press)
        p.mousePressEvent(press)
        p.begin_press_hold(stale)
        self.assertFalse(p.dragging)
        p.cancel_pointer()
        QTest.qWait(PRESS_HOLD_MS+40)
        self.assertFalse(p.dragging)
        self.assertNotEqual(p.current['id'], 'drag')

    def finish_segment(self):
        p = self.pet
        p.player.ended = True
        p.player.frame_index = p.player.range_end or p.current['frames']-1
        with patch.object(p.player, 'advance', return_value=(None, True)):
            p._animate_frame()

    def test_short_release_keeps_the_full_lift_then_plays_the_original_landing(self):
        self.drag()
        p = self.pet
        item = p.current
        self.assertEqual(item['id'], 'drag')
        self.assertEqual(p.player.range_start, item['dragStartFrame'])
        self.assertEqual(p.player.range_end, item['dragHoldFrame'])
        self.assertEqual(item['dragHoldFrame'], item['sourceFrameOffset']+170)
        self.assertEqual(item['sourceFrames'], 289)
        self.assertEqual(item['releaseFrame'], item['dragHoldFrame']+1)
        p.mouseReleaseEvent(self.press)
        self.assertFalse(p.dragging)
        self.assertTrue(p._landing_due)
        self.assertEqual(p.mode, 'drag')
        self.finish_segment()
        self.assertEqual(p.mode, 'landing')
        self.assertEqual(p.player.range_start, item['releaseFrame'])
        self.finish_segment()
        self.assertEqual((p.mode, p.current['id']), ('idle', 'idle'))

    def test_long_drag_freezes_without_restarting_or_decoding_a_loop(self):
        self.drag()
        p = self.pet
        self.finish_segment()
        self.assertEqual((p.mode, p._drag_loop_phase), ('drag', 'held'))
        frame = p.frames[0].toImage()
        with patch.object(p.player, 'start', wraps=p.player.start) as start:
            for _ in range(5):
                p._animate_frame()
            start.assert_not_called()
        self.assertEqual(frame, p.frames[0].toImage())
        p.mouseReleaseEvent(self.press)
        self.assertEqual(p.mode, 'landing')
        self.assertFalse(p._landing_due)
        self.finish_segment()
        self.assertEqual(p.current['id'], 'idle')

    def test_regrab_before_the_lift_finishes_preserves_its_progress(self):
        self.drag()
        p = self.pet
        started = p.started
        p.mouseReleaseEvent(self.press)
        self.assertTrue(p._landing_due)
        self.drag()
        self.assertEqual(p.started, started)
        self.assertFalse(p._landing_due)
        self.assertTrue(p.dragging)
        self.finish_segment()
        self.assertEqual(p._drag_loop_phase, 'held')

    def test_unprepared_release_seeks_to_the_tail_and_repeated_land_is_idempotent(self):
        self.drag()
        p = self.pet
        self.finish_segment()
        p.drop_release()
        p.mouseReleaseEvent(self.press)
        self.assertEqual(p.player.range_start, p.current['releaseFrame'])
        started = p.started
        p.land()
        self.assertEqual(p.started, started)

    def test_inertia_completion_does_not_restart_an_already_started_landing(self):
        self.drag()
        p = self.pet
        self.finish_segment()
        p.mouseReleaseEvent(self.press)
        p.throwing = True
        p._fx, p._fy = float(p.x()), float(p.y())
        p.velocity = (0., 0.)
        started = p.started
        p._move_frame()
        self.assertFalse(p.throwing)
        self.assertEqual(p.mode, 'landing')
        self.assertEqual(p.started, started)

    def test_ready_visible_entry_is_adopted_without_a_gui_thread_seek(self):
        p = self.pet
        item = p.manifest['dragAnimation']
        p.prepare_next(item,item['dragStartFrame'],item['dragHoldFrame'])
        deadline = time.monotonic()+5
        while not p.upcoming[1].ready.is_set() and time.monotonic()<deadline:
            QTest.qWait(5)
        self.assertTrue(p.upcoming[1].ready.is_set())
        with patch.object(p.player,'start',side_effect=AssertionError('Unexpected GUI-thread seek')):
            self.assertTrue(p.play(item,'drag'))
        self.assertIsNone(p.upcoming)
        self.assertEqual(p.player.frame_index, item['sourceFrameOffset']+27)

    def test_menu_preview_keeps_the_complete_video_including_its_idle_lead_in(self):
        p = self.pet
        p.choose(p.manifest['dragAnimation'],interactive=True,manual=True)
        self.assertEqual(p.player.range_start,0)
        self.assertIsNone(p.player.range_end)


if __name__ == '__main__':
    unittest.main()
