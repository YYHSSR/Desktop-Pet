import os
import sys
import json
import tempfile
import unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch,Mock
from PIL import Image
from PySide6.QtWidgets import QApplication
import optional_tools
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from asset_pack import encode_exact,frame_fingerprints
APP=QApplication.instance() or QApplication([])

class AssetEncodingTests(unittest.TestCase):
    def test_reencoding_preserves_all_rgba_timing_loop_and_canvas(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a.webp';b=Path(d)/'b.webp'
            frames=[Image.new('RGBA',(32,32),(i,40,80,100+i)) for i in (1,2,3)]
            frames[0].save(a,save_all=True,append_images=frames[1:],lossless=True,method=0,duration=[40,42,41],loop=2)
            encode_exact(a,b);self.assertEqual(frame_fingerprints(a),frame_fingerprints(b));self.assertLessEqual(b.stat().st_size,a.stat().st_size)
    def test_invalid_container_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a';p.write_bytes(b'bad')
            with self.assertRaises(ValueError):encode_exact(p,Path(d)/'b')


class OptionalToolTests(unittest.TestCase):
    def test_webp_import_does_not_find_or_run_converter(self):
        from desktop_services import import_character
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'source/idle').mkdir(parents=True);Image.new('RGBA',(32,32),(0,0,0,0)).save(root/'source/idle/a.webp')
            with patch('optional_tools.find_ffmpeg',side_effect=AssertionError('not needed')):key,m=import_character(root/'source',root/'characters')
            self.assertTrue((root/'characters'/key/'素材清单.json').is_file())
    def test_missing_converter_gives_actionable_webm_import_error_and_cleans_stage(self):
        from desktop_services import import_character
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'source/idle').mkdir(parents=True);(root/'source/idle/a.webm').write_bytes(b'video')
            with patch('optional_tools.find_ffmpeg',return_value=None),self.assertRaisesRegex(ValueError,'角色页选择'):import_character(root/'source',root/'characters')
            self.assertEqual(list((root/'characters').iterdir()),[])
    def test_selected_tool_is_version_checked_and_only_path_is_saved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'ffmpeg.exe';p.write_bytes(b'test');config=Path(d)/'tools.json'
            with patch('optional_tools.settings_file',return_value=config),patch('optional_tools.subprocess.run',return_value=Mock(returncode=0,stdout=b'ffmpeg version 7')) as run:optional_tools.save_ffmpeg(p)
            self.assertEqual(run.call_args.args[0],[str(p.resolve()),'-version']);self.assertEqual(json.loads(config.read_text()),{'ffmpeg':str(p.resolve())})
    def test_wrong_executable_is_not_saved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.exe';p.write_bytes(b'test');config=Path(d)/'tools.json'
            with patch('optional_tools.settings_file',return_value=config),patch('optional_tools.subprocess.run',return_value=Mock(returncode=0,stdout=b'other')),self.assertRaises(ValueError):optional_tools.save_ffmpeg(p)
            self.assertFalse(config.exists())


if __name__=='__main__':unittest.main()
