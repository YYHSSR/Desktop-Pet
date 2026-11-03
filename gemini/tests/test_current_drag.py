"""Current Gemini artwork: own MP4 drag, completed short lift, static hold and release."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT.parent)]
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import QApplication
from companion import Companion

APP=QApplication.instance() or QApplication([])


def pump(milliseconds):
    deadline=time.monotonic()+milliseconds/1000
    while time.monotonic()<deadline:APP.processEvents();time.sleep(.005)


class CurrentDragTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(Companion,'make_quota_reader',return_value=None),
                      patch.object(Companion,'make_token_source',return_value=None),
                      patch('companion.native_windows',return_value=None)]
        for item in self.patches:item.start()
        self.pet=Companion(APP,Path(self.temp.name),root=ROOT,tray=False)
        self.pet.set_option('random_actions',False)

    def tearDown(self):
        self.pet.shutdown();APP.processEvents()
        from share.pet_engine.decode_runtime import STATS
        STATS.drain()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def drag(self):
        press=SimpleNamespace(button=lambda:Qt.MouseButton.LeftButton,globalPosition=lambda:QPointF(100,100),accept=lambda:None)
        move=SimpleNamespace(globalPosition=lambda:QPointF(160,130))
        self.pet.sprite.mousePressEvent(press);self.pet.sprite.mouseMoveEvent(move)
        return press

    def finish_range(self):
        s=self.pet.sprite;s.player.ended=True;s.player.frame_index=s.player.range_end
        with patch.object(s.player,'advance',return_value=(None,True)):s.animate()
        s.tick.stop()

    def test_fourteen_own_mp4_actions_match_the_original_inventory(self):
        pack=self.pet.pack
        self.assertEqual(len(pack.actions),14)
        self.assertEqual(pack.actions['drag']['source'],'MP4/\u62d6\u62fd.mp4')
        self.assertNotIn('lift',pack.actions)
        self.assertEqual(len({item['file'] for item in pack.actions.values()}),14)
        self.assertEqual({pack.actions[key]['walk']['direction'] for key in ('walk-left','walk-right')},{-1,1})
        inventory=json.loads((pack.root/'manifest.json').read_text(encoding='utf-8'))
        for item in inventory['files']:
            path=pack.root/item['file']
            with path.open('rb') as stream:self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),item['sha256'])
            self.assertEqual(path.stat().st_size,item['bytes'])

    def test_drag_starts_before_release_and_holds_without_replaying_standing(self):
        self.pet.set_option('hop_after_drag',False)
        press=self.drag();sprite=self.pet.sprite;item=self.pet.pack.actions['drag']
        self.assertTrue(sprite.dragging)
        self.assertEqual(sprite.player.range_start,item['dragStartFrame'])
        first=sprite.player.frame_index;pump(300)
        self.assertTrue(sprite.dragging);self.assertGreater(sprite.player.frame_index,first)
        sprite.tick.stop();self.finish_range()
        self.assertEqual(sprite.lift,'held');self.assertFalse(sprite.tick.isActive())
        serial=sprite.serial;frame=sprite.frame.toImage()
        for _ in range(5):sprite.animate()
        self.assertEqual(sprite.serial,serial);self.assertEqual(sprite.frame.toImage(),frame)
        sprite.mouseReleaseEvent(press);sprite.tick.stop()
        self.assertEqual(sprite.player.range_start,item['releaseFrame'])
        self.finish_range();self.assertEqual(sprite.action,'idle')

    def test_short_release_completes_its_return_before_optional_hop_and_prioritizes_completion(self):
        self.pet.set_option('hop_after_drag',True)
        press=self.drag();s=self.pet.sprite;s.mouseReleaseEvent(press);s.tick.stop()
        self.assertTrue(s.landing_due);self.assertEqual(s.action,'drag')
        self.assertEqual(self.pet.director.queued,'hop')
        self.finish_range();self.assertEqual(s.player.range_start,self.pet.pack.actions['drag']['releaseFrame'])
        self.finish_range();self.assertEqual(s.action,'hop')
        press=self.drag()
        self.pet.director.request('catch',completion=True,dragging=True)
        s.mouseReleaseEvent(press);s.tick.stop()
        self.finish_range();self.finish_range();self.assertEqual(s.action,'catch')


if __name__=='__main__':unittest.main()
