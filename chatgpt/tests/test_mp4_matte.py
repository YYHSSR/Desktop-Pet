"""Preserve pale source cloth and highlights while removing only the backdrop."""
import unittest
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from mp4_matte import matte_frame


class SourceMatteTests(unittest.TestCase):
    def test_white_cloth_enclosed_by_a_purple_outline_remains_opaque(self):
        rgb = np.full((96, 96, 3), 255, np.uint8)
        rgb[12:88, 16:80] = (160, 130, 185)
        rgb[15:85, 19:77] = (250, 249, 251)
        result = np.asarray(matte_frame(Image.fromarray(rgb)))
        self.assertTrue((result[20:80, 24:72, 3] == 255).all())
        np.testing.assert_array_equal(result[20:80, 24:72, :3], rgb[20:80, 24:72])
        self.assertFalse(result[:8, :, 3].any())

    def test_central_bright_highlights_are_not_cut_out(self):
        rgb = np.full((96, 96, 3), 255, np.uint8)
        rgb[8:90, 10:86] = (180, 135, 205)
        rgb[32:40, 44:52] = 255
        rgba = np.asarray(matte_frame(Image.fromarray(rgb)))
        self.assertTrue((rgba[33:39, 45:51, 3] == 255).all())

    def test_soft_exterior_glow_is_translucent_but_enclosed_white_cloth_stays_opaque(self):
        rgb = np.full((96, 96, 3), 255, np.uint8)
        rgb[12:88, 16:70] = (160, 130, 185)
        rgb[15:85, 19:67] = (250, 249, 251)
        rgb[24:38, 78:90] = (248, 232, 255)
        rgba = np.asarray(matte_frame(Image.fromarray(rgb), soft_effects=True))
        self.assertTrue((rgba[20:80, 24:62, 3] == 255).all())
        np.testing.assert_array_equal(rgba[20:80, 24:62, :3], rgb[20:80, 24:62])
        self.assertTrue(((rgba[27:35, 81:87, 3] > 0) & (rgba[27:35, 81:87, 3] < 200)).all())

    def test_opaque_artwork_is_never_repainted_and_transparent_rgb_is_clean(self):
        yy, xx = np.mgrid[:96, :96]
        rgb = np.full((96, 96, 3), 255, np.uint8)
        rgb[15:85, 12:84] = np.stack((155+xx[15:85, 12:84]//3,
                                      100+yy[15:85, 12:84]//2,
                                      190+xx[15:85, 12:84]//4), axis=-1)
        rgba = np.asarray(matte_frame(Image.fromarray(rgb)))
        opaque = rgba[..., 3] == 255
        np.testing.assert_array_equal(rgba[..., :3][opaque], rgb[opaque])
        self.assertFalse(rgba[..., :3][rgba[..., 3] == 0].any())


class VerifiedOutputReuseTests(unittest.TestCase):
    def test_changed_source_pose_or_output_invalidates_verified_reuse(self):
        import prepare_mp4_character as prepare
        with tempfile.TemporaryDirectory() as folder, patch.object(prepare, 'ASSETS', Path(folder)):
            root = Path(folder)
            source = root/'source.mp4'
            output = root/'playback-mp4/greeting.webp'
            output.parent.mkdir()
            output.write_bytes(b'verified')
            sha = hashlib.sha256(output.read_bytes()).hexdigest()
            record = dict(file='source.mp4', playbackFile='playback-mp4/greeting.webp',
                          sourceSha256='source', preparation=prepare.RECIPE, referencePose='pose',
                          sourceFrames=2, frames=2, durationMs=83, playbackBytes512=8, playbackSha256512=sha)
            report = dict(allFramesVerified=True, opaqueRGBMaximumError=0, sourceFramesKept=2,
                          encoded=dict(sha256=sha, frames=2, durationMs=83))
            self.assertTrue(prepare.verified_previous('greeting', source, 'source', 'pose', record, report))
            self.assertFalse(prepare.verified_previous('greeting', source, 'changed', 'pose', record, report))
            self.assertFalse(prepare.verified_previous('greeting', source, 'source', 'new-pose', record, report))
            self.assertFalse(prepare.verified_previous('greeting', source, 'source', 'pose',
                                                       dict(record, durationMs=84), report))
            output.write_bytes(b'corrupt!')
            self.assertFalse(prepare.verified_previous('greeting', source, 'source', 'pose', record, report))


if __name__ == '__main__':
    unittest.main()
