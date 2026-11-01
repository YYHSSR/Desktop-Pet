import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT.parent), str(ROOT/'build/asset-tools')]
from PIL import Image, ImageDraw
try:
    from share.asset_tools.white_background import matte_white
except ImportError:
    matte_white = None


@unittest.skipIf(matte_white is None, 'Install share/requirements-assets.txt for asset-tool tests')
class MattingTests(unittest.TestCase):
    def test_white_dress_inside_dark_outline_stays_opaque_while_background_disappears(self):
        image = Image.new('RGB', (160, 200), 'white')
        painter = ImageDraw.Draw(image)
        painter.ellipse((35, 10, 125, 90), fill='#9d7be0')
        painter.rectangle((45, 80, 115, 180), fill='#392c6f')
        painter.rectangle((50, 85, 110, 175), fill='white')
        result = matte_white(image)
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertEqual(result.getpixel((80, 140))[3], 255)
        self.assertGreater(result.getpixel((80, 40))[3], 250)

    def test_disconnected_coloured_star_is_preserved(self):
        image = Image.new('RGB', (160, 200), 'white')
        painter = ImageDraw.Draw(image)
        painter.ellipse((40, 20, 120, 190), fill='#9475d1')
        painter.rectangle((5, 10, 15, 20), fill='#7098d5')
        result = matte_white(image)
        self.assertGreater(result.getpixel((10, 15))[3], 240)
        self.assertEqual(result.getpixel((150, 195))[3], 0)


if __name__ == '__main__':
    unittest.main()
