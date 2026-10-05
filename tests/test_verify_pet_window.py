# -*- coding: utf-8 -*-
"""打包冒烟对桌宠窗口的判定：Tool 窗口算成功，引导错误框算失败。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load():
    script = REPO / "scripts" / "verify_pet_window.py"
    spec = importlib.util.spec_from_file_location("verify_pet_window", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_pet_window"] = module
    spec.loader.exec_module(module)
    return module


def test_qt_tool_window_is_a_successful_pet_launch_even_after_auto_hide():
    module = _load()
    shown = [
        ("Qt6112QWindowToolSaveBits", "dsh-pet-standalone-webm-chat", True),
        ("Qt6112ThemeChangeObserverWindow", "", False),
        ("IME", "Default IME", False),
    ]
    hidden = [("Qt6112QWindowToolSaveBits", "dsh-pet-standalone-webm-chat", False)]
    assert module.classify_process_windows(shown) == "ok"
    assert module.classify_process_windows(hidden) == "ok"


def test_hidden_qt_helper_alone_is_not_a_pet_window():
    module = _load()
    rows = [("Qt6112ThemeChangeObserverWindow", "", False)]
    assert module.classify_process_windows(rows) == "missing"


def test_bootloader_dialog_without_qt_window_is_a_startup_failure():
    module = _load()
    rows = [("#32770", "Fatal Error!", True)]
    assert module.classify_process_windows(rows) == "bootloader"
