"""Public regressions for the silent, manually opened desktop integration."""
import json
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QMenu, QPushButton

from pet.config import Config
from pet.modern_settings_dialog import ModernSettingsDialog, SettingRow, SettingsTabContainer


def test_retired_audio_fields_are_removed_on_reload_and_save(tmp_path):
    cfg = Config(tmp_path)
    cfg.dir.mkdir(parents=True, exist_ok=True)
    cfg.path.write_text(json.dumps({
        "collision_enabled": True, "click_sound_enabled": True,
        "click_sound_path": "old.wav", "collision_sound_volume": 0.9,
        "self_talk_speak_enabled": True, "voice_chime_enabled": True,
        "festival_reminder_speak": True,
        "agent_link": {"codex": True, "sound_enabled": True, "sound_done_path": "old.wav"},
    }), encoding="utf-8")
    cfg.reload()
    assert cfg.save()
    disk = json.loads(cfg.path.read_text(encoding="utf-8"))
    for data in (cfg.data, disk):
        assert not any("sound" in key or "voice" in key or "speak" in key for key in data)
        assert not any(key.startswith("sound_") for key in data["agent_link"])
        assert data["agent_link"]["codex"] is True
        assert data["collision_enabled"] is True


def test_settings_group_active_pet_preferences_and_save_them(tmp_path):
    app = QApplication.instance() or QApplication([])
    cfg = Config(tmp_path)
    dialog = ModernSettingsDialog(cfg)
    try:
        assert [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())] == [
            "常规", "桌宠", "互动", "菜单", "自动化与联动",
        ]
        pet_page = dialog.pages.widget(1)
        tabs = pet_page.findChild(SettingsTabContainer, "settingsTaskTabs")
        assert tabs.keys() == ("appearance", "movement", "companions")
        for setting_id in ("pet_opacity", "animation_gap", "lock_position", "collision_enabled"):
            assert pet_page.isAncestorOf(dialog.findChild(SettingRow, "settingRow_" + setting_id))
        assert not any(any(word in row.objectName() for word in ("sound", "voice", "speak")) for row in dialog.findChildren(SettingRow))
        dialog.lock_position_check.setChecked(True)
        for control in (dialog.shift_drag_check, dialog.slingshot_check, dialog.throw_strength_select):
            assert not control.isEnabled()
        dialog.lock_position_check.setChecked(False)
        assert dialog.shift_drag_check.isEnabled()
        dialog.gap_spin.setValue(2.0)
        dialog.pet_opacity_spin.setValue(85)
        assert dialog._write_config()
        reloaded = Config(tmp_path)
        assert reloaded.get("animation_gap_seconds") == 2.0
        assert reloaded.get("pet_opacity") == 85
    finally:
        dialog.close()
        app.processEvents()
