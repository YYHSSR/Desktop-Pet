import sys
from pathlib import Path
import unittest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT.parent), str(ROOT/'build/asset-tools')]
try:
    from share.asset_tools.pose_bridge import pose_bridge
except ImportError:
    pose_bridge = None


@unittest.skipIf(pose_bridge is None, 'Install the optional asset preparation dependencies')
class PoseBridgeTests(unittest.TestCase):
    def frames(self):
        source = Image.new('RGBA', (80, 80))
        painter = ImageDraw.Draw(source)
        painter.rectangle((24, 18, 56, 74), fill='#9478d2')
        painter.rectangle((4, 8, 7, 11), fill='#9ec8ff')
        destination = Image.new('RGBA', (80, 80))
        ImageDraw.Draw(destination).rectangle((26, 18, 58, 74), fill='#9478d2')
        return source, destination

    def test_endpoints_remain_exact_and_detached_star_fades_at_its_own_position(self):
        source, destination = self.frames()
        result = pose_bridge(source, destination, 9)
        self.assertEqual(result[0].tobytes(), source.tobytes())
        self.assertEqual(result[-1].tobytes(), destination.tobytes())
        brightness = [frame.getpixel((5, 9))[3] for frame in result]
        self.assertEqual(brightness, sorted(brightness, reverse=True))
        self.assertEqual(brightness[-1], 0)

    def test_transparent_pixels_do_not_acquire_a_dark_or_white_backing(self):
        source, destination = self.frames()
        for frame in pose_bridge(source, destination, 7):
            self.assertEqual(frame.getpixel((0, 79)), (0, 0, 0, 0))
            self.assertGreater(frame.getpixel((40, 40))[3], 240)


if __name__ == '__main__':
    unittest.main()
