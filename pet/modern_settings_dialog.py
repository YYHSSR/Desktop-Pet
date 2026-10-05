# -*- coding: utf-8 -*-
"""Modern-inspired sidebar settings panel used by the modern context menu.

拆分后的主对话框模块：ModernSettingsDialog 及对话框装配/配置写回逻辑留守本文件。
控件库 / 主题 QSS 已按结构线拆至
settings_widgets / settings_theme_qss。
本文件保留这些符号的 re-export，供 tests 与 pet/ 既有调用向后兼容。
"""

from __future__ import annotations

import logging
import sys

import shiboken6


from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import (
    QFontDatabase,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .config import (
    DEFAULT_CONTEXT_MENU_APPEARANCE,
    DEFAULT_QUICK_LAUNCH_APPS,
    DEFAULT_QUICK_URLS,
    DEFAULT_SELF_TALK_TEXTS,
)
from .context_menus.icons import vector_widget_icon


from .settings_widgets import (
    _system_font_families,
    SETTINGS_DOMAIN_NAV,
    ToggleSwitch,
    ImagePreviewDrawer,
    ResourcePathPicker,
    ColorSwatchButton,
    ColorPicker,
    configure_settings_action_popup,
    SettingsMenuButton,
    ModernSelect,
    BrowserSpinBox,
    CollapsibleGroup,
    SettingRow,
    ResponsiveActionRow,
    SettingsCard,
    SettingsDisclosureHeader,
    SettingsSection,
    SettingsTabContainer,
    _SettingsPageShell,
    QuickLaunchEditor,
    QuickUrlEditor,
    _system_dark,
)
from .settings_theme_qss import _settings_stylesheet
from .persona_template import (
    CONDITIONAL_PARAMETERS,
    PARAMETERS,
)
from . import settings_interaction
from . import settings_pet_controls
from .report_gates import REPORT_GATE_KEYS, REPORT_GATE_LABELS, gate_for_event

# Shared widgets used by settings modules and their public UI tests.
__all__ = ['BrowserSpinBox', 'ColorPicker', 'ColorSwatchButton', 'ImagePreviewDrawer', 'ModernSelect', 'ModernSettingsDialog', 'QColorDialog', 'QFileDialog', 'QFrame', 'QLabel', 'QMessageBox', 'Qt', 'QuickLaunchEditor', 'ResourcePathPicker', 'ResponsiveActionRow', 'SETTINGS_DOMAIN_NAV', 'SettingRow', 'SettingsDisclosureHeader', 'SettingsMenuButton', 'SettingsSection', 'SettingsTabContainer', 'ToggleSwitch', '_settings_stylesheet', 'dialogue_params_hint']


# 语言配置页只展示用户能理解的事件名称；内部 key 仍用于保存和渲染。
DIALOGUE_LABELS = {
    "start": "开始工作",
    "thinking": "思考",
    "activity.read": "读取文件",
    "activity.search": "搜索或查找",
    "activity.edit": "编辑代码",
    "activity.run": "运行或测试",
    "activity.default": "其他工具操作",
    "agent.attention": "需要用户处理",
    "agent.error": "Agent 出错",
    "agent.missing": "未找到 Agent",
    "approval.command": "审批命令",
    "approval.tool": "审批工具",
    "approval.generic": "审批提示",
    "question.empty": "等待选择",
    "question.one": "单个用户问题",
    "question.many": "多个用户问题",
    "watchdog.warning": "循环检测警告",
    "model_access.one": "模型访问失败（单次）",
    "model_access.many": "模型访问失败（连续）",
    "llm_error.api": "AI 服务错误",
    "done.success": "任务完成",
    "done.attention": "任务暂停待确认",
    "failure.retry": "重试后失败",
    "failure.tool": "工具执行失败",
    "failure.generic": "执行失败",
    "stuck.reminder": "卡住提醒",
    "pattern.warning": "行为重复警告",
    "pattern.control": "行为重复干预",
}

DIALOGUE_PARAMS = {
    "name": "Agent 名称",
    "command": "命令文本",
    "label": "标签（工具标签/会话标签随事件而定）",
    "body": "问题内容",
    "count": "数量",
    "reasons": "判断原因",
    "detail": "错误详情",
    "text": "显示文本",
    "event": "未知事件名（bridge.unknown）",
    "tool": "原始工具名",
    "callId": "工具调用 ID",
    "step": "步骤序号",
    "toolName": "审批原始工具名",
    "argsKey": "工具参数摘要键",
    "sessionName": "会话显示名",
    "projectName": "项目名",
    "errorCode": "错误码（llm_error 为上游真实码，如 bad_response_status_code）",
    "errorMessage": "错误信息原文",
    "errorKind": "错误分类（api=AI API 请求失败）",
    "consecutiveRetryCount": "连续模型访问失败次数",
    "retry": "重试序号",
    "retries": "已重试次数",
    "retryExhausted": "是否重试耗尽",
    "failureType": "失败类型",
}

# 与 persona_template.PARAMETERS 保持同一真相源：调用点注入什么，这里就宣称什么。
DIALOGUE_KEY_PARAMS = dict(PARAMETERS)


def dialogue_params_hint(key: str) -> str:
    """「可用参数」提示文案：区分保证注入与条件注入（仅上游记录提供时可用）。"""
    params = DIALOGUE_KEY_PARAMS.get(key, ())
    if not params:
        return ""
    text = "、".join("{" + item + "}（" + DIALOGUE_PARAMS[item] + "）" for item in params)
    conditional = [item for item in params if item in CONDITIONAL_PARAMETERS.get(key, ())]
    if conditional:
        text += "；其中 " + "、".join("{" + item + "}" for item in conditional) + " 仅在上游记录提供时可用"
    return text


class ModernSettingsDialog(QDialog):
    """Settings window matching Modern's sidebar and rounded-card hierarchy."""

    def __init__(self, config, parent=None, *, standalone: bool = False):
        super().__init__(parent)
        self.config = config
        # standalone=True：本对话框跑在独立设置进程（python -m pet --settings）里，
        # 没有桌宠窗口/AppShell 可依附。只影响下面几处显式分支，默认 False 时
        # 全部行为与改动前逐位一致。
        self.standalone = bool(standalone)
        self.setProperty("modernStyle", True)
        self.setProperty("menuStyle", "modern")
        self.setWindowTitle("桌宠设置")
        self.resize(800, 560)
        self.setMinimumSize(720, 500)
        self._positioned_away = False
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        font.setPixelSize(13)
        self.setFont(font)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        sidebar_pane = QFrame(self)
        sidebar_pane.setObjectName("sidebarPane")
        sidebar_pane.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar_pane)
        sidebar_layout.setContentsMargins(12, 16, 12, 12)
        sidebar_layout.setSpacing(9)
        self.save_exit_button = QPushButton("保存并退出", sidebar_pane)
        self.save_exit_button.setObjectName("saveAndExit")
        self.save_exit_button.setIcon(vector_widget_icon(self.save_exit_button, "back", 16))
        self.save_exit_button.clicked.connect(self._save)
        self.save_exit_button.setAutoDefault(False)
        self.save_exit_button.setDefault(False)
        sidebar_layout.addWidget(self.save_exit_button)
        self.search_edit = QLineEdit(sidebar_pane)
        self.search_edit.setObjectName("settingsSearch")
        self.search_edit.setPlaceholderText("搜索设置…")
        self.search_edit.addAction(
            vector_widget_icon(self, "search", 16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search_edit.installEventFilter(self)
        sidebar_layout.addWidget(self.search_edit)
        self.search_status = QLabel("", sidebar_pane)
        self.search_status.setObjectName("searchStatus")
        self.search_status.setWordWrap(True)
        self.search_status.hide()
        sidebar_layout.addWidget(self.search_status)
        self.sidebar = QListWidget(sidebar_pane)
        self.sidebar.setObjectName("settingsSidebar")
        self.sidebar.setIconSize(QSize(18, 18))
        self.sidebar.setSpacing(2)
        sidebar_layout.addWidget(self.sidebar, 1)

        self.pages = QStackedWidget(self)
        body.addWidget(sidebar_pane)
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)

        self._build_pet_controls()

        general_content = QWidget()
        general_layout = QVBoxLayout(general_content)
        general_layout.setContentsMargins(0, 0, 0, 0)
        general_layout.setSpacing(18)
        launch_rows = []
        if sys.platform == "darwin" and getattr(self, "dock_icon_check", None) is not None:
            launch_rows.append(
                SettingRow(
                    "dock_icon",
                    "显示 Dock 图标",
                    "在 macOS Dock 中显示桌宠应用；关闭后仍可通过桌宠和托盘操作。",
                    self.dock_icon_check,
                )
            )
        if launch_rows:
            general_layout.addWidget(SettingsSection("应用启动", launch_rows, general_content))
        window_rows = [
        ]
        if sys.platform == "win32":
            if getattr(self, "auto_hide_fullscreen_check", None) is not None:
                window_rows.append(
                    SettingRow("auto_hide_fullscreen", "全屏时自动隐藏", "全屏游戏或视频期间自动隐藏桌宠。", self.auto_hide_fullscreen_check)
                )
            if getattr(self, "cursor_hidden_passthrough_check", None) is not None:
                window_rows.append(
                    SettingRow(
                        "cursor_hidden_passthrough",
                        "光标隐藏时自动穿透",
                        "Windows 光标隐藏后，桌宠自动穿透点击；光标出现立即恢复。适用于游戏，也可能影响自动隐藏光标的视频播放器。",
                        self.cursor_hidden_passthrough_check,
                    )
                )
        if window_rows:
            general_layout.addWidget(SettingsSection("窗口与系统", window_rows, general_content))
        # 拓扑收口 Phase A：「单进程多开」实验开关从设置页隐藏（多进程为唯一
        # 多宠拓扑方向；开关控件已从 settings_pet_controls 移除，设置页不再
        # 写该键；配置键 experimental_single_process_spawn 随 config.save()
        # 原样回写，存量用户与回滚路径不受影响）。
        general_layout.addStretch(1)
        self._add_page("常规", "settings", self._page_shell("常规", general_content))
        behavior_content = QWidget()
        behavior_layout = QVBoxLayout(behavior_content)
        behavior_layout.setContentsMargins(0, 0, 0, 0)
        behavior_layout.setSpacing(16)
        behavior_layout.addWidget(
            SettingsSection(
                "动画",
                [
                    SettingRow("codex_link", "ChatGPT 工作状态", "读取本机 Work/Codex 会话，切换桌宠动作和提示；请自行打开桌面端。", self.codex_link_check),
                    SettingRow("cursor_link", "Cursor 工作状态", "读取本机 Cursor 会话转写，切换桌宠动作和提示；请自行打开 Cursor。", self.cursor_link_check),
                    SettingRow("animation_gap", "动作等待间隔", "非待机动作之间的休息时间；0 秒表示连续播放。", self.gap_spin),
                ],
                behavior_content,
            )
        )
        behavior_layout.addWidget(
            SettingsSection(
                "拖拽与弹射",
                [
                    SettingRow("throw_strength", "甩出力度", "控制桌宠被甩出或弹射发射时的最大速度限制。", self.throw_strength_select),
                    SettingRow("slingshot_enabled", "弹弓弹射", "拖拽桌宠时点击右键进入蓄力瞄准，松开左键弹射飞出（Esc或右键取消）。", self.slingshot_check),
                    SettingRow("lock_position", "锁定位置", "桌宠固定不动，无法拖动（点击互动仍有效）。", self.lock_position_check),
                    SettingRow("shift_drag", "SHIFT+左键拖动", "开启后必须按住 SHIFT 再左键才能拖动桌宠。", self.shift_drag_check),
                ],
                behavior_content,
            )
        )
        behavior_layout.addWidget(
            SettingsSection(
                "生小肥鱼",
                [
                    SettingRow(
                        "spawn_inherit_size",
                        "生小肥鱼继承大小",
                        "开启后生成的小肥鱼与主肥鱼大小一致；关闭后使用下方为小肥鱼单独选择的大小。",
                        self.spawn_inherit_size_check,
                    ),
                    SettingRow("spawn_scale", "小肥鱼大小", "关闭“继承大小”时，新生成小肥鱼使用的桌面尺寸。", self.spawn_scale_combo, stacked=True),
                ],
                behavior_content,
            )
        )
        behavior_layout.addWidget(
            SettingsSection(
                "多开碰撞",
                [
                    SettingRow(
                        "collision_enabled",
                        "碰撞开关",
                        "多开桌宠之间发生碰撞物理互动。开启鼠标穿透的桌宠仍会参与碰撞，锁定位置的桌宠作为固定障碍。",
                        self.collision_enabled_check,
                    ),
                    SettingRow("collision_restitution", "弹性系数", "碰撞反弹的能量保留程度（0~1.00，默认 0.82）。", self.collision_restitution_spin),
                    SettingRow("collision_friction", "摩擦系数", "擦边碰撞时的切向摩擦阻力（0~0.30，默认 0.08）。", self.collision_friction_spin),
                    SettingRow("collision_mass_scale", "质量倍率", "桌宠的基础质量加权倍率（0.5~2.0，默认 1.0）。", self.collision_mass_scale_spin),
                    SettingRow("collision_impulse_cap", "冲量上限", "单次碰撞能施加的最大冲量上限（1000~12000，默认 9000）。", self.collision_impulse_cap_spin),
                ],
                behavior_content,
            )
        )
        # 「点击反馈」与「自言自语」两组归「互动」域（settings_interaction 构建，
        # 行数预算原因；组名与顺序的既有契约见 tests/test_settings_ui.py）。
        # 事件气泡触发概率：每个事件聚合类别一个 0.00–1.00 滑块（没有开关），
        # 与该类的气泡文案行同组；域导航重建时整体收进「事件气泡触发概率」
        # 下的可折叠框，让设置位置与真正控制的位置绑定。
        self.report_gate_rows = {}
        report_gate_rows = []
        for gate in REPORT_GATE_KEYS:
            gate_label = REPORT_GATE_LABELS[gate]
            row = SettingRow(
                f"report_gate_{gate}",
                "汇报概率",
                f"{gate_label}：这一类气泡的通过概率。0.00 = 该类完全不汇报（静音），"
                "1.00 = 每次都汇报，中间值按概率抽稀。概率只作用于「出气泡」这一步，"
                "卡住 / 行为重复 / 循环等检测本身不受影响；右键菜单只提供 0/1 两端快捷入口。",
                self.report_gate_sliders[gate],
                stacked=True,
            )
            # 行内可见标题统一是「汇报概率」，无障碍名必须带上类别才不歧义。
            row.control.setAccessibleName(f"{gate_label}：汇报概率")
            self.report_gate_rows[gate] = row
            report_gate_rows.append(row)
        # 暂存宿主：这些行由域导航重建时认领并移入「事件气泡触发概率」可折叠框，
        # 认领后本卡片为空（不残留空标题小节）。与气泡文案行同一处理方式。
        behavior_layout.addWidget(SettingsCard(report_gate_rows, behavior_content))
        labels = DIALOGUE_LABELS
        behavior_layout.addWidget(
            SettingsSection(
                "表达风格",
                [
                    SettingRow(
                        "dialogue_mode",
                        "表达风格",
                        "控制桌宠自言自语、候选内容和主动气泡的说话方式；同时覆盖 Agent 状态、审批、提问、错误、模型访问失败等所有气泡。内置「默认模式」与「鲸鱼娘女仆模式」不可编辑；选择「自定义台词」后，可粘贴下方 JSON 一键导入全部弹窗文案。",
                        self.dialogue_mode_select,
                    ),
                    SettingRow(
                        "dialogue_scope",
                        "专属文案对象(仅在自定义模式生效)",
                        "下方逐事件编辑针对的对象：默认（全局文案）或某 Agent 的专属文案。留空的事件自动沿用全局（或默认模式）文案。",
                        self.dialogue_scope_select,
                        stacked=True,
                    ),
                ],
                behavior_content,
            )
        )
        behavior_layout.addWidget(
            SettingsCard(
                [
                    SettingRow(
                        "dialogue_template_actions",
                        "弹窗文案模板（JSON）",
                        "一键复制当前全部弹窗内容模板到剪贴板；把复制的 JSON 粘贴回「导入模板」可一次覆盖所有「自定义台词」，也可以直接发给 AI 依角色卡改写。事件留空时自动沿用默认模式文案；模板占位符会自动读取上游事件字段。",
                        self.dialogue_template_actions,
                        stacked=True,
                    ),
                ],
                behavior_content,
            )
        )
        behavior_layout.addWidget(
            SettingsCard(
                [
                    SettingRow(
                        f"dialogue_{key}",
                        labels.get(key, key),
                        "留空则使用基础模式台词。可用参数：" + (dialogue_params_hint(key) or "无"),
                        edit,
                        stacked=True,
                    )
                    for key, edit in self.dialogue_phrase_edits.items()
                ],
                behavior_content,
            )
        )
        behavior_layout.addStretch(1)
        self._add_page("桌宠行为", "play", self._page_shell("桌宠行为", behavior_content))

        appearance_content = QWidget()
        appearance_layout = QVBoxLayout(appearance_content)
        appearance_layout.setContentsMargins(0, 0, 0, 0)
        appearance_layout.setSpacing(16)
        appearance_layout.addWidget(
            SettingsSection(
                "桌宠显示",
                [
                    SettingRow(
                        "bubble_text_scale",
                        "气泡文字大小",
                        "气泡里文字的显示尺寸：气泡与字号一起等比放大（100% 为默认）。"
                        "大屏上嫌气泡字小时调大；审批/提问气泡为固定布局，不随本项变化。",
                        self.bubble_text_scale_spin,
                    ),
                    SettingRow("pet_opacity", "不透明度", "调整桌宠窗口的整体透明度；100% 为完全不透明。", self.pet_opacity_spin),
                    # 「气泡方案」行归「互动 · 自言自语」（settings_interaction 构建）。
                ],
                appearance_content,
            )
        )
        appearance_layout.addWidget(
            SettingsSection(
                "菜单外观",
                [
                    SettingRow("menu_theme", "颜色主题", "可跟随系统，或固定使用浅色/深色菜单。", self.menu_theme_select),
                    SettingRow("menu_density", "菜单密度", "调整新版右键菜单的菜单项高度和分组留白。", self.menu_density_select),
                    SettingRow("menu_radius", "圆角大小", "调整新版右键菜单和子菜单的外轮廓圆角。", self.menu_radius_select),
                    SettingRow("menu_font", "UI 字体", "设置新版菜单使用的界面字体。", self.menu_font_select),
                    SettingRow("menu_font_size", "UI 字号", "同步调整主菜单与多级菜单的字号。", self.menu_font_size_select),
                    SettingRow("menu_translucent", "半透明菜单", "使用接近 Modern 的半透明浮层表面。", self.menu_translucent_check),
                    SettingRow("menu_opacity", "表面不透明度", "调整菜单背景透出桌面内容的程度。", self.menu_opacity_spin),
                ],
                appearance_content,
            )
        )
        appearance_layout.addWidget(
            SettingsSection(
                "浅色主题",
                [
                    SettingRow("light_background", "背景色", "浅色菜单的浮层背景。", self.light_background_picker),
                    SettingRow("light_foreground", "文字色", "浅色菜单的主要文字与图标颜色。", self.light_foreground_picker),
                    SettingRow("light_hover", "悬停色", "鼠标悬停菜单项时的背景。", self.light_hover_picker),
                ],
                appearance_content,
            )
        )
        appearance_layout.addWidget(
            SettingsSection(
                "深色主题",
                [
                    SettingRow("dark_background", "背景色", "深色菜单的浮层背景。", self.dark_background_picker),
                    SettingRow("dark_foreground", "文字色", "深色菜单的主要文字与图标颜色。", self.dark_foreground_picker),
                    SettingRow("dark_hover", "悬停色", "鼠标悬停菜单项时的背景。", self.dark_hover_picker),
                ],
                appearance_content,
            )
        )
        appearance_layout.addStretch(1)
        self._add_page("外观", "appearance", self._page_shell("外观", appearance_content))

        launcher_content = QWidget()
        launcher_layout = QVBoxLayout(launcher_content)
        launcher_layout.setContentsMargins(0, 0, 0, 0)
        launcher_layout.setSpacing(18)
        self.quick_launch_editor = QuickLaunchEditor(
            self.config.get("quick_launch_apps", DEFAULT_QUICK_LAUNCH_APPS),
            launcher_content,
        )
        launcher_layout.addWidget(
            SettingsSection(
                "已配置应用",
                [
                    SettingRow(
                        "quick_launch_apps",
                        "应用快捷启动",
                        "这些应用将按图标和名称显示在新版右键菜单的“快捷应用”子菜单中。",
                        self.quick_launch_editor,
                        stacked=True,
                    ),
                ],
                launcher_content,
            )
        )
        launcher_layout.addStretch(1)
        self._add_page("快捷应用", "application", self._page_shell("快捷应用", launcher_content))

        quick_urls_content = QWidget()
        quick_urls_layout = QVBoxLayout(quick_urls_content)
        quick_urls_layout.setContentsMargins(0, 0, 0, 0)
        quick_urls_layout.setSpacing(18)
        self.quick_urls_editor = QuickUrlEditor(
            self.config.get("quick_urls", DEFAULT_QUICK_URLS),
            quick_urls_content,
        )
        quick_urls_layout.addWidget(
            SettingsSection(
                "已配置网址",
                [
                    SettingRow(
                        "quick_urls",
                        "网址快捷打开",
                        "这些网址将按名称显示在右键菜单的“快捷网址”子菜单中。",
                        self.quick_urls_editor,
                        stacked=True,
                    ),
                ],
                quick_urls_content,
            )
        )
        quick_urls_layout.addStretch(1)
        self._add_page("快捷网址", "web", self._page_shell("快捷网址", quick_urls_content))


        # AI rows are composed directly into the final capability domain by
        # _rebuild_domain_navigation. Do not temporarily hand the controller
        # widget to a QScrollArea: that creates a second Qt ownership path when
        # its rows are reparented into the shared card system.

        # Agent Exploration Loop Watchdog 独立设置页
        from .exploration_watchdog_settings import WatchdogSettingsPage

        agent_link_cfg = self.config.get("agent_link", {})
        self.watchdog_page = WatchdogSettingsPage(self.config, agent_link_cfg, self)


        self._rebuild_domain_navigation()
        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.sidebar.setCurrentRow(0)
        self._search_rows = self.findChildren(SettingRow)
        self._search_matches: list[SettingRow] = []
        self._search_index = -1
        self.search_edit.textChanged.connect(self._search_settings)

        self.self_talk_check.toggled.connect(self._update_self_talk_controls)
        self.menu_translucent_check.toggled.connect(self._update_translucency_controls)
        self.lock_position_check.toggled.connect(self._update_drag_controls)
        self._update_drag_controls(self.lock_position_check.isChecked())
        self.collision_enabled_check.toggled.connect(self._update_collision_controls)
        self.spawn_inherit_size_check.toggled.connect(self._update_spawn_size_controls)
        self._update_self_talk_controls(self.self_talk_check.isChecked())
        self._update_translucency_controls(self.menu_translucent_check.isChecked())
        self._update_collision_controls(self.collision_enabled_check.isChecked())
        self._update_spawn_size_controls(self.spawn_inherit_size_check.isChecked())
        # 初始同步须在全部 SettingRow 构建完成后执行，否则 findChild 找不到行

        self.menu_theme_select.currentIndexChanged.connect(self._apply_selected_theme)
        self._apply_selected_theme()
        # 行全部就位后收敛台词编辑可见性：初始层若为某 Agent 专属则隐藏公共事件行
        settings_pet_controls._apply_dialogue_scope_rows(self)
        self.move_away_from_pet()


    def _build_pet_controls(self) -> None:
        """Compatibility delegation (settings_pet_controls.build_pet_controls)."""
        settings_pet_controls.build_pet_controls(self)


    def _update_self_talk_controls(self, enabled: bool) -> None:
        """周期气泡（``self_talk``）的细项显隐。

        点击侧（``click_self_talk*`` / ``click_talk_bindings``）**不在这里**：它们是
        独立开关的后续项，见 :meth:`_update_click_self_talk_controls`。绑在一起会让
        「只想点击听声」的用户在设置页里连开关都看不到。
        """
        keys = (
            "self_talk_duration",
            "self_talk_min",
            "self_talk_max",
            "self_talk_texts",
            "self_talk_images",
            "self_talk_image_scale",
            "self_talk_image_chance",
        )
        self._set_setting_rows_visible(keys, enabled)


    def _update_drag_controls(self, locked: bool) -> None:
        for control in (self.shift_drag_check, self.slingshot_check, self.throw_strength_select):
            control.setEnabled(not locked)

    def _update_collision_controls(self, enabled: bool) -> None:
        self._set_setting_rows_visible(
            (
                "collision_restitution",
                "collision_friction",
                "collision_mass_scale",
                "collision_impulse_cap",
            ),
            enabled,
            dependency="collision_enabled",
        )


    def _set_setting_rows_visible(
        self,
        keys: tuple[str, ...],
        visible: bool,
        *,
        dependency: str = "parent",
    ) -> None:
        """Show dependent settings as a complete group and repair card dividers."""
        cards: set[SettingsCard] = set()
        sections: set[SettingsSection] = set()
        for key in keys:
            row = self.findChild(SettingRow, f"settingRow_{key}")
            if row is None:
                continue
            dependencies = getattr(row, "_visibility_dependencies", {})
            dependencies[dependency] = bool(visible)
            row._visibility_dependencies = dependencies
            row.setVisible(all(dependencies.values()))
            card = row.parentWidget()
            if isinstance(card, SettingsCard):
                cards.add(card)
                section = card.parentWidget()
                if isinstance(section, SettingsSection):
                    sections.add(section)
        for section in sections:
            section.refresh_dependency_visibility()
        for card in cards:
            card.refresh_separators()

    def _populate_menu_fonts(self) -> None:
        if shiboken6.isValid(self) is False or self._menu_fonts_populated:
            return
        self._menu_fonts_populated = True
        appearance = self.config.get("context_menu_appearance", DEFAULT_CONTEXT_MENU_APPEARANCE)
        for family in _system_font_families():
            if self.menu_font_select.findData(family) < 0:
                self.menu_font_select.addItem(family, family)
        current_font = str(appearance.get("ui_font") or "system")
        if self.menu_font_select.findData(current_font) < 0:
            self.menu_font_select.addItem(current_font, current_font)
        self.menu_font_select.setCurrentData(current_font)


    def _import_dialogue_template_json(self) -> None:
        """Import a complete persona template from the inline JSON editor."""
        settings_pet_controls._import_dialogue_template_json(self)

    def _dialogue_flush_scope(self, scope: str | None = None) -> None:
        """把当前编辑区的文本快照写回 scope buffer（切换/保存前调用）。"""
        settings_pet_controls._dialogue_flush_scope(self, scope)

    def _on_dialogue_scope_changed(self, index: int) -> None:
        """切换 global/某 Agent 专属文案编辑层：flush 当前层后载入目标层内容。"""
        settings_pet_controls._on_dialogue_scope_changed(self, index)

    def _dialogue_scope_values(self, scope: str) -> dict[str, list[str]]:
        """scope buffer 某层的非空事件 → list[str]（供保存/导出）。"""
        return settings_pet_controls._dialogue_scope_values(self, scope)

    def _dialogue_phrase_values(self) -> dict[str, list[str]]:
        return settings_pet_controls._dialogue_phrase_values(self)

    def _current_dialogue_template(self) -> dict:
        return settings_pet_controls._current_dialogue_template(self)

    def _export_dialogue_template(self) -> None:
        """Export the complete current template to the clipboard (no file dialog)."""
        settings_pet_controls._export_dialogue_template(self)


    def _update_translucency_controls(self, enabled: bool) -> None:
        self._set_setting_rows_visible(("menu_opacity",), enabled)

    def _update_spawn_size_controls(self, inherit_size: bool) -> None:
        """“生小肥鱼继承大小”关闭时才显示独立小肥鱼大小选择。"""
        self._set_setting_rows_visible(
            ("spawn_scale",),
            not bool(inherit_size),
            dependency="spawn_inherit_size",
        )


    def move_away_from_pet(self) -> None:
        """把窗口定位到不与桌宠相交的位置。

        在 show() 之前调用（_present_dialog 的 before_present），窗口首帧
        即落在最终位置，避免 Windows 上"先显示默认位置再跳走"的两段式。
        """
        parent = self.parentWidget()
        if parent is not None and parent.isVisible():
            if self._move_away_from(parent.geometry()):
                self._positioned_away = True
                return
        if self.standalone:
            # 独立进程没有桌宠窗口：改读配置目录 runtime 状态文件取桌宠位置；
            # 读不到返回 None，保持默认位置（不许崩、也不许静默乱跳）。
            from .settings_standalone import standalone_pet_geometry

            pet_geo = standalone_pet_geometry(self.config)
            if pet_geo is not None:
                if self._move_away_from(pet_geo):
                    self._positioned_away = True
                    return
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            self.move(
                avail.center().x() - self.width() // 2,
                avail.center().y() - self.height() // 2,
            )
        self._positioned_away = True

    def showEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().showEvent(event)
        # 兜底：未经 _present_dialog 直接 show 的路径仍要避让桌宠
        if not self._positioned_away:
            self.move_away_from_pet()
        if not getattr(self, "_initial_focus_assigned", False):
            self._initial_focus_assigned = True
            self.sidebar.setFocus(Qt.FocusReason.OtherFocusReason)

    def _move_away_from(self, pet_geo: QRect) -> bool:
        """首次显示时把窗口移到不与桌宠相交的位置（右侧优先，再左侧/下方/上方）"""
        size = self.size()
        screen = self.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen is not None else QRect()
        for rect in (
            QRect(pet_geo.right() + 12, pet_geo.top(), size.width(), size.height()),
            QRect(pet_geo.left() - 12 - size.width(), pet_geo.top(), size.width(), size.height()),
            QRect(pet_geo.left(), pet_geo.bottom() + 12, size.width(), size.height()),
            QRect(pet_geo.left(), pet_geo.top() - 12 - size.height(), size.width(), size.height()),
        ):
            if avail.contains(rect):
                self.move(rect.topLeft())
                return True
        return False

    def _page_shell(self, title: str, content: QWidget) -> QWidget:
        content_max_width = int(content.property("contentMaxWidth") or 960)
        page = _SettingsPageShell(content_max_width, self.pages)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 24, 28, 20)
        layout.setSpacing(12)
        heading_host = QWidget(page)
        heading_host.setObjectName("pageHeader")
        heading_host.setMaximumWidth(content_max_width)
        heading_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        heading_layout = QVBoxLayout(heading_host)
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading_layout.setSpacing(0)
        heading = QLabel(title, heading_host)
        heading.setObjectName("pageTitle")
        heading_layout.addWidget(heading)
        page.heading_host = heading_host
        layout.addWidget(heading_host, 0, Qt.AlignmentFlag.AlignHCenter)
        scroll = QScrollArea(page)
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        content.setMaximumWidth(content_max_width)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page

    def _add_page(self, label: str, icon_name: str, page: QWidget) -> None:
        item = QListWidgetItem(vector_widget_icon(self, icon_name, 16), label)
        item.setSizeHint(QSize(0, 34))
        self.sidebar.addItem(item)
        self.pages.addWidget(page)

    def _rebuild_domain_navigation(self) -> None:
        """Move existing rows into stable capability domains without cloning state."""
        old_pages = {self.sidebar.item(index).text(): self.pages.widget(index) for index in range(self.pages.count())}
        all_rows = list(self.findChildren(SettingRow))
        claimed: set[SettingRow] = set()

        def claim(*setting_ids: str) -> list[SettingRow]:
            rows = []
            for setting_id in setting_ids:
                row = self.findChild(SettingRow, f"settingRow_{setting_id}")
                if row is not None and row not in claimed:
                    claimed.add(row)
                    rows.append(row)
            return rows

        def claim_prefix(prefix: str) -> list[SettingRow]:
            rows = [row for row in all_rows if row.objectName().startswith(f"settingRow_{prefix}") and row not in claimed]
            claimed.update(rows)
            return rows

        def page_content(sections) -> QWidget:
            content = QWidget(self)
            layout = QVBoxLayout(content)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(18)
            for section in sections:
                title, rows, *options = section
                rows = [row for row in rows if row is not None]
                if rows:
                    layout.addWidget(
                        SettingsSection(
                            title,
                            rows,
                            content,
                            advanced=bool(options and options[0]),
                        )
                    )
            layout.addStretch(1)
            return content

        general_sections = [
            ("应用外观", claim("dock_icon")),
            ("窗口与系统", claim("auto_hide_fullscreen", "cursor_hidden_passthrough")),
        ]
        general = page_content(general_sections)
        pet = SettingsTabContainer(self)
        pet.addTab("appearance", "外观与气泡", page_content([
            ("桌宠外观", claim("pet_opacity")),
            ("气泡显示", claim("bubble_text_scale")),
        ]))
        pet.addTab("movement", "动画与拖拽", page_content([
            ("动画与移动", claim("animation_gap")),
            ("拖拽方式", claim("lock_position", "shift_drag")),
            ("弹射", claim("slingshot_enabled", "throw_strength")),
        ]))
        pet.addTab("companions", "多宠与碰撞", page_content([
            ("生成小桌宠", claim("spawn_inherit_size", "spawn_scale")),
            ("多宠碰撞", claim("collision_enabled")),
            ("碰撞参数（高级）", claim("collision_restitution", "collision_friction", "collision_mass_scale", "collision_impulse_cap"), True),
        ]))
        # 「互动」域（2026-09-22 分页）：整页在本模块构建（settings_interaction，
        # 行不进 all_rows 快照，因此不需要 claim，也不会掉进「待分类（开发期）」。
        interaction = settings_interaction.build_interaction_domain(self)
        # 同享 click_ 前缀，按 2026-09-17 定稿口径整组留在 interaction 域。
        menu = SettingsTabContainer(self)
        menu.addTab(
            "launcher",
            "快捷应用",
            page_content(
                [
                    ("已配置应用", claim("quick_launch_apps")),
                ]
            ),
        )
        menu.addTab(
            "quick_urls",
            "快捷网址",
            page_content(
                [
                    ("已配置网址", claim("quick_urls")),
                ]
            ),
        )
        menu.addTab(
            "appearance",
            "外观",
            page_content(
                [
                    ("菜单外观", claim("menu_theme", "menu_density", "menu_radius", "menu_font", "menu_font_size", "menu_translucent", "menu_opacity")),
                    (
                        "高级配色",
                        claim(
                            "light_background",
                            "light_foreground",
                            "light_hover",
                            "dark_background",
                            "dark_foreground",
                            "dark_hover",
                        ),
                        True,
                    ),
                ]
            ),
        )
        menu.setProperty("contentMaxWidth", 1240)

        watchdog_rows = list(self.watchdog_page.findChildren(SettingRow))
        claimed.update(watchdog_rows)
        # 行为重复检测内置；这里只分组循环和卡住检测的可调偏好。
        stuck_rows = [r for r in watchdog_rows if r.objectName().startswith("settingRow_stuck_")]
        loop_rows = [r for r in watchdog_rows if not r.objectName().startswith(("settingRow_stuck_",))]
        dialogue_rows = claim_prefix("dialogue_")
        gate_rows = claim_prefix("report_gate_")
        automation = page_content(
            [
                ("ChatGPT Work/Codex", claim("codex_link")),
                ("Cursor", claim("cursor_link")),
                ("循环检测", loop_rows),
                ("卡住检测", stuck_rows),
            ]
        )
        # 「事件气泡触发概率」＝一个可折叠框：按**事件聚合类别**分组，每组只放
        # 该类触发概率滑块（紧凑、常用，默认展开）。
        # 逐事件自定义文案行单独收进第二个折叠框并**默认折叠**（不用自定义台词的用户
        # 不该翻过整页文案框；搜索命中时两个框都会自动展开，见 _search_settings）。
        gates_box = CollapsibleGroup("事件气泡触发概率", automation)
        phrases_box = CollapsibleGroup("自定义台词（逐事件文案）", automation)
        gate_row_by_id = {row.objectName(): row for row in gate_rows}
        phrase_rows_by_gate: dict[str, list] = {}
        for row in dialogue_rows:
            event_key = row.objectName()[len("settingRow_dialogue_") :]
            phrase_rows_by_gate.setdefault(gate_for_event(event_key) or "", []).append(row)
        for gate in REPORT_GATE_KEYS:
            gate_row = gate_row_by_id.get(f"settingRow_report_gate_{gate}")
            if gate_row is not None:
                gates_box.add_group(REPORT_GATE_LABELS[gate], [gate_row])
            phrase_rows = phrase_rows_by_gate.get(gate, [])
            if phrase_rows:
                phrases_box.add_group(REPORT_GATE_LABELS[gate], phrase_rows)
        # 默认展开：这些文案行改造前就在该页可见，折叠框只提供"可以收起来"，
        # 不把原有入口藏起来；搜索命中时也会自动展开（见 _search_settings）。
        gates_box.set_expanded(False)
        phrases_box.set_expanded(False)
        self.report_gates_box = gates_box
        self.dialogue_phrases_box = phrases_box
        automation_layout = automation.layout()
        # dialogue_* 里有一类行**不属于任何事件门**（表达风格、专属文案对象、弹窗文案
        # 模板 JSON）：它们不是某个事件的气泡文案，而是文案风格的全局控件，因此
        # gate_for_event 返回 None、只会落到上面那个空串桶里。这些行已被
        # claim_prefix("dialogue_") 认领（不再进 leftovers），若不显式放回本域就会
        # 从设置页里彻底消失。
        # 顶层顺序：「文案风格与模板」（全局风格控件）在前，「事件气泡触发概率」
        # 折叠框**排在其末尾**——概率门按**事件类别**抽稀气泡，与文案风格/模板无关，
        # 所以让风格控件先出现，概率门收在它后面。
        insert_at = 2
        ungated_dialogue_rows = phrase_rows_by_gate.get("", [])
        if ungated_dialogue_rows:
            automation_layout.insertWidget(
                insert_at,
                SettingsSection("文案风格与模板", ungated_dialogue_rows, automation, advanced=True),
            )
            insert_at += 1
        automation_layout.insertWidget(insert_at, gates_box)
        insert_at += 1
        automation_layout.insertWidget(insert_at, phrases_box)
        # 顶层顺序：消费统计 → Agent 联动 → 文案风格 → 触发概率 → 自定义台词 → 各类检测。
        # 「消费统计」独立成一级分组且排最前（直接可见，不藏在折叠框里）。
        # 必须在上面的插入全部做完之后再插，否则会被后来的 insertWidget(0, ...) 挤下去。

        # Preserve any newly added row until it receives an explicit domain decision.
        leftovers = [row for row in all_rows if row not in claimed]
        if leftovers:
            layout = automation.layout()
            layout.insertWidget(max(0, layout.count() - 1), SettingsSection("待分类（开发期）", leftovers, automation))

        while self.pages.count():
            self.pages.removeWidget(self.pages.widget(0))
        self.sidebar.clear()
        domain_content = {
            "常规": general,
            "桌宠": pet,
            "互动": interaction,
            "菜单": menu,
            "自动化与联动": automation,
        }
        for label, icon in SETTINGS_DOMAIN_NAV:
            content = domain_content.get(label)
            if content is None:
                continue
            self._add_page(label, icon, self._page_shell(label, content))
        for page in old_pages.values():
            page.deleteLater()

    def _clear_search_matches(self) -> None:
        for row in self._search_rows:
            if row.property("searchMatch"):
                row.setProperty("searchMatch", False)
                row.style().unpolish(row)
                row.style().polish(row)

    def _search_settings(self, query: str, *, advance: bool = False) -> None:
        query = query.strip().lower()
        self._clear_search_matches()
        if not query:
            self._search_matches = []
            self._search_index = -1
            self.search_status.hide()
            return
        matches = [row for row in self._search_rows if query in f"{row.label.text()} {row.hint_label.text()} {row.objectName()}".lower()]
        if not matches:
            self._search_matches = []
            self._search_index = -1
            self.search_status.setText("未找到匹配的设置")
            self.search_status.show()
            return
        if matches != self._search_matches:
            self._search_matches = matches
            self._search_index = 0
        elif advance:
            self._search_index = (self._search_index + 1) % len(matches)
        row = matches[self._search_index]
        row.setProperty("searchMatch", True)
        row.style().unpolish(row)
        row.style().polish(row)
        page_index = 0
        for index in range(self.pages.count()):
            if self.pages.widget(index).isAncestorOf(row):
                page_index = index
                break
        self.sidebar.setCurrentRow(page_index)
        page = self.pages.widget(page_index)
        ancestor = row.parentWidget()
        while ancestor is not None and ancestor is not page:
            if isinstance(ancestor, CollapsibleGroup):
                # 命中折叠框内的行：先自动展开，否则搜索结果存在但看不见。
                ancestor.set_expanded(True)
            if isinstance(ancestor, SettingsTabContainer):
                ancestor.activate_for_descendant(row)
                break
            ancestor = ancestor.parentWidget()
        scroll = page.findChild(QScrollArea, "settingsScroll")
        if scroll is not None:
            scroll.ensureWidgetVisible(row, 0, 24)
        self.search_status.setText(f"{self._search_index + 1}/{len(matches)} · {row.label.text()}")
        self.search_status.show()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.search_edit and event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._search_settings(self.search_edit.text(), advance=True)
            return True
        return super().eventFilter(watched, event)

    def _apply_selected_theme(self, *_args) -> None:
        theme = str(self.menu_theme_select.currentData() or "system")
        dark = theme == "dark" or (theme == "system" and _system_dark())
        self.setProperty("settingsDark", dark)
        self.setStyleSheet(_settings_stylesheet(theme))
        for control in self.findChildren(ModernSelect):
            if control._popup is not None:
                control._popup.setStyleSheet(control.popupStyleSheet())
            control.update()
        for popup in self.findChildren(QMenu):
            if popup.property("settingsPopup"):
                configure_settings_action_popup(popup)
        for control in self.findChildren(ToggleSwitch):
            control.update()


    def _save(self) -> None:
        """「保存并退出」：写入配置并关闭对话框。"""
        if not self._write_config():
            return
        self._saved_via_button = True
        self.accept()

    def _write_config(self) -> bool:
        """把当前控件值写入 config 并落盘（按钮与直接关闭共用）。

        保存前从磁盘重读：吸收外部对本对话框未暴露字段的改动。
        standalone 下这条尤其关键——主进程在设置开着期间会自己写 config
        （托盘菜单开关等），不 reload 就把别人的改动回滚了。
        已知限制：已暴露字段仍是 last-writer-wins（对话框获胜）。
        返回是否成功落盘；失败时提示用户。
        """
        self.config.reload()
        minimum = min(self.min_spin.value(), self.max_spin.value())
        maximum = max(self.min_spin.value(), self.max_spin.value())
        texts = [line.strip()[:120] for line in self.texts_edit.toPlainText().splitlines() if line.strip()]
        self.config.set("spawn_inherit_size", self.spawn_inherit_size_check.isChecked())
        self.config.set("spawn_scale", float(self.spawn_scale_combo.currentData()))
        if self.dock_icon_check is not None:
            self.config.set("show_dock_icon", self.dock_icon_check.isChecked())
        self.config.set("throw_strength", str(self.throw_strength_select.currentData() or "standard"))
        self.config.set("slingshot_enabled", self.slingshot_check.isChecked())
        self.config.set("collision_enabled", self.collision_enabled_check.isChecked())
        self.config.set("collision_restitution", self.collision_restitution_spin.value())
        self.config.set("collision_friction", self.collision_friction_spin.value())
        self.config.set("collision_mass_scale", self.collision_mass_scale_spin.value())
        self.config.set("collision_impulse_cap", self.collision_impulse_cap_spin.value())
        self.config.set("lock_position", self.lock_position_check.isChecked())
        self.config.set("shift_drag", self.shift_drag_check.isChecked())
        self.config.set("pet_opacity", int(self.pet_opacity_spin.value()))
        self.config.set("click_show_self_talk", self.click_self_talk_check.isChecked())
        if self.auto_hide_fullscreen_check is not None:
            self.config.set("auto_hide_fullscreen", self.auto_hide_fullscreen_check.isChecked())
        # 「单进程多开」键不落盘控件值：开关已隐藏（拓扑收口 Phase A），
        # 配置字典里加载的原值随 config.save() 原样回写（兼容保留）。
        if self.cursor_hidden_passthrough_check is not None:
            self.config.set("cursor_hidden_passthrough", self.cursor_hidden_passthrough_check.isChecked())
        self.config.set("animation_gap_seconds", self.gap_spin.value())
        self.config.set("self_talk_enabled", self.self_talk_check.isChecked())
        self.config.set("self_talk_bubble_style", self.bubble_style_select.currentData())
        self.config.set("self_talk_min_interval", minimum)
        self.config.set("self_talk_max_interval", maximum)
        self.config.set("self_talk_duration_seconds", self.self_talk_duration_spin.value())
        self.config.set("self_talk_texts", texts or list(DEFAULT_SELF_TALK_TEXTS))
        self.config.set("self_talk_image_dir", self.self_talk_image_dir_picker.text())
        self.config.set("self_talk_image_scale", self.self_talk_image_scale_spin.value())
        self.config.set("self_talk_image_chance", self.self_talk_image_chance_spin.value())
        self.config.set("bubble_text_scale", self.bubble_text_scale_spin.value())
        self.config.set("dialogue_mode", str(self.dialogue_mode_select.currentData() or "legacy"))
        # 统一预设：编辑区当前层 flush 后，global 层 + agents delta 分层写回
        self._dialogue_flush_scope()
        new_global = self._dialogue_scope_values("")
        agents_delta: dict[str, dict[str, list[str]]] = {}
        for scope in self._dialogue_scope_buffer:
            if scope == "":
                continue
            values = self._dialogue_scope_values(str(scope))
            if values:
                agents_delta[str(scope)] = values
        # 兼容旧扁平存储：双层仅当存在 agents delta 或原配置已是双层时启用
        current_phrases = self.config.get("dialogue_phrases", {})
        was_preset = isinstance(current_phrases, dict) and ("global" in current_phrases or "agents" in current_phrases)
        # Retired event text has no editor, but it remains historical user data.
        if isinstance(current_phrases, dict):
            old_global = current_phrases.get("global", {}) if was_preset else current_phrases
            if isinstance(old_global, dict):
                for key in ("balance.loading", "balance.result"):
                    if key in old_global:
                        new_global[key] = old_global[key]
            old_agents = current_phrases.get("agents", {}) if was_preset else {}
            if isinstance(old_agents, dict):
                for scope, old_values in old_agents.items():
                    if not isinstance(old_values, dict):
                        continue
                    retired = {key: old_values[key] for key in ("balance.loading", "balance.result") if key in old_values}
                    if retired:
                        agents_delta.setdefault(str(scope), {}).update(retired)
        if agents_delta or was_preset:
            self.config.set("dialogue_phrases", {"global": new_global, "agents": agents_delta})
        else:
            self.config.set("dialogue_phrases", new_global)
        # 记住上次编辑层：下次打开设置直接回到该 Agent 专属层（未知值回落全局）
        self.config.set("dialogue_last_scope", str(getattr(self, "_dialogue_scope", "") or ""))
        agent_cfg = dict(self.config.get("agent_link", {}))
        agent_cfg["codex"] = self.codex_link_check.isChecked()
        agent_cfg["cursor"] = self.cursor_link_check.isChecked()
        # 循环检测设置页（合并写回，不覆盖 agent_link 其他字段）
        if self.watchdog_page is not None:
            agent_cfg = self.watchdog_page.apply_to_config(agent_cfg)

        # 事件汇报概率门：滑块值即通过概率（0.00–1.00，步长 0.05），逐类写回。
        report_gates = dict(agent_cfg.get("report_gates") or {})
        for gate, slider in self.report_gate_sliders.items():
            report_gates[gate] = round(float(slider.value()), 2)
        agent_cfg["report_gates"] = report_gates

        self.config.set("agent_link", agent_cfg)
        self.config.set(
            "context_menu_appearance",
            {
                "theme": self.menu_theme_select.currentData(),
                "density": self.menu_density_select.currentData(),
                "corner_radius": self.menu_radius_select.currentData(),
                "ui_font": self.menu_font_select.currentData(),
                "ui_font_size": self.menu_font_size_select.currentData(),
                "translucent": self.menu_translucent_check.isChecked(),
                "opacity": self.menu_opacity_spin.value(),
                "light_background": self.light_background_picker.text(),
                "light_foreground": self.light_foreground_picker.text(),
                "light_hover": self.light_hover_picker.text(),
                "dark_background": self.dark_background_picker.text(),
                "dark_foreground": self.dark_foreground_picker.text(),
                "dark_hover": self.dark_hover_picker.text(),
            },
        )
        self.config.set("quick_launch_apps", self.quick_launch_editor.apps())
        self.config.set("quick_urls", self.quick_urls_editor.urls())
        # 落种占位语义——仅当用户在该子肥鱼自己的设置界面保存过才置真；
        # 位置自动保存等一切后台写盘不得置位。主配置（slot 0/主肥鱼）保存不置位。
        if self.config.instance_id:
            self.config.set("user_customized", True)
        ok = self.config.save()
        if not ok:
            QMessageBox.warning(
                self,
                "保存失败",
                "配置未能写入磁盘，改动可能在重启后丢失。\n\n配置路径：" + str(self.config.path),
            )
        return ok


    def reject(self) -> None:  # noqa: N802 - Qt API
        """Esc 路径与关闭按钮一致：保存设置。"""
        if not getattr(self, "_saved_via_button", False):
            try:
                self._write_config()
            except Exception:
                logging.exception("Esc 关闭设置时保存配置失败")
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        """直接关闭（X / Esc）时同样落盘，避免修改丢失。

        设置项都是即时型偏好，与右键菜单/托盘修改的写入时机保持一致；
        已走「保存并退出」则跳过（防重复写入）。
        """
        if not getattr(self, "_saved_via_button", False):
            try:
                if not self._write_config():
                    event.ignore()
                    return
            except Exception:
                logging.exception("关闭设置时保存配置失败")
        super().closeEvent(event)
