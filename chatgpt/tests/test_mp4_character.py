"""Acceptance for the MP4 character and safe missing legacy actions."""
import hashlib
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QPointF
import test_native_interactions as native
from desktop_services import all_items

ROOT = Path(__file__).resolve().parents[1]


class MP4CharacterTests(unittest.TestCase):
    setUp = native.InteractionTests.setUp
    tearDown = native.InteractionTests.tearDown

    def test_only_the_twenty_three_mp4_actions_are_active_and_each_source_is_preserved(self):
        p = self.pet
        self.assertEqual(p.manifest['sourceFormat'], 'mp4')
        expected = {'idle', 'move-left', 'move-right', 'proud', 'greeting', 'inspiration', 'affection',
                    'snack', 'tsundere', 'sleepy', 'annoyed', 'dragon-breath', 'celebrate', 'heart', 'bond-mark',
                    'task-process', 'treasure', 'task-receive', 'inspect', 'quota-check', 'trust', 'dragon-pact', 'drag'}
        self.assertEqual({item['id'] for item in all_items(p.manifest)}, expected)
        self.assertEqual({item['id'] for item in p.role_actions()}, expected)
        self.assertEqual(len(p.role_actions()), 23)
        self.assertEqual({item['id'] for item in p.variants}, expected-{'idle', 'move-left', 'move-right', 'drag'})
        self.assertEqual(p.manifest['dragAnimation']['id'], 'drag')
        for key in ('landingAnimation', 'quotaAnimation'):
            self.assertNotIn(key, p.manifest)
        for record in p.manifest['sourceInventory']:
            path = ROOT/'assets/character'/record['file']
            self.assertEqual(path.suffix, '.mp4')
            with path.open('rb') as stream:
                self.assertEqual(hashlib.file_digest(stream, 'sha256').hexdigest(), record['sha256'])

    def test_all_clips_share_exact_endpoints_and_keep_the_original_timing(self):
        anchor = None
        for item in all_items(self.pet.manifest):
            with Image.open(self.pet.asset_path(item)) as image:
                self.assertEqual(image.size, (512, 512))
                self.assertEqual(item['sourceFrames'], 361 if item['id']=='treasure' else 289)
                self.assertEqual(image.n_frames, item['sourceFrames']+item['entryBridgeFrames']+item['exitBridgeFrames'])
                image.seek(0)
                first = image.convert('RGBA').tobytes()
                image.seek(image.n_frames-1)
                last = image.convert('RGBA').tobytes()
                self.assertEqual(first, last)
                if anchor is None:anchor = first
                self.assertEqual(first, anchor)
                self.assertEqual(item['durationMs'], round(image.n_frames*1000/24))

    def test_each_new_gesture_plays_without_movement_and_returns_to_idle(self):
        p = self.pet
        origin = p.pos()
        for item in p.variants:
            self.assertNotIn('walk', item)
            self.assertFalse(item['loop'])
            p.single_click()
            p.choose(item, interactive=True, manual=True)
            self.assertEqual(p.current['id'], item['id'])
            self.assertFalse(p.walking)
            self.assertEqual(p.pos(), origin)
            with patch.object(p.player, 'advance', return_value=(None, True)):
                p._animate_frame()
            self.assertEqual((p.current['id'], p.mode), ('idle', 'idle'))

    def test_manual_walks_translate_in_the_chosen_direction_and_finish_at_idle(self):
        p = self.pet
        area = p.screen().availableGeometry()
        for item in p.manifest['moveAnimations']:
            p.stop_walk()
            p.move(area.center().x()-p.width()//2, p.y())
            origin = p.x()
            p.single_click()
            self.assertEqual(p.gate.state, 'click')
            p.choose(item, interactive=True, manual=True)
            self.assertTrue(p.walking)
            self.assertEqual(p.current['id'], item['id'])
            p.player.frame_index = item['walk']['end']
            p._move_frame()
            self.assertGreater((p.x()-origin)*item['direction'], 0)
            with patch.object(p.player, 'advance', return_value=(None, True)):
                p._animate_frame()
            self.assertFalse(p.walking)
            self.assertEqual((p.current['id'], p.mode), ('idle', 'idle'))

    def test_encoded_body_frames_keep_the_mp4_artwork_and_return_without_a_hard_cut(self):
        import cv2
        for item in all_items(self.pet.manifest):
            capture = cv2.VideoCapture(str(ROOT/'assets/character'/item['file']))
            try:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 100)
                ok, bgr = capture.read()
                self.assertTrue(ok)
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            finally:
                capture.release()
            with Image.open(self.pet.asset_path(item)) as image:
                image.seek(item['sourceFrameOffset']+100)
                rgba = np.asarray(image.convert('RGBA'))[16:496, 16:496]
                opaque = rgba[..., 3] == 255
                np.testing.assert_array_equal(rgba[..., :3][opaque], rgb[opaque])
                previous = None
                for index in range(image.n_frames-item['exitBridgeFrames']-1, image.n_frames):
                    image.seek(index)
                    value = np.asarray(image.convert('RGBA'), np.float32)/255
                    value[..., :3] *= value[..., 3:]
                    if previous is not None:
                        self.assertLess(float(np.abs(value-previous).mean()), .006)
                    previous = value

    def test_locked_manual_walk_previews_in_place_and_dragging_uses_the_supplied_clip(self):
        p = self.pet
        p.apply_settings(dict(no_move=True), save=False)
        point = p.pos()
        p.choose(p.manifest['moveAnimations'][0], interactive=True, manual=True)
        self.assertFalse(p.walking)
        self.assertEqual(p.pos(), point)
        self.assertEqual(p.current['id'], 'move-left')
        p.apply_settings(dict(no_move=False), save=False)
        p.gate.state = 'idle'
        press = SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton,
                                globalPosition=lambda: QPointF(200, 200))
        move = SimpleNamespace(buttons=lambda: Qt.MouseButton.LeftButton,
                               globalPosition=lambda: QPointF(245, 230))
        p.mousePressEvent(press)
        p.mouseMoveEvent(move)
        self.assertTrue(p.dragging)
        self.assertEqual(p.current['id'], 'drag')
        p.mouseReleaseEvent(press)
        self.assertEqual((p.current['id'], p.mode), ('drag', 'drag'))
        self.assertTrue(p._landing_due)

    def test_full_idle_loop_is_cached_at_native_size_and_large_windows_do_not_upscale_decode(self):
        p = self.pet
        path = p.asset_path(p.manifest['idle'])
        p.player.start(path, 512, cache_loop=True)
        while p.player.frames.get(timeout=10)[0] is not None:pass
        self.assertEqual(p.player.loop_cache.stats()['entries'], 1)
        with patch('stream_player.Image.open', side_effect=AssertionError('Repeated disk decode')):
            p.player.start(path, 512, cache_loop=True)
            while p.player.frames.get(timeout=10)[0] is not None:pass
        self.assertGreater(p.player.loop_cache.stats()['hits'], 0)
        self.assertLessEqual(p.player.loop_cache.stats()['bytes'], p.player.loop_cache.limit)
        p.setFixedSize(640, 640)
        p.sync_decode_size()
        self.assertEqual(p.frame_size, 512)

    def test_missing_legacy_actions_do_not_break_status_updates_or_autonomous_selection(self):
        p = self.pet
        p.apply_settings(dict(status_actions=True), save=False)
        p.on_activity(dict(kind='status', session='mp4-test', turn='one', state='thinking',
                           active=1, text='Working', display='Working'))
        p.play_status_reaction(time.monotonic()+20)
        self.assertEqual(p.current['id'], 'idle')
        with patch.object(p, 'refresh_quota', return_value=None):
            p.quota()
        self.assertEqual(p.current['id'], 'idle')
        p.apply_settings(dict(status_actions=False, wandering=False, random_actions=True), save=False)
        p.next_chain = p.buffer_until = p.status_hold = 0
        with patch.object(p.picker.rng, 'choices',
                          side_effect=lambda pool, weights: ['variant'] if isinstance(pool[0], str) else [pool[0]]):
            kind, item = p.roll_autonomous(time.monotonic())
        self.assertEqual(kind, 'variant')
        self.assertIn(item, p.variants)


if __name__ == '__main__':
    unittest.main()
