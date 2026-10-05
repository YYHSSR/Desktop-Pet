"""User-facing bubble placement, preference ownership and tray recovery."""
import json
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from pet.app import AppShell
from pet.config import Config
from pet.modern_settings_dialog import ModernSettingsDialog, SettingRow
from pet.persona_phrases import PhrasePicker
from pet.speech_bubble import bubble_rect_for_anchor
from pet.window_placement import bubble_anchor_rect


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_retired_preferences_do_not_return_during_concurrent_save(tmp_path):
    cfg = Config(tmp_path)
    cfg.dir.mkdir(parents=True, exist_ok=True)
    retired = {"idle_low_fps_enabled": True, "idle_low_fps_threshold": 5,
               "dynamic_island": {"enabled": True}, "spawn_inherit_dynamic_island": True,
               "menu_easter_egg": {"enabled": True}, "context_menu_layout": {"nodes": []}}
    cfg.path.write_text(json.dumps({**retired, "version": 4, "scale": 0.85, "self_talk_texts": ["我的台词"]}), encoding="utf-8")
    cfg.reload()
    cfg.set("pet_opacity", 88)
    cfg.path.write_text(json.dumps({**retired, "version": 4, "scale": 0.85, "self_talk_texts": ["我的台词"]}), encoding="utf-8")
    assert cfg.save()
    for data in (cfg.data, json.loads(cfg.path.read_text(encoding="utf-8"))):
        assert retired.keys().isdisjoint(data)
        assert data["scale"] == 0.85
        assert data["self_talk_texts"] == ["我的台词"]


def test_settings_do_not_overwrite_preferences_owned_by_other_surfaces(app, tmp_path):
    cfg = Config(tmp_path)
    cfg.save()
    dialog = ModernSettingsDialog(cfg, standalone=True)
    try:
        ids = {row.objectName()[len("settingRow_"):] for row in dialog.findChildren(SettingRow)}
        assert {"scale", "playback_speed", "on_top", "no_move", "mouse_through", "drag_physics", "autostart", "edge_probe", "idle_low_fps", "context_menu_layout"}.isdisjoint(ids)
        assert not any(key.startswith(("dynamic_island", "egg_")) for key in ids)
        external = Config(tmp_path)
        external.set("scale", 0.85)
        external.set("playback_speed", 1.5)
        external.set("mouse_through", True)
        external.set("on_top", False)
        assert external.save()
        dialog.pet_opacity_spin.setValue(85)
        assert dialog._write_config()
        saved = Config(tmp_path)
        assert (saved.get("scale"), saved.get("playback_speed"), saved.get("mouse_through"), saved.get("on_top"), saved.get("pet_opacity")) == (0.85, 1.5, True, False, 85)
    finally:
        dialog.close()
        app.processEvents()


@pytest.mark.parametrize("placement", ["top", "top_left", "top_right"])
def test_bubble_keeps_a_close_anchor_at_screen_top(placement):
    anchor = QRect(580, 10, 160, 215)
    placed = bubble_rect_for_anchor(anchor, QSize(180, 120), QRect(0, 0, 1000, 700), placement)
    assert not placed.intersects(anchor)
    # At the top, use a nearby side or bottom; never drift to distant canvas whitespace.
    nearest_x = max(0, anchor.left() - placed.right(), placed.left() - anchor.right())
    nearest_y = max(0, anchor.top() - placed.bottom(), placed.top() - anchor.bottom())
    assert max(nearest_x, nearest_y) <= 9


def test_bubble_anchor_uses_body_instead_of_wide_animation_effects():
    host = SimpleNamespace(
        _collision_local_bounds=QRect(0, 0, 600, 420),
        _stable_body_local_rect=lambda: QRect(210, 70, 160, 215),
        _draw_delta=QPoint(8, 0),
        frameGeometry=lambda: QRect(100, 50, 600, 420),
        visible_content_rect=lambda: QRect(310, 120, 160, 215),
    )
    assert bubble_anchor_rect(host) == QRect(318, 120, 160, 215)


@pytest.mark.parametrize("mode", ["legacy", "whale_maid"])
def test_activity_copy_is_readable_without_optional_log_fields(mode):
    picker = PhrasePicker()
    for key in ("activity.read", "activity.search", "activity.edit", "activity.run", "activity.default"):
        for _ in range(8):
            text = picker.get(mode, key, "工作中", autohide={"step", "sessionName"}, name="ChatGPT", label="处理任务", tool="shell")
            assert "第  步" not in text and "第 步" not in text and "会话  " not in text
            assert "{step}" not in text and "{sessionName}" not in text
            assert len(text) <= 48


def test_tray_owns_system_options_and_refresh_does_not_write_autostart(app, tmp_path, monkeypatch):
    import pet.app as app_mod
    cfg = Config(tmp_path)
    writes = []
    state = {"enabled": False}
    monkeypatch.setattr(app_mod.autostart_mod, "is_enabled", lambda: state["enabled"])
    pixmap = QPixmap(24, 24)
    pixmap.fill()
    win = SimpleNamespace(icon_pixmap=lambda: pixmap, hide_speech_bubble=lambda: None, isVisible=lambda: True,
                          go_default_corner=lambda: None,
                          set_mouse_through=lambda value: cfg.set("mouse_through", value))
    instance = SimpleNamespace(win=win, config=cfg, open_modern_settings=lambda: None, switch_character=lambda *_: None,
                               _set_autostart=lambda value, _win: writes.append(value))
    shell = object.__new__(AppShell)
    shell.app, shell.config, shell._instances = app, cfg, [instance]
    shell.instance = instance
    shell._tray_menu, shell._tray_submenus, shell._tray_actions = None, [], []
    tray = shell._build_tray(win)
    try:
        menu = tray.contextMenu()
        labels = [act.text() for act in menu.actions() if not act.isSeparator()]
        assert labels == ["显示 / 隐藏所有桌宠", "鼠标穿透", "开机自启", "退出"]
        state["enabled"] = True
        menu.aboutToShow.emit()
        assert writes == []
        assert next(act for act in menu.actions() if act.text() == "开机自启").isChecked()
    finally:
        tray.hide()
        tray.deleteLater()
        menu.close()
        menu.deleteLater()
        app.processEvents()


def test_custom_step_phrase_remains_readable_when_log_omits_step():
    from pet.persona_phrases import render_template
    assert render_template("ChatGPT 正在执行第 {step} 步。", {}, autohide={"step"}) == "ChatGPT 正在执行当前步骤。"
    assert render_template("ChatGPT 正在执行第 {step} 步。", {"step": 3}, autohide={"step"}) == "ChatGPT 正在执行第 3 步。"


def test_thought_bubble_lines_fit_measured_font_height(app):
    from PySide6.QtGui import QFontMetrics
    from pet.speech_bubble import PetSpeechBubble
    bubble = PetSpeechBubble(style_id="breath_bubble")
    try:
        bubble.show_text("ChatGPT 正在检查修改，马上就好。", QRect(580, 10, 160, 215), pet_scale=0.5)
        metrics = QFontMetrics(bubble.label.font())
        assert len(bubble.label.text().split("\n")) * metrics.lineSpacing() <= bubble.label.height()
    finally:
        bubble.close()
        bubble.deleteLater()
        app.processEvents()


def test_thought_tail_points_toward_pet_after_screen_edge_fallback(app):
    from pet.speech_bubble import PetSpeechBubble
    bubble = PetSpeechBubble(style_id="breath_bubble")
    try:
        for _ in range(2):
            bubble.show_text("马上就好。", QRect(10, 10, 100, 180), pet_scale=0.5)
            app.processEvents()
            main = bubble._main_bubble_path.boundingRect()
            tail = bubble._breath_paths[-1].boundingRect()
            assert bubble._breath_mirrored
            assert tail.center().x() < main.center().x()
            assert main.contains(bubble.label.geometry().center())
    finally:
        bubble.close()
        bubble.deleteLater()
        app.processEvents()
