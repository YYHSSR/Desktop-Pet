"""Interaction regressions for the shared Gpt-style companion surface."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'app'), str(ROOT.parent)]
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication, QWidget, QLabel
from PySide6.QtTest import QTest
from share.desktop.typography import install_ui_font
from share.desktop.quota import QuotaSnapshot, Meter
from card import CompanionCard
from model import SCHEMA, normalized

APP = QApplication.instance() or QApplication([])
install_ui_font(APP)


class CardSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.actions = {key: dict(id=key, name=key, group='test') for key in
                        ('idle', 'wave', 'peek', 'flower', 'idea', 'bow')}
        self.card = CompanionCard(self.actions, normalized({}, SCHEMA))
        self.card.geometry_provider = lambda size: QRect(40, 650-size.height(), size.width(), size.height())

    def tearDown(self):
        self.card.close(); APP.processEvents()

    def show_card(self):
        self.card.reveal(); self.card.finish_transition(); APP.processEvents()

    def test_dashboard_matches_reference_shape_and_does_not_scroll(self):
        self.show_card()
        self.assertEqual(self.card.size().toTuple(), (268, 188))
        self.assertEqual(self.card.scroller.verticalScrollBar().maximum(), 0)
        self.assertEqual(self.card.menu_button.toolTip(), '设置')
        self.assertFalse(hasattr(self.card.dashboard, 'focus_tab'))

    def test_settings_button_opens_editor_and_return_preserves_unsaved_draft(self):
        self.show_card(); self.card.menu_button.click(); self.card.finish_transition()
        panel = self.card.settings_panel
        self.assertEqual(self.card.pages.currentIndex(), self.card.PAGE_SETTINGS)
        self.assertEqual(self.card.width(), 560)
        self.assertEqual([panel.tabs.tabText(i) for i in range(panel.tabs.count())], ['常规', '动作'])
        panel.fields['size'].setValue(1.15)
        panel.return_button.click(); self.card.finish_transition()
        self.card.menu_button.click(); self.card.finish_transition()
        self.assertEqual(panel.fields['size'].value(), 1.15)
        self.assertIn('size', panel.dirty)

    def test_home_uses_two_quota_tiles_without_an_action_or_focus_pane(self):
        self.show_card(); APP.processEvents()
        self.assertEqual(len(self.card.dashboard.rows),2)
        self.assertFalse(self.card.quick_buttons)
        self.assertFalse(hasattr(self.card.dashboard,'action_tab'))
        self.assertEqual(self.card.size().toTuple(), (268, 188))
        self.assertEqual(self.card.scroller.verticalScrollBar().maximum(), 0)

    def test_editor_has_two_navigation_buttons_and_collapsed_advanced_controls(self):
        self.show_card();self.card.enter_settings();self.card.finish_transition()
        panel=self.card.settings_panel
        self.assertEqual([b.text() for b in self.card.navigation_buttons],['状态','设置'])
        self.assertEqual(panel.tabs.count(),2)
        self.assertFalse({'on_top','lock_position','nickname'} & set(panel.fields))
        self.assertFalse(hasattr(panel,'draft_status'))
        self.assertTrue(panel.advanced_card.isHidden())
        self.assertFalse(any('这里的偏好' in label.text() for label in panel.findChildren(QLabel)))
        panel.tabs.setCurrentIndex(1);APP.processEvents();canvas=self.card.geometry()
        panel.advanced_button.click();APP.processEvents()
        self.assertFalse(panel.advanced_card.isHidden())
        self.assertEqual(self.card.geometry(),canvas)
        panel.advanced_button.click();self.assertTrue(panel.advanced_card.isHidden())

    def test_quota_expands_status_and_editor_returns_to_the_same_origin(self):
        self.show_card()
        tile=self.card.dashboard.rows[0][0].parentWidget()
        QTest.mouseClick(tile,Qt.MouseButton.LeftButton,pos=QPoint(20,20))
        self.card.finish_transition();APP.processEvents()
        self.assertTrue(self.card.expanded_status);self.assertEqual(self.card.width(),360)
        self.assertTrue(self.card.navigation.isVisible())
        self.assertEqual(self.card.menu_button.icon_name,'collapse')
        self.card.enter_settings();self.card.finish_transition()
        self.card.settings_panel.return_button.click();self.card.finish_transition()
        self.assertTrue(self.card.expanded_status);self.assertEqual(self.card.width(),360)
        self.card.menu_button.click();self.card.finish_transition()
        self.assertFalse(self.card.expanded_status);self.assertEqual(self.card.width(),268)

    def test_ctrl_s_applies_the_settings_draft(self):
        self.show_card(); self.card.menu_button.click(); self.card.finish_transition()
        panel = self.card.settings_panel; seen = []
        panel.optionChanged.connect(lambda key, value: (seen.append((key, value)), panel.sync(key, value)))
        panel.fields['size'].setValue(1.15)
        panel.fields['size'].setFocus(); self.card.activateWindow(); APP.processEvents()
        QTest.keyClick(panel.fields['size'], Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
        self.assertIn(('size', 345), seen)

    def test_apply_is_explicit_and_external_changes_preserve_the_draft(self):
        panel = self.card.settings_panel; seen = []
        panel.optionChanged.connect(lambda key, value: (seen.append((key, value)), panel.sync(key, value)))
        panel.fields['size'].setValue(1.15); panel.tabs.setCurrentIndex(1)
        self.assertEqual(seen, [])
        panel.sync('size', 330)
        self.assertEqual(panel.fields['size'].value(), 1.15)
        self.assertIn('size', panel.conflicts)
        panel.discard()
        self.assertEqual(panel.fields['size'].value(), 1.1)
        panel.fields['size'].setValue(1.2); panel.apply()
        self.assertEqual(seen, [('size', 360)])
        self.assertFalse(panel.dirty)

    def test_restore_defaults_only_changes_the_current_draft_page(self):
        panel = self.card.settings_panel
        panel.sync('size', 340); panel.sync('random_interval', 100)
        panel.restore_defaults()
        self.assertEqual(panel.values['size'], 300)
        self.assertEqual(panel.baseline['size'], 340)
        self.assertEqual(panel.values['random_interval'], 100)

    def test_motion_does_not_resize_or_relayout_the_native_window_per_frame(self):
        self.show_card(); self.card.menu_button.click()
        self.assertTrue(self.card.transition_active)
        canvas = self.card.geometry(); content_size = self.card.content.size()
        before_key, after_key = self.card.before.cacheKey(), self.card.after.cacheKey()
        with patch.object(self.card, 'setGeometry', wraps=self.card.setGeometry) as resize:
            for milliseconds in (30, 100, 200, 300, 400):
                self.card.animation.setCurrentTime(milliseconds)
                self.assertEqual(self.card.geometry(), canvas)
                self.assertEqual(self.card.content.size(), content_size)
                self.assertEqual(self.card.before.cacheKey(), before_key)
                self.assertEqual(self.card.after.cacheKey(), after_key)
            resize.assert_not_called()
        self.card.finish_transition()
        self.assertFalse(self.card.transition_active)
        self.assertTrue(self.card.content.isVisible())

    def test_fast_navigation_keeps_the_latest_request_and_returns_cleanly(self):
        self.show_card(); self.card.set_page(self.card.PAGE_SETTINGS)
        self.card.set_page(self.card.PAGE_ACTIONS); self.card.set_page(0)
        self.assertEqual(self.card.pending_page, 0)
        self.card.finish_transition(); APP.processEvents(); self.card.finish_transition()
        self.assertEqual(self.card.pages.currentIndex(), 0)
        self.assertEqual(self.card.size().toTuple(), (268, 188))

    def test_escape_returns_then_dismisses_and_hiding_stops_animation(self):
        self.show_card(); self.card.set_page(self.card.PAGE_SETTINGS); self.card.finish_transition()
        QTest.keyClick(self.card, Qt.Key.Key_Escape); self.card.finish_transition()
        self.assertEqual(self.card.pages.currentIndex(), 0)
        QTest.keyClick(self.card, Qt.Key.Key_Escape)
        self.assertTrue(self.card.closing_surface)
        self.card.finish_transition(); self.assertFalse(self.card.isVisible())
        self.card.reveal(); self.card.hide()
        self.assertFalse(self.card.transition_active)
        self.assertEqual(self.card.animation.state().name, 'Stopped')

    def test_missing_allowance_stays_absent_and_real_allowance_reaches_the_dashboard(self):
        self.card.update_quota(None)
        self.assertTrue(all(row[1].text() == '—' for row in self.card.dashboard.rows))
        self.card.update_quota(QuotaSnapshot('Claude', connected=True, meters=(Meter('5 小时', .26), Meter('本周', .38))))
        self.assertEqual([row[1].text() for row in self.card.dashboard.rows], ['74%', '62%'])
        self.assertTrue(all(row[3].text() == '重置时间未提供' for row in self.card.dashboard.rows))

    def test_right_click_on_card_requests_the_shared_menu_at_the_pointer(self):
        self.show_card()
        requested = []
        self.card.contextRequested.connect(requested.append)
        local = QPoint(25, 40)
        pointer = self.card.mapToGlobal(local)
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, local, pointer)
        APP.sendEvent(self.card, event)
        self.assertEqual(requested, [pointer])
        self.assertTrue(event.isAccepted())
