"""Current Gemini artwork: independent lift, live dragging, held loop and release."""
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
                      patch.object(Companion,'make_token_source',return_value=None)]
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

    def test_new_drag_and_renamed_lift_match_different_originals(self):
        pack=self.pet.pack
        self.assertEqual(len(pack.actions),13)
        self.assertEqual(pack.actions['drag']['source'],'互动/拖拽.webp')
        self.assertEqual(pack.actions['lift']['source'],'互动/被拎起来.webp')
        self.assertNotEqual(pack.actions['drag']['sourceSha256'],pack.actions['lift']['sourceSha256'])
        self.assertEqual(pack.actions['lift']['randomWeight'],0)
        self.assertEqual(len({item['file'] for item in pack.actions.values()}),13)
        inventory=json.loads((pack.root/'manifest.json').read_text(encoding='utf-8-sig'))
        for item in inventory['files']:
            path=pack.root/item['file']
            with path.open('rb') as stream:self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),item['sha256'])
            self.assertEqual(path.stat().st_size,item['bytes'])

    def test_drag_advances_before_release_and_held_loop_never_replays_standing(self):
        self.pet.set_option('hop_after_drag',False)
        press=self.drag();sprite=self.pet.sprite;item=self.pet.pack.actions['drag']
        self.assertTrue(sprite.dragging)
        self.assertEqual(sprite.player.frame_index,item['dragStartFrame'])
        first=sprite.player.frame_index;pump(300)
        self.assertTrue(sprite.dragging);self.assertGreater(sprite.player.frame_index,first)
        # Exercise the real end boundary without waiting through the entire intro.
        sprite.player.start(self.pet.pack.path(item),sprite.decode_size,start_frame=item['dragLoopEnd']-2,end_frame=item['dragLoopEnd'])
        sprite.schedule()
        deadline=time.monotonic()+3
        while sprite.player.path.name!='drag-held.webp' and time.monotonic()<deadline:pump(20)
        pump(150)
        self.assertTrue(sprite.dragging);self.assertEqual(sprite.player.path.name,'drag-held.webp')
        self.assertGreater(sprite.player.frame_index,0)
        sprite.mouseReleaseEvent(press)
        self.assertFalse(sprite.dragging);self.assertEqual(sprite.action,'idle')

    def test_release_respects_hop_preference_and_completion_priority(self):
        self.pet.set_option('hop_after_drag',True)
        press=self.drag();self.pet.sprite.mouseReleaseEvent(press)
        self.assertEqual(self.pet.sprite.action,'hop')
        press=self.drag()
        self.pet.director.request('catch',completion=True,dragging=True)
        self.pet.sprite.mouseReleaseEvent(press)
        self.assertEqual(self.pet.sprite.action,'catch')


if __name__=='__main__':unittest.main()
