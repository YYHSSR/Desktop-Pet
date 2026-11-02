"""Preserve pale source cloth and highlights while removing only the backdrop."""
import unittest
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


if __name__ == '__main__':
    unittest.main()
