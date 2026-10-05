# -*- coding: utf-8 -*-
"""批5.2a：子系统上移 + 托盘聚合（单进程多窗共享）的机器可验测试。

覆盖 DISPATCH_batch52a 验收 ①：
- agent_link 上移：flag 开时单 manager 扇出——两窗各收到呈现事件（全体跳舞）；
- 托盘聚合：flag 开时单托盘 + 每窗子菜单存在，动作路由正确（显示/隐藏、切换角色、退出这只）；
- 灵动岛单击 toggle **全部**窗（按聚合可见态同步 set_pet_visible）；
- flag 关逐位一致：共享子系统不实例化（每窗各自 manager，既有 spawn 测试族全绿）。

flag 关的逐位一致由既有 tests/test_single_process_spawn.py 族保证（本批不弱化、
只在 __init__ 注入 None → 每窗各自建）。
"""
from __future__ import annotations

import os
import uuid

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

import pet.app as app_mod
import pet.slot_manager as slot_manager_mod
from pet import catalog
from pet.agent_link import AgentLinkManager
from pet.app import AppShell, PetInstance
from pet.config import Config
from pet.multi_window_shared import MultiWindowProxy


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


class _FakeLib:
    def pause_warm(self):
        pass

    def resume_warm(self):
        pass


class _RecordWin:
    """记录调用的多窗替身：记录呈现事件，供代理扇出断言。"""

    def __init__(self, visible=True):
        self.is_shown = visible
        self.bubbles: list[str] = []
        self.anims: list[str] = []
        self.activities = 0
        self.link_provider = None
        self.cfg = None
        self._single_process_spawn = True
        self._bubble_busy_until = 0.0
        # 非空 dict（代理以 `if c:` 判真）
        self.cats = {"idle": "idle", "acts": ["写代码"], "moves": [], "turns": []}
        self._dragging = False
        self._physics_mode = None
        self._click_effect_phase = 0
        self.mouse_through = False

    # ---- 代理/呈现接口 ----
    def set_link_next_provider(self, p):
        self.link_provider = p

    def show_bubble(self, text, duration_ms=4500):
        self.bubbles.append(text)

    def request_link_anim(self, name):
        self.anims.append(name)

    def request_link_idle(self):
        pass

    def mark_activity(self):
        self.activities += 1

    def clear_pending_link_anim(self):
        pass

    def hold_bubble(self, seconds):
        self._bubble_busy_until = seconds

    def on_look_synced(self, user_text, reply):
        pass

    def isVisible(self):
        return self.is_shown

    def hide(self, notify=True):
        self.is_shown = False

    def show(self):
        self.is_shown = True

    def deleteLater(self):
        pass

    # ---- 托盘构建所需 ----
    def icon_pixmap(self, _size=None):
        return QPixmap(2, 2)

    def set_mouse_through(self, on):
        pass

    def hide_speech_bubble(self):
        pass


def _make_flag_on_shell(tmp_path):
    config = Config(tmp_path)
    config.set("experimental_single_process_spawn", True)
    config.save()
    slot_id, slot_handle = slot_manager_mod.acquire_pet_slot(config.dir, preferred_slot=0)
    shell = AppShell(QApplication.instance(), config,
                     slot_handle=slot_handle, slot_id=slot_id)
    return shell, config, slot_handle


def _make_primary_record_win(shell, config):
    win = _RecordWin()
    win.cfg = config
    shell.instance.win = win
    return win


def _make_second_record_win(shell, tmp_path, monkeypatch):
    """经 spawn_in_process_window 生成第二实例（独立 slot/Config），窗口为 _RecordWin。"""
    def fake_build_window(self, character_id, lib=None, build_tray=True):
        win = _RecordWin()
        win.cfg = self.config
        win._single_process_spawn = self.shell._single_process_spawn
        self.win = win
        return win

    monkeypatch.setattr(app_mod.PetInstance, "_build_window", fake_build_window)
    monkeypatch.setattr(app_mod.PetInstance, "_apply_spawn_offset", lambda self: None)
    second = shell.spawn_in_process_window(1)
    return second


def _stop_sessions(*insts):
    for inst in insts:
        try:
            inst.collision_ipc.stop()
        except Exception:
            pass


def test_flag_on_agent_link_single_manager_fans_out(tmp_path, app, monkeypatch):
    """§③.1 / 验收①：flag 开时同一份 AgentLinkManager 服务两窗；
    联动气泡只发首个可见窗（多窗不重复弹），联动动画仍扇出到各可见窗。"""
    shell, config, primary_handle = _make_flag_on_shell(tmp_path)
    try:
        primary_win = _make_primary_record_win(shell, config)
        second = _make_second_record_win(shell, tmp_path, monkeypatch)
        second_win = second.win

        # 一份共享 manager（对象身份一致）
        assert shell._shared is not None
        mgr = shell._shared.agent_link
        assert len(shell.instances) == 2

        # 触发一次联动气泡呈现 → 仅首个可见窗收到（多窗不重复弹）
        mgr._show_link_bubble("全体跳舞", important=True, duration_ms=2000)
        assert "全体跳舞" in primary_win.bubbles
        assert "全体跳舞" not in second_win.bubbles

        # 「全体跳舞」动画扇出：state_applied 忙状态 → request_link_anim 到两可见窗
        primary_win.bubbles.clear()
        second_win.bubbles.clear()
        mgr._on_agent_state("codex", "working", gen=0)
        assert primary_win.anims, "主窗应收到联动动画"
        assert second_win.anims, "第二窗应收到联动动画（全体跳舞）"

        # 主窗隐藏后：呈现不再扇出到隐藏窗
        second_win.hide()
        second_win.bubbles.clear()
        mgr._show_link_bubble("只看主窗", important=True, duration_ms=2000)
        assert "只看主窗" in primary_win.bubbles
        assert "只看主窗" not in second_win.bubbles, "隐藏窗不接收呈现事件"
    finally:
        _stop_sessions(*getattr(shell, "instances", []))
        if getattr(shell, "_shared", None) is not None:
            shell._shared.stop_all()
        slot_manager_mod._unlock_file(primary_handle)


def test_flag_off_shared_subsystems_none(tmp_path, app):
    """验收④：flag 关不实例化共享子系统（每窗各自建，逐位一致）。"""
    config = Config(tmp_path)
    config.set("experimental_single_process_spawn", False)
    config.save()
    shell = AppShell(QApplication.instance(), config,)
    assert shell._single_process_spawn is False
    assert shell._shared is None
    assert shell.instance.win is None


def test_shared_tray_toggles_all_windows(tmp_path, app, monkeypatch):
    """§③.3 / 验收②：单托盘的显示操作路由到全部本地桌宠。"""
    shell, config, primary_handle = _make_flag_on_shell(tmp_path)
    try:
        primary_win = _make_primary_record_win(shell, config)
        second = _make_second_record_win(shell, tmp_path, monkeypatch)

        tray = shell._build_tray(primary_win)
        menu = shell._tray_menu
        labels = [a.text() for a in menu.actions() if not a.isSeparator()]
        assert labels == ["显示 / 隐藏所有桌宠", "鼠标穿透", "开机自启", "退出"]
        assert all(a.menu() is None for a in menu.actions())
        toggle = menu.actions()[0]
        toggle.trigger()
        assert not primary_win.is_shown and not second.win.is_shown
        toggle.trigger()
        assert primary_win.is_shown and second.win.is_shown
        tray.hide()
    finally:
        _stop_sessions(*getattr(shell, "instances", []))
        if getattr(shell, "_shared", None) is not None:
            shell._shared.stop_all()
        slot_manager_mod._unlock_file(primary_handle)


def test_flag_on_hidden_notify_text_non_primary(tmp_path, app, monkeypatch):
    """§③.4：隐藏提示文案对非主窗改为指引托盘子菜单（P2-5 消除误导）。"""
    shell, config, primary_handle = _make_flag_on_shell(tmp_path)
    try:
        primary_win = _make_primary_record_win(shell, config)
        second = _make_second_record_win(shell, tmp_path, monkeypatch)

        shown = []
        tray = type("_FakeTray", (), {
            "tray": None,
            "showMessage": lambda self, *a, **k: shown.append((a, k)),
        })()
        shell.tray = tray

        # 非主窗隐藏：文案指向托盘子菜单
        second._notify_pet_hidden()
        assert shown, "非主窗隐藏应弹托盘提示"
        msg = shown[-1][0][1]
        assert "显示 / 隐藏" in msg, f"非主窗提示应指向托盘子菜单: {msg}"

        # 主窗隐藏：恢复旧文案
        shown.clear()
        primary_win.cfg = config
        shell.instance._notify_pet_hidden()
        msg = shown[-1][0][1]
        assert "显示 / 隐藏所有桌宠" in msg
    finally:
        _stop_sessions(*getattr(shell, "instances", []))
        if getattr(shell, "_shared", None) is not None:
            shell._shared.stop_all()
        slot_manager_mod._unlock_file(primary_handle)


# ---------------------------------------------------------------- P1 复审回归
def test_new_window_receives_link_provider_after_real_build(tmp_path, app, monkeypatch):
    """P1-1 回归（真实 _build_window 路径，不再整体 monkeypatch）：新窗必须在
    建窗完成后拿到共享联动 provider——`_wire_shared_subsystems` 若早于
    `self.win = win` 执行，扇出遍历不到新窗，provider 永远缺位。"""
    from tests.test_predictive_prewarm import FakeLibrary

    shell, config, handle = _make_flag_on_shell(tmp_path)
    win = None
    try:
        win = shell.instance._build_window("shenshen", lib=FakeLibrary())
        assert getattr(win, "_link_next_provider", None) is not None, (
            "真实建窗路径下新窗必须拿到联动 provider（P1-1 时序回归）")
    finally:
        if win is not None:
            win.close()
            win.deleteLater()
        slot_manager_mod._unlock_file(handle)
        app.processEvents()


def test_shared_fullscreen_broadcast_respects_per_window_config(tmp_path, app):
    """P1-2 回归：共享全屏广播必须按每窗 auto_hide_fullscreen 过滤——
    关掉该功能的窗不得被无关广播隐藏。"""
    from tests.test_predictive_prewarm import FakeLibrary

    shell, config, handle = _make_flag_on_shell(tmp_path)
    win1 = win2 = None
    try:
        win1 = shell.instance._build_window("shenshen", lib=FakeLibrary())
        sec = PetInstance(shell, Config(base=tmp_path, instance_id="slot-1"),)
        shell._instances.append(sec)
        win2 = sec._build_window("shenshen", lib=FakeLibrary(), build_tray=False)
        win2.set_auto_hide_fullscreen(False)

        shell._on_shared_fullscreen(True)
        app.processEvents()

        assert not win1.isVisible(), "开启自动隐藏的窗应被全屏广播隐藏"
        assert win2.isVisible(), "关闭 auto_hide_fullscreen 的窗不得被广播误隐藏（P1-2）"

        shell._on_shared_fullscreen(False)
        app.processEvents()
        assert win1.isVisible(), "全屏结束后被隐藏的窗应恢复"
        assert win2.isVisible()
    finally:
        for w in (win1, win2):
            if w is not None:
                w.close()
                w.deleteLater()
        _stop_sessions(shell.instance, sec)
        slot_manager_mod._unlock_file(handle)
        if sec.slot_handle is not None:
            slot_manager_mod._unlock_file(sec.slot_handle)
        app.processEvents()


# ======================================================================
# PR57 根因修复：共享 AgentLinkManager 的 win 是 MultiWindowProxy，
# 但它缺 show_alert / resolve_alert，导致单进程多窗下所有交互式提醒
# （审批/问题/控制级 Watchdog）全部静默退化为无按钮纯文本气泡。
# 这里给 proxy 补上 alert 扇出面，并用红→绿测试钉住行为。
# ======================================================================


class _AlertRecordWin:
    """记录 show_alert / show_bubble / resolve_alert 的多窗替身，供 proxy 扇出断言。"""

    def __init__(self, visible=True):
        self.is_shown = bool(visible)
        self.alerts: list[dict] = []
        self.bubbles: list[dict] = []
        self.resolved: list[str] = []
        self.cleared = 0
        self.hidden = 0
        self._bubble_suppressed = False
        self._sticky_bubble_active = False
        self.cfg = None
        self._bubble_busy_until = 0.0
        self._dragging = False
        self._physics_mode = None
        self._click_effect_phase = 0
        self.mouse_through = False
        self.cats = {"idle": "idle", "acts": ["写代码"], "moves": [], "turns": []}

    # ---- 代理/呈现接口 ----
    def isVisible(self):
        return self.is_shown

    def show_bubble(self, text, duration_ms=4500, sticky=False, buttons=None):
        self.bubbles.append({"text": str(text), "sticky": bool(sticky), "buttons": buttons})

    def show_alert(self, text, *, subtitle="", duration_ms=0, buttons=None, sticky=True,
                   alert_id="", priority=3, alert_type="watchdog", metadata=None):
        self.alerts.append({
            "text": str(text), "subtitle": str(subtitle), "buttons": buttons,
            "sticky": bool(sticky), "duration_ms": int(duration_ms),
            "alert_id": str(alert_id), "priority": int(priority),
            "alert_type": str(alert_type), "metadata": dict(metadata or {}),
        })

    def resolve_alert(self, alert_id):
        self.resolved.append(str(alert_id))

    def clear_alerts(self):
        self.cleared += 1

    def hide_bubble(self):
        self.hidden += 1

    def request_link_anim(self, anim):
        pass

    def request_link_idle(self):
        pass

    def set_link_next_provider(self, p):
        pass

    def mark_activity(self):
        pass

    def clear_pending_link_anim(self):
        pass

    def hold_bubble(self, seconds):
        self._bubble_busy_until = seconds

    def on_look_synced(self, user_text, reply):
        pass

    def hide(self, notify=True):
        self.is_shown = False

    def show(self):
        self.is_shown = True

    def deleteLater(self):
        pass


class _ProxyShell:
    """只读 window 替身集合，满足 MultiWindowProxy 的 shell.instances/config 访问面。"""

    def __init__(self, config, windows):
        self.config = config
        self.instances = [type("_Inst", (), {"win": w})() for w in windows]
        self._shared = None


def _proxy_payload(**over):
    payload = {
        "type": "pet/exploration-watchdog",
        "level": "control",
        "risk": 6,
        "riskScore": 6,
        "reasons": ["W6 同类重复"],
        "steps": [{"behaviors": ["READ"], "targets": ["src/a.py"]}],
        "session_id": "sess-1",
        "goal": "修好登录",
        "agent_key": "codex",
        "agent_name": "ChatGPT",
        "targetCount": 1,
        "targets": ["src/a.py"],
    }
    payload.update(over)
    return payload


def _make_proxy_manager(tmp_path, windows):
    """构造共享 manager，win 为只读 MultiWindowProxy 集合（生产 320 行同构）。"""
    config = Config(base=tmp_path)
    proxy = MultiWindowProxy(_ProxyShell(config, windows))
    mgr = AgentLinkManager(proxy, config)
    mgr._clock = lambda: 1000.0
    return proxy, mgr


def _control_buttons(alert):
    return [name for name, _ in (alert["buttons"] or [])]


def test_proxy_control_alert_fans_out_buttons(tmp_path, app):
    """红→绿：无 show_alert 的 proxy 会把控制提醒退化为无按钮气泡（按钮丢失）。
    现行语义：交互式提醒只入队首个可见窗（多窗不重复轰炸），按钮不丢。"""
    w1, w2 = _AlertRecordWin(visible=True), _AlertRecordWin(visible=True)
    _, mgr = _make_proxy_manager(tmp_path, [w1, w2])
    try:
        mgr._on_exploration_warning("sess-1", _proxy_payload())
        assert w1.alerts, "首个可见窗应收到控制提醒（而非退化气泡）"
        alert = w1.alerts[-1]
        assert alert["alert_type"] == "control"
        assert _control_buttons(alert) == ["忽略"]
        assert alert["sticky"] is True
        assert not w2.alerts, "交互式提醒只在首个可见窗展示，不多窗重复"
    finally:
        mgr.shutdown()


def test_proxy_interaction_approval_buttons_fan_out(tmp_path, app):
    """红→绿：审批按钮也要经 show_alert 展示，不因 proxy 缺面而退化无按钮。"""
    w1, w2 = _AlertRecordWin(visible=True), _AlertRecordWin(visible=True)
    _, mgr = _make_proxy_manager(tmp_path, [w1, w2])
    try:
        mgr._pending_interactions["itest"] = {
            "kind": "approval", "text": "DSH 请求执行：rm -rf，请选择：",
            "interactive": True, "rpc_id": "rpc-1", "alert_id": "interaction:itest",
            "session_id": "s1", "agent_key": "codex",
        }
        mgr._show_interaction_bubble("itest")
        assert w1.alerts, "审批应经 show_alert 展示（同意/拒绝按钮不丢）"
        assert _control_buttons(w1.alerts[-1]) == []
        assert not w2.alerts, "审批只在首个可见窗展示"
    finally:
        mgr.shutdown()


def test_proxy_resolve_alert_collapses_all_windows(tmp_path, app):
    """新行为：任一窗点「忽略」，其它窗的同款控制气泡也必须被收起。"""
    w1, w2 = _AlertRecordWin(visible=True), _AlertRecordWin(visible=True)
    proxy, mgr = _make_proxy_manager(tmp_path, [w1, w2])
    try:
        mgr._on_exploration_warning("sess-1", _proxy_payload())
        ignore = next(cb for name, cb in w1.alerts[-1]["buttons"] if name == "忽略")
        ignore()
        assert w1.resolved == ["exploration-control:sess-1"]
        assert w2.resolved == ["exploration-control:sess-1"], "其它窗同款气泡也要收起"
    finally:
        mgr.shutdown()


def test_proxy_control_uses_show_alert_not_bubble_fallback(tmp_path, app):
    """钉住 :3175 的 TypeError 兜底：proxy 有 show_alert 后，控制提醒绝不落入
    show_bubble 兜底（否则按钮会随兜底退化掉）。提醒只在首个可见窗入队。"""
    w1, w2 = _AlertRecordWin(visible=True), _AlertRecordWin(visible=True)
    _, mgr = _make_proxy_manager(tmp_path, [w1, w2])
    try:
        mgr._on_exploration_warning("sess-1", _proxy_payload())
        assert w1.alerts, "首个可见窗应走 show_alert 通路"
        for win in (w1, w2):
            assert win.bubbles == [], "不得退化到 show_bubble 的 TypeError 兜底路径"
    finally:
        mgr.shutdown()


def test_proxy_bubble_suppressed_aggregates_any(tmp_path, app):
    """新行为：任一见窗打开设置(suppressed)则共享 manager 读到的抑制态为 True。"""
    w1, w2 = _AlertRecordWin(visible=True), _AlertRecordWin(visible=True)
    proxy, mgr = _make_proxy_manager(tmp_path, [w1, w2])
    try:
        assert proxy._bubble_suppressed is False
        w1._bubble_suppressed = True
        assert proxy._bubble_suppressed is True, "任一窗抑制则全局抑制"
        w1._bubble_suppressed = False
        w2._bubble_suppressed = True
        assert proxy._bubble_suppressed is True
        w2._bubble_suppressed = False
        assert proxy._bubble_suppressed is False
    finally:
        mgr.shutdown()


# ============================================================================
# 哨兵语义：_physics_mode 的哨兵是 None（非 False）
#
# 单窗 PetWindow._physics_mode 的取值域是 None / 'drag' / 'throw'，消费方
# （proactive G1 守卫）按 `is not None` 读哨兵。代理早期实现返回 `any(...)`
# 的 bool，把「无人处于物理模式」表达成 False——`False is not None` 恒真，
# 于是共享模式下 interacting 恒为 True、每次 tick 都在 G1 被静默拦截，
# 「主动识屏从不触发」且用户侧开关无效（拿到的是同一个共享实例）。
# 红→绿：修复前 proxy._physics_mode is False。
# ============================================================================


def test_proxy_physics_mode_is_none_when_nobody_in_physics(tmp_path, app):
    """红→绿：所有窗都不在物理模式时，代理必须返回哨兵 None（不是 False）。

    这是 G1 守卫的契约：False 与 None 在布尔上等价，但在 `is not None` 上
    天差地别。返回 False 等于对守卫谎报「有人正在拖拽/抛掷」。
    """
    w1, w2 = _RecordWin(visible=True), _RecordWin(visible=True)
    proxy = MultiWindowProxy(_ProxyShell(Config(base=tmp_path), [w1, w2]))
    value = proxy._physics_mode
    assert value is not False, "不得用 False 冒充「无物理模式」——G1 读的是 is not None"
    assert value is None, "无窗处于物理模式时哨兵必须是 None"


def test_proxy_physics_mode_reports_active_mode(tmp_path, app):
    """任一窗进入物理模式时，代理按哨兵语义报出该模式（任一窗生效）。"""
    w1, w2 = _RecordWin(visible=True), _RecordWin(visible=True)
    proxy = MultiWindowProxy(_ProxyShell(Config(base=tmp_path), [w1, w2]))
    assert proxy._physics_mode is None
    w2._physics_mode = "throw"
    assert proxy._physics_mode == "throw", "任一生效即视为全局处于物理模式（G1 拦话）"
    w2._physics_mode = None
    w1._physics_mode = "drag"
    assert proxy._physics_mode == "drag"
    w1._physics_mode = None
    assert proxy._physics_mode is None
