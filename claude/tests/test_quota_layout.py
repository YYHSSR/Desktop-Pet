"""Actual card layout, truthful family grouping and the rebuilt Claude drag."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import sys
import tempfile
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT.parent)]
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import QApplication
from share.desktop.quota import Meter,QuotaSnapshot
from share.desktop.quota_dashboard import quota_groups
from companion import Companion

APP=QApplication.instance() or QApplication([])


def pump(ms):
    deadline=time.monotonic()+ms/1000
    while time.monotonic()<deadline:
        APP.processEvents();time.sleep(.005)


class GroupTests(unittest.TestCase):
    def test_model_families_use_worst_remaining_and_never_duplicate_a_missing_week(self):
        snapshot=QuotaSnapshot('Antigravity',connected=True,meters=(Meter('Gemini Flash',.2),Meter('Gemini Pro',.6),
                  Meter('Claude Sonnet',.4),Meter('Other GPT',.7)))
        rows=quota_groups(snapshot,'gemini')
        self.assertEqual([(r['family'],r['window']) for r in rows],
                         [('Gemini','5h'),('Gemini','week'),('Other Model','5h'),('Other Model','week')])
        self.assertAlmostEqual(rows[0]['meter'].remaining,.4)
        self.assertAlmostEqual(rows[2]['meter'].remaining,.3)
        self.assertIsNone(rows[1]['meter']);self.assertIsNone(rows[3]['meter'])

    def test_explicit_week_windows_remain_separate_from_current_quotas(self):
        snapshot=QuotaSnapshot('Antigravity',connected=True,meters=(Meter('Gemini 5h',.1),Meter('Gemini weekly',.6),
                                    Meter('Claude Sonnet',.2),Meter('Claude 周额度',.8)))
        self.assertEqual([r['meter'].used for r in quota_groups(snapshot,'gemini')],[.1,.6,.2,.8])


class CurrentClaudeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(Companion,'make_quota_reader',return_value=None),
                      patch.object(Companion,'make_token_source',return_value=None)]
        for p in self.patches:p.start()
        self.pet=Companion(APP,Path(self.temp.name),root=ROOT,tray=False)
        self.pet.set_option('random_actions',False)

    def tearDown(self):
        self.pet.shutdown();APP.processEvents()
        from share.pet_engine.decode_runtime import STATS
        STATS.drain()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def drag(self):
        press=SimpleNamespace(button=lambda:Qt.MouseButton.LeftButton,globalPosition=lambda:QPointF(100,100),accept=lambda:None)
        move=SimpleNamespace(globalPosition=lambda:QPointF(150,125))
        self.pet.sprite.mousePressEvent(press);self.pet.sprite.mouseMoveEvent(move)
        return press

    def test_drag_animates_while_pressed_and_releases_without_replaying_the_lift(self):
        p=self.pet; press=self.drag(); sprite=p.sprite
        self.assertTrue(sprite.dragging);self.assertEqual(sprite.action,'drag')
        self.assertEqual(sprite.player.frame_index,p.pack.actions['drag']['dragStartFrame'])
        first=sprite.player.frame_index;pump(300)
        self.assertTrue(sprite.dragging);self.assertGreater(sprite.player.frame_index,first)
        pump(950)
        self.assertEqual(sprite.player.path.name,'drag-held.webp')
        sprite.mouseReleaseEvent(press)
        self.assertFalse(sprite.dragging);self.assertEqual(sprite.action,'idle')
        self.assertEqual(p.director.current,'idle')

    def test_current_pack_matches_all_selected_originals_and_has_common_endpoints(self):
        p=self.pet
        self.assertEqual(len(p.pack.actions),9)
        self.assertEqual(len({a['referencePose'] for a in p.pack.actions.values()}),1)
        for action in p.pack.actions.values():
            with (p.pack.root/action['source']).open('rb') as stream:
                self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),action['sourceSha256'])
            self.assertEqual(action['endpointDifference'],0)
        drag=p.pack.actions['drag']
        self.assertEqual((drag['sourceStartFrame'],drag['sourceEndFrame']),(40,65))

    def test_home_has_only_two_quota_tiles_and_today_tokens(self):
        p=self.pet;p.show_panel();p.card.finish_transition();pump(50)
        card=p.card
        card.update_quota(QuotaSnapshot('Claude',connected=True,meters=(Meter('5 小时',.25),Meter('本周',.5))))
        self.assertEqual([v.text() for _,v,_,_ in card.dashboard.rows],['75%','50%'])
        self.assertEqual(card.dashboard.deck.currentIndex(),0)
        self.assertFalse(card.quick_buttons)
        self.assertEqual(card.scroller.verticalScrollBar().maximum(),0)
        card.footer_widget.click();APP.processEvents();self.assertEqual(card.dashboard.deck.currentIndex(),1)
        card.dashboard.quota_return.click();self.assertEqual(card.dashboard.deck.currentIndex(),0)
