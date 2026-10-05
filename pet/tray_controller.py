"""Own the tray menu and synchronize its checks with live pet and system state."""
from __future__ import annotations

from pathlib import Path
import logging
import sys
import weakref

import shiboken6
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QCursor, QIcon, QPainter
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import autostart
from .context_menus.menu_styles import apply_modern_menu_style
from .context_menus.menu_styles.modern import paint_modern_checks
from .context_menus.menu_styles.common import install_responsive_menu_style


class TrayMenu(QMenu):
    """Paint checks in the menu's own frame, including its first visible frame."""

    def paintEvent(self, event):  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        paint_modern_checks(self, painter)
        painter.end()


class TrayController(QObject):
    def __init__(self, shell) -> None:
        super().__init__()
        self.shell = shell
        self.menu: QMenu | None = None
        self._actions = []
        self._windows = weakref.WeakSet()
        self._autostart_enabled = False

    def _live_windows(self):
        return [inst.win for inst in self.shell.instances
                if inst.win is not None and shiboken6.isValid(inst.win)]

    def _observe(self, win) -> None:
        if win not in self._windows:
            win.installEventFilter(self)
            self._windows.add(win)

    def eventFilter(self, watched, event):  # noqa: N802 - Qt API
        if event.type() in (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.Close):
            self.sync_checks()
        return False

    def sync_checks(self) -> None:
        if self.menu is None:
            return
        windows = self._live_windows()
        for win in windows:
            self._observe(win)
        self.visible_action.setChecked(any(win.isVisible() for win in windows))
        self.visible_action.setEnabled(bool(windows))
        self.mouse_action.setChecked(any(inst.config.get("mouse_through", False)
                                        for inst in self.shell.instances if inst.win in windows))
        self._autostart_enabled = autostart.is_enabled()
        self.autostart_action.setChecked(self._autostart_enabled)
        self.menu.update()

    def toggle_visibility(self) -> None:
        windows = self._live_windows()
        visible = not any(win.isVisible() for win in windows)
        for win in windows:
            if visible:
                win.show()
            else:
                win.hide(notify=False)
        self.sync_checks()

    def _set_mouse_through(self, checked: bool) -> None:
        for win in self._live_windows():
            win.set_mouse_through(checked)
        self.sync_checks()

    def _toggle_autostart(self, _checked: bool) -> None:
        instance = self.shell.instance
        if instance is None:
            return
        # Use the last synchronized system state, independent of QAction's click state.
        enabled = not self._autostart_enabled
        written = autostart.set_enabled(enabled)
        instance.config.set("autostart_wanted", enabled if written else autostart.is_enabled())
        instance.config.save()
        # Config persistence and window notifications must not separate the success
        # message from the state the menu actually displays.
        self.sync_checks()
        actual = self._autostart_enabled
        ok = written and actual == enabled
        logging.info("Tray autostart value=%r key=%r requested=%s actual=%s checked=%s written=%s ok=%s",
                     autostart.VALUE_NAME, autostart.RUN_KEY, enabled, actual,
                     self.autostart_action.isChecked(), written, ok)
        win = self.shell.win
        if win is not None:
            message = (
                "开机自启已开启，下次登录时鲸鱼娘会来陪你。" if actual else "开机自启已关闭。"
            ) if ok else "开机自启写入失败，最终状态与请求不一致，请查看运行日志。"
            win.show_bubble(message, duration_ms=6000)

    def _activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_visibility()
        elif reason == QSystemTrayIcon.ActivationReason.Context and sys.platform == "win32":
            if self.menu is not None:
                self.menu.popup(QCursor.pos())
                self.menu.activateWindow()
                self.menu.setFocus(Qt.FocusReason.PopupFocusReason)

    def _hide_bubble(self) -> None:
        win = self.shell.win
        if win is not None:
            win.hide_speech_bubble()

    def build(self, win, tray: QSystemTrayIcon | None = None) -> QSystemTrayIcon:
        if tray is None:
            icon = QIcon(str(Path(__file__).resolve().parents[1] / "assets" / "icon.ico"))
            tray = QSystemTrayIcon(icon)
            tray.activated.connect(self._activated)
        menu = TrayMenu()
        self.visible_action = menu.addAction("显示 / 隐藏所有桌宠")
        self.visible_action.setCheckable(True)
        self.visible_action.triggered.connect(self.toggle_visibility)
        self.mouse_action = menu.addAction("鼠标穿透")
        self.mouse_action.setCheckable(True)
        self.mouse_action.triggered.connect(self._set_mouse_through)
        menu.addSeparator()
        self.autostart_action = menu.addAction("开机自启")
        self.autostart_action.setCheckable(True)
        self.autostart_action.triggered.connect(self._toggle_autostart)
        menu.addSeparator()
        menu.addAction("退出", self.shell.app.quit)
        menu.aboutToShow.connect(self._hide_bubble)
        menu.aboutToShow.connect(self.sync_checks)
        apply_modern_menu_style(menu, self.shell.config.get("context_menu_appearance", {}))
        install_responsive_menu_style(menu)
        menu.setObjectName("petTrayMenu")
        # Windows' native HMENU cannot paint the Qt check layer or menu QSS.
        tray.setContextMenu(None if sys.platform == "win32" else menu)
        old_menu = self.menu
        self.menu = menu
        # Retain QAction wrappers alongside QMenu to prevent premature Qt destruction.
        self._actions = menu.actions()
        self._observe(win)
        self.sync_checks()
        if old_menu is not None:
            old_menu.close()
            old_menu.deleteLater()
        tray.setToolTip("鲸鱼娘")
        tray.show()
        return tray

    def refresh(self) -> None:
        if self.shell.tray is not None and self.shell.win is not None:
            self.build(self.shell.win, tray=self.shell.tray)

    def shutdown(self) -> None:
        for win in tuple(self._windows):
            if shiboken6.isValid(win):
                win.removeEventFilter(self)
        self._windows.clear()
        if self.menu is not None:
            self.menu.close()
            self.menu.deleteLater()
            self.menu = None
        self._actions.clear()
        if self.shell.tray is not None:
            self.shell.tray.hide()
            self.shell.tray.deleteLater()
            self.shell.tray = None
