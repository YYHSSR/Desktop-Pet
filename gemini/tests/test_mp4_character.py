"""Acceptance for Gemini's own MP4 pack and complete-action dragging."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools'),str(ROOT.parent)]
from PIL import Image
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF,Qt
from PySide6.QtTest import QTest
from share.pet_engine.character_pack import CharacterPack
from sprite import GeminiSprite

APP=QApplication.instance() or QApplication([])
descriptor=json.loads((ROOT/'assets/character/character.json').read_text(encoding='utf-8'))

@unittest.skipUnless(descriptor.get('sourceFormat')=='mp4','Prepare the Gemini MP4 pack first')
class MP4CharacterTests(unittest.TestCase):
    def setUp(self):
        self.pack=CharacterPack(ROOT/'assets/character')
        self.sprite=GeminiSprite(self.pack,300)
        self.sprite.show();self.sprite.play('idle',blend=False);self.sprite.tick.stop()
        self.sprite.dragged.connect(lambda:self.sprite.start_drag('drag'))
        self.sprite.dragFinished.connect(lambda:self.sprite.release_drag('drag'))
        self.sprite.playbackFinished.connect(lambda key:self.sprite.play('idle',blend=False))
        APP.processEvents()

    def tearDown(self):
        self.sprite.close();APP.processEvents()

    def pointer(self):
        self.press=SimpleNamespace(button=lambda:Qt.MouseButton.LeftButton,globalPosition=lambda:QPointF(200,200),accept=lambda:None)
        move=SimpleNamespace(globalPosition=lambda:QPointF(245,220))
        self.sprite.mousePressEvent(self.press);self.sprite.mouseMoveEvent(move);self.sprite.tick.stop()
        self.assertTrue(self.sprite.dragging)

    def finish_range(self):
        s=self.sprite;s.player.ended=True;s.player.frame_index=s.player.range_end
        with patch.object(s.player,'advance',return_value=(None,True)):s.animate()
        s.tick.stop()

    def test_idle_is_the_reference_for_all_fourteen_actions_and_own_sources_are_preserved(self):
        self.assertEqual(len(self.pack.actions),14)
        self.assertEqual(self.pack.actions['idle']['source'],'MP4/\u5f85\u673a.mp4')
        self.assertNotIn('lift',self.pack.actions)
        inventory=json.loads((self.pack.root/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(inventory['files']),14)
        for item in inventory['files']:
            path=self.pack.root/item['file']
            self.assertEqual(path.suffix,'.mp4')
            with path.open('rb') as stream:self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),item['sha256'])
        anchor=None
        for item in self.pack.actions.values():
            with Image.open(self.pack.path(item)) as image:
                self.assertEqual(image.size,(512,512))
                self.assertEqual(image.n_frames,item['sourceFrames']+item['entryBridgeFrames']+item['exitBridgeFrames'])
                first=image.convert('RGBA').tobytes();image.seek(image.n_frames-1)
                self.assertEqual(first,image.convert('RGBA').tobytes())
                if anchor is None:anchor=first
                self.assertEqual(first,anchor)
                self.assertEqual(item['durationMs'],round(image.n_frames*1000/24))

    def test_each_playback_frame_matches_fixed_resize_of_its_own_source(self):
        import cv2
        from mp4_matte import matte_frame
        for item in self.pack.actions.values():
            cap=cv2.VideoCapture(str(self.pack.root/item['source']))
            try:
                cap.set(cv2.CAP_PROP_POS_FRAMES,100);ok,bgr=cap.read();self.assertTrue(ok)
                rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
            finally:cap.release()
            native=matte_frame(Image.fromarray(rgb),soft_effects=item['id']=='catch')
            rgba=np.asarray(native);opaque=rgba[...,3]==255
            np.testing.assert_array_equal(rgba[...,:3][opaque],rgb[opaque])
            expected=Image.new('RGBA',(512,512))
            expected.paste(native.resize((480,480),Image.Resampling.LANCZOS),(16,16))
            with Image.open(self.pack.path(item)) as image:
                image.seek(item['sourceFrameOffset']+100)
                self.assertEqual(image.convert('RGBA').tobytes(),expected.tobytes())

    def test_short_drag_finishes_its_action_before_playing_its_own_return(self):
        self.pointer();s=self.sprite;item=self.pack.actions['drag']
        self.assertEqual(s.player.range_start,item['dragStartFrame'])
        self.assertEqual(s.player.range_end,item['dragHoldFrame'])
        s.mouseReleaseEvent(self.press);s.tick.stop()
        self.assertTrue(s.landing_due);self.assertEqual(s.lift,'lift')
        self.finish_range()
        self.assertEqual(s.player.range_start,item['releaseFrame'])
        self.finish_range()
        self.assertEqual(s.action,'idle')

    def test_long_drag_holds_one_frame_without_restarting_until_mouse_release(self):
        self.pointer();s=self.sprite
        self.finish_range();self.assertEqual(s.lift,'held')
        self.assertFalse(s.tick.isActive())
        before=s.frame.toImage()
        with patch.object(s.player,'start',side_effect=AssertionError('Held pose decoded again')):
            for _ in range(5):s.animate()
        self.assertEqual(s.frame.toImage(),before)
        s.mouseReleaseEvent(self.press);s.tick.stop()
        self.assertEqual(s.player.range_start,self.pack.actions['drag']['releaseFrame'])
        self.finish_range();self.assertEqual(s.action,'idle')

    def test_regrab_preserves_the_action_and_no_prepared_tail_still_plays_the_return(self):
        self.pointer();s=self.sprite;serial=s.serial
        s.mouseReleaseEvent(self.press);self.assertTrue(s.landing_due)
        self.pointer();self.assertEqual(s.serial,serial);self.assertFalse(s.landing_due)
        self.finish_range();self.assertEqual(s.lift,'held')
        s.drop_release();s.mouseReleaseEvent(self.press);s.tick.stop()
        self.assertEqual(s.player.range_start,self.pack.actions['drag']['releaseFrame'])

    def test_a_press_without_movement_stays_a_click_and_the_menu_plays_the_full_clip(self):
        s=self.sprite
        event=SimpleNamespace(button=lambda:Qt.MouseButton.LeftButton,globalPosition=lambda:QPointF(200,200),accept=lambda:None)
        s.mousePressEvent(event);QTest.qWait(300)
        self.assertFalse(s.dragging);self.assertEqual(s.action,'idle')
        s.mouseReleaseEvent(event);s.click_timer.stop()
        self.assertIsNone(s._pickup)
        s.play('drag');s.tick.stop()
        self.assertEqual(s.player.range_start,0);self.assertIsNone(s.player.range_end)


if __name__=='__main__':unittest.main()
