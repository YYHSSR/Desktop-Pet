import os
import types

import pytest
from datetime import datetime, timezone


def test_bubble_text_scale_row_persists(tmp_path, monkeypatch):
    """「气泡文字大小」设置行：默认 100%，改值保存并持久化，越界被配置清洗钳位。"""
    from PySide6.QtWidgets import QApplication

    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = QApplication.instance() or QApplication([])

    config = Config(tmp_path)
    assert config.get("bubble_text_scale") == 100

    dialog = settings_mod.ModernSettingsDialog(config,)
    try:
        assert dialog.bubble_text_scale_spin.value() == 100
        assert dialog.bubble_text_scale_spin.minimum() == 50
        assert dialog.bubble_text_scale_spin.maximum() == 300
        assert dialog.findChild(
            settings_mod.SettingRow, "settingRow_bubble_text_scale"
        ) is not None, "设置页必须有可发现的「气泡文字大小」行"
        dialog.bubble_text_scale_spin.setValue(180)
        assert dialog._write_config() is True
    finally:
        dialog.close()
        app.processEvents()
    assert Config(tmp_path).get("bubble_text_scale") == 180


def test_harness_autostart_toggle_retired(tmp_path):
    """「随桌宠启动 dsh 服务」已退役。"""
    from pet.config import Config

    config = Config(tmp_path)
    assert "harness_autostart" not in config.data


def test_settings_dialog_position_avoids_pet_window(tmp_path, monkeypatch):
    """设置窗口激活时不应遮挡桌宠：打开时移动到不与桌宠相交的位置。"""
    import pet.modern_settings_dialog as settings_mod
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication, QWidget

    from pet.config import Config

    app = QApplication.instance() or QApplication([])

    pet = QWidget()
    pet.setGeometry(QRect(100, 100, 200, 200))
    pet.show()
    app.processEvents()
    config = Config(tmp_path)
    dialog = settings_mod.ModernSettingsDialog(config, pet,)
    # 真实最小尺寸 720x500 在 offscreen 800x600 屏幕上无处可避，放宽以测试避让逻辑
    dialog.setMinimumSize(360, 260)
    dialog.resize(420, 320)
    dialog.show()
    app.processEvents()
    try:
        assert dialog._move_away_from(pet.geometry())
        app.processEvents()
        assert not dialog.geometry().intersects(pet.geometry())
    finally:
        dialog.close()
        pet.close()
        app.processEvents()


def test_menu_font_select_lists_system_fonts(tmp_path, monkeypatch):
    """UI 字体设置项应枚举系统可用字体，而不是硬编码少数几个。"""
    import pet.modern_settings_dialog as settings_mod
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    from pet.config import Config

    app = QApplication.instance() or QApplication([])

    config = Config(tmp_path)
    dialog = settings_mod.ModernSettingsDialog(config,)
    select = dialog.menu_font_select
    # 字体枚举延迟到事件循环空闲时填充（避免阻塞窗口打开）。
    # 测试直接同步触发填充，不等待 QTimer：QTest.qWait 的嵌套事件循环
    # 会触发 GC 析构残留测试对象，在 macOS/Windows CI 上均可致进程
    # abort（setParent_helper / QPA 平台层），同步调用则完全绕开。
    dialog._populate_menu_fonts()
    available = {select.itemData(i) for i in range(select.count())}
    system_families = set(QFontDatabase.families())
    assert "system" in available
    custom = available - {"system"}
    # 所有可选字体必须来自系统字体表
    assert custom <= system_families
    # 必须真正列出系统字体（而非只剩硬编码几项）；无系统字体的平台
    # （如 Windows offscreen CI）跳过数量断言
    if system_families:
        assert len(custom) >= 4
    dialog.close()
    app.processEvents()


def test_settings_first_paint_does_not_enumerate_system_fonts(tmp_path, monkeypatch):
    """系统字体枚举可能在 Windows 阻塞数秒，只能在用户展开字体选择器时执行。"""
    from PySide6.QtWidgets import QApplication

    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = QApplication.instance() or QApplication([])
    calls = []

    monkeypatch.setattr(
        settings_mod,
        "_system_font_families",
        lambda: calls.append("enumerated") or ("Regression Test Font",),
    )

    dialog = settings_mod.ModernSettingsDialog(Config(tmp_path),)
    dialog.show()
    app.processEvents()
    assert calls == [], "首次显示设置窗口时不应枚举全部系统字体"

    dialog.menu_font_select.showPopup()
    assert calls == ["enumerated"]
    dialog.menu_font_select._popup.close()
    dialog.close()
    app.processEvents()


def test_settings_save_preserves_custom_font_before_selector_is_opened(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = QApplication.instance() or QApplication([])

    config = Config(tmp_path)
    appearance = dict(config.get("context_menu_appearance"))
    appearance["ui_font"] = "Regression Custom Font"
    config.set("context_menu_appearance", appearance)

    dialog = settings_mod.ModernSettingsDialog(config,)
    assert dialog._menu_fonts_populated is False
    assert dialog.menu_font_select.currentData() == "Regression Custom Font"
    dialog._save()
    assert config.get("context_menu_appearance")["ui_font"] == "Regression Custom Font"
    app.processEvents()


def test_modern_select_reuses_one_popup_without_accumulating_children(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMenu

    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = QApplication.instance() or QApplication([])

    dialog = settings_mod.ModernSettingsDialog(Config(tmp_path),)
    select = dialog.menu_theme_select

    popup_ids = []
    for _ in range(3):
        select.showPopup()
        app.processEvents()
        popup_ids.append(id(select._popup))
        select._popup.close()
        app.processEvents()
        assert len(select.findChildren(QMenu)) == 1

    assert len(set(popup_ids)) == 1

    dialog.close()
    app.processEvents()


def test_dock_icon_row_platform_gated(tmp_path, monkeypatch):
    """「显示 Dock 图标」是 macOS 专属选项，其他平台不应显示。"""
    import sys

    import pet.modern_settings_dialog as settings_mod
    from PySide6.QtWidgets import QApplication

    from pet.config import Config

    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(sys, "platform", "win32")
    config = Config(tmp_path)
    dialog = settings_mod.ModernSettingsDialog(config,)
    assert dialog.findChild(settings_mod.SettingRow, "settingRow_dock_icon") is None
    dialog.close()
    monkeypatch.setattr(sys, "platform", "darwin")
    dialog2 = settings_mod.ModernSettingsDialog(config,)
    assert dialog2.findChild(settings_mod.SettingRow, "settingRow_dock_icon") is not None
    dialog2.close()
    app.processEvents()


def test_macos_hide_pet_respects_dock_icon_hidden_preference(tmp_path, monkeypatch):
    """macOS 关闭「显示 Dock 图标」后，隐藏桌宠不得再临时唤回 Dock 图标。

    issue #74：托盘（菜单栏）菜单已承担恢复入口（显示/隐藏、鼠标穿透、
    桌宠设置），因此隐藏桌宠应尊重用户关闭 Dock 图标的偏好，不再把
    activation policy 临时改回 Regular，也不写回配置。
    """
    import sys

    from unittest import mock

    from PySide6.QtWidgets import QWidget

    import pet.app
    from pet.config import Config
    from pet.window import PetWindow

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(pet.app, "_mac_set_dock_icon_visible", mock.Mock())

    for pref in (False, True):
        with mock.patch.object(QWidget, "hide") as mock_hide:
            win = PetWindow.__new__(PetWindow)
            win.cfg = Config(tmp_path)
            win.cfg.set("show_dock_icon", pref)
            PetWindow.hide(win, notify=False)
            mock_hide.assert_called_once()
            assert win.cfg.get("show_dock_icon") is pref
            pet.app._mac_set_dock_icon_visible.assert_not_called()


def test_windows_settings_has_no_orphan_macos_dock_toggle(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod.sys, "platform", "win32")

    config = Config(tmp_path)
    config.set("show_dock_icon", False)
    dialog = settings_mod.ModernSettingsDialog(config,)

    assert dialog.dock_icon_check is None
    assert not any(
        isinstance(child, settings_mod.ToggleSwitch)
        for child in dialog.children()
    ), "所有开关都必须被设置行接管，不能游离在窗口左上角"
    assert dialog.findChild(
        settings_mod.SettingRow, "settingRow_auto_hide_fullscreen"
    ) is not None
    assert dialog.findChild(
        settings_mod.SettingRow, "settingRow_stream_capture"
    ) is None

    dialog._save()
    assert config.get("show_dock_icon") is False
    app.processEvents()


# Linux 回归：Windows 专属开关不得在非 Windows 平台创建后游离到设置窗左上角。
def test_linux_settings_has_no_orphan_windows_cursor_passthrough_toggle(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod.sys, "platform", "linux")

    dialog = settings_mod.ModernSettingsDialog(Config(tmp_path),)

    assert dialog.cursor_hidden_passthrough_check is None
    assert not any(
        isinstance(child, settings_mod.ToggleSwitch)
        for child in dialog.children()
    ), "所有开关都必须被设置行接管，不能游离在窗口左上角"

    dialog.close()
    app.processEvents()


def test_hide_pet_notifies_and_dock_click_restores(tmp_path, monkeypatch):
    """用户主动隐藏：弹托盘提示 + macOS 点击 Dock 图标恢复桌宠。"""
    import sys

    from unittest import mock

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    import pet.window as window_mod
    from pet.config import Config

    monkeypatch.setattr(sys, "platform", "darwin")
    app = QApplication.instance() or QApplication([])
    win = window_mod.PetWindow.__new__(window_mod.PetWindow)
    win.cfg = Config(tmp_path)
    notified = []
    win.on_hidden = lambda: notified.append(True)

    with mock.patch.object(QWidget, "hide"), mock.patch.object(
        window_mod.PetWindow, "show"
    ) as mock_show, mock.patch.object(app, "applicationStateChanged") as m_sig:
        window_mod.PetWindow.hide(win)
        assert notified, "用户主动隐藏应触发托盘提示回调"
        # 隐藏后 arm Dock 点击恢复监听
        m_sig.connect.assert_called_once()
        # 点击 Dock 图标 → 应用激活 → 自动恢复桌宠
        window_mod.PetWindow._restore_on_dock_reactivate(
            win, Qt.ApplicationState.ApplicationActive
        )
        mock_show.assert_called_once()
        # 一次性监听：再次激活不再恢复
        mock_show.reset_mock()
        window_mod.PetWindow._restore_on_dock_reactivate(
            win, Qt.ApplicationState.ApplicationActive
        )
        mock_show.assert_not_called()


def test_hide_pet_internal_replacement_skips_notify(tmp_path, monkeypatch):
    """角色切换等内部替换隐藏：不弹提示、不 arm Dock 恢复监听。"""
    import sys

    from unittest import mock

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    import pet.window as window_mod
    from pet.config import Config

    monkeypatch.setattr(sys, "platform", "darwin")
    app = QApplication.instance() or QApplication([])
    win = window_mod.PetWindow.__new__(window_mod.PetWindow)
    win.cfg = Config(tmp_path)
    win.on_hidden = lambda: pytest.fail("内部替换不应弹提示")

    with mock.patch.object(QWidget, "hide"), mock.patch.object(
        window_mod.PetWindow, "show"
    ) as mock_show, mock.patch.object(app, "applicationStateChanged") as m_sig:
        window_mod.PetWindow.hide(win, notify=False)
        m_sig.connect.assert_not_called()
        window_mod.PetWindow._restore_on_dock_reactivate(
            win, Qt.ApplicationState.ApplicationActive
        )
        mock_show.assert_not_called()


def test_animation_icon_applier_updates_action_and_cleans_worker():
    """图标解码完成回调须经 GUI 线程槽更新 QAction，并清理 worker 记录。

    回归背景：ready 信号此前直连普通闭包，setIcon/update 在 QThreadPool
    工作线程执行（Qt 未定义行为）；现经 _AnimationIconApplier（挂在
    submenu 下、随菜单生命周期）队列投递回 GUI 线程。
    """
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QMenu

    from pet.context_menus.shared import _AnimationIconApplier

    app = QApplication.instance() or QApplication([])
    menu = QMenu()
    submenu = QMenu(menu)
    submenu._animation_icon_workers = []
    action = submenu.addAction("测试动画")
    pump_calls = []
    worker = object()

    # 无图（解码失败/空帧）：不 setIcon，但必须移除 worker 并继续泵任务
    applier = _AnimationIconApplier(
        submenu, action, worker, lambda: pump_calls.append(1), parent=submenu
    )
    applier.on_ready(None)
    assert submenu._animation_icon_workers == []
    assert pump_calls == [1]

    # 有效图：菜单不可见（offscreen）时更新图标
    image = QImage(16, 16, QImage.Format.Format_ARGB32)
    image.fill(0xFF3366FF)
    submenu._animation_icon_workers.append(worker)
    applier2 = _AnimationIconApplier(
        submenu, action, worker, lambda: pump_calls.append(2), parent=submenu
    )
    applier2.on_ready(image)
    assert submenu._animation_icon_workers == []
    assert pump_calls == [1, 2]
    assert not action.icon().isNull()

    # 菜单已销毁：槽必须静默返回，不访问已删 C++ 对象
    menu.deleteLater()
    app.processEvents()


def test_spawned_children_are_reaped_after_exit():
    """孵化的子进程退出后必须从登记表回收（防 POSIX 僵尸 / 句柄泄漏）。"""
    import sys

    import pet.instance_launcher as launcher

    before = list(launcher._SPAWNED_CHILDREN)
    try:
        proc = launcher.launch_new_pet(offset_index=99)
        assert proc in launcher._SPAWNED_CHILDREN
        # 触发回收：活着的子进程必须保留
        launcher._reap_children()
        assert proc in launcher._SPAWNED_CHILDREN
        # 退出后必须被回收
        proc.terminate()
        import time
        deadline = time.time() + 10
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.05)
        launcher._reap_children()
        assert proc not in launcher._SPAWNED_CHILDREN
    finally:
        for proc in list(launcher._SPAWNED_CHILDREN):
            if proc not in before and proc.poll() is None:
                proc.terminate()
        launcher._SPAWNED_CHILDREN[:] = before


def test_modern_settings_close_autosaves(tmp_path, monkeypatch):
    """直接关闭（X）新版设置也必须落盘，不能只靠「保存并退出」。

    回归背景：用户改完字体颜色/气泡方案后直接关窗，修改全部丢失。
    """
    from PySide6.QtWidgets import QApplication

    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = QApplication.instance() or QApplication([])

    config = Config(tmp_path)
    dialog = settings_mod.ModernSettingsDialog(config,)
    dialog.bubble_style_select.setCurrentData("breath_bubble")
    dialog.light_background_picker.edit.setText("#123456")
    dialog.close()  # 不点「保存并退出」
    app.processEvents()
    assert config.get("self_talk_bubble_style") == "breath_bubble"
    assert config.get("context_menu_appearance", {}).get("light_background") == "#123456"
    # 重载磁盘验证
    reloaded = Config(tmp_path)
    assert reloaded.get("self_talk_bubble_style") == "breath_bubble"


def test_settings_stylesheet_has_dark_overrides(monkeypatch):
    """深色系统下新版设置必须追加深色覆盖段（白底白字不可读问题）。"""
    from pet.modern_settings_dialog import _settings_stylesheet

    monkeypatch.setattr("pet.settings_theme_qss._system_dark", lambda: True)
    qss = _settings_stylesheet()
    assert "background: #202024" in qss
    assert "color: #e4e4e9" in qss
    monkeypatch.setattr("pet.settings_theme_qss._system_dark", lambda: False)
    qss_light = _settings_stylesheet()
    assert "background: #202024" not in qss_light
    # 浅色也必须显式给按钮补文字色（防深色 palette 白字）
    assert "QPushButton { color: #202020; }" in qss_light


def test_settings_window_uses_the_explicit_dark_appearance_on_a_light_system(
    tmp_path, monkeypatch,
):
    from PySide6.QtWidgets import QApplication

    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_system_dark", lambda: False)

    config = Config(tmp_path)
    config.set("context_menu_appearance", {"theme": "dark"})

    dialog = settings_mod.ModernSettingsDialog(config,)
    assert "QDialog { background: #202024" in dialog.styleSheet()

    dialog.close()
    app.processEvents()


def test_settings_window_rethemes_immediately_with_the_appearance_selector(
    tmp_path, monkeypatch,
):
    from PySide6.QtWidgets import QApplication

    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("pet.settings_theme_qss._system_dark", lambda: False)

    dialog = settings_mod.ModernSettingsDialog(Config(tmp_path),)
    assert "QDialog { background: #202024" not in dialog.styleSheet()

    dialog.menu_theme_select.setCurrentData("dark")
    app.processEvents()
    assert "QDialog { background: #202024" in dialog.styleSheet()

    dialog.menu_theme_select.setCurrentData("light")
    app.processEvents()
    assert "QDialog { background: #202024" not in dialog.styleSheet()

    dialog.close()
    app.processEvents()


def test_modern_settings_finished_refreshes_even_on_rejected(tmp_path, monkeypatch):
    """新版设置直接关闭（Rejected）也必须把改动应用到桌宠。

    回归背景：只有 Accepted（保存并退出）才刷新；X 关闭时 closeEvent 已
    自动保存，但桌宠 scale/拖动物理等不生效。
    """
    from PySide6.QtWidgets import QApplication

    import pet.app as app_mod
    from pet.app import AppShell, PetInstance
    from pet.config import Config

    app = QApplication.instance() or QApplication([])
    owner = PetInstance.__new__(PetInstance)
    owner.shell = AppShell.__new__(AppShell)
    owner.modern_settings_dialog = object()
    refreshed = []

    class FakeWin:
        def refresh_pet_settings(self):
            refreshed.append(1)

        def set_bubble_suppressed(self, _suppressed):
            pass

    owner.win = FakeWin()
    owner.config = Config(tmp_path)
    owner.shell._sync_dynamic_island = lambda: None
    owner.shell._sync_festival_service = lambda: None  # 节日提醒同样懒启停（其内部会连带同步报时通道）
    owner._refresh_chat_windows = lambda: None
    owner._sync_animation_prewarm = lambda: None
    monkeypatch.setattr(app_mod, "_mac_set_dock_icon_visible", lambda *a, **k: None)
    PetInstance._modern_settings_finished(owner, 0)  # QDialog.Rejected（X 关闭）
    assert refreshed == [1], "Rejected 关闭也必须刷新桌宠"


def test_modern_settings_save_warns_on_failure(tmp_path, monkeypatch):
    """保存失败（此处置目标为目录迫使 os.replace 失败）时提示用户+配置路径。"""
    from PySide6.QtWidgets import QApplication

    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = QApplication.instance() or QApplication([])

    warnings = []
    monkeypatch.setattr(settings_mod.QMessageBox, "warning", lambda *a, **k: warnings.append(a))
    config = Config(tmp_path)
    config.path.mkdir(parents=True, exist_ok=True)  # 目标为目录，os.replace 必失败
    dialog = settings_mod.ModernSettingsDialog(config,)
    dialog._save()
    assert any("保存失败" in str(x[1]) for x in warnings)
    assert any(str(config.path) in str(x[2]) for x in warnings)
    dialog.close()
    app.processEvents()


# --- macOS Dock recovery menu regression (2026-09-03) ---
