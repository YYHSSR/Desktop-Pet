"""Actual card layout, truthful family grouping and the rebuilt Claude drag."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from datetime import datetime
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

    def test_a_long_drag_holds_the_settled_swing_and_sets_her_down_on_release(self):
        p=self.pet; press=self.drag(); sprite=p.sprite; item=p.pack.actions['drag']
        self.assertTrue(sprite.dragging);self.assertEqual(sprite.action,'drag')
        self.assertEqual(sprite.player.frame_index,item['dragStartFrame'])
        # The supplied lifted pose is held once, without restarting a sway loop.
        self.assertTrue(item['liftCompletes'])
        self.assertEqual(item['dragHoldFrame']+1,item['releaseFrame'])
        pump(300)
        self.assertTrue(sprite.dragging);self.assertGreater(sprite.player.frame_index,0)
        deadline=time.monotonic()+9
        while sprite.lift!='held' and time.monotonic()<deadline:pump(30)
        self.assertEqual(sprite.player.frame_index,item['dragHoldFrame']);self.assertEqual(sprite.lift,'held')
        self.assertTrue(sprite.release_tail.ready.is_set())
        sprite.mouseReleaseEvent(press)
        self.assertFalse(sprite.dragging);self.assertEqual(sprite.action,'drag')
        self.assertEqual(sprite.player.frame_index,item['releaseFrame'])
        self.assertIsNotNone(sprite.outgoing)
        deadline=time.monotonic()+7
        while sprite.action=='drag' and time.monotonic()<deadline:pump(20)
        self.assertEqual(sprite.action,'idle');self.assertEqual(p.director.current,'idle')

    def test_a_quick_release_still_plays_the_whole_lift_before_she_comes_down(self):
        p=self.pet; press=self.drag(); sprite=p.sprite; item=p.pack.actions['drag']
        pump(300)
        reached=sprite.player.frame_index
        sprite.mouseReleaseEvent(press)
        self.assertFalse(sprite.dragging);self.assertTrue(sprite.landing_due)
        self.assertEqual((sprite.action,sprite.lift,p.director.current),('drag','lift','drag'))
        self.assertGreaterEqual(sprite.player.frame_index,reached)
        self.assertLess(sprite.player.frame_index,item['releaseFrame'])
        deadline=time.monotonic()+9
        while sprite.landing_due and time.monotonic()<deadline:pump(10)
        # The lift ends on the release frame, so the way down is a plain cut.
        self.assertFalse(sprite.landing_due);self.assertEqual(sprite.action,'drag')
        self.assertGreaterEqual(sprite.player.frame_index,item['releaseFrame'])
        self.assertIsNone(sprite.outgoing)
        deadline=time.monotonic()+7
        while sprite.action=='drag' and time.monotonic()<deadline:pump(20)
        self.assertEqual(sprite.action,'idle');self.assertEqual(p.director.current,'idle')

    def test_catching_her_again_during_the_lift_carries_it_on(self):
        p=self.pet; press=self.drag(); sprite=p.sprite
        pump(300)
        sprite.mouseReleaseEvent(press)
        reached=sprite.player.frame_index
        self.drag()
        self.assertTrue(sprite.dragging);self.assertFalse(sprite.landing_due)
        self.assertEqual((sprite.action,sprite.lift),('drag','lift'))
        self.assertGreaterEqual(sprite.player.frame_index,reached)

    def test_current_pack_matches_all_selected_originals_and_has_common_endpoints(self):
        p=self.pet
        self.assertEqual(len(p.pack.actions),12)
        self.assertEqual(len({a['referencePose'] for a in p.pack.actions.values()}),1)
        for action in p.pack.actions.values():
            with (p.pack.root/action['source']).open('rb') as stream:
                self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),action['sourceSha256'])
            self.assertEqual(action['sourceFrames'],289)
            self.assertTrue(action['source'].startswith('MP4/'))
        self.assertEqual(p.pack.data['sourceFormat'],'mp4')
        self.assertEqual(p.pack.actions['drag']['dragStartFrame'],p.pack.actions['drag']['sourceFrameOffset']+36)
        for key,direction in (('walk-left',-1),('walk-right',1)):
            walk=p.pack.actions[key]['walk']
            self.assertEqual(walk['direction'],direction);self.assertLess(walk['start'],walk['end'])

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
