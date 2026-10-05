# -*- coding: utf-8 -*-
"""互动竖排卡片、搜索、侧栏归属和设置行可达性回归。"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

EXPECTED_SIDEBAR = [
    "常规", "桌宠", "互动", "菜单", "自动化与联动",
]
# 标签键/名：键给代码（稳定），名给用户（可读）。顺序 = 使用顺序。

# 每组行各自应该落在哪个标签
ROW_GROUPS = {
    "click": (
        "click_self_talk",
    ),
    "self_talk": (
        "self_talk_bubble_style", "self_talk", "self_talk_duration", "self_talk_min",
        "self_talk_max", "self_talk_texts", "self_talk_images", "self_talk_image_scale",
        "self_talk_image_chance",
    ),
}


def _qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(tmp_path, monkeypatch):
    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    app = _qapp()

    dlg = settings_mod.ModernSettingsDialog(Config(tmp_path),)
    yield dlg
    dlg.close()
    app.processEvents()


def _interaction_page(dialog):
    index = next(
        i for i in range(dialog.sidebar.count()) if dialog.sidebar.item(i).text() == "互动"
    )
    return dialog.pages.widget(index)


def _row(dialog, key: str):
    from pet.modern_settings_dialog import SettingRow

    found = dialog.findChild(SettingRow, f"settingRow_{key}")
    assert found is not None, f"缺少设置行 {key}"
    return found


def test_retired_cost_and_balance_settings_are_absent(dialog):
    from pet.modern_settings_dialog import SettingRow

    for key in ("click_balance", "agent_cost", "balance_refresh", "balance_tier_mode",
                "balance_tier_peak", "balance_tier_idle", "balance_tier_color"):
        assert dialog.findChild(SettingRow, f"settingRow_{key}") is None
    dialog._search_settings("余额")
    assert [row.objectName() for row in dialog._search_matches] == []


def test_interaction_domain_uses_vertical_sections_like_general(dialog):
    """互动域直接使用竖排卡片布局（类似常规设置），取消页内 Tab。"""
    from pet.settings_widgets import SettingsSection, SettingsTabContainer

    assert [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())] == EXPECTED_SIDEBAR

    page = _interaction_page(dialog)
    tabs = page.findChild(SettingsTabContainer, "settingsTaskTabs")
    assert tabs is None, "互动域已取消页内 Tab，改为类似常规设置的竖排卡片布局"

    sections = page.findChildren(SettingsSection)
    titles = [s.findChild(pytest.importorskip("PySide6.QtWidgets").QLabel, "sectionTitle").text() for s in sections]
    assert titles == ["点击反馈", "自言自语"]


def test_every_interaction_row_is_in_interaction_page_and_reachable(dialog):
    """每行都在互动域的对应组内。"""
    page = _interaction_page(dialog)
    dialog.self_talk_check.setChecked(True)
    dialog.click_self_talk_check.setChecked(True)

    for keys in ROW_GROUPS.values():
        for key in keys:
            row = _row(dialog, key)
            assert page.isAncestorOf(row) is True, f"{key} 不在互动页内"


def test_search_jumps_to_interaction_domain(dialog):
    """搜索互动行直接跳到互动域。"""
    app = _qapp()
    dialog.self_talk_check.setChecked(True)

    dialog.search_edit.setText("配图概率")
    for _ in range(3):
        app.processEvents()
    assert dialog.sidebar.currentItem().text() == "互动"

    dialog.search_edit.setText("点击触发自言自语")
    for _ in range(3):
        app.processEvents()
    assert dialog.sidebar.currentItem().text() == "互动"


def test_every_setting_row_still_lives_in_a_domain_page(dialog):
    """全局不变量：没有孤儿行、没有掉进「待分类（开发期）」。"""
    from PySide6.QtWidgets import QLabel, QWidget

    from pet.modern_settings_dialog import SettingRow

    pages = [dialog.pages.widget(i) for i in range(dialog.pages.count())]
    orphans = [
        row.objectName()
        for row in dialog.findChildren(SettingRow)
        if not any(page.isAncestorOf(row) for page in pages)
    ]
    assert orphans == [], f"这些行没有落在任何域页里：{orphans}"

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "待分类（开发期）" not in labels
    assert all(page is not None for page in pages)
    assert isinstance(_interaction_page(dialog), QWidget)
