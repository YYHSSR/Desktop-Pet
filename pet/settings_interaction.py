# -*- coding: utf-8 -*-
"""互动设置：点击反馈与周期自言自语，使用共享设置卡片。"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from .settings_widgets import SettingRow, SettingsSection


def build_click_rows(dialog) -> list[SettingRow]:
    """「点击反馈」组的行（仅保留点击自言自语触发）。"""
    return [
        SettingRow("click_self_talk", "点击触发自言自语", "点击时随机显示一条自言自语内容。", dialog.click_self_talk_check),
    ]


def build_self_talk_rows(dialog) -> list[SettingRow]:
    """「自言自语」组的行（周期气泡的台词 / 节奏 / 配图）。"""
    return [
        SettingRow(
            "self_talk_bubble_style",
            "气泡方案",
            "选择气泡视觉与相对桌宠的位置；贴近屏幕边缘时自动换位。",
            dialog.bubble_style_select,
        ),
        SettingRow("self_talk", "气泡自言自语", "让桌宠偶尔显示一条随机思考气泡。", dialog.self_talk_check),
        SettingRow("self_talk_duration", "显示时间", "每条文字或图片气泡保持显示的时间。", dialog.self_talk_duration_spin),
        SettingRow("self_talk_min", "最短间隔", "上一条气泡消失后，到下一条出现前的最短空闲时间。", dialog.min_spin),
        SettingRow("self_talk_max", "最长间隔", "上一条气泡消失后，到下一条出现前的最长空闲时间。", dialog.max_spin),
        SettingRow("self_talk_texts", "候选内容", "每行一条；留空时恢复内置文本。", dialog.texts_edit, stacked=True),
        SettingRow(
            "self_talk_images",
            "图片目录",
            "从目录中的常见图片格式随机选择；默认使用内置配图，留空时只显示文本。",
            dialog.self_talk_image_dir_picker,
            stacked=True,
        ),
        SettingRow("self_talk_image_scale", "配图大小", "气泡里配图的显示尺寸（100% 为默认）。", dialog.self_talk_image_scale_spin),
        SettingRow(
            "self_talk_image_chance",
            "配图概率",
            "点击/定时自言自语时显示配图的概率，其余显示文本；0% 表示只出文本。"
            "图片目录里往往有几十张图，这一项决定文本还能不能轮到（默认 30%）。",
            dialog.self_talk_image_chance_spin,
        ),
    ]


def build_interaction_domain(dialog) -> QWidget:
    """「互动」域整页：合并点击反馈与自言自语，像常规中的设置一样直接按卡片竖排布局。"""
    content = QWidget(dialog)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(18)
    layout.addWidget(SettingsSection("点击反馈", build_click_rows(dialog), content))
    layout.addWidget(SettingsSection("自言自语", build_self_talk_rows(dialog), content))
    layout.addStretch(1)
    return content
