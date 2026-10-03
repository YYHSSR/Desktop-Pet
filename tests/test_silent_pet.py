"""Public regressions for the silent, manually opened desktop integration."""
import json
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QMenu, QPushButton

from pet.config import Config
from pet.context_menus.shared import add_agent_link_menu
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


def test_link_menu_has_status_preferences_without_app_launch(tmp_path):
    app = QApplication.instance() or QApplication([])
    cfg = Config(tmp_path)
    menu = QMenu()
    pet = SimpleNamespace(cfg=cfg, toggle_agent_link=lambda *args: None)
    sub = add_agent_link_menu(menu, pet)
    assert any("Work / Codex" in action.text() for action in sub.actions())
    assert not any("打开" in action.text() and "ChatGPT" in action.text() for action in sub.actions())
    menu.close()
    app.processEvents()


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
        for setting_id in ("scale", "playback_speed", "no_move", "lock_position", "collision_enabled"):
            assert pet_page.isAncestorOf(dialog.findChild(SettingRow, "settingRow_" + setting_id))
        assert not any(any(word in row.objectName() for word in ("sound", "voice", "speak")) for row in dialog.findChildren(SettingRow))
        dialog.lock_position_check.setChecked(True)
        for control in (dialog.shift_drag_check, dialog.drag_physics_check, dialog.slingshot_check, dialog.throw_strength_select):
            assert not control.isEnabled()
        dialog.lock_position_check.setChecked(False)
        assert dialog.shift_drag_check.isEnabled()
        dialog.speed_select.setCurrentData(1.5)
        dialog.no_move_check.setChecked(True)
        assert dialog._write_config()
        reloaded = Config(tmp_path)
        assert reloaded.get("playback_speed") == 1.5
        assert reloaded.get("no_move") is True
    finally:
        dialog.close()
        app.processEvents()


def test_island_card_only_offers_pet_and_settings(tmp_path):
    from pet.dynamic_island import DynamicIsland
    app = QApplication.instance() or QApplication([])
    island = DynamicIsland(Config(tmp_path))
    try:
        assert {button.text() for button in island._card_box.findChildren(QPushButton)} == {"隐藏桌宠", "设置"}
    finally:
        island.close()
        island.deleteLater()
        app.processEvents()
