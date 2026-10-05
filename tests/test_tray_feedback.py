"""Tray commands, readable feedback and retirement of unused settings."""
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from pet import autostart
from pet.agent_link import AgentLinkManager
from pet.app import AppShell, PetInstance
from pet.config import Config
from pet.modern_settings_dialog import ModernSettingsDialog, SettingRow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_autostart_query_is_read_only_for_frozen_app(monkeypatch):
    from tests.test_autostart import _force_win
    fake = _force_win(monkeypatch)
    fake.values[autostart.VALUE_NAME] = '"C:/pet/whale.exe" --slot 0'
    original = dict(fake.values)
    monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
    assert autostart.is_enabled()
    assert fake.values == original


def test_autostart_query_handles_denied_registry_read(monkeypatch):
    from tests.test_autostart import _force_win
    fake = _force_win(monkeypatch)
    monkeypatch.setattr(fake, "OpenKey", lambda *_: (_ for _ in ()).throw(PermissionError()))
    assert autostart.is_enabled() is False


def test_autostart_enable_creates_missing_run_key(monkeypatch):
    from tests.test_autostart import _force_win
    fake = _force_win(monkeypatch)
    original_open = fake.OpenKey
    state = {"created": False}

    def open_key(*args):
        if not state["created"]:
            raise FileNotFoundError()
        return original_open(*args)

    def create_key(*args):
        state["created"] = True
        return original_open(*args)

    monkeypatch.setattr(fake, "OpenKey", open_key)
    monkeypatch.setattr(fake, "CreateKeyEx", create_key)
    assert autostart.enable() is True
    assert autostart.is_enabled() is True


def test_tray_autostart_click_confirms_state_and_has_visible_checks(app, tmp_path, monkeypatch):
    from pet import app as app_module
    state = {"enabled": False}
    writes, messages = [], []
    monkeypatch.setattr(app_module.autostart_mod, "is_enabled", lambda: state["enabled"])

    def set_enabled(value):
        writes.append(value)
        state["enabled"] = value
        return True

    monkeypatch.setattr(app_module.autostart_mod, "set_enabled", set_enabled)
    cfg = Config(tmp_path)
    win = SimpleNamespace(hide_speech_bubble=lambda: None,
                          show_bubble=lambda text, **kw: messages.append(text))
    instance = object.__new__(PetInstance)
    instance.win, instance.config = win, cfg
    shell = object.__new__(AppShell)
    shell.app, shell.config, shell._instances, shell.instance = app, cfg, [instance], instance
    shell._tray_menu, shell._tray_submenus, shell._tray_actions = None, [], []
    tray = shell._build_tray(win)
    try:
        menu = shell._tray_menu
        assert tray.toolTip() == "鲸鱼娘"
        assert not tray.icon().isNull()
        assert menu.property("paintChecksOnRight")
        auto = next(a for a in menu.actions() if a.text() == "开机自启")
        auto.trigger()
        assert auto.isChecked() and autostart.is_enabled()
        assert messages[-1] == "开机自启已开启，下次登录时鲸鱼娘会来陪你。"
        auto.trigger()
        assert not auto.isChecked() and not autostart.is_enabled()
        assert messages[-1] == "开机自启已关闭。"
        menu.aboutToShow.emit()
        assert writes == [True, False]
    finally:
        tray.hide()
        tray.deleteLater()
        menu.close()
        menu.deleteLater()
        app.processEvents()


def test_tray_toggle_reads_system_state_when_checked_argument_is_stale(app, tmp_path, monkeypatch):
    from pet import app as app_module
    state = {"enabled": False}
    writes, changes = [], []
    monkeypatch.setattr(app_module.autostart_mod, "is_enabled", lambda: state["enabled"])

    def write(enabled):
        writes.append(enabled)
        state["enabled"] = enabled
        return True

    monkeypatch.setattr(app_module.autostart_mod, "set_enabled", write)
    cfg = Config(tmp_path)
    win = SimpleNamespace(hide_speech_bubble=lambda: None, show_bubble=lambda *_a, **_kw: None)
    instance = object.__new__(PetInstance)
    instance.win, instance.config = win, cfg
    shell = object.__new__(AppShell)
    shell.app, shell.config, shell._instances, shell.instance = app, cfg, [instance], instance
    shell._tray_menu, shell._tray_submenus, shell._tray_actions = None, [], []
    tray = shell._build_tray(win)
    menu = shell._tray_menu
    try:
        auto = next(a for a in menu.actions() if a.text() == "开机自启")
        auto.changed.connect(lambda: changes.append(auto.isChecked()))
        auto.triggered[bool].emit(True)
        assert auto.isChecked() and state["enabled"]
        auto.triggered[bool].emit(True)
        assert not auto.isChecked() and not state["enabled"]
        assert writes == [True, False]
        assert changes == [True, False]
    finally:
        tray.hide()
        tray.deleteLater()
        menu.close()
        menu.deleteLater()
        app.processEvents()


def test_menu_greeting_shows_cartoon_images_without_immediate_repeat(app, tmp_path):
    from tests.test_pet_interaction_locks import _make_win
    win = _make_win(app, tmp_path, self_talk_enabled=False)
    try:
        win.show()
        app.processEvents()
        win.respond_to_menu_click()
        bubble = win._speech_bubble
        assert bubble.isVisible()
        assert bubble._content_kind == "image"
        assert bubble._raw_text == ""
        first = win._menu_response_image
        win.respond_to_menu_click()
        assert bubble._content_kind == "image"
        assert win._menu_response_image != first
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_windows_tray_context_activation_opens_the_styled_qt_menu(app, tmp_path, monkeypatch):
    from pet import app as app_module
    from PySide6.QtWidgets import QSystemTrayIcon
    monkeypatch.setattr(app_module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(app_module.autostart_mod, "is_enabled", lambda: True)
    cfg = Config(tmp_path)
    instance = SimpleNamespace(config=cfg, win=SimpleNamespace(hide_speech_bubble=lambda: None))
    shell = object.__new__(AppShell)
    shell.app, shell.config, shell._instances, shell.instance = app, cfg, [instance], instance
    shell._tray_menu, shell._tray_submenus, shell._tray_actions = None, [], []
    tray = shell._build_tray(instance.win)
    menu = shell._tray_menu
    try:
        tray.activated.emit(QSystemTrayIcon.ActivationReason.Context)
        app.processEvents()
        assert tray.contextMenu() is None
        assert menu.isVisible()
        auto = next(a for a in menu.actions() if a.text() == "开机自启")
        assert auto.isChecked()
        assert menu._modern_check_layer.isVisible()
    finally:
        tray.hide()
        tray.deleteLater()
        menu.close()
        menu.deleteLater()
        app.processEvents()


def test_failed_autostart_does_not_save_requested_enabled_state(app, tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "set_enabled", lambda _value: False)
    monkeypatch.setattr(autostart, "is_enabled", lambda: False)
    cfg = Config(tmp_path)
    instance = object.__new__(PetInstance)
    instance.config, instance.win = cfg, SimpleNamespace(show_bubble=lambda *_a, **_kw: None)
    assert instance._set_autostart(True) is False
    assert Config(tmp_path).get("autostart_wanted") is False


def test_todo_and_advanced_pattern_preferences_are_retired(app, tmp_path):
    cfg = Config(tmp_path)
    cfg.set("todo_reminder_enabled", True)
    cfg.set("todo_reminder_lead_minutes", 9)
    cfg.set("agent_link", {**cfg.get("agent_link"), "pattern_detect": False, "pattern_w6_control": 19})
    cfg.save()
    cfg = Config(tmp_path)
    assert "todo_reminder_enabled" not in cfg.data
    assert "todo_reminder_lead_minutes" not in cfg.data
    assert not any(k.startswith("pattern_") for k in cfg.get("agent_link"))
    dialog = ModernSettingsDialog(cfg)
    try:
        rows = [r.objectName() for r in dialog.findChildren(SettingRow)]
        assert not any("todo_reminder" in k or "pattern_" in k for k in rows)
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("duration", [2600, 3000, 4500])
def test_link_bubble_stays_two_seconds_longer(app, tmp_path, duration):
    seen = []
    cfg = Config(tmp_path)
    win = SimpleNamespace(show_bubble=lambda text, **kw: seen.append(kw["duration_ms"]))
    manager = AgentLinkManager(win, cfg)
    try:
        manager._show_link_bubble("ChatGPT 正在工作", important=False, duration_ms=duration)
        assert seen == [duration + 2000]
    finally:
        manager.shutdown()


def test_greeting_header_has_keyboard_action_and_calls_pet_response(app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMenu, QPushButton
    from pet.context_menus.pet_header import add_pet_greeting
    seen = []
    menu = QMenu()
    pet = SimpleNamespace(respond_to_menu_click=lambda: seen.append("responded"))
    try:
        action = add_pet_greeting(menu, pet)
        button = action.defaultWidget()
        assert isinstance(button, QPushButton)
        assert "请点击" in button.text()
        assert action.text() == "厉害了我的鲸"
        button.show()
        button.setFocus()
        QTest.keyClick(button, Qt.Key.Key_Space)
        assert seen == ["responded"]
    finally:
        menu.close()
        menu.deleteLater()
        app.processEvents()
