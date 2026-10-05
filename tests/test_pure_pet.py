"""Public contracts for the pet + ChatGPT Work build."""
import json
import sys

import pytest

from PySide6.QtWidgets import QApplication

from pet.config import Config
from pet.modern_settings_dialog import ModernSettingsDialog


def test_retired_ai_config_does_not_return_from_disk_merge(tmp_path):
    cfg = Config(tmp_path)
    path = cfg.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'chat': {'providers': {'old': {'api_key': 'secret'}}},
                               'proactive_screen': {'enabled': True},
                               'file_interpret': {'enabled': True},
                               'chat_ui_style': 'classic', 'scale': 0.75,
                               'agent_link': {'codex': True}}), encoding='utf-8')
    cfg.reload()
    assert cfg.get('agent_link')['codex'] is True
    assert cfg.save()
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert not {'chat', 'proactive_screen', 'file_interpret', 'chat_ui_style'} & saved.keys()
    assert not {'chat', 'proactive_screen', 'file_interpret', 'chat_ui_style'} & cfg.data.keys()


def test_settings_only_offer_current_pet_capabilities(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = ModernSettingsDialog(Config(tmp_path))
    try:
        labels = [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())]
        assert labels == ['常规', '桌宠', '互动', '菜单', '自动化与联动']
        assert not hasattr(dialog, 'ai_page')
        assert not hasattr(dialog, 'festival_page')
        assert not any(name == 'pet.chat' or name.startswith('pet.chat.') for name in sys.modules)
        assert dialog._write_config()
    finally:
        dialog.close()
        app.processEvents()


@pytest.mark.parametrize("value", [False, "false", "FALSE", "0", "off", "no"])
def test_string_false_does_not_enable_agent_monitoring(tmp_path, value):
    cfg = Config(tmp_path)
    cfg.set("agent_link", {"codex": value, "cursor": value})
    assert cfg.get("agent_link")["codex"] is False
    assert cfg.get("agent_link")["cursor"] is False
    assert cfg.save()
    reloaded = Config(tmp_path)
    assert reloaded.get("agent_link")["codex"] is False


def test_desktop_pet_no_longer_accepts_file_drops(tmp_path):
    import importlib.util

    from pet.library import MovieLibrary
    from pet.window import PetWindow

    app = QApplication.instance() or QApplication([])
    cfg = Config(tmp_path)
    for key in ("auto_hide_fullscreen", "cursor_hidden_passthrough", "collision_enabled"):
        cfg.set(key, False)
    lib = MovieLibrary(prewarm_enabled=False)
    win = PetWindow(lib, cfg)
    try:
        assert not win.acceptDrops()
        assert not hasattr(win, "install_file_eater")
        assert importlib.util.find_spec("pet.file_eater") is None
    finally:
        win.hide(notify=False)
        win._stop_all_timers()
        lib.shutdown()
        win.close()
        app.processEvents()


def test_settings_save_merges_another_process_changes(tmp_path):
    pet = Config(tmp_path)
    pet.set("scale", 0.7)
    assert pet.save()
    settings = Config(tmp_path)
    pet.set("animation_gap_seconds", 3.0)
    assert pet.save()
    settings.set("bubble_text_scale", 120)
    assert settings.save()
    merged = Config(tmp_path)
    assert merged.get("animation_gap_seconds") == 3.0
    assert merged.get("bubble_text_scale") == 120


def test_retired_festival_data_does_not_return_from_disk_merge(tmp_path):
    import importlib.util

    cfg = Config(tmp_path)
    assert not any(key.startswith("festival_") for key in cfg.data)
    cfg.path.parent.mkdir(parents=True, exist_ok=True)
    cfg.path.write_text(json.dumps({"festival_reminder_enabled": True,
                                    "festival_custom_quotes_cn": "旧文案", "scale": 0.7}), encoding="utf-8")
    cfg.reload()
    assert not any(key.startswith("festival_") for key in cfg.data)
    # Another process still using an older version must not reintroduce the feature.
    cfg.path.write_text(json.dumps({"festival_reminder_enabled": True, "scale": 0.7}), encoding="utf-8")
    cfg.set("bubble_text_scale", 120)
    assert cfg.save()
    assert not any(key.startswith("festival_") for key in json.loads(cfg.path.read_text(encoding="utf-8")))
    for module in ("festival", "festival_calendar", "festival_service", "festival_settings", "reminder_values"):
        assert importlib.util.find_spec("pet." + module) is None


def test_removed_chat_notifications_do_not_return_from_config(tmp_path):
    import importlib.util

    cfg = Config(tmp_path)
    cfg.path.parent.mkdir(parents=True, exist_ok=True)
    cfg.path.write_text(json.dumps({"system_notifications_enabled": True}), encoding="utf-8")
    cfg.reload()
    assert "system_notifications_enabled" not in cfg.data
    assert cfg.save()
    assert "system_notifications_enabled" not in json.loads(cfg.path.read_text(encoding="utf-8"))
    assert importlib.util.find_spec("pet.desktop_notify") is None


def test_legacy_config_migration_keeps_settings_without_copying_retired_chat_sessions(tmp_path, monkeypatch):
    import pet.config as config_module

    monkeypatch.setattr(config_module, "APP_DIR_NAME", "pet-test-variant")
    legacy = tmp_path / "dsh-pet-standalone"
    sessions = legacy / "sessions"
    sessions.mkdir(parents=True)
    (legacy / "config.json").write_text(json.dumps({"version": 4, "scale": 0.7}), encoding="utf-8")
    old_chat = sessions / "old-chat.json"
    old_chat.write_text("{}", encoding="utf-8")
    cfg = Config(tmp_path)
    assert cfg.get("scale") == 0.7
    assert not (cfg.dir / "sessions").exists()
    assert old_chat.is_file()
