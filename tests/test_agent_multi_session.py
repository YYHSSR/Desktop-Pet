# -*- coding: utf-8 -*-
"""测试多会话/回合状态聚合（F08）与隐藏时持续采集（F09）。"""

from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QCoreApplication

from pet.config import Config
from pet.agent_link import AgentLinkManager, AgentEvent


def _ensure_app():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


class DummyWin:
    def __init__(self, visible: bool = True):
        self._visible = visible
        self.activities = []
        self.bubbles = []
        self.anims = []
        self.cats = {"acts": ["写代码", "吃Token", "轻快记录"]}

    def isVisible(self) -> bool:
        return self._visible

    def mark_activity(self) -> None:
        self.activities.append(True)

    def request_link_anim(self, anim: str) -> None:
        self.anims.append(anim)

    def request_link_idle(self) -> None:
        self.anims.append("idle")

    def show_bubble(self, text: str, duration_ms: int = 3000, important: bool = False) -> None:
        if not self.isVisible():
            return
        self.bubbles.append(text)


def test_f08_interleaved_multi_sessions(tmp_path: Path):
    """F08 验收：两个会话交错执行时，某个会话结束不应打断其他会话的运行状态，全部结束才进 idle。"""
    _ensure_app()
    win = DummyWin(visible=True)
    cfg = Config(base=tmp_path)
    cfg.set("agent_link", {"codex": True})
    mgr = AgentLinkManager(win, cfg, min_interval=0.0)
    mon = mgr.monitors["codex"]
    mon.start()
    gen = mon._emit_gen

    # 会话 1 开始干活
    mgr._on_agent_state_event(
        AgentEvent("codex", "state", gen=gen, state="working", session_id="sess-A", turn_id="turn-1")
    )
    assert mgr._last_raw["codex"] == "working"
    assert mgr._session_states[("codex", "sess-A")] == "working"
    assert len(win.anims) > 0

    # 会话 2 也开始干活
    mgr._on_agent_state_event(
        AgentEvent("codex", "state", gen=gen, state="working", session_id="sess-B", turn_id="turn-1")
    )
    assert mgr._last_raw["codex"] == "working"
    assert mgr._session_states[("codex", "sess-B")] == "working"

    # 会话 1 完成，但会话 2 仍在进行
    mgr._on_agent_state_event(
        AgentEvent("codex", "state", gen=gen, state="idle", session_id="sess-A", turn_id="turn-1")
    )
    # 宏观聚合状态必须依然是 working，不能被单会话完成误拉到 idle
    assert mgr._last_raw["codex"] == "working"
    assert mgr._session_states[("codex", "sess-A")] == "idle"
    assert mgr._session_states[("codex", "sess-B")] == "working"
    # 完成检查计时器不应该启动
    assert "codex" not in mgr._done_pending

    # 会话 2 也完成
    mgr._on_agent_state_event(
        AgentEvent("codex", "state", gen=gen, state="idle", session_id="sess-B", turn_id="turn-1")
    )
    # 此时全部会话均完成，宏观聚合状态转为 idle
    assert mgr._last_raw["codex"] == "idle"
    assert mgr._session_states[("codex", "sess-B")] == "idle"
    # 触发完成确认
    assert "codex" in mgr._done_pending

    mgr.shutdown()


def test_f08_stale_turn_done_protection(tmp_path: Path):
    """F08 验收：旧回合迟到的 done 事件不能结束新回合。"""
    _ensure_app()
    win = DummyWin(visible=True)
    cfg = Config(base=tmp_path)
    cfg.set("agent_link", {"codex": True})
    mgr = AgentLinkManager(win, cfg, min_interval=0.0)
    mon = mgr.monitors["codex"]
    mon.start()
    gen = mon._emit_gen

    # 会话进入新回合 Turn 2
    mgr._on_agent_state_event(
        AgentEvent("codex", "state", gen=gen, state="working", session_id="sess-A", turn_id="turn-2")
    )
    assert mgr._last_raw["codex"] == "working"
    assert mgr._session_turn_ids[("codex", "sess-A")] == "turn-2"

    # 网络或尾读延迟送达了旧回合 Turn 1 的迟到 idle 事件
    mgr._on_agent_state_event(
        AgentEvent("codex", "state", gen=gen, state="idle", session_id="sess-A", turn_id="turn-1")
    )

    # 迟到 idle 必须被丢弃，当前 Turn 2 状态保持 working！
    assert mgr._last_raw["codex"] == "working"
    assert mgr._session_states[("codex", "sess-A")] == "working"
    assert "codex" not in mgr._done_pending

    mgr.shutdown()


def test_f09_hidden_state_tracking(tmp_path: Path):
    """F09 验收：窗口隐藏时，状态仍持续被采集与追踪，但不触发可见动画与弹窗。"""
    _ensure_app()
    win = DummyWin(visible=False)  # 隐藏窗口
    cfg = Config(base=tmp_path)
    cfg.set("agent_link", {"codex": True})
    mgr = AgentLinkManager(win, cfg, min_interval=0.0)
    mon = mgr.monitors["codex"]
    mon.start()
    gen = mon._emit_gen

    mgr._on_agent_state_event(
        AgentEvent("codex", "state", gen=gen, state="working", session_id="sess-H", turn_id="turn-1")
    )

    # 状态簿记照常推进
    assert mgr._last_raw["codex"] == "working"
    assert mgr._session_states[("codex", "sess-H")] == "working"
    # 但隐藏状态下，没有弹出任何气泡，也没有切桌面动作
    assert len(win.anims) == 0
    assert len(win.bubbles) == 0

    mgr.shutdown()
