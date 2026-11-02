"""Regression coverage for missing pale fabric and persistent negative spaces."""
import unittest
from pathlib import Path
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from character_alpha import seal_fabric, stabilize


class FabricRepairTests(unittest.TestCase):
    def sequence(self):
        frames = []
        for index in range(21):
            value = np.zeros((96, 96, 4), np.uint8)
            shift = index//5
            value[12:86, 18+shift:76+shift] = (190, 168, 216, 255)
            # A permanent opening must remain transparent in every frame.
            value[20:32, 44+shift:52+shift] = 0
            value[46:48, 18+shift:76+shift, :3] = (110, 80, 145)
            frames.append(Image.fromarray(value))
        return frames

    def test_large_multiframe_dropout_is_restored_without_filling_real_opening(self):
        frames = self.sequence()
        damaged = [np.asarray(frame).copy() for frame in frames]
        for index in range(8, 12):
            damaged[index][58:80, 25:42] = 0
        fixed, report = stabilize([Image.fromarray(value) for value in damaged])
        self.assertGreater(report['restoredPixels'], 1000)
        for index in range(8, 12):
            alpha = np.asarray(fixed[index])[..., 3]
            self.assertGreater((alpha[61:77, 28:39] == 255).mean(), .95)
        for index, frame in enumerate(fixed):
            value = np.asarray(frame)
            shift = index//5
            self.assertFalse(value[22:30, 46+shift:50+shift, 3].any())
            self.assertFalse(value[:8, :, 3].any())
            opaque = damaged[index][..., 3] == 255
            np.testing.assert_array_equal(value[opaque], damaged[index][opaque])

    def test_recovered_colour_uses_intact_fabric_and_preserves_source_pixels(self):
        frames = self.sequence()
        damaged = [np.asarray(frame).copy() for frame in frames]
        trusted = [value[..., 3].copy() for value in damaged]
        damaged[10][60:76, 27:39, :3] = (240, 240, 240)
        trusted[10][60:76, 27:39] = 0
        fixed, _ = stabilize([Image.fromarray(value) for value in damaged], trusted)
        colour = np.asarray(fixed[10])[64:72, 30:36, :3].mean(axis=(0, 1))
        np.testing.assert_allclose(colour, (190, 168, 216), atol=3)
        np.testing.assert_array_equal(np.asarray(fixed[10])[36:42, 32:38],
                                      damaged[10][36:42, 32:38])

    def test_short_sequence_is_unchanged(self):
        frames = self.sequence()[:2]
        fixed, report = stabilize(frames)
        self.assertEqual(report['restoredPixels'], 0)
        for before, after in zip(frames, fixed):
            self.assertEqual(before.tobytes(), after.tobytes())

    def test_persistent_side_fabric_holes_are_solid_and_leg_separation_stays_open(self):
        value = np.asarray(self.sequence()[0]).copy()
        value[60:72, 26:36] = 0
        value[66:86, 44:52] = 0
        fixed, count = seal_fabric([Image.fromarray(value)])
        result = np.asarray(fixed[0])
        self.assertGreater(count, 100)
        self.assertTrue((result[61:71, 27:35, 3] == 255).all())
        self.assertFalse(result[68:84, 46:50, 3].any())
        self.assertFalse(result[22:30, 46:50, 3].any())


if __name__ == '__main__':
    unittest.main()
