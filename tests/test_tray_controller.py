"""Tray checks must reflect actions, external changes and failed system writes."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from pet import autostart
from pet.app import AppShell, PetInstance
from pet.config import Config


class PetSurface(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.messages = []

    def hide(self, *, notify=True):
        super().hide()

    def hide_speech_bubble(self):
        pass

    def show_bubble(self, text, **kwargs):
        self.messages.append(text)

    def set_mouse_through(self, checked):
        self.config.set("mouse_through", checked)


@pytest.fixture
def tray_state(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    system = SimpleNamespace(enabled=False, fail=False,
                             read=autostart.is_enabled, write=autostart.set_enabled)
    monkeypatch.setattr(autostart, "is_enabled", lambda: system.enabled)

    def set_enabled(enabled):
        if system.fail:
            return False
        system.enabled = enabled
        return True

    monkeypatch.setattr(autostart, "set_enabled", set_enabled)
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: None)
    monkeypatch.setattr(QSystemTrayIcon, "showMessage", lambda *args: None)
    config = Config(tmp_path)
    shell = AppShell(app, config)
    primary = PetSurface(config)
    shell.instance.win = primary
    second = PetInstance(shell, Config(tmp_path, instance_id="slot-1"))
    second.win = PetSurface(second.config)
    shell._instances.append(second)
    primary.show()
    shell.tray = shell.tray_controller.build(primary)
    try:
        yield shell, system
    finally:
        shell.tray_controller.shutdown()
        for instance in shell.instances:
            instance.win.close()
            instance.collision_ipc.stop()
        app.processEvents()


def test_visibility_check_toggles_all_pets_and_follows_external_changes(tray_state):
    shell, _ = tray_state
    controller = shell.tray_controller
    assert controller.visible_action.isChecked()
    controller.visible_action.trigger()
    assert not controller.visible_action.isChecked()
    assert not any(instance.win.isVisible() for instance in shell.instances)
    controller.visible_action.trigger()
    assert controller.visible_action.isChecked()
    assert all(instance.win.isVisible() for instance in shell.instances)
    for instance in shell.instances:
        instance.win.hide()
    assert not controller.visible_action.isChecked()
    shell.instances[1].win.show()
    assert controller.visible_action.isChecked()


def test_autostart_check_uses_system_state_and_recovers_failed_write(tray_state):
    shell, system = tray_state
    action = shell.tray_controller.autostart_action
    assert not action.isChecked()
    action.trigger()
    assert system.enabled and action.isChecked()
    assert shell.config.get("autostart_wanted") is True
    action.trigger()
    assert not system.enabled and not action.isChecked()
    assert shell.config.get("autostart_wanted") is False
    system.enabled = True
    shell.tray_controller.menu.aboutToShow.emit()
    assert action.isChecked()
    system.fail = True
    action.trigger()
    assert system.enabled and action.isChecked()
    assert "写入失败" in shell.win.messages[-1]


def test_mouse_check_updates_without_writing_on_menu_open(tray_state):
    shell, _ = tray_state
    action = shell.tray_controller.mouse_action
    action.trigger()
    assert action.isChecked()
    assert all(instance.config.get("mouse_through") for instance in shell.instances)
    for instance in shell.instances:
        instance.config.set("mouse_through", False)
    shell.tray_controller.menu.aboutToShow.emit()
    assert not action.isChecked()
    assert not any(instance.config.get("mouse_through") for instance in shell.instances)


def test_autostart_click_uses_the_selected_state_when_registry_read_changes(tray_state, monkeypatch):
    shell, system = tray_state
    controller = shell.tray_controller
    system.enabled = True
    controller.sync_checks()
    reads = iter((False,))
    monkeypatch.setattr(autostart, "is_enabled", lambda: next(reads, system.enabled))
    controller.autostart_action.trigger()
    assert system.enabled is False
    assert controller.autostart_action.isChecked() is False
    assert "已关闭" in shell.win.messages[-1]


def test_autostart_disables_even_if_action_lost_its_check(tray_state):
    shell, system = tray_state
    controller = shell.tray_controller
    controller.autostart_action.trigger()
    assert system.enabled is True
    controller.autostart_action.setChecked(False)
    controller.autostart_action.trigger()
    assert system.enabled is False
    assert controller.autostart_action.isChecked() is False
    assert "已关闭" in shell.win.messages[-1]


def test_autostart_does_not_report_success_when_state_changes_during_save(tray_state, monkeypatch):
    shell, system = tray_state
    original_save = shell.config.save

    def save_then_remove_registration():
        result = original_save()
        system.enabled = False
        return result

    monkeypatch.setattr(shell.config, "save", save_then_remove_registration)
    shell.tray_controller.autostart_action.trigger()
    assert shell.tray_controller.autostart_action.isChecked() is False
    assert shell.win.messages == ["开机自启写入失败，最终状态与请求不一致，请查看运行日志。"]


def test_first_frame_draws_checks_without_processing_events(tray_state):
    shell, system = tray_state
    system.enabled = True
    controller = shell.tray_controller
    menu = controller.menu
    menu.popup(QPoint(20, 20))
    try:
        image = menu.grab().toImage().scaled(menu.size())
        for action in (controller.visible_action, controller.autostart_action):
            rect = menu.actionGeometry(action)
            assert any((color := image.pixelColor(x, y)).blue() > 150 and color.red() < 60
                       for y in range(rect.top(), rect.bottom() + 1)
                       for x in range(menu.width() - 30, menu.width() - 10))
    finally:
        menu.close()


def test_menu_replacement_releases_old_menu_and_retains_current_actions(tray_state):
    import shiboken6

    shell, _ = tray_state
    controller = shell.tray_controller
    old = controller.menu
    controller.refresh()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(old)
    assert all(shiboken6.isValid(action) for action in controller.menu.actions())
    controller.visible_action.trigger()
    assert not controller.visible_action.isChecked()


def test_checked_actions_draw_the_visible_tick(tray_state):
    shell, system = tray_state
    controller = shell.tray_controller
    system.enabled = True
    menu = controller.menu
    menu.popup(QPoint(20, 20))
    QApplication.processEvents()

    def blue_pixels(action):
        rect = menu.actionGeometry(action)
        image = menu.grab().toImage().scaled(menu.size())
        return sum(1 for y in range(rect.top(), rect.bottom() + 1)
                   for x in range(menu.width() - 30, menu.width() - 10)
                   if (color := image.pixelColor(x, y)).blue() > 150 and color.red() < 60)

    try:
        assert blue_pixels(controller.visible_action) > 10
        assert blue_pixels(controller.autostart_action) > 10
        controller.visible_action.trigger()
        controller.autostart_action.trigger()
        QApplication.processEvents()
        assert blue_pixels(controller.visible_action) == 0
        assert blue_pixels(controller.autostart_action) == 0
    finally:
        menu.close()


@pytest.mark.skipif(not autostart._IS_WIN, reason="Windows registry integration")
@pytest.mark.parametrize("frozen", [False, True])
def test_actual_registry_and_mouse_click_toggle_twice(tray_state, monkeypatch, frozen):
    import sys
    import uuid
    import winreg
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    shell, system = tray_state
    # Use a unique non-Run key, so this test cannot change the user's login items.
    key_path = rf"Software\DesktopPetTest-{uuid.uuid4().hex}"
    monkeypatch.setattr(autostart, "is_enabled", system.read)
    monkeypatch.setattr(autostart, "set_enabled", system.write)
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(autostart, "RUN_KEY", key_path)
    monkeypatch.setattr(autostart, "VALUE_NAME", "pet-test")
    monkeypatch.setattr(QSystemTrayIcon, "showMessage", lambda *args: None)
    controller = shell.tray_controller
    try:
        for expected in (True, False, True, False):
            controller.menu.popup(QPoint(20, 20))
            QApplication.processEvents()
            QTest.mouseClick(controller.menu, Qt.MouseButton.LeftButton,
                             pos=controller.menu.actionGeometry(controller.autostart_action).center())
            QApplication.processEvents()
            assert autostart.is_enabled() is expected
            controller.menu.popup(QPoint(20, 20))
            QApplication.processEvents()
            assert controller.autostart_action.isChecked() is expected
            assert shell.config.get("autostart_wanted") is expected
            image = controller.menu.grab().toImage().scaled(controller.menu.size())
            rect = controller.menu.actionGeometry(controller.autostart_action)
            pixels = sum(1 for y in range(rect.top(), rect.bottom() + 1)
                         for x in range(controller.menu.width() - 30, controller.menu.width() - 10)
                         if (color := image.pixelColor(x, y)).blue() > 150 and color.red() < 60)
            assert (pixels > 10) is expected
            if expected and frozen:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    command, _ = winreg.QueryValueEx(key, "pet-test")
                assert command == f'"{autostart.Path(sys.executable).resolve()}" --slot 0'
        assert "已关闭" in shell.win.messages[-1]
    finally:
        controller.menu.close()
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        except FileNotFoundError:
            pass
