"""Check the reorganized entry points and the desktop without updater services."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class EntryPointTests(unittest.TestCase):
    def test_asset_preflight_reports_missing_playback_and_seams(self):
        from tools.import_assets import missing_assets
        from desktop_services import all_items
        from sustained_assets import seam_items
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assets = root / 'assets/character'
            assets.mkdir(parents=True)
            source = ROOT / 'assets/character/素材清单.json'
            (assets / source.name).write_bytes(source.read_bytes())
            data = json.loads(source.read_text(encoding='utf-8'))
            expected = all_items(data) + seam_items(data)
            self.assertEqual(len(missing_assets(root)), len(expected))
            for item in expected:
                path = assets / (item.get('playbackFile') or item['file'])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'placeholder-for-existence-check')
            self.assertEqual(missing_assets(root), [])

    def test_build_rejects_missing_assets_before_running_pyinstaller(self):
        import tools.build as builder
        with tempfile.TemporaryDirectory() as folder, patch.object(builder, 'ROOT', Path(folder)), \
                patch.object(builder.subprocess, 'run') as execute:
            with self.assertRaises(FileNotFoundError):
                builder.build()
            execute.assert_not_called()

    def test_legacy_update_setting_is_removed_from_saved_configuration(self):
        from desktop_core import normalized
        settings = normalized(dict(update_checks=True, scale=1.5))
        self.assertNotIn('update_checks', settings)
        self.assertEqual(settings['scale'], 1.5)

    def test_materials_have_no_network_download(self):
        self.assertFalse((ROOT / 'app/material_download.py').exists())
        source = (ROOT / 'app/material_store.py').read_text(encoding='utf-8')
        for marker in ('urllib', 'http', 'open_url'):
            self.assertNotIn(marker, source)

    def test_import_validates_every_playback_file_before_writing(self):
        from tools.import_assets import import_assets
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir()
            data=dict(idle=dict(id='idle',file='idle.webp'),variants=[dict(id='missing',file='missing.webp')])
            (source/'素材清单.json').write_text(json.dumps(data),encoding='utf-8')
            (source/'idle.webp').write_bytes(b'fixture')
            with self.assertRaises(FileNotFoundError):import_assets(source,root/'target')
            self.assertFalse((root/'target').exists())

    def test_import_rejects_escape_and_cleans_historical_annotations(self):
        from tools.import_assets import import_assets
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir()
            data=dict(idle=dict(id='idle',file='../outside.webp'),variants=[],upstreamAnimationVersion='old',qualityBaseline='old.txt')
            (source/'素材清单.json').write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(ValueError):import_assets(source,root/'target')
            data['idle']['file']='idle.webp'
            (source/'素材清单.json').write_text(json.dumps(data),encoding='utf-8')
            (source/'idle.webp').write_bytes(b'fixture')
            self.assertEqual(import_assets(source,root/'target'),1)
            target=root/'target/assets/character'
            self.assertEqual((target/'idle.webp').read_bytes(),b'fixture')
            manifest=json.loads((target/'素材清单.json').read_text(encoding='utf-8'))
            self.assertNotIn('upstreamAnimationVersion',manifest)
            self.assertNotIn('qualityBaseline',manifest)


class DesktopLifecycleTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        from PySide6.QtWidgets import QApplication
        from desktop_services import all_items
        from sustained_assets import seam_items
        from material_store import MaterialStore
        from desktop import DesktopPet
        self.app = QApplication.instance() or QApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        assets = root / 'assets/character'
        assets.mkdir(parents=True)
        source = ROOT / 'assets/character/素材清单.json'
        (assets / source.name).write_bytes(source.read_bytes())
        manifest = json.loads(source.read_text(encoding='utf-8'))
        frames = [Image.new('RGBA', (32, 32), (80 + i * 30, 120, 180, 255)) for i in range(3)]
        for item in all_items(manifest) + seam_items(manifest):
            path = assets / (item.get('playbackFile') or item['file'])
            path.parent.mkdir(parents=True, exist_ok=True)
            frames[0].save(path, save_all=True, append_images=frames[1:], duration=42, lossless=True)
        state = root / 'state'
        state.mkdir()
        store = MaterialStore(root, state)
        for target, value in [('enhanced.CONFIG', state / 'settings.json'),
                              ('enhanced.STATE_DIR', state), ('desktop.CONFIG', state / 'settings.json'),
                              ('desktop.STATE_DIR', state)]:
            current = patch(target, value)
            current.start()
            self.addCleanup(current.stop)
        for target in ('desktop_settings.autostart_enabled', 'codex_startup.enabled'):
            current = patch(target, return_value=False)
            current.start()
            self.addCleanup(current.stop)
        with patch('material_store.MaterialStore', return_value=store):
            self.pet = DesktopPet(monitor=False)
        self.pet.tick.stop()
        self.pet.motion_timer.stop()
        self.addCleanup(self.close_pet)

    def close_pet(self):
        self.pet.close()
        self.app.processEvents()

    def test_desktop_starts_and_records_state_without_release_fields_or_updater(self):
        self.assertFalse(hasattr(self.pet, 'updates'))
        self.assertFalse(hasattr(self.pet, 'install_app_update'))
        import desktop
        self.pet.record_state()
        state = json.loads((desktop.STATE_DIR / 'runtime.json').read_text(encoding='utf-8'))
        for key in ('version', 'ui_revision', 'in_app_updates', 'program_only_updates',
                    'installation_ready_receipt', 'update_phase'):
            self.assertNotIn(key, state)
        self.assertIn('connection_health', state)
        self.assertTrue(self.pet.frames)

    def test_manual_actions_only_offer_playable_groups(self):
        from PySide6.QtWidgets import QMenu
        groups = self.pet.action_groups()
        self.assertTrue(groups)
        self.assertTrue(all(groups.values()))
        self.assertNotIn('转向', groups)
        self.assertNotIn('移动', groups)
        menu = QMenu()
        self.pet.build_menu(menu)
        manual = next(child for child in menu.findChildren(QMenu) if child.title() == '手动动作')
        submenus = [child for child in manual.findChildren(QMenu)]
        self.assertEqual(sorted(sub.title() for sub in submenus), sorted(groups))
        for sub in submenus:
            self.assertTrue(sub.actions())
            self.assertTrue(all(action.isEnabled() for action in sub.actions()))

    def test_builtin_chat_is_absent(self):
        from PySide6.QtWidgets import QMenu
        from quick_actions import WEB_TARGETS
        self.assertFalse((ROOT / 'app/chat_window.py').exists())
        self.assertFalse(hasattr(self.pet, 'open_chat'))
        self.assertFalse(hasattr(self.pet.bubble, 'chatRequested'))
        self.assertNotIn('chat', [target[0] for target in WEB_TARGETS])
        self.assertFalse((ROOT / 'app/island_widgets.py').exists())
        for name in ('set_mode', 'is_island', 'shortcutRequested', 'modeChanged'):
            self.assertFalse(hasattr(self.pet.bubble, name), name)
        menu = QMenu()
        self.pet.build_menu(menu)
        self.assertFalse(any('聊天' in action.text() for action in menu.actions()))

    def test_embedded_settings_has_no_update_controls_and_still_applies_changes(self):
        from PySide6.QtWidgets import QLabel
        self.pet.open_settings()
        self.app.processEvents()
        settings = self.pet.settings_dialog
        self.assertNotIn('update_checks', settings.fields)
        self.assertFalse(hasattr(settings, 'update_panel'))
        self.assertFalse(any('软件更新' in label.text() for label in settings.findChildren(QLabel)))
        self.pet.apply_settings(dict(wandering=False, on_top=False))
        self.assertFalse(self.pet.settings['wandering'])
        self.assertFalse(self.pet.settings['on_top'])


if __name__ == '__main__':
    unittest.main()
