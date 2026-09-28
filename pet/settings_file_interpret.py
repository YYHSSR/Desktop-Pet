# -*- coding: utf-8 -*-
"""设置页「文件识别」域：拖文件解读的控件创建 / 行装配 / 保存。

modern_settings_dialog.py 行数预算已无余量，本域的控件与行全部在本模块
构建，对话框只做三处接线：控件安装（_build_file_interpret_controls）、
域导航挂页（_rebuild_domain_navigation）、保存委托（_write_config）。
"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from .config import _default_file_interpret_data
from .settings_widgets import BrowserDoubleSpinBox, SettingRow, ToggleSwitch

# 与 Config 归一化区间同源（config.py file_interpret 段）
_PROGRESS_INTERVAL_RANGE = (5.0, 120.0)
_PROGRESS_INTERVAL_DEFAULT = 15.0


def _clamp_interval(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _PROGRESS_INTERVAL_DEFAULT
    return max(_PROGRESS_INTERVAL_RANGE[0], min(_PROGRESS_INTERVAL_RANGE[1], number))


def create_file_interpret_controls(dialog) -> None:
    """在对话框上创建本域控件（已废弃/移除，脱离界面树）。"""
    if getattr(dialog, "file_interpret_enabled_check", None) is not None:
        return
    defaults = _default_file_interpret_data()
    cfg = dialog.config.get("file_interpret") or {}
    if not isinstance(cfg, dict):
        cfg = {}

    dialog.file_interpret_enabled_check = ToggleSwitch(None)
    dialog.file_interpret_enabled_check.setChecked(bool(cfg.get("enabled", defaults["enabled"])))

    dialog.file_interpret_interval_spin = BrowserDoubleSpinBox(None)
    dialog.file_interpret_interval_spin.setRange(*_PROGRESS_INTERVAL_RANGE)
    dialog.file_interpret_interval_spin.setDecimals(0)
    dialog.file_interpret_interval_spin.setSuffix(" 秒")
    dialog.file_interpret_interval_spin.setValue(
        _clamp_interval(cfg.get("progress_interval_seconds", defaults["progress_interval_seconds"]))
    )


def build_file_interpret_rows(dialog) -> list[SettingRow]:
    """「文件识别」已彻底移除，不向界面贡献任何 SettingRow。"""
    return []


def build_file_interpret_page(dialog) -> QWidget | None:
    """「文件识别」域整页内容（已移除）。"""
    return None


def save_file_interpret_settings(dialog) -> None:
    """_write_config 委托：持久化强制设为禁用。"""
    dialog.config.set("file_interpret", {"enabled": False, "progress_interval_seconds": 15.0})
