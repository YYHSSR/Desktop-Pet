from pet.context_menu import load_default_menu_layout
import pytest


def test_modern_default_v1_has_compact_root_and_safety_actions():
    layout = load_default_menu_layout()

    assert layout["schema_version"] == 1
    assert layout["layout_id"] == "modern-default-v1"
    assert [node["id"] for node in layout["nodes"]] == [
        "pet_greeting",
        "default.separator-profile",
        "animations_hub",
        "character",
        "playback_speed",
        "size",
        "default.separator-playback",
        "pet_controls",
        "quick_launch",
        "quick_urls",
        "default.separator-pet",
        "modern_settings",
        "quit",
    ]
    assert layout["nodes"][-2:] == [
        {"type": "action", "id": "modern_settings", "visible": True, "section": "system"},
        {"type": "action", "id": "quit", "visible": True, "section": "system"},
    ]


def test_default_layout_populates_real_qmenu_hierarchy(monkeypatch):
    import sys
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication, QMenu

    from pet import catalog
    from pet.context_menu import populate_context_menu
    from pet.context_menus import shared

    class FakeConfig:
        values = {
            "context_menu_template": "modern",
            "context_menu_layout": None,
            "context_menu_appearance": {"theme": "light"},
            "character": "shenshen",
            "on_top": True,
            "agent_link": {},
        }

        def get(self, key, default=None):
            return self.values.get(key, default)

        def set(self, key, value):
            self.values[key] = value

        def save(self):
            return None

    class FakePet:
        cfg = FakeConfig()
        on_open_chat = lambda self: None
        on_look_screen = lambda self: None
        on_open_modern_settings = lambda self: None
        on_spawn_pet = lambda self: None
        idles = ["待机"]
        turns = moves = clicks = acts = []
        playback_speed = scale = 1.0
        drag_physics = no_move = mouse_through = False

        def icon_pixmap(self, size=64):
            pixmap = QPixmap(size, size)
            pixmap.fill()
            return pixmap

        def __getattr__(self, _name):
            return lambda *args, **kwargs: None

    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(catalog, "list_available_characters", lambda: ["shenshen"])
    menu = QMenu()

    populate_context_menu(menu, FakePet())

    root = [action.text() for action in menu.actions() if not action.isSeparator()]
    expected_root = [
        "厉害了我的鲸",
        "播放动画",
        "切换角色",
        "播放速率",
        "大小",
        "桌宠控制",
        "快捷应用",
        "快捷网址",
        "桌宠设置",
        "退出",
    ]
    # 报时/节日四项默认不在菜单上（模板 visible: false，2026-09-19 起）
    assert root == expected_root
    rendered = ["|" if action.isSeparator() else action.text() for action in menu.actions()]
    expected_rendered = [
        "厉害了我的鲸", "|",
        "播放动画", "切换角色", "播放速率", "大小", "|",
        "桌宠控制", "快捷应用", "快捷网址", "|",
        "桌宠设置", "退出",
    ]
    assert rendered == expected_rendered
    pet_controls = next(action.menu() for action in menu.actions() if action.text() == "桌宠控制")
    assert [action.text() for action in pet_controls.actions() if not action.isSeparator()] == [
        "拖动物理",
        "不移动",
        "窗口置顶",
        "回到右下角",
        "生小肥鱼",
        "退出子肥鱼",
        "黄金回旋",
        "边缘探头",
    ]
    menu.close()
    app.processEvents()


def test_settings_sidebar_uses_stable_domains_and_owns_representative_rows(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from pet import modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog, SettingRow

    app = QApplication.instance() or QApplication([])

    dialog = ModernSettingsDialog(Config(tmp_path))
    expected = ["常规", "桌宠", "互动", "菜单", "自动化与联动"]
    assert [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())] == expected

    def owner(setting_id):
        row = dialog.findChild(SettingRow, f"settingRow_{setting_id}")
        return next(expected[index] for index in range(dialog.pages.count()) if dialog.pages.widget(index).isAncestorOf(row))

    assert owner("click_self_talk") == "互动"
    assert owner("self_talk_image_chance") == "互动"
    assert owner("menu_theme") == "菜单"
    assert owner("quick_launch_apps") == "菜单"
    assert owner("festival_reminder_enabled") == "自动化与联动"
    assert "待分类（开发期）" not in [
        label.text() for label in dialog.findChildren(settings_mod.QLabel)
    ]
    dialog.reject()
    app.processEvents()


def _section_of(dialog, settings_mod, setting_id):
    """返回某个设置行所属的 SettingsSection（域重构后行会被 reparent 进共享卡片）。"""
    from pet.modern_settings_dialog import SettingRow

    row = dialog.findChild(SettingRow, f"settingRow_{setting_id}")
    assert row is not None, f"{setting_id} 行必须存在"
    parent = row.parentWidget()
    while parent is not None and not isinstance(parent, settings_mod.SettingsSection):
        parent = parent.parentWidget()
    assert parent is not None, f"{setting_id} 必须落在某个 SettingsSection 内"
    return parent


def _section_title(section) -> str:
    if section.toggle is not None:  # 高级组（默认收起）标题在 disclosure 按钮上
        return section.toggle.text()
    from pet import modern_settings_dialog as settings_mod

    label = section.findChild(settings_mod.QLabel, "sectionTitle")
    assert label is not None
    return label.text()


def test_click_and_festival_search_jump_to_owning_domains(tmp_path, monkeypatch):
    """搜索按「语音」定稿口径跳域：点击音效 → 互动、碰撞音效 → 桌宠、
    节日提醒 / 语音报时 → 语音、Agent 提示音 → 自动化与联动。"""
    from PySide6.QtWidgets import QApplication

    from pet import modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog

    app = QApplication.instance() or QApplication([])

    dialog = ModernSettingsDialog(Config(tmp_path))
    try:
        # (查询词, 应跳到的域, 命中行是否应可见)：只有「碰撞参数（高级）」里的行
        # 藏在默认收起的 disclosure 后面（搜索不展开 disclosure），其余行可见。
        cases = (
            ("点击触发自言自语", "互动", True),
            ("节日提醒", "自动化与联动", True),
        )
        for query, domain, should_be_visible in cases:
            dialog.search_edit.setText(query)
            app.processEvents()
            assert dialog.sidebar.currentItem().text() == domain, (
                f"搜索「{query}」必须跳到「{domain}」域"
            )
            page = dialog.pages.widget(dialog.sidebar.currentRow())
            match = dialog._search_matches[dialog._search_index]
            assert page.isAncestorOf(match), f"搜索「{query}」命中的行不在「{domain}」域"
            if should_be_visible:
                assert match.isVisibleTo(page), (
                    f"搜索「{query}」命中的行在「{domain}」域里不可见"
                )
    finally:
        dialog.reject()
        app.processEvents()


def test_menu_domain_uses_in_page_task_tabs_without_changing_sidebar(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from pet import modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog, SettingRow, SettingsTabContainer

    app = QApplication.instance() or QApplication([])

    dialog = ModernSettingsDialog(Config(tmp_path))

    expected_sidebar = ["常规", "桌宠", "互动", "菜单", "自动化与联动"]
    assert [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())] == expected_sidebar
    tabs = dialog.pages.widget(3).findChild(SettingsTabContainer, "settingsTaskTabs")
    assert tabs is not None
    assert tabs.keys() == ("launcher", "quick_urls", "appearance")
    assert tabs.labels() == ("快捷应用", "快捷网址", "外观")

    launcher_row = dialog.findChild(SettingRow, "settingRow_quick_launch_apps")
    quick_urls_row = dialog.findChild(SettingRow, "settingRow_quick_urls")
    appearance_row = dialog.findChild(SettingRow, "settingRow_menu_theme")
    assert tabs.key_for_descendant(launcher_row) == "launcher"
    assert tabs.key_for_descendant(quick_urls_row) == "quick_urls"
    assert tabs.key_for_descendant(appearance_row) == "appearance"

    dialog.search_edit.setText("应用快捷启动")
    app.processEvents()
    assert dialog.sidebar.currentItem().text() == "菜单"
    assert tabs.currentKey() == "launcher"
    dialog.reject()
    app.processEvents()


def test_advanced_setting_groups_use_single_collapsed_disclosure_layer(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QToolButton

    from pet import modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.modern_settings_dialog import (
        ModernSettingsDialog,
        SettingsDisclosureHeader,
        SettingsSection,
    )

    app = QApplication.instance() or QApplication([])

    dialog = ModernSettingsDialog(Config(tmp_path))

    color_toggle = next(
        button for button in dialog.findChildren(SettingsDisclosureHeader)
        if button.text() == "高级配色"
    )
    assert not dialog.findChildren(QToolButton, "advancedSectionToggle")
    color_section = color_toggle.parentWidget()
    assert isinstance(color_section, SettingsSection)
    assert color_section.card.isHidden()
    assert not color_toggle.isChecked()

    color_toggle.click()

    assert not color_section.card.isHidden()
    assert color_toggle.isChecked()
    dialog.reject()
    app.processEvents()


def test_settings_visual_hierarchy_uses_shared_product_tokens(tmp_path, monkeypatch):
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from pet import modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog, SettingRow

    app = QApplication.instance() or QApplication([])

    dialog = ModernSettingsDialog(Config(tmp_path))
    dialog.show()
    app.processEvents()

    assert dialog.findChild(settings_mod.QFrame, "sidebarPane").width() == 200
    assert dialog.sidebar.iconSize() == QSize(18, 18)
    dialog.sidebar.setCurrentRow(1)
    app.processEvents()
    page_title = dialog.pages.currentWidget().findChild(settings_mod.QLabel, "pageTitle")
    section_title = dialog.pages.currentWidget().findChild(settings_mod.QLabel, "sectionTitle")
    row = dialog.findChild(SettingRow, "settingRow_animation_gap")
    assert page_title.font().pixelSize() == 22
    assert section_title.font().pixelSize() == 13
    assert row.label.font().pixelSize() == 13
    assert row.label.font().weight() == 500
    assert row.hint_label.font().pixelSize() == 12
    dialog.reject()
    app.processEvents()


def test_wide_settings_title_tracks_the_centered_page_content(tmp_path, monkeypatch):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QScrollArea

    from pet import modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog

    app = QApplication.instance() or QApplication([])

    dialog = ModernSettingsDialog(Config(tmp_path))
    dialog.resize(1600, 900)
    dialog.show()
    app.processEvents()

    page = dialog.pages.currentWidget()
    title = page.findChild(settings_mod.QLabel, "pageTitle")
    scroll = page.findChild(QScrollArea, "settingsScroll")
    content = scroll.widget()
    assert title.mapTo(page, QPoint(0, 0)).x() == content.mapTo(page, QPoint(0, 0)).x()

    dialog.resize(720, 700)
    app.processEvents()
    assert title.mapTo(page, QPoint(0, 0)).x() == content.mapTo(page, QPoint(0, 0)).x()
    dialog.reject()
    app.processEvents()


def test_setting_rows_name_and_describe_their_controls_for_accessibility(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from pet import modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog, SettingRow

    app = QApplication.instance() or QApplication([])

    dialog = ModernSettingsDialog(Config(tmp_path))
    row = dialog.findChild(SettingRow, "settingRow_animation_gap")

    assert row.label.buddy() is row.control
    assert row.label.wordWrap()
    assert row.control.accessibleName() == row.label.text()
    assert row.control.accessibleDescription() == row.hint_label.text()
    assert "QPushButton:focus" in dialog.styleSheet()

    dialog.reject()
    app.processEvents()


def test_setting_row_stacks_a_wide_control_before_copy_becomes_unreadable():
    from PySide6.QtWidgets import QApplication, QPushButton

    from pet.modern_settings_dialog import SettingRow

    app = QApplication.instance() or QApplication([])
    control = QPushButton("宽控件")
    control.setFixedWidth(340)
    row = SettingRow(
        "responsive",
        "跨平台同步与自动恢复策略的超长本地化标题示例",
        "说明文字必须保持可读。",
        control,
    )
    row.resize(500, 180)
    row.show()
    app.processEvents()

    assert control.y() > row.label.y() + row.label.height()
    assert row.property("responsiveStacked") is True

    row.resize(900, 180)
    app.processEvents()

    assert control.x() > row.label.x()
    assert row.property("responsiveStacked") is False
    row.close()
    app.processEvents()


def test_responsive_action_row_can_stack_wide_actions_vertically():
    from PySide6.QtWidgets import QApplication, QPushButton

    from pet.modern_settings_dialog import ModernSelect, ResponsiveActionRow

    app = QApplication.instance() or QApplication([])
    primary = ModernSelect(width=230)
    first = QPushButton("第一个很长的本地化操作")
    second = QPushButton("第二个很长的本地化操作")
    first.setMinimumWidth(260)
    second.setMinimumWidth(260)
    row = ResponsiveActionRow(primary, [first, second])
    row.setFixedWidth(454)
    row.resize(454, 180)
    row.show()
    app.processEvents()

    assert row.minimumSizeHint().width() <= 260
    assert row.property("responsiveMode") == "compact"
    assert first.y() < second.y()
    assert first.geometry().right() <= row.rect().right()
    assert second.geometry().right() <= row.rect().right()
    row.close()
    app.processEvents()


def test_responsive_action_row_inline_mode_does_not_reserve_compact_height():
    from PySide6.QtWidgets import QApplication, QPushButton

    from pet.modern_settings_dialog import ModernSelect, ResponsiveActionRow

    app = QApplication.instance() or QApplication([])
    primary = ModernSelect(width=230)
    first = QPushButton("新增")
    second = QPushButton("删除")
    row = ResponsiveActionRow(primary, [first, second])
    row.setFixedWidth(800)
    row.show()
    app.processEvents()

    expected_height = max(
        widget.minimumHeight() or widget.minimumSizeHint().height()
        for widget in (primary, first, second)
    )
    assert row.property("responsiveMode") == "inline"
    assert row.minimumSizeHint().height() == expected_height
    row.close()
    app.processEvents()


def test_settings_domains_use_semantic_sidebar_icons():
    from pet.modern_settings_dialog import SETTINGS_DOMAIN_NAV

    assert SETTINGS_DOMAIN_NAV == (
        ("常规", "settings"),
        ("桌宠", "pet"),
        ("互动", "interaction"),
        ("菜单", "application"),
        ("自动化与联动", "automation"),
    )


def test_non_windows_settings_does_not_create_orphan_windows_control(tmp_path, monkeypatch):
    import sys

    from PySide6.QtWidgets import QApplication

    from pet import modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.modern_settings_dialog import ModernSettingsDialog

    if sys.platform == "win32":
        return
    app = QApplication.instance() or QApplication([])

    dialog = ModernSettingsDialog(Config(tmp_path))

    assert dialog.cursor_hidden_passthrough_check is None
    dialog.reject()
    app.processEvents()


# --- Settings menu customization regressions (2026-09-03) ---


def test_settings_tabs_are_compact_left_aligned_plugin_style_navigation():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

    from pet.modern_settings_dialog import SettingsTabContainer

    app = QApplication.instance() or QApplication([])
    tabs = SettingsTabContainer()
    for key, label in (("launcher", "快捷启动"), ("appearance", "外观")):
        tabs.addTab(key, label, QWidget())
    tabs.resize(900, 420)
    tabs.show()
    app.processEvents()

    assert tabs.tab_bar.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Maximum
    assert tabs.tab_layout.alignment() & Qt.AlignmentFlag.AlignLeft
    assert tabs.tab_bar.width() < tabs.width() * 0.7
    assert all(button.property("navigationStyle") == "plugin" for button in tabs._buttons)
    tabs.close()
    app.processEvents()
