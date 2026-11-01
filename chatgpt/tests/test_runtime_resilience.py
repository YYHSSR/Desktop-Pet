"""Regression coverage for frozen resources, cancellation and malformed preferences."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

os.environ['QT_QPA_PLATFORM']='offscreen'


class ResourceTests(unittest.TestCase):
    def test_reorganized_assets_take_precedence_and_legacy_layout_is_still_readable(self):
        from runtime_paths import asset_file
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            old=root/'app/sounds/click.wav';old.parent.mkdir(parents=True);old.write_bytes(b'old')
            new=root/'assets/sounds/click.wav'
            with patch('runtime_paths.resource_root',return_value=root):
                self.assertEqual(asset_file('sounds/click.wav'),old)
                new.parent.mkdir(parents=True);new.write_bytes(b'current')
                self.assertEqual(asset_file('sounds/click.wav'),new)

    def test_onefile_reads_embedded_resources_independent_of_executable_directory(self):
        from runtime_paths import resource_root
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',str(root),create=True),patch.object(sys,'executable',str(root/'elsewhere/DesktopPet.exe')):
                self.assertEqual(resource_root(),root)


class WorkerTests(unittest.TestCase):
    def test_shutdown_is_nonblocking_and_connects_each_worker_only_once(self):
        from PySide6.QtCore import QObject,Signal
        from worker_lifecycle import workers_finished
        class Worker(QObject):
            finished=Signal()
            running=True
            def isRunning(self):return self.running
            def wait(self,*args):raise AssertionError('GUI must never wait')
        owner=SimpleNamespace(close=Mock());worker=Worker()
        self.assertFalse(workers_finished(owner,[worker]));self.assertFalse(workers_finished(owner,[worker]))
        self.assertEqual(len(owner._closing_workers),1)
        worker.running=False;worker.finished.emit()
        owner.close.assert_called_once_with();self.assertTrue(workers_finished(owner,[worker]))
    def test_already_deleted_qt_wrapper_does_not_break_shutdown(self):
        from worker_lifecycle import workers_finished
        worker=Mock();worker.isRunning.side_effect=RuntimeError('already deleted')
        self.assertTrue(workers_finished(SimpleNamespace(close=Mock()),[worker]))


class PreferencesTests(unittest.TestCase):
    def test_wrong_json_shapes_never_crash_preferences(self):
        from desktop_core import normalized
        for value in ([],None,42,'invalid'):
            self.assertEqual(normalized(value)['character'],'builtin')
        self.assertEqual(normalized(dict(character=[]))['character'],'builtin')
        self.assertEqual(normalized(dict(web_button='chat'))['web_button'],'chatgpt')
        self.assertEqual(normalized(dict(card_hide_delay='x'))['card_hide_delay'],10.)
    def test_malformed_material_preference_falls_back_to_default(self):
        from material_store import MaterialStore
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/'state';state.mkdir()
            for value in ([],None,42):
                (state/'material-preferences.json').write_text(json.dumps(value))
                self.assertEqual(MaterialStore(root,state).preferred,'light')


class PackagingTests(unittest.TestCase):
    def test_folder_build_embeds_native_pack_and_conda_native_dependencies(self):
        import tools.build as builder
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();materials=root/'materials';(materials/'quality-v1').mkdir(parents=True)
            Image.new('RGBA',(256,256),'white').save(materials/'quality-v1/idle.webp',lossless=True)
            (materials/'manifest.json').write_text(json.dumps(dict(idle=dict(file='quality-v1/idle.webp'))),encoding='utf-8')
            native=root/'python/Library/bin';native.mkdir(parents=True)
            names=('ffi.dll','sqlite3.dll','liblzma.dll','LIBBZ2.dll','libexpat.dll','libmpdec-4.dll')
            for name in names:(native/name).write_bytes(b'fixture')
            with patch.object(builder,'ROOT',root),patch.object(builder,'prepare_materials',return_value=materials),patch.object(builder.sys,'base_prefix',str(root/'python')),patch.object(builder.subprocess,'run') as compile,patch.object(builder,'embed_materials') as embedded,patch.object(builder,'trim_spec'):
                result=builder.build(root/'output')
                single=builder.build(root/'single',onefile=True)
            command=compile.call_args_list[0].args[0]
            self.assertIn('--onedir',command)
            self.assertEqual(embedded.call_args_list[0].args,(root/'output/ChatGpt/ChatGpt.exe',materials))
            self.assertFalse(any('assets/character' in argument for argument in command))
            self.assertEqual(result,root/'output/ChatGpt/ChatGpt.exe')
            self.assertEqual(single,root/'single/ChatGpt.exe')
            self.assertIn('--onefile',compile.call_args_list[2].args[0])
            self.assertTrue(all(call.kwargs['env']['PATH'].startswith(str(native)+os.pathsep) for call in compile.call_args_list))
            bundled={command[i+1] for i,argument in enumerate(command[:-1]) if argument=='--add-binary'}
            self.assertTrue({str(native/name)+';.' for name in names}<=bundled)


if __name__=='__main__':unittest.main()
