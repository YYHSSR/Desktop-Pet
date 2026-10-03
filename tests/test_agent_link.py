# -*- coding: utf-8 -*-
"""多 Agent 状态感知与动作联动单元测试。

测试覆盖：
- 默认全关；
- 有界 Byte-Offset Tailer：新增行增量读取、重复读取不重放、文件轮转/截断安全、backfill 防护；
- 事件 JSONL 解析与状态规范化映射；
- AgentLinkManager 生命周期与 pause / resume；
- 状态变更触发桌宠行为与气泡反馈；
- Example Agent 确认框逻辑（拒绝则不写入 hooks）；
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import pet.agent_link as agent_link
from pet.agent_link import (
    AgentLinkManager,
    AgentEvent,
    BaseAgentMonitor,
    ByteOffsetTailer,
    CursorMonitor,
    CustomAgentMonitor,
    normalize_event_state,
)
from pet.config import Config
from pet.config import _clean_agent_link_data, _clean_custom_agents
from pet.report_gates import REPORT_GATE_DEFAULTS
from pet.speech_bubble import SECTION_HEADER_LABEL, SECTION_HINT_LABEL


# 测试门基线：本文件验证「机制」，不隐式依赖产品默认值。
# 概率门全关（各类汇报需要用例显式开门才该弹），只保留「审批与提问」常开——它
# 是交互身份/关闭配对用例的前置条件，不属于本文件要验证的汇报抽稀行为。
# 专门校验产品默认值的用例是 TestAgentLinkManager::test_default_all_disabled，不套本基线。
_AGENT_GATE_BASELINE = {
    "state": 0.0,
    "activity": 0.0,
    "approval": 1.0,
    "done": 0.0,
    "exec_failed": 0.0,
    "model_access": 0.0,
    "stuck": 0.0,
    "bridge": 0.0,
}


def _agent_gates(**overrides) -> dict:
    """在门基线上按门名覆盖，返回**完整 8 门**字典。

    写全 8 门是刻意的：调用方普遍 `{**cfg.data["agent_link"], **patch}` 浅合并，
    部分字典会整块替换 report_gates，让未点名的门回落到产品默认（1.0 / activity 0.6），
    从而破坏基线的不确定性隔离。写全 8 门后每个用例只开自己那一类门。
    """
    gates = dict(_AGENT_GATE_BASELINE)
    gates.update(overrides)
    return gates


@pytest.fixture(autouse=True)
def _agent_gate_baseline(monkeypatch, request):
    """把 agent_link 的概率门复位为基线（产品默认值与门语义见 tests/test_report_gates.py）。"""
    if request.node.name == "test_default_all_disabled":
        yield
        return
    from pet import config as config_module

    real_defaults = config_module._default_agent_link_data
    monkeypatch.setattr(
        config_module,
        "_default_agent_link_data",
        lambda: {
            **real_defaults(),
            "report_gates": dict(_AGENT_GATE_BASELINE),
            "stuck_detect": False,
            "pattern_detect": False,
        },
    )
    yield


class TestMainlineAgentLinkHardening:
    def test_cost_worker_is_absent_for_legacy_enabled_config(self, tmp_path):
        QApplication.instance() or QApplication([])
        cfg = Config(base=tmp_path)
        cfg.set("agent_cost_enabled", True)
        manager = AgentLinkManager(None, cfg)
        try:
            assert not hasattr(manager, "_cost")
            assert not hasattr(manager, "_query_cost_balance")
        finally:
            manager.shutdown()

    def test_monitor_polling_uses_worker_and_stops(self, tmp_path):
        """监视器轮询不占 GUI 线程，stop 后 worker 必须退出。"""
        app = QApplication.instance() or QApplication([])
        seen = []
        ready = threading.Event()

        class ProbeMonitor(BaseAgentMonitor):
            _POLL_INTERVAL_S = 0.01

            def _poll(self, gen=None):
                seen.append(threading.get_ident())
                self._emit_state("working", self._emit_gen if gen is None else gen)
                ready.set()
                self._worker_stop.set()

        monitor = ProbeMonitor("probe", tmp_path)
        events = []
        monitor.state_event.connect(events.append)
        monitor.start()
        assert ready.wait(1.0)
        app.processEvents()
        assert seen and seen[0] != threading.get_ident()
        assert events and isinstance(events[0], AgentEvent)
        assert events[0].gen == monitor._gen
        monitor.stop()
        assert monitor._worker is not None and not monitor._worker.is_alive()

    def test_pause_buffers_events_until_resume(self, tmp_path):
        """隐藏期间落在 poll 中的状态事件在 resume 时补发。"""
        monitor = BaseAgentMonitor("probe", tmp_path)
        events = []
        monitor.state_event.connect(events.append)
        monitor.start()
        monitor.pause()
        monitor._emit_state("working", monitor._emit_gen)
        assert events == []
        monitor.resume()
        assert [event.state for event in events] == ["working"]
        monitor.stop()

    def test_stale_generation_is_rejected_at_manager(self, tmp_path):
        class Win:
            def isVisible(self):
                return True

            def mark_activity(self):
                pass

        mgr = AgentLinkManager(Win(), Config(base=tmp_path), min_interval=0.0)
        monitor = mgr.monitors["cursor"]
        monitor.start()
        old_gen = monitor._emit_gen
        monitor.stop()
        monitor.start()
        current_gen = monitor._emit_gen
        mgr._on_agent_state_event(AgentEvent("cursor", "state", gen=old_gen, state="working"))
        assert "cursor" not in mgr._last_raw
        mgr._on_agent_state_event(AgentEvent("cursor", "state", gen=current_gen, state="working"))
        assert mgr._last_raw["cursor"] == "working"
        mgr.shutdown()


    def test_state_and_activity_refresh_idle_activity_anchor(self, tmp_path):
        class Win:
            def __init__(self):
                self.activity_count = 0

            def isVisible(self):
                return True

            def mark_activity(self):
                self.activity_count += 1

        win = Win()
        mgr = AgentLinkManager(win, Config(base=tmp_path), min_interval=0.0)
        mgr._on_agent_state("codex", "working")
        mgr._on_agent_activity("codex", "read")
        assert win.activity_count == 2
        mgr.shutdown()


# ============================================================================
# 1. ByteOffsetTailer 核心增量读取测试
# ============================================================================
class TestByteOffsetTailer:
    def test_backfill_protection_on_startup(self, tmp_path):
        fpath = tmp_path / "test.jsonl"
        fpath.write_text('{"event": "old1"}\n{"event": "old2"}\n', encoding="utf-8")

        tailer = ByteOffsetTailer(fpath)
        # 首次调用 read_new_lines 应当做 backfill 防护，不读取启动前的历史行
        lines = tailer.read_new_lines()
        assert lines == []
        assert tailer.offset == fpath.stat().st_size

        # 写入新行
        with open(fpath, "a", encoding="utf-8") as f:
            f.write('{"event": "new1"}\n')

        new_lines = tailer.read_new_lines()
        assert len(new_lines) == 1
        assert json.loads(new_lines[0])["event"] == "new1"

    def test_no_duplicate_reads(self, tmp_path):
        fpath = tmp_path / "test.jsonl"
        fpath.touch()
        tailer = ByteOffsetTailer(fpath)
        tailer.read_new_lines()  # 初始化

        with open(fpath, "a", encoding="utf-8") as f:
            f.write('{"event": "ev1"}\n')

        lines1 = tailer.read_new_lines()
        assert len(lines1) == 1

        # 再次调用不应重复读取
        lines2 = tailer.read_new_lines()
        assert len(lines2) == 0

    def test_file_truncation_resets_safely(self, tmp_path):
        fpath = tmp_path / "test.jsonl"
        fpath.write_text('{"event": "a"}\n{"event": "b"}\n', encoding="utf-8")
        tailer = ByteOffsetTailer(fpath)
        tailer.offset = 100  # 假设之前读取了较大 offset

        # 文件被清空重写（size < offset）
        fpath.write_text('{"event": "fresh"}\n', encoding="utf-8")
        tailer._initial_backfill_done = True

        lines = tailer.read_new_lines()
        assert len(lines) == 1
        assert json.loads(lines[0])["event"] == "fresh"






class TestEventStateNormalization:
    def test_known_events_mapping(self):
        assert normalize_event_state("thinking") == "thinking"
        assert normalize_event_state("tool/call") == "working"
        assert normalize_event_state("tool/result") == "working"
        assert normalize_event_state("attention") == "attention"
        assert normalize_event_state("attention") == "attention"
        assert normalize_event_state("execution/failed") == "error"
        assert normalize_event_state("session/created") == "idle"

    def test_explicit_valid_state_override(self):
        assert normalize_event_state("CustomUnknownEvent", explicit_state="thinking") == "thinking"
        # 未知事件 + 非法显式状态：返回空串表示「忽略」，绝不默认当成 working 过度触发
        assert normalize_event_state("CustomUnknownEvent", explicit_state="invalid") == ""
        assert normalize_event_state("CustomUnknownEvent") == ""


# ============================================================================
# 3. AgentLinkManager 管理器与生命周期测试
# ============================================================================


# ============================================================================
# ============================================================================
class TestRealFileTailEndToEnd:
    def test_cursor_multi_file_tail(self, tmp_path):
        app = QApplication.instance() or QApplication([])

        # 模拟 Cursor transcripts 目录
        cursor_dir = tmp_path / ".cursor" / "projects" / "proj1" / "agent-transcripts"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        transcript_file = cursor_dir / "session1.jsonl"
        transcript_file.touch()

        cfg_dir = tmp_path / "dsh-config"
        cfg_dir.mkdir(parents=True, exist_ok=True)

        received_states = []
        mon = CursorMonitor(cfg_dir, base_dir=tmp_path / ".cursor" / "projects")
        mon.state_changed.connect(lambda k, s: received_states.append((k, s)))

        mon.start()
        mon._poll()  # 初始化 tailer

        # 模拟 Cursor 追加写入事件行
        with open(transcript_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "tool/call"}) + "\n")
            f.write(json.dumps({"type": "attention"}) + "\n")

        mon._poll()

        assert len(received_states) == 2
        assert received_states[0] == ("cursor", "working")
        assert received_states[1] == ("cursor", "attention")

        mon.stop()

    def test_agent_state_triggers_pet_action(self, tmp_path):
        app = QApplication.instance() or QApplication([])

        switched_anims = []
        bubbles = []

        class DummyPetWindow:
            def __init__(self):
                self.cats = {"acts": ["写代码", "原地敲击桌面互动", "吃Token", "轻快记录", "漂浮踏步"]}
                self.idles = ["待机呼吸"]

            def isVisible(self):
                return True

            def _switch(self, name):
                switched_anims.append(name)

            def request_link_anim(self, name):
                switched_anims.append(name)

            def request_link_idle(self):
                if self.idles:
                    switched_anims.append(self.idles[0])

            def show_bubble(self, text, duration_ms=3000):
                bubbles.append(text)

            def _pick(self, lst):
                return lst[0]

        cfg = Config(base=tmp_path)
        # 本用例验的是「状态 → 桌宠动作 + 完成提醒」的映射，所以显式开 done 门
        # （基线其它门全关；见文件头 _AGENT_GATE_BASELINE）。
        ag = dict(cfg.get("agent_link", {}))
        ag["report_gates"] = _agent_gates(done=1.0)
        cfg.set("agent_link", ag)
        win = DummyPetWindow()
        mgr = AgentLinkManager(win, cfg, min_interval=0.0)  # 测试关闭节流，逐个验证状态映射

        # 模拟 Agent 状态分发（busy 动作池轮换：写代码→吃Token）
        mgr._on_agent_state("cursor", "thinking")
        assert "写代码" in switched_anims

        mgr._on_agent_state("cursor", "working")
        assert "吃Token" in switched_anims

        mgr._on_agent_state("cursor", "attention")
        # 等待用户输入时立即提醒，但不能提前宣布完成。
        assert any("确认一下" in b for b in bubbles)
        assert "cursor" not in mgr._done_pending
        mgr._on_agent_state("cursor", "idle")
        assert "cursor" in mgr._done_pending
        mgr._fire_done("cursor")
        assert any("已停止" in b for b in bubbles)

        # 非 busy 后独立出现的 attention 仍立即提醒
        mgr._on_agent_state("codex", "attention")
        assert any("需要你确认" in b for b in bubbles)


# ============================================================================
# 5. 终审修复回归：hooks 格式 / 半行缓冲 / 去抖节流 / 菜单回弹
# ============================================================================


class TestByteOffsetTailerPartialLine:
    def test_partial_line_buffered_not_dropped(self, tmp_path):
        """半行（无换行结尾）必须缓冲等待拼接，绝不能当整行解析或丢弃。"""
        fpath = tmp_path / "t.jsonl"
        fpath.touch()
        tailer = ByteOffsetTailer(fpath)
        tailer.read_new_lines()  # 初始化

        # 写入半行
        with open(fpath, "a", encoding="utf-8") as f:
            f.write('{"event": "tool/')
        assert tailer.read_new_lines() == []  # 半行不产出

        # 补全该行
        with open(fpath, "a", encoding="utf-8") as f:
            f.write('call"}\n{"event": "attention"}\n')
        lines = tailer.read_new_lines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "tool/call"
        assert json.loads(lines[1])["event"] == "attention"

    def test_chunk_boundary_mid_line(self, tmp_path):
        """读取窗口恰好切在行中间时，半行拼接依然正确。"""
        fpath = tmp_path / "t.jsonl"
        fpath.touch()
        tailer = ByteOffsetTailer(fpath, max_chunk_bytes=16)
        tailer.read_new_lines()

        line1 = '{"event": "tool/call"}\n'  # 24 bytes，跨越 16B 边界
        with open(fpath, "a", encoding="utf-8") as f:
            f.write(line1)
        out = []
        for _ in range(3):
            out.extend(tailer.read_new_lines())
        assert out == [line1.strip()]


class TestAgentStateDebounce:
    def _make_mgr(self, tmp_path):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        switched = []

        class DummyWin:
            cats = {"acts": ["写代码", "原地敲击桌面互动", "吃Token", "轻快记录", "漂浮踏步"]}
            idles = ["待机呼吸"]

            def isVisible(self):
                return True

            def _switch(self, name):
                switched.append(name)

            def request_link_anim(self, name):
                switched.append(name)

            def request_link_idle(self):
                if self.idles:
                    switched.append(self.idles[0])

            def show_bubble(self, text, duration_ms=3000):
                pass

            def _pick(self, lst):
                return lst[0]

        cfg = Config(base=tmp_path)
        clock = [1000.0]
        mgr = AgentLinkManager(DummyWin(), cfg, min_interval=2.0, clock=lambda: clock[0])
        return mgr, switched, clock

    def test_same_state_deduped(self, tmp_path):
        mgr, switched, clock = self._make_mgr(tmp_path)
        mgr._on_agent_state("cursor", "working")
        mgr._on_agent_state("cursor", "working")
        mgr._on_agent_state("cursor", "working")
        assert switched == ["写代码"]  # 只切一次

    def test_throttled_within_interval(self, tmp_path):
        mgr, switched, clock = self._make_mgr(tmp_path)
        mgr._on_agent_state("cursor", "working")
        clock[0] += 1.0  # 1s < 2s 节流间隔
        mgr._on_agent_state("cursor", "thinking")
        assert switched == ["写代码"]  # 被节流
        clock[0] += 2.0  # 超过间隔
        mgr._on_agent_state("cursor", "thinking")
        assert switched == ["写代码", "吃Token"]  # 动作池轮换：写代码→吃Token


class TestAgentMenuRebound:
    def test_decline_rolls_back_checkbox(self, tmp_path, monkeypatch):
        """用户拒绝授权后，菜单勾选态必须回滚，不允许 UI 骗人。"""
        from PySide6.QtWidgets import QApplication
        from pet.window import PetWindow
        from pet.library import MovieLibrary

        app = QApplication.instance() or QApplication([])
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)

        cfg = Config(base=tmp_path)
        lib = MovieLibrary(character_id="shenshen")
        win = PetWindow(lib, cfg)
        try:
            class FakeAction:
                def __init__(self):
                    self.checked = True  # 用户刚勾上
                    self._blocked = []

                def blockSignals(self, b):
                    self._blocked.append(b)

                def setChecked(self, v):
                    self.checked = v

            act = FakeAction()
            win._toggle_agent_link("unknown-agent", True, act)
            assert act.checked is False  # 已退役的联动键必须回滚
            assert "unknown-agent" not in cfg.data["agent_link"]
        finally:
            # 窗口必须关闭：否则泄漏的真实窗口会在共享事件循环上继续推进动画链，
            # 后续测试 processEvents 时持续拉起 reader 线程（跨测试干扰）。
            win.close()
            win.deleteLater()
            # 处理 deleteLater 投递的 Qt 清理事件，避免窗口的动画/reader 事件泄漏到后续测试。
            app.processEvents()

    def test_bom_prefixed_file_tolerated(self, tmp_path):
        """PowerShell Add-Content -Encoding UTF8 会在新建文件首行写 BOM，
        tailer 必须容忍，否则带 BOM 的事件无法解析。"""
        fpath = tmp_path / "bom.jsonl"
        fpath.touch()
        tailer = ByteOffsetTailer(fpath)
        tailer.read_new_lines()  # 完成初始化（文件须先存在）
        # 外部以带 BOM 的方式重写文件（模拟轮转后首行带 BOM）
        fpath.write_bytes(b"\xef\xbb\xbf" + '{"event": "attention"}\n'.encode("utf-8"))
        tailer.offset = 0  # 模拟轮转重置
        lines = tailer.read_new_lines()
        assert len(lines) == 1
        assert json.loads(lines[0])["event"] == "attention"


# ============================================================================
# ============================================================================




class TestCooldownUnits:
    def test_seconds_and_minutes_conversion(self, tmp_path):
        """冷却间隔秒/分钟双单位：45 秒应存为 0.75 分钟。"""
        from PySide6.QtWidgets import QApplication
        from pet.modern_settings_dialog import ModernSettingsDialog

        app = QApplication.instance() or QApplication([])
        cfg = Config(base=tmp_path)
        dlg = ModernSettingsDialog(cfg)
        try:
            if not hasattr(dlg, "pro_cooldown_unit"):
                import pytest
                pytest.skip("非 Windows 无主动识屏设置组")

            # 切到秒，设 45 秒
            dlg.pro_cooldown_unit.setCurrentIndex(1)
            dlg.pro_cooldown_spin.setValue(45)
            assert abs(dlg._pro_cooldown_minutes() - 0.75) < 1e-9

            # 切回分钟应自动换算显示
            dlg.pro_cooldown_unit.setCurrentIndex(0)
            assert abs(dlg.pro_cooldown_spin.value() - 0.75) < 1e-9

            # 保存后配置为分钟值
            dlg._save()
            assert abs(cfg.data["proactive_screen"]["cooldown_minutes"] - 0.75) < 1e-9
        finally:
            dlg.close()
            dlg.deleteLater()






# ============================================================================
# 12. ChatGPT profile 枚举（桥接插件安装/卸载目标）
# ============================================================================


# ============================================================================
# 13. Agent 联动气泡测试（开始干活 / 完成通知 / 冷却 / 抖动 / 占用延后）
# ============================================================================








# ============================================================================
# 14. Agent 动作轮换、过程汇报与 window 平滑衔接测试
# ============================================================================
class TestAgentLinkChainingAndActivity:
    def _make_mgr(self, tmp_path, agent_link_cfg=None, acts=None):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        switched = []
        bubbles = []

        class DummyWin:
            cats = {"acts": ["写代码", "吃Token", "轻快记录", "漂浮踏步"] if acts is None else acts}
            idles = ["待机呼吸"]
            _bubble_busy_until = 0.0

            def isVisible(self):
                return True

            def _switch(self, name):
                switched.append(name)

            def show_bubble(self, text, duration_ms=3000):
                bubbles.append(text)

            def _pick(self, lst):
                return lst[0]

            def request_link_anim(self, name):
                switched.append(name)

            def request_link_idle(self):
                switched.append(self.idles[0])

        win = DummyWin()
        win.switched = switched
        cfg = Config(base=tmp_path)
        if agent_link_cfg is not None:
            data = cfg.data
            data["agent_link"] = {**data.get("agent_link", {}), **agent_link_cfg}
            cfg.save()

        clock = [1000.0]
        mgr = AgentLinkManager(win, cfg, min_interval=2.0, clock=lambda: clock[0])
        return mgr, win, bubbles, clock

    def test_anim_rotation_sequence(self, tmp_path):
        """1. 动作池轮换顺序：DummyWin 的 cats.acts 含 ['写代码','吃Token','轻快记录','漂浮踏步']，
        连续 6 次 busy（每次 clock 前进 3s 避免节流）→ 依次为 写代码/吃Token/轻快记录/写代码/吃Token/漂浮踏步（每第3次插播摸鱼）。"""
        mgr, win, bubbles, clock = self._make_mgr(
            tmp_path, acts=["写代码", "吃Token", "轻快记录", "漂浮踏步"]
        )
        res = [mgr._next_link_anim_rotation() for _ in range(6)]
        expected = ["写代码", "吃Token", "轻快记录", "吃Token", "写代码", "漂浮踏步"]
        assert res == expected

    def test_anim_rotation_falls_back_to_keywords_and_available_acts(self, tmp_path):
        """精确动作名不存在时，按主/摸鱼关键词选择；完全不匹配时回退到任意动作。"""
        mgr, win, bubbles, clock = self._make_mgr(
            tmp_path, acts=["敲击键盘", "伸懒腰", "发呆"]
        )
        res = [mgr._next_link_anim_rotation() for _ in range(6)]
        assert res == ["敲击键盘", "敲击键盘", "伸懒腰", "敲击键盘", "敲击键盘", "伸懒腰"]

        mgr, win, bubbles, clock = self._make_mgr(tmp_path, acts=["跳舞"])
        assert mgr._next_link_anim_rotation() == "跳舞"


    def test_empty_acts_returns_none(self, tmp_path):
        """2. 无可用动作时 _next_link_anim_rotation 返回 None（DummyWin cats.acts 为空列表）不抛异常。"""
        mgr, win, bubbles, clock = self._make_mgr(tmp_path, acts=[])
        assert mgr._next_link_anim_rotation() is None
        # 触发状态变更也不抛异常
        mgr._on_agent_state("codex", "working")
        assert win.switched == []

    def test_activity_reporting(self, tmp_path):
        """3. 过程汇报：report_gates.activity=1.0 时 mgr._on_agent_activity('dsh','bash') → 气泡含「正在跑命令」；
        10 秒内第二次任何工具不弹；同工具 60 秒内不重复（clock 前进 15s 再发 bash 仍不弹；换成 read 则弹「正在读文件」）；
        全局限流 8s（另一 agent 在 8s 内也不弹）。activity 门关闭时不弹（本文件基线默认 0.0，
        见文件头 _AGENT_GATE_BASELINE；产品默认值是 0.6 的过程汇报抽稀）。
        未知工具（如 'frobnicate'）弹安全兜底文案。"""
        # activity 门关着（基线 0.0）时不弹
        mgr_off, win_off, bubbles_off, clock_off = self._make_mgr(tmp_path)
        mgr_off._on_agent_activity("codex", "bash")
        assert bubbles_off == []

        # activity 门开到 1.0（确定性全放行，避免 0.6 抽稀导致断言不确定）
        mgr, win, bubbles, clock = self._make_mgr(
            tmp_path, agent_link_cfg={"report_gates": _agent_gates(activity=1.0)}
        )

        # 未知工具弹安全兜底文案，不泄露原始参数
        mgr._on_agent_activity("codex", "frobnicate")
        assert len(bubbles) == 1
        assert "正在调用工具" in bubbles[-1]
        assert "frobnicate" not in bubbles[-1]

        # dsh bash → 弹「正在跑命令」
        clock[0] += 10.0
        mgr._on_agent_activity("codex", "bash")
        assert len(bubbles) == 2
        assert "正在跑命令" in bubbles[-1]

        # 10 秒内第二次任何工具不弹
        clock[0] += 5.0
        mgr._on_agent_activity("codex", "read")
        assert len(bubbles) == 2

        # 全局限流 8s（另一 agent 在 8s 内也不弹，从 1000.0 起算此时 1005.0 < 1008.0）
        mgr._on_agent_activity("cursor", "read")
        assert len(bubbles) == 2

        # 同工具 60 秒内不重复：前进 15s（总共 +20s > 10s，但 < 60s），再发 bash 仍不弹
        clock[0] += 15.0
        mgr._on_agent_activity("codex", "bash")
        assert len(bubbles) == 2

        # 换成 read 则弹「正在读文件」
        mgr._on_agent_activity("codex", "read")
        assert len(bubbles) == 3
        assert "正在读文件" in bubbles[-1]

        clock[0] += 10.0
        mgr._on_agent_activity("codex", "pwsh")
        assert len(bubbles) == 4
        assert "pwsh" in bubbles[-1]  # activity.run 轮换到含工具名的变体
        clock[0] += 10.0
        mgr._on_agent_activity("codex", "memory_search")
        assert len(bubbles) == 5
        assert bubbles[-1].strip()  # activity.default 轮换文案，仅断言有气泡

    def test_activity_bubble_receives_tool_record_fields(self, tmp_path):
        """过程汇报气泡必须拿到上游 tool/call 记录的字段（显式注入，非隐式上下文）。

        监视器同轮转发的工具记录被按 agent 缓存，_on_agent_activity 把
        tool/label/command/argsKey/callId/step + 会话字段显式传给模板；
        条件字段缺失时占位符自动隐藏（不原样露出 {target} 等死占位符）。"""
        mgr, win, bubbles, clock = self._make_mgr(
            tmp_path, agent_link_cfg={"report_gates": _agent_gates(activity=1.0)}
        )
        # 模拟监视器 _poll 的同轮顺序：先 raw_record（工具记录），再 activity 信号
        # 字段以桥接真实写出的 tool/call 为准（tool/argsKey/command/callId/step）。
        mgr._remember_dialogue_record("codex", {
            "ts": 1, "event": "tool/call", "tool": "read", "command": "cat src/app.py",
            "argsKey": "a1b2", "callId": "call-1", "step": 2,
            "sessionId": "sess-1",
        })
        cfg = mgr.cfg
        cfg.data["dialogue_mode"] = "custom"
        cfg.data["dialogue_phrases"] = {
            "activity.read": ["正在读取（{tool}，第 {step} 步，命令 {command}）"],
            "activity.search": ["搜索（{tool}）argsKey={argsKey}"],
        }
        cfg.save()
        mgr._on_agent_activity("codex", "read")
        assert bubbles, "气泡未弹出"
        assert "第 2 步" in bubbles[-1]
        assert "cat src/app.py" in bubbles[-1]

        # 字段缺失的最小记录：条件占位符自动隐藏，不原样保留 {command}/{step}
        clock[0] += 15.0
        mgr._remember_dialogue_record("codex", {"ts": 2, "event": "tool/call", "tool": "grep"})
        mgr._on_agent_activity("codex", "grep")
        assert "argsKey=a1b2" not in bubbles[-1]
        assert "{command}" not in bubbles[-1]
        assert "{step}" not in bubbles[-1]
        assert "{argsKey}" not in bubbles[-1]

    def test_activity_bubble_text_is_truncated_at_source(self, tmp_path):
        """过程汇报文案源头截断：自定义模板塞进超长命令时截到 80 字 + 「…」。

        过程汇报只是一句状态提示，不进分页/滚动；审批/提问气泡走
        _show_interaction_bubble，不受该截断影响。
        """
        mgr, win, bubbles, clock = self._make_mgr(
            tmp_path, agent_link_cfg={"report_gates": _agent_gates(activity=1.0)}
        )
        # 先缓存 tool/call 记录（监视器 _poll 的同轮顺序），命令长到必定超上限
        mgr._remember_dialogue_record("codex", {
            "ts": 1, "event": "tool/call", "tool": "bash",
            "command": "x" * 200, "step": 3,
        })
        cfg = mgr.cfg
        cfg.data["dialogue_mode"] = "custom"
        cfg.data["dialogue_phrases"] = {"activity.run": ["正在跑命令（{command}）"]}
        cfg.save()

        mgr._on_agent_activity("codex", "bash")
        assert bubbles, "气泡未弹出"
        text = bubbles[-1]
        assert text.startswith("正在跑命令（")
        assert len(text) == AgentLinkManager._ACTIVITY_TEXT_LIMIT + 1
        assert text.endswith("…")

        # 上限内的文案原样展示（不追加省略号）
        clock[0] += 15.0
        mgr._remember_dialogue_record("codex", {
            "ts": 2, "event": "tool/call", "tool": "read", "command": "cat a.py",
        })
        cfg.data["dialogue_phrases"] = {"activity.read": ["正在读取 {command}"]}
        cfg.save()
        mgr._on_agent_activity("codex", "read")
        assert bubbles[-1] == "正在读取 cat a.py"

    def test_window_smooth_chaining(self, tmp_path):
        """4. window 侧平滑衔接（用真实 PetWindow + MovieLibrary，offscreen，参考 TestAgentMenuRebound 的构造）：
        win._switch('优雅女仆舞')（一次性动作）后 win.request_link_anim('写代码') →
        当前 anim 仍是 '优雅女仆舞' 且 _pending_link_anim=='写代码'（不打断）；
        手动调 win._on_anim_ended('优雅女仆舞') → anim 变为 '写代码'。
        再测：待机中（win.anim 在 win.idles 里）request_link_anim 立即切换。
        request_link_idle 在一次性动作播放中不切回待机（anim 不变、pending 清空）。"""
        from PySide6.QtWidgets import QApplication
        from pet.window import PetWindow
        from pet.library import MovieLibrary

        app = QApplication.instance() or QApplication([])
        cfg = Config(base=tmp_path)
        lib = MovieLibrary(character_id="shenshen")
        win = PetWindow(lib, cfg)

        try:
            # 确保 '优雅女仆舞' 是一次性动作 (acts)
            assert "优雅女仆舞" in win.acts
            win._switch("优雅女仆舞")
            assert win.anim == "优雅女仆舞"
            assert win._is_one_shot_playing() is True

            win.request_link_anim("写代码")
            assert win.anim == "优雅女仆舞"
            assert win._pending_link_anim == "写代码"

            # 手动调 _on_anim_ended('优雅女仆舞') → 播放待播的 '写代码'
            win._on_anim_ended("优雅女仆舞")
            assert win.anim == "写代码"
            assert win._pending_link_anim is None

            # 待机中（win.anim 在 win.idles 里）request_link_anim 立即切换
            idle_name = win.idles[0]
            win._switch(idle_name)
            assert win.anim in win.idles
            assert win._is_one_shot_playing() is False

            win.request_link_anim("吃Token")
            assert win.anim == "吃Token"

            # request_link_idle 在一次性动作播放中不切回待机（anim 不变、pending 清空）
            win._switch("优雅女仆舞")
            win._pending_link_anim = "写代码"
            win.request_link_idle()
            assert win.anim == "优雅女仆舞"
            assert win._pending_link_anim is None
        finally:
            win.close()
            win.deleteLater()

    def test_on_anim_ended_continuation(self, tmp_path):
        """5. _on_anim_ended 联动续播：构造 PetWindow 后，设置 win._link_anim_current='写代码'，
        win._link_next_provider=lambda: '吃Token'，调 win._on_anim_ended('写代码') → anim=='吃Token'；
        provider 返回 None 时走正常动画链（不抛异常即可）。"""
        from PySide6.QtWidgets import QApplication
        from pet.window import PetWindow
        from pet.library import MovieLibrary

        app = QApplication.instance() or QApplication([])
        cfg = Config(base=tmp_path)
        lib = MovieLibrary(character_id="shenshen")
        win = PetWindow(lib, cfg)

        try:
            win._link_anim_current = "写代码"
            win._link_next_provider = lambda: "吃Token"
            win._on_anim_ended("写代码")
            assert win.anim == "吃Token"
            assert win._link_anim_current == "吃Token"

            # provider 返回 None 时走正常动画链（不抛异常）
            win._link_next_provider = lambda: None
            win._on_anim_ended("吃Token")
            # 正常推进，不抛异常
            assert win._link_anim_current is None
        finally:
            win.close()
            win.deleteLater()



# ============================================================================
# 14. 过程汇报：事件 tool 字段 → activity 信号
# ============================================================================
class TestActivitySignal:
    def test_tool_field_emits_activity_without_state(self, tmp_path):
        """jsonl 事件带 tool 字段时发 activity 信号，且不产生状态变化。"""
        app = QApplication.instance() or QApplication([])
        cfg = Config(base=tmp_path)
        mon = BaseAgentMonitor("codex", cfg.dir)
        got, states = [], []
        mon.activity.connect(lambda a, t: got.append((a, t)))
        mon.state_changed.connect(lambda a, s: states.append(s))
        mon.events_dir.mkdir(parents=True, exist_ok=True)
        mon.events_file.touch()  # 先建空文件，backfill 才能落到末尾
        mon._tailer.read_new_lines()  # backfill 初始化
        with mon.events_file.open("a", encoding="utf-8") as fh:
            fh.write('{"ts":1,"agent":"codex","event":"tool/call","tool":"bash"}\n')
        mon._poll()
        assert got == [("codex", "bash")]
        assert states == ["working"]

    def test_no_tool_no_activity(self, tmp_path):
        """普通状态事件不发 activity。"""
        app = QApplication.instance() or QApplication([])
        cfg = Config(base=tmp_path)
        mon = BaseAgentMonitor("codex", cfg.dir)
        got = []
        mon.activity.connect(lambda a, t: got.append(t))
        mon.events_dir.mkdir(parents=True, exist_ok=True)
        mon.events_file.touch()
        mon._tailer.read_new_lines()
        with mon.events_file.open("a", encoding="utf-8") as fh:
            fh.write('{"ts":1,"agent":"codex","event":"AgentStatus","state":"working"}\n')
        mon._poll()
        assert got == []

    class _HiddenWin:
        cats = {"acts": ["写代码"]}
        idles = ["待机呼吸"]
        _bubble_busy_until = 0.0
        switched = None
        bubbles = None

        def __init__(self):
            self.switched = []
            self.bubbles = []

        def isVisible(self):
            return False

        def _switch(self, name):
            self.switched.append(name)

        def show_bubble(self, text, duration_ms=3000):
            self.bubbles.append(text)

        def _pick(self, lst):
            return lst[0]

    def test_fire_done_hidden_window_is_noop(self, tmp_path):
        """opus 评审 H1：隐藏窗口上 _fire_done 不得切动画/弹气泡。"""
        app = QApplication.instance() or QApplication([])
        win = TestActivitySignal._HiddenWin()
        cfg = Config(base=tmp_path)
        mgr = AgentLinkManager(win, cfg)
        mgr._last_raw["codex"] = "idle"
        mgr._fire_done("codex")
        assert win.switched == []
        assert win.bubbles == []

    def test_pause_cancels_done_pending(self, tmp_path):
        """opus 评审 H1：pause 必须取消所有完成确认计时器。"""
        app = QApplication.instance() or QApplication([])
        cfg = Config(base=tmp_path)
        bubbles = []

        class Win:
            cats = {"acts": ["写代码"]}
            idles = ["待机呼吸"]
            _bubble_busy_until = 0.0

            def isVisible(self):
                return True

            def _switch(self, name):
                pass

            def request_link_idle(self):
                pass

            def show_bubble(self, text, duration_ms=3000):
                bubbles.append(text)

            def _pick(self, lst):
                return lst[0]

        mgr = AgentLinkManager(Win(), cfg)
        mgr._on_agent_state("codex", "working")
        mgr._on_agent_state("codex", "idle")
        assert "codex" in mgr._done_pending
        mgr.pause()
        assert mgr._done_pending == {}

# ============================================================================
# 15. 旧集成 子代理会话过滤（防「干完活啦」刷屏）
# ============================================================================


# ============================================================================
# 自定义联动 Agent（agent_link.custom_agents 配置驱动）
# ============================================================================
class TestCustomAgentConfigCleaning:
    def test_valid_entry_kept_and_normalized(self):
        cleaned = _clean_custom_agents([
            {"key": "Gemini", "name": "  Gemini CLI  ", "path": " ~/.gemini/ev.jsonl "},
        ])
        assert cleaned == [{"key": "gemini", "name": "Gemini CLI", "path": "~/.gemini/ev.jsonl"}]

    def test_name_defaults_to_key(self):
        cleaned = _clean_custom_agents([{"key": "myagent", "path": "~/x.jsonl"}])
        assert cleaned == [{"key": "myagent", "name": "myagent", "path": "~/x.jsonl"}]

    def test_invalid_entries_dropped(self):
        cleaned = _clean_custom_agents([
            "not-a-dict",                                # 非对象
            {"key": "Bad Key", "path": "~/x.jsonl"},     # key 含空格/大写
            {"key": "cursor", "path": "~/x.jsonl"},      # 与内置键冲突
            {"key": "ok", "path": ""},                   # 空 path
            {"key": "ok2"},                              # 缺 path
        ])
        assert cleaned == []

    def test_duplicate_keys_deduped(self):
        cleaned = _clean_custom_agents([
            {"key": "gemini", "path": "~/a.jsonl"},
            {"key": "gemini", "path": "~/b.jsonl"},
        ])
        assert len(cleaned) == 1
        assert cleaned[0]["path"] == "~/a.jsonl"

    def test_max_entries_truncated(self):
        raw = [{"key": f"agent{i}", "path": f"~/{i}.jsonl"} for i in range(20)]
        assert len(_clean_custom_agents(raw)) == 8

    def test_non_list_returns_empty(self):
        assert _clean_custom_agents(None) == []
        assert _clean_custom_agents({"key": "gemini"}) == []

    def test_clean_agent_link_data_cleans_and_keeps_custom_key_booleans(self):
        cleaned = _clean_agent_link_data({
            "custom_agents": [{"key": "gemini", "name": "Gemini CLI", "path": "~/ev.jsonl"}],
            "gemini": True,        # 自定义键的开关布尔（set_enabled 写入路径）
            "notify_done": False,  # 旧布尔开关：一次性迁移进 done 门，且不再写回旧键
        })
        assert cleaned["custom_agents"] == [{"key": "gemini", "name": "Gemini CLI", "path": "~/ev.jsonl"}]
        assert cleaned["gemini"] is True
        # 旧开关被弹出（配置形状里不留兼容别名），语义落到概率门上：False → done=0.0；
        # 其余门取产品默认（activity 抽稀到 0.6），不受旧键迁移影响。
        assert "notify_done" not in cleaned
        assert cleaned["report_gates"] == {**REPORT_GATE_DEFAULTS, "done": 0.0}


class TestCustomAgentMonitor:
    def test_tail_events_and_signals(self, tmp_path):
        """统一协议三种形态（state / event+tool / state 收尾）→ 信号正确。"""
        app = QApplication.instance() or QApplication([])
        events = tmp_path / "sub" / "gemini.jsonl"
        events.parent.mkdir(parents=True)
        events.touch()

        states, tools = [], []
        mon = CustomAgentMonitor("gemini", tmp_path / "cfg", str(events))
        mon.state_changed.connect(lambda k, s: states.append((k, s)))
        mon.activity.connect(lambda k, t: tools.append((k, t)))
        mon.start()
        mon._poll()  # backfill 初始化

        with open(events, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": 1.0, "state": "working"}) + "\n")
            f.write(json.dumps({"ts": 2.0, "event": "tool/call", "tool": "bash"}) + "\n")
            f.write(json.dumps({"ts": 3.0, "state": "idle"}) + "\n")

        mon._poll()
        # PreToolUse 事件按内置映射同时产生 working 状态 + bash 工具过程
        assert states == [("gemini", "working"), ("gemini", "working"), ("gemini", "idle")]
        assert tools == [("gemini", "bash")]
        mon.stop()

    def test_missing_file_idle_then_appears(self, tmp_path):
        """文件不存在时空转；出现后 backfill 防护跳过历史，只读新增行。"""
        app = QApplication.instance() or QApplication([])
        missing = tmp_path / "not_yet.jsonl"
        mon = CustomAgentMonitor("gemini", tmp_path / "cfg", str(missing))
        states = []
        mon.state_changed.connect(lambda k, s: states.append((k, s)))
        mon.start()
        mon._poll()
        mon._poll()
        assert states == []

        missing.write_text('{"state": "working"}\n', encoding="utf-8")
        mon._poll()  # 首次发现文件：backfill，不回放历史
        assert states == []

        with open(missing, "a", encoding="utf-8") as f:
            f.write('{"state": "idle"}\n')
        mon._poll()
        assert states == [("gemini", "idle")]
        mon.stop()

    def test_start_does_not_create_dirs(self, tmp_path):
        """只读监听：绝不替用户在任意路径创建目录。"""
        app = QApplication.instance() or QApplication([])
        mon = CustomAgentMonitor(
            "gemini", tmp_path / "cfg", str(tmp_path / "deep" / "nested" / "ev.jsonl"),
        )
        mon.start()
        mon._poll()
        assert not (tmp_path / "deep").exists()
        mon.stop()

    def test_tilde_path_expanded(self, tmp_path, monkeypatch):
        # expanduser 在 Windows 读 USERPROFILE、POSIX 读 HOME，两个都设以保证跨平台
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        mon = CustomAgentMonitor("gemini", tmp_path / "cfg", "~/events.jsonl")
        assert mon.events_file == tmp_path / "events.jsonl"
        assert "~" not in str(mon.events_file)


class TestCustomAgentManager:
    def test_registered_names_merged_and_generic_toggle(self, tmp_path):
        """custom_agents → 监视器注册 + 显示名合并 + 通用开关联动（无需授权弹窗）。"""
        app = QApplication.instance() or QApplication([])
        cfg = Config(base=tmp_path)
        ag = dict(cfg.get("agent_link", {}))
        ag["custom_agents"] = [
            {"key": "gemini", "name": "Gemini CLI", "path": str(tmp_path / "gemini.jsonl")},
        ]
        cfg.set("agent_link", ag)
        cfg.save()

        mgr = AgentLinkManager(None, cfg)
        assert "gemini" in mgr.monitors
        assert isinstance(mgr.monitors["gemini"], CustomAgentMonitor)
        assert mgr.agent_names["gemini"] == "Gemini CLI"
        # 类级 AGENT_NAMES 保持仅内置：设置页按内置枚举的遍历不受自定义影响
        assert "gemini" not in AgentLinkManager.AGENT_NAMES
        assert mgr.agent_names["cursor"] == "Cursor"

        # 通用开关：开启持久化并启动监视器
        assert mgr.set_enabled("gemini", True) is True
        assert cfg.data["agent_link"]["gemini"] is True
        assert mgr.monitors["gemini"].is_running() is True

        # 隐藏暂停 / 显示恢复
        mgr.pause()
        assert mgr.monitors["gemini"].is_running() is False
        mgr.resume()
        assert mgr.monitors["gemini"].is_running() is True

        # 关闭
        assert mgr.set_enabled("gemini", False) is True
        assert cfg.data["agent_link"]["gemini"] is False
        assert mgr.monitors["gemini"].is_running() is False

    def test_builtin_key_in_custom_agents_ignored(self, tmp_path):
        """config 清洗会拒绝与内置键冲突的自定义条目，管理器不覆盖内置监视器。"""
        app = QApplication.instance() or QApplication([])
        cfg = Config(base=tmp_path)
        ag = dict(cfg.get("agent_link", {}))
        ag["custom_agents"] = [{"key": "cursor", "name": "Fake", "path": str(tmp_path / "x.jsonl")}]
        cfg.set("agent_link", ag)
        cfg.save()

        mgr = AgentLinkManager(None, cfg)
        assert not isinstance(mgr.monitors["cursor"], CustomAgentMonitor)
        assert mgr.agent_names["cursor"] == "Cursor"


class TestCustomAgentMenu:
    def test_menu_lists_custom_agent_and_toggle_routes(self, tmp_path):
        """右键菜单动态渲染自定义 Agent（收进「自定义联动 Agent」三级子菜单），勾选走通用 _toggle_agent_link。"""
        from PySide6.QtWidgets import QMenu
        from pet.context_menus.shared import add_agent_link_menu

        app = QApplication.instance() or QApplication([])
        cfg = Config(base=tmp_path)
        ag = dict(cfg.get("agent_link", {}))
        ag["custom_agents"] = [
            {"key": "gemini", "name": "Gemini CLI", "path": "~/gemini.jsonl"},
        ]
        cfg.set("agent_link", ag)
        cfg.save()

        toggles, options = [], []

        class DummyPet:
            def __init__(self):
                self.cfg = cfg

            def toggle_agent_link(self, key, on, action=None):
                toggles.append((key, on))

            def set_agent_link_option(self, key, on):
                options.append((key, on))

            _toggle_agent_link = toggle_agent_link
            _set_agent_link_option = set_agent_link_option

        menu = QMenu()
        try:
            add_agent_link_menu(menu, DummyPet())
            sub = menu.actions()[0].menu()
            texts = [a.text() for a in sub.actions()]
            # 内置 Cursor 项在顶层，只列当前内置来源，自定义项收进三级子菜单「自定义联动 Agent」
            assert "Cursor" in texts
            assert "Gemini CLI" not in texts
            custom_sub = next(a.menu() for a in sub.actions() if a.text() == "自定义联动 Agent")
            custom_texts = [a.text() for a in custom_sub.actions()]
            assert "Gemini CLI" in custom_texts
            # Agent 联动子菜单不再带「台词风格」「循环检测/卡住检测」入口——
            # 检测类配置已收敛到设置页（自动化与联动），仅保留联动相关设置
            assert "台词风格" not in texts

            gemini_act = next(a for a in custom_sub.actions() if a.text() == "Gemini CLI")
            gemini_act.setChecked(True)
            assert toggles == [("gemini", True)]
        finally:
            import shiboken6
            shiboken6.delete(menu)


# ============================================================================
# 阻塞型交互气泡生命周期（审批 / 用户问题统一处理，一直挂到 resolved）
# ============================================================================
class TestApprovalStickyBubble:
    """阻塞型交互气泡永久挂着：approval/request、question/requested → sticky；
    decided / resolved / idle / offline → 消失。

    覆盖：sticky 展示、resolved 收尾、并发交互互不覆盖、idle 兜底、全量清除、
    _saw_alert 补记（完成后不误说"干完活啦"）、question 选项排版。
    """

    def _make_mgr(self, tmp_path):
        class FakeWin:
            def __init__(self):
                self._sticky_bubble_active = False
                self.sticky_shown: list[tuple[str, bool]] = []
                self.hidden_calls = 0
                self._alert_current = None
                self._alert_queue = []

            def show_bubble(self, text, duration_ms=3200, sticky=False, buttons=None):
                self._sticky_bubble_active = bool(sticky)
                self.sticky_shown.append((str(text), bool(sticky)))
                if buttons:
                    self.shown_buttons.append((str(text), [item for pair in buttons for item in (pair if pair[0] in (SECTION_HEADER_LABEL, SECTION_HINT_LABEL) else (pair[0],))]))

            def show_alert(self, text, *, subtitle="", duration_ms=0, buttons=None, sticky=True, alert_id=""):
                self._alert_queue.append({"id": alert_id, "text": str(text), "sticky": sticky})
                if self._alert_current is None and self._alert_queue:
                    self._alert_current = self._alert_queue.pop(0)
                    self._sticky_bubble_active = self._alert_current.get("sticky", True)
                self.sticky_shown.append((str(text), sticky))
                if buttons:
                    self.shown_buttons.append((str(text), [item for pair in buttons for item in (pair if pair[0] in (SECTION_HEADER_LABEL, SECTION_HINT_LABEL) else (pair[0],))]))

            def resolve_alert(self, alert_id):
                if self._alert_current and self._alert_current.get("id") == alert_id:
                    self._alert_current = None
                    self.hidden_calls += 1
                    self._sticky_bubble_active = False
                    if self._alert_queue:
                        self._alert_current = self._alert_queue.pop(0)
                        self._sticky_bubble_active = self._alert_current.get("sticky", True)
                else:
                    self._alert_queue = [q for q in self._alert_queue if q.get("id") != alert_id]

            def hide_bubble(self):
                self.hidden_calls += 1
                self._sticky_bubble_active = False
                self._alert_current = None

        cfg = Config(base=tmp_path)
        mgr = AgentLinkManager(FakeWin(), cfg)
        mgr.win.shown_buttons = []
        return mgr

    def _single_pending(self, mgr, agent_key: str) -> dict:
        """取该 agent 唯一一条 pending 交互（多条时断言失败，供单交互测试用）。"""
        items = mgr.pending_interactions_for(agent_key)
        assert len(items) == 1, f"期望 {agent_key} 只有一条 pending，实际 {len(items)} 条"
        return next(iter(items.values()))

    def _single_iid(self, mgr, agent_key: str) -> str:
        items = mgr.pending_interactions_for(agent_key)
        assert len(items) == 1
        return next(iter(items))

    def _agent_keys(self, mgr) -> set:
        return {item.get("agent_key") for item in mgr._pending_interactions.values()}

    def test_approval_request_shows_sticky(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "bash", "approvalId": "ap-hint", "sessionId": "s-1"})
        assert self._agent_keys(mgr) == {"codex"}
        pending = self._single_pending(mgr, "codex")
        assert pending["kind"] == "approval"
        assert pending["interactive"] is False
        assert mgr.win._sticky_bubble_active is True
        text, sticky = mgr.win.sticky_shown[-1]
        assert sticky is True
        # legacy 内置预设 approval.tool 首句：请求使用工具名（原 fallback 含「审批」字样）
        assert "请求使用工具" in text and "bash" in text
        assert mgr.win.shown_buttons == [], "无 rpcId 时不得出按钮（纯提示）"

    def test_approval_request_shows_full_command(self, tmp_path):
        """审批气泡必须展示被审批命令的完整内容（来自 bridge 的 command 字段）。"""
        mgr = self._make_mgr(tmp_path)
        cmd = "pip install pytest --index-url http://mirrors.aliyun.com/pypi/simple/"
        mgr._on_approval_request("codex", {"tool": "bash", "command": cmd, "approvalId": "ap-cmd", "sessionId": "s-1"})
        text, _sticky = mgr.win.sticky_shown[-1]
        assert cmd in text, "气泡文案必须包含命令完整内容"
        assert self._single_pending(mgr, "codex")["command"] == cmd

    def test_approval_request_formats_command_single_line(self, tmp_path):
        """多行/多空格命令折叠成单行展示（气泡图片不保留换行）。"""
        mgr = self._make_mgr(tmp_path)
        raw = "pip install pytest\n\n  --index-url http://example.com/simple/\n"
        mgr._on_approval_request("codex", {"tool": "bash", "command": raw, "approvalId": "ap-raw", "sessionId": "s-1"})
        text, _sticky = mgr.win.sticky_shown[-1]
        assert "\n" not in text, "换行必须折叠成空格"
        assert "pip install pytest --index-url http://example.com/simple/" in text

    def test_approval_request_truncates_overlong_command(self, tmp_path):
        """超长命令截断并加省略号，避免撑爆气泡。"""
        mgr = self._make_mgr(tmp_path)
        long_cmd = "x" * 500
        mgr._on_approval_request("codex", {"tool": "bash", "command": long_cmd, "approvalId": "ap-long", "sessionId": "s-1"})
        text, _sticky = mgr.win.sticky_shown[-1]
        assert "…" in text
        assert "x" * 500 not in text

    def test_approval_request_command_missing_falls_back_to_tool(self, tmp_path):
        """无 command 字段时回退到工具名文案（兼容旧桥接路径）。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "write", "approvalId": "ap-w", "sessionId": "s-1"})
        text, _sticky = mgr.win.sticky_shown[-1]
        assert "请求执行" not in text
        assert "请求使用工具" in text

    def test_approval_resolved_dismisses(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "bash", "approvalId": "ap-r", "sessionId": "s-1"})
        mgr._on_approval_resolved("codex", {"approvalId": "ap-r"})
        assert mgr._pending_interactions == {}
        assert mgr.win.hidden_calls == 1
        assert mgr.win._sticky_bubble_active is False

    def test_concurrent_approvals_resolved_last(self, tmp_path):
        """两个 agent 并发审批：各自 pending；队列模型下逐条关闭并推进下一条。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "bash", "approvalId": "ap-d", "sessionId": "s-1"})
        mgr._on_approval_request("cursor", {"tool": "write", "approvalId": "ap-c", "sessionId": "s-2"})
        assert self._agent_keys(mgr) == {"codex", "cursor"}
        mgr._on_approval_resolved("codex", {"approvalId": "ap-d"})
        assert self._agent_keys(mgr) == {"cursor"}
        assert mgr.win._sticky_bubble_active is True, "dsh 审批关闭后 example-agent 审批顶上，气泡仍挂着"
        mgr._on_approval_resolved("cursor", {"approvalId": "ap-c"})
        assert mgr._pending_interactions == {}
        assert mgr.win.hidden_calls == 2
        assert mgr.win._sticky_bubble_active is False

    def test_idle_dismisses_approval(self, tmp_path):
        """agent 回待机但没收到 decided：交互必然失效，兜底清掉（含窗口隐藏时）。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "bash", "approvalId": "ap-i", "sessionId": "s-1"})
        mgr._on_agent_state("codex", "idle")
        assert mgr._pending_interactions == {}
        assert mgr.win.hidden_calls == 1

    def test_dismiss_all_approvals(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "bash", "approvalId": "ap-all", "sessionId": "s-1"})
        mgr.dismiss_all_approvals()
        assert mgr._pending_interactions == {}
        assert mgr.win.hidden_calls == 1
        assert mgr.win._sticky_bubble_active is False

    def test_approval_records_saw_alert(self, tmp_path):
        """审批打断算"需要主人看一眼"：完成后不误说"干完活啦"。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "bash", "approvalId": "ap-saw", "sessionId": "s-1"})
        assert "codex" in mgr._saw_alert

    def test_resolved_unknown_agent_noop(self, tmp_path):
        """没有对应 pending 的 resolved 事件是空操作，不误关气泡。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_resolved("codex")
        assert mgr._pending_interactions == {}
        assert mgr.win.hidden_calls == 0

    def test_approval_resolved_call_id_does_not_close_question(self, tmp_path):
        """审批 resolved 帧带 callId 时不得按 callId 关闭问题交互。

        `_on_approval_resolved` 的 callId 分支是从问题侧复制粘贴来的错位判定：
        approval 与 question 的 callId 是两个独立命名空间，若该分支按
        kind == "question" 遍历，一条无关审批的收尾帧就会把同名 callId 的
        问题气泡误关掉（用户还没回答，问题弹窗先消失）。
        """
        mgr = self._make_mgr(tmp_path)
        mgr._on_question_request(
            "codex", {"questions": self.QUESTIONS, "callId": "call-shared"}
        )

        mgr._on_approval_resolved("codex", {"callId": "call-shared"})

        pending = mgr.pending_interactions_for("codex")
        assert len(pending) == 1, "审批 resolved 不得误关同名 callId 的问题气泡"
        assert next(iter(pending.values()))["kind"] == "question"
        assert mgr.win.hidden_calls == 0

    def test_approval_resolved_call_id_closes_approval(self, tmp_path):
        """审批 resolved 帧带 callId 时按 callId 关闭审批交互。

        登记端必须存下审批的 callId 身份，否则改判 kind 后新分支也无从匹配。
        """
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request(
            "codex", {"tool": "bash", "callId": "call-ap", "sessionId": "s-1"}
        )
        assert mgr.pending_interactions_for("codex") != {}

        mgr._on_approval_resolved("codex", {"callId": "call-ap"})

        assert mgr.pending_interactions_for("codex") == {}
        assert mgr.win.hidden_calls == 1

    # ---- 用户问题（ask_user_question）与审批同待遇 ----
    QUESTIONS = [
        {"id": "q1", "question": "要执行哪个方案？",
         "options": [{"label": "方案 A"}, {"label": "方案 B"}, {"label": "方案 C"}],
         "multiSelect": False},
    ]

    def test_question_request_shows_sticky_with_options(self, tmp_path):
        """question/requested 带 options：常驻气泡列出选项，让用户选一个才能继续。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_question_request("codex", {"questions": self.QUESTIONS, "callId": "call-q1"})
        pending = mgr.pending_interactions_for("codex")
        assert pending, "应有至少一条 pending 交互"
        item = next(iter(pending.values()))
        assert item["kind"] == "question"
        assert item["interactive"] is False
        assert mgr.win._sticky_bubble_active is True
        text, sticky = mgr.win.sticky_shown[-1]
        assert sticky is True
        assert "要执行哪个方案" in text
        assert "方案 A" in text and "方案 B" in text and "方案 C" in text
        assert "请选择一个" in text
        assert mgr.win.shown_buttons == [], "无 rpcId 时不得出按钮（纯提示）"

    def test_question_resolved_dismisses(self, tmp_path):
        """question/resolved → 气泡收尾。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_question_request("codex", {"questions": self.QUESTIONS, "callId": "call-qr"})
        mgr._on_question_resolved("codex", {"callId": "call-qr"})
        assert mgr._pending_interactions == {}
        assert mgr.win.hidden_calls == 1
        assert mgr.win._sticky_bubble_active is False

    def test_question_resolved_matches_call_id_with_multiple_pending(self, tmp_path):
        """并发问题必须按 callId 关闭，不能因无 rpcId 而让整个提醒队列卡住。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_question_request("codex", {
            "questions": self.QUESTIONS, "callId": "call-a", "sessionId": "session-a",
        })
        mgr._on_question_request("codex", {
            "questions": self.QUESTIONS, "callId": "call-b", "sessionId": "session-a",
        })

        assert len(mgr.pending_interactions_for("codex")) == 2
        mgr._on_question_resolved("codex", {"callId": "call-b", "sessionId": "session-a"})

        assert len(mgr.pending_interactions_for("codex")) == 1
        remaining = next(iter(mgr.pending_interactions_for("codex").values()))
        assert remaining["call_id"] == "call-a"

    def test_pending_interaction_uses_interaction_id_not_agent_key(self, tmp_path):
        """pending_interactions 的键是 interaction_id 而非 agent_key。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_question_request("codex", {"questions": self.QUESTIONS, "rpcId": "rpc-x"})
        keys = list(mgr._pending_interactions.keys())
        assert keys, "应有至少一条 pending 交互"
        assert "codex" not in keys, "键应为 interaction_id，不是 agent_key"
        assert "rpc-x" in keys[0], f"键应包含 rpcId（如 approval:rpc-x），实际为 {keys[0]}"
        pending = mgr.pending_interactions_for("codex")
        assert len(pending) == 1
        item = next(iter(pending.values()))
        assert item["agent_key"] == "codex"
        assert item["kind"] == "question"

    def test_concurrent_pending_resolved_independently(self, tmp_path):
        """同一个 Agent 有两个 pending interaction → 解决其中一个，另一个仍然存在。

        并发两个审批后分别解决一个，验证未解决的审批不会因另一个解决而关闭。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request(
            "codex", {"tool": "bash", "rpcId": "rpc-a", "approvalId": "ap-a", "sessionId": "s-1"}
        )
        mgr._on_approval_request(
            "codex", {"tool": "pwsh", "rpcId": "rpc-b", "approvalId": "ap-b", "sessionId": "s-1"}
        )
        pending_before = mgr.pending_interactions_for("codex")
        assert len(pending_before) == 2, f"应有 2 条 pending 交互，实际 {len(pending_before)}"
        pending_keys = set(pending_before)
        assert "approval:rpc-a" in pending_keys and "approval:rpc-b" in pending_keys

        # 解决 A
        mgr._on_approval_resolved("codex", {"rpcId": "rpc-a"})
        remaining = mgr.pending_interactions_for("codex")
        assert len(remaining) == 1, "解决 A 后应只剩 B"
        assert "approval:rpc-b" in remaining, "B 仍应处于 pending 状态"
        item_b = remaining["approval:rpc-b"]
        assert item_b["tool"] == "pwsh"
        assert item_b["approval_id"] == "ap-b"

        # 解决 B 后全部清空
        mgr._on_approval_resolved("codex", {"rpcId": "rpc-b"})
        assert mgr.pending_interactions_for("codex") == {}, "解决 B 后应全部清空"

    def test_question_no_options_needs_input(self, tmp_path):
        """无 options 的问题（自由输入/确认）：提示需要输入，不出交互按钮。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_question_request(
            "codex", {"questions": [{"id": "q2", "question": "请补充上下文"}], "rpcId": "rpc-free"}
        )
        text, sticky = mgr.win.sticky_shown[-1]
        assert sticky is True
        assert "请补充上下文" in text
        assert "正在询问" in text
        # 无选项=自由输入：即使 preset 文案被覆盖，结构引导也必须保留
        assert "请到 ChatGPT 界面输入文本回答" in text
        assert mgr.win.shown_buttons == [], "自由输入问题不出可点按钮"

    def test_question_multi_question(self, tmp_path):
        """一次多个问题：提示有几个问题等你回答。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_question_request(
            "codex", {"questions": [{"id": "a", "question": "Q1"}, {"id": "b", "question": "Q2"}], "callId": "call-multi"}
        )
        text, sticky = mgr.win.sticky_shown[-1]
        assert sticky is True
        assert "2 个问题" in text

    def test_question_and_approval_independent(self, tmp_path):
        """并发一个审批 + 一个问题：各自独立 pending，不再互相覆盖；分别 resolved 后全部关闭。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "bash", "approvalId": "ap-ind", "sessionId": "s-1"})
        mgr._on_question_request("codex", {"questions": self.QUESTIONS, "callId": "call-ind"})
        # 同一 agent 的多个交互各自独立存储（不再互相覆盖）
        assert self._agent_keys(mgr) == {"codex"}
        pending = mgr.pending_interactions_for("codex")
        assert len(pending) == 2, "审批和问题应共存，各自一条 pending"
        # 审批和问题各自有 kind
        kinds = {item["kind"] for item in pending.values()}
        assert kinds == {"approval", "question"}
        # 分别 resolved：先关闭问题
        mgr._on_question_resolved("codex", {"callId": "call-ind"})
        assert len(mgr.pending_interactions_for("codex")) == 1, "问题关闭后审批还在"
        assert self._single_pending(mgr, "codex")["kind"] == "approval"
        # 再关闭审批
        mgr._on_approval_resolved("codex", {"approvalId": "ap-ind"})
        assert mgr.pending_interactions_for("codex") == {}

    # ---- 交互模式（带 rpcId，气泡内可直接点选） ----






    def test_question_no_options_needs_input_mentions_desktop(self, tmp_path):
        """单个自由文本问题：纯提示气泡，文案明确引导回 ChatGPT 界面输入文本。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_question_request(
            "codex", {"questions": [{"id": "q2", "question": "请补充上下文"}], "rpcId": "rpc-free2"}
        )
        text, sticky = mgr.win.sticky_shown[-1]
        assert sticky is True
        assert "请补充上下文" in text
        assert "正在询问" in text
        assert "请到 ChatGPT 界面输入文本回答" in text
        assert mgr.win.shown_buttons == []









    def test_question_payload_keeps_custom_and_intent_per_question(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        questions = [{"id": "q1", "question": "评审", "intent": {"kind": "plan-review"}}, {"id": "q2", "question": "补充", "options": []}]
        mgr._on_question_request("codex", {"questions": questions, "rpcId": "rpc-custom", "sessionId": "s-custom"})
        item = next(iter(mgr.pending_interactions_for("codex").values()))
        assert item["questions"] == questions
        assert item["questions"] == questions

    def test_question_resolved_matches_session_and_question_rpc_id(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        for session, rpc in (("s1", "r1"), ("s2", "r2")):
            mgr._on_question_request("codex", {"questions": self.QUESTIONS, "rpcId": rpc, "sessionId": session})
        mgr._on_question_resolved("codex", {"rpcId": "r1", "sessionId": "s1"})
        assert set(mgr.pending_interactions_for("codex")) == {"question:r2"}



# ============================================================================
# 阻塞交互身份门禁（防普通工具调用 / 审计事件误触发审批弹窗）
# ============================================================================
class TestInteractionIdentityGate:
    """Get-Location 等普通工具调用、无身份的审计事件绝不能被升级成审批弹窗。

    覆盖：
    - approval 无任何可关联身份（rpcId/approvalId/requestId/callId）→ 不弹窗；
    - 仅带 approvalId（无 rpcId）的真实兼容路径 → 纯提示且可被身份 resolved 关闭；
    - monitor 层：裸 approval/asked 无论带不带身份都不触发审批信号；
    - monitor 层：普通 tool/call（pwsh Get-Location）只发 activity，绝不触发审批；
    - question 无 rpcId 也无 callId → 不弹窗；带 callId 的兜底路径仍可提示并关闭；
    - cordis 仅严格布尔 requiresApproval=True 且带 requestId 才触发；
    - turn 结束兜底清理：漏发 resolved 时不留永久弹窗，且只清对应会话。
    """

    def _make_mgr(self, tmp_path):
        class FakeWin:
            def __init__(self):
                self._sticky_bubble_active = False
                self.hidden_calls = 0
                self._alert_current = None
                self._alert_queue = []
                self.shown_buttons = []
                self.sticky_shown = []

            def show_bubble(self, text, duration_ms=3200, sticky=False, buttons=None):
                self._sticky_bubble_active = bool(sticky)
                self.sticky_shown.append((str(text), bool(sticky)))
                if buttons:
                    self.shown_buttons.append((str(text), [item for pair in buttons for item in (pair if pair[0] in (SECTION_HEADER_LABEL, SECTION_HINT_LABEL) else (pair[0],))]))

            def show_alert(self, text, *, subtitle="", duration_ms=0, buttons=None, sticky=True, alert_id=""):
                self._alert_queue.append({"id": alert_id, "text": str(text), "sticky": sticky})
                if self._alert_current is None and self._alert_queue:
                    self._alert_current = self._alert_queue.pop(0)
                    self._sticky_bubble_active = self._alert_current.get("sticky", True)
                self.sticky_shown.append((str(text), sticky))
                if buttons:
                    self.shown_buttons.append((str(text), [item for pair in buttons for item in (pair if pair[0] in (SECTION_HEADER_LABEL, SECTION_HINT_LABEL) else (pair[0],))]))

            def resolve_alert(self, alert_id):
                if self._alert_current and self._alert_current.get("id") == alert_id:
                    self._alert_current = None
                    self.hidden_calls += 1
                    self._sticky_bubble_active = False
                    if self._alert_queue:
                        self._alert_current = self._alert_queue.pop(0)
                        self._sticky_bubble_active = self._alert_current.get("sticky", True)
                else:
                    self._alert_queue = [q for q in self._alert_queue if q.get("id") != alert_id]

            def hide_bubble(self):
                self.hidden_calls += 1
                self._sticky_bubble_active = False
                self._alert_current = None

        cfg = Config(base=tmp_path)
        mgr = AgentLinkManager(FakeWin(), cfg)
        mgr.win.shown_buttons = []
        return mgr

    def _make_mon(self, tmp_path):
        app = QApplication.instance() or QApplication([])
        cfg = Config(base=tmp_path)
        mon = BaseAgentMonitor("codex", cfg.dir)
        mon.events_dir.mkdir(parents=True, exist_ok=True)
        mon.events_file.touch()
        mon._tailer.read_new_lines()  # backfill 初始化
        return mon

    def _write_events(self, mon, events):
        with mon.events_file.open("a", encoding="utf-8") as fh:
            for line in events:
                fh.write(json.dumps(line) + "\n")
        mon._poll()

    @pytest.mark.parametrize("command", [
        "Get-Location", "Get-ChildItem", "pwd", "ls", "git status",
        "Get-Location | Select-Object -ExpandProperty Path",
    ])
    def test_approval_without_identity_ignored(self, tmp_path, command):
        """无任何可关联身份的审批记录（普通工具调用被误标 approval/asked 后的残留）不弹窗。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "pwsh", "command": command})
        assert mgr.pending_interactions_for("codex") == {}
        assert mgr.win.sticky_shown == []
        assert mgr.win._sticky_bubble_active is False

    def test_approval_with_only_approval_id_is_hint_and_closable(self, tmp_path):
        """仅带 approvalId（无 rpcId）的真实兼容路径：显示纯提示，且可被身份 resolved 精确关闭。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "bash", "approvalId": "ap-x", "sessionId": "s-1"})
        pending = mgr.pending_interactions_for("codex")
        item = next(iter(pending.values()))
        assert item["kind"] == "approval"
        assert item["interactive"] is False
        assert item["approval_id"] == "ap-x"
        assert mgr.win.shown_buttons == [], "无 rpcId 时不得出按钮（纯提示）"
        mgr._on_approval_resolved("codex", {"approvalId": "ap-x"})
        assert mgr.pending_interactions_for("codex") == {}

    def test_approval_asked_never_emits_request_signal(self, tmp_path):
        """monitor 层：裸 approval/asked 无论带不带身份，都绝不触发审批弹窗信号。"""
        mon = self._make_mon(tmp_path)
        got = []
        mon.approval_requested.connect(lambda a, p: got.append((a, p.get("event"))))
        self._write_events(mon, [
            {"ts": 1, "agent": "codex", "event": "approval/asked", "tool": "pwsh", "command": "Get-Location"},
            {"ts": 2, "agent": "codex", "event": "approval/asked", "approvalId": "ap-a", "sessionId": "s-1"},
            {"ts": 3, "agent": "codex", "event": "approval/asked", "rpcId": "rpc-a", "sessionId": "s-1"},
        ])
        assert got == [], "approval/asked 不应驱动审批弹窗信号"

    def test_approval_requested_still_emits_request_signal(self, tmp_path):
        """monitor 层：权威 approval/request 与兼容旧名 approval/requested 正常触发审批信号。"""
        mon = self._make_mon(tmp_path)
        got = []
        mon.approval_requested.connect(lambda a, p: got.append((a, p.get("event"))))
        self._write_events(mon, [
            {"ts": 1, "agent": "codex", "event": "approval/request", "rpcId": "r1", "sessionId": "s1"},
            {"ts": 2, "agent": "codex", "event": "approval/requested", "rpcId": "r2", "sessionId": "s1"},
        ])
        assert got == [("codex", "approval/request"), ("codex", "approval/requested")]

    def test_tool_call_never_becomes_approval(self, tmp_path):
        """monitor 层：普通 tool/call（pwsh Get-Location）只发 activity，绝不发审批信号。"""
        mon = self._make_mon(tmp_path)
        approvals, activities = [], []
        mon.approval_requested.connect(lambda a, p: approvals.append((a, p)))
        mon.activity.connect(lambda a, t: activities.append((a, t)))
        self._write_events(mon, [
            {"ts": 1, "agent": "codex", "event": "tool/call", "tool": "pwsh", "command": "Get-Location"},
        ])
        assert approvals == [], "普通工具调用不得触发审批"
        assert ("codex", "pwsh") in activities

    def test_question_without_identity_ignored(self, tmp_path):
        """question/requested 无 rpcId 也无 callId：不弹窗（无法可靠关闭）。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_question_request("codex", {
            "questions": [{"id": "q1", "question": "选择？", "options": [{"label": "A"}]}],
        })
        assert mgr.pending_interactions_for("codex") == {}
        assert mgr.win.sticky_shown == []

    def test_question_with_call_id_is_hint_and_closable(self, tmp_path):
        """question/requested 带 callId（tool/call 兜底路径）：显示纯提示且可被关闭。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_question_request("codex", {
            "questions": [{"id": "q1", "question": "选择？", "options": [{"label": "A"}]}],
            "callId": "call-q", "sessionId": "s-1",
        })
        pending = mgr.pending_interactions_for("codex")
        item = next(iter(pending.values()))
        assert item["kind"] == "question"
        assert item["interactive"] is False
        assert mgr.win.shown_buttons == []
        mgr._on_question_resolved("codex", {"callId": "call-q", "sessionId": "s-1"})
        assert mgr.pending_interactions_for("codex") == {}






    def test_turn_end_clears_stale_pending(self, tmp_path):
        """turn 结束兜底清理：DSH 漏发 resolved 时，会话结束不再留永久弹窗。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "bash", "rpcId": "rpc-z", "approvalId": "ap-z", "sessionId": "s-1"})
        assert mgr.pending_interactions_for("codex")
        mgr._on_interaction_lifecycle("codex", {"event": "turn/end", "sessionId": "s-1"})
        assert mgr.pending_interactions_for("codex") == {}

    def test_turn_end_keeps_other_session_interaction(self, tmp_path):
        """turn 结束只清对应会话的交互，不影响其他会话并发的真实审批。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "bash", "rpcId": "rpc-a", "approvalId": "ap-a", "sessionId": "s-1"})
        mgr._on_approval_request("codex", {"tool": "pwsh", "rpcId": "rpc-b", "approvalId": "ap-b", "sessionId": "s-2"})
        mgr._on_interaction_lifecycle("codex", {"event": "turn/end", "sessionId": "s-1"})
        remaining = mgr.pending_interactions_for("codex")
        assert set(remaining) == {"approval:rpc-b"}

    def test_agent_idle_clears_pending_via_lifecycle(self, tmp_path):
        """AgentStatus idle 兜底清理：同现有 _on_agent_state idle 语义。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_approval_request("codex", {"tool": "bash", "rpcId": "rpc-idle", "approvalId": "ap-idle", "sessionId": "s-1"})
        mgr._on_interaction_lifecycle("codex", {"event": "AgentStatus", "state": "idle"})
        assert mgr.pending_interactions_for("codex") == {}


# ============================================================================
# 硬失败（execution/failed）：DSH 已决定本轮不再继续，直接提醒
# ============================================================================
class TestExecutionFailed:
    """execution/failed 不经行为分析直接提醒：失败动画 + 气泡。"""

    def _make_mgr(self, tmp_path, exec_failed=True):
        class FakeWin:
            def __init__(self):
                self.shown: list[str] = []
                self.alerts: list[dict] = []
                self.anims: list[str] = []
                self._visible = True

            def isVisible(self):
                return self._visible

            def show_bubble(self, text, duration_ms=3200, sticky=False, buttons=None):
                self.shown.append(str(text))

            def show_alert(self, text, *, subtitle="", duration_ms=0, buttons=None, sticky=True):
                self.alerts.append({
                    "text": str(text), "sticky": bool(sticky),
                    "duration_ms": int(duration_ms),
                })

            def request_link_anim(self, anim):
                self.anims.append(str(anim))

        cfg = Config(base=tmp_path)
        ag = dict(cfg.get("agent_link", {}))
        # 本类只看「硬失败直接提醒」这一条链路：exec_failed 门按参数开/关，
        # 其余门留在文件头基线（写全 8 门，避免整块替换后回落到产品默认）。
        ag["report_gates"] = _agent_gates(exec_failed=1.0 if exec_failed else 0.0)
        cfg.set("agent_link", ag)
        mgr = AgentLinkManager(FakeWin(), cfg)
        return mgr

    def test_retry_exhausted_shows_reminder(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_execution_failed("codex", {"failureType": "model_retry_exhausted", "retryExhausted": True, "retries": 4})
        assert mgr.win.alerts, "应入队失败提醒"
        assert "重试" in mgr.win.alerts[-1]["text"]  # failure.retry 预设（多次重试后仍未成功）
        assert mgr.win.alerts[-1]["sticky"] is False, "失败提醒是限时气泡（非 sticky）"

    def test_tool_failure_shows_reminder(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_execution_failed("codex", {"failureType": "tool_failed", "retryExhausted": False})
        assert mgr.win.alerts
        assert "工具执行失败" in mgr.win.alerts[-1]["text"]  # failure.tool 预设首句

    def test_generic_failure(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_execution_failed("codex", {})
        assert mgr.win.alerts
        assert "执行失败" in mgr.win.alerts[-1]["text"]  # failure.generic 预设首句

    def test_picks_fail_anim(self, tmp_path):
        """角色动作池含「失败/冒烟」类动作时选择它。"""
        mgr = self._make_mgr(tmp_path)
        mgr.win.cats = {"acts": ["待机", "失败冒烟", "写代码"]}
        anim = mgr._pick_fail_anim()
        assert anim == "失败冒烟"

    def test_exec_failed_gate_closed_no_reminder(self, tmp_path):
        """report_gates.exec_failed=0.0 时不提醒。"""
        mgr = self._make_mgr(tmp_path, exec_failed=False)
        mgr._on_execution_failed("codex", {"failureType": "model_retry_exhausted", "retryExhausted": True})
        assert mgr.win.shown == []





class TestModelAccessAlert:
    """model_access 事件 → 高优先级提醒，合并计数，按 session 隔离，可关闭。"""

    def _make_mgr(self, tmp_path):
        class FakeWin:
            def __init__(self):
                self.alerts: list[dict] = []
                self.resolved: list[str] = []
                self.shown: list[str] = []
                self._visible = True
                # 有意不提供 _bubble_busy_until：_schedule_model_access_dismiss 会据 sentinel 跳过 QTimer

            def isVisible(self):
                return self._visible

            def show_alert(self, text, *, subtitle="", duration_ms=0, buttons=None,
                           sticky=True, alert_id="", priority=3, alert_type="watchdog",
                           metadata=None):
                self.alerts.append({
                    "text": str(text), "sticky": bool(sticky),
                    "duration_ms": int(duration_ms), "alert_id": str(alert_id),
                    "priority": int(priority), "alert_type": str(alert_type),
                })

            def resolve_alert(self, alert_id):
                self.resolved.append(str(alert_id))

            def show_bubble(self, text, duration_ms=3200, sticky=False, buttons=None):
                self.shown.append(str(text))

        cfg = Config(base=tmp_path)
        # model_access 门开 1.0（本类主链路）；exec_failed 也开 1.0——有两个用例
        # 用模型访问提醒去抑制/不抑制通用失败横幅，exec_failed 关着就测不到抑制分支。
        ag = dict(cfg.get("agent_link", {}))
        ag["report_gates"] = _agent_gates(model_access=1.0, exec_failed=1.0)
        cfg.set("agent_link", ag)
        mgr = AgentLinkManager(FakeWin(), cfg)
        return mgr

    def test_first_model_access_shows_reminder(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_model_access("codex", {"sessionId": "sess-1"})
        assert mgr.win.alerts, "应弹出模型访问失败提醒"
        alert = mgr.win.alerts[-1]
        assert alert["alert_id"] == "model-access:sess-1", "alert_id 必须带 sessionId 隔离"
        # 可见文案走 legacy model_access.one 预设（模型访问失败语义）；服务端限流码由 alert_id/alert_type 承载
        assert "模型访问失败" in alert["text"]
        assert alert["priority"] == mgr._MODEL_ACCESS_PRIORITY and alert["priority"] == 1

    def test_consecutive_model_access_merged_same_session(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_model_access("codex", {"sessionId": "sess-2"})
        mgr._on_model_access("codex", {"sessionId": "sess-2"})  # 8s 冷却窗口内 → 合并
        assert mgr._model_access_cache["sess-2"]["count"] == 2
        # 合并后的可见文案走 legacy model_access.many 预设首句：
        # 「当前会话 … 的模型访问已连续失败 {count} 次，请稍后再试。」
        merged = mgr.win.alerts[-1]["text"]
        assert "模型访问" in merged and "连续失败" in merged, merged
        assert "2 次" in merged, merged
        assert mgr.win.alerts[-2]["alert_id"] == mgr.win.alerts[-1]["alert_id"], "同 session 复用同一 alert_id"

    def test_multi_session_isolated(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_model_access("codex", {"sessionId": "sess-A"})
        mgr._on_model_access("codex", {"sessionId": "sess-B"})
        ids = [a["alert_id"] for a in mgr.win.alerts]
        assert ids == ["model-access:sess-A", "model-access:sess-B"], "不同 session 不得互相顶替"
        assert set(mgr._model_access_cache) == {"sess-A", "sess-B"}

    def test_dismiss_clears_cache_and_alert(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_model_access("codex", {"sessionId": "sess-3"})
        mgr._dismiss_model_access_alert("sess-3")
        assert "sess-3" not in mgr._model_access_cache, "关闭后清理缓存"
        assert "model-access:sess-3" in mgr.win.resolved, "关闭对应 alert"

    def test_execution_failed_suppressed_while_model_access_active(self, tmp_path):
        """存在活跃模型访问失败提醒时，仅真正的模型访问失败（errorCode 属限流类码）不再弹通用横幅；
        模型重试耗尽（retryExhausted）是另一条语义，照常提醒。"""
        mgr = self._make_mgr(tmp_path)
        # 先触发模型访问失败提醒，冷却窗口内再出现真·模型访问失败（errorCode=RATE_LIMIT）→ 抑制
        mgr._on_model_access("codex", {"sessionId": "sess-4"})
        before = len(mgr.win.alerts)
        mgr._on_execution_failed("codex", {"sessionId": "sess-4", "failureType": "model_retry_exhausted",
                                         "retryExhausted": True, "errorCode": "RATE_LIMIT"})
        assert len(mgr.win.alerts) == before, "活跃模型访问失败提醒 + 真模型访问失败 → 抑制通用失败横幅"

    def test_retry_exhausted_not_suppressed_as_model_access(self, tmp_path):
        """模型重试耗尽失败（无限流类 errorCode）不是模型访问失败：提醒活跃也不抑制，照常弹 failure.retry。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_model_access("codex", {"sessionId": "sess-5"})
        before = len(mgr.win.alerts)
        mgr._on_execution_failed("codex", {"sessionId": "sess-5", "failureType": "model_retry_exhausted",
                                         "retryExhausted": True})
        assert len(mgr.win.alerts) == before + 1, "重试耗尽失败不应被当作模型访问失败抑制"
        assert "重试" in mgr.win.alerts[-1]["text"]  # failure.retry 文案

    def test_execution_failed_suppressed_beyond_cooldown_while_429_alive(self, tmp_path):
        """F2 回归：模型访问失败提醒展示 15s > 合并冷却 8s，turn/end 的 execution/failed 常
        在 8~15s 窗口到达——只要提醒仍未 dismiss，通用失败横幅必须继续抑制
        （旧实现按 8s cooldown 判断会绕过抑制造成双弹）。dismiss 后新失败正常提醒。"""
        mgr = self._make_mgr(tmp_path)
        now = [1000.0]
        mgr._clock = lambda: now[0]
        mgr._on_model_access("codex", {"sessionId": "sess-f2",
                                     "errorCode": "RATE_LIMIT", "consecutiveRetryCount": 1})
        assert len(mgr.win.alerts) == 1
        now[0] += 10.0  # 超出 8s cooldown，仍在 15s 展示寿命内
        mgr._on_execution_failed("codex", {"sessionId": "sess-f2", "failureType": "model_retry_exhausted",
                                         "retryExhausted": True, "retries": 5,
                                         "errorCode": "RATE_LIMIT"})
        assert len(mgr.win.alerts) == 1, "模型访问失败提醒存活期间不得二次弹通用失败横幅"
        # 收起提醒后：新的（非限流）失败应正常提醒
        mgr._dismiss_model_access_alert("sess-f2")
        mgr._on_execution_failed("codex", {"sessionId": "sess-f2", "failureType": "tool_failed",
                                         "retryExhausted": False, "retries": 0,
                                         "errorCode": ""})
        assert len(mgr.win.alerts) == 2, "提醒已收起后工具失败应正常提醒"


class TestModelAccessStreakCleanup:
    """F13：清理模型访问提醒时必须同步清空 tracker 内部 streak。

    只清外部镜像（``_model_access_cache`` / ``_model_access_retry_counts``）会
    让 tracker 里按 (source, session) 留存的连续计数残留；重新开启联动后同一
    会话的新一轮失败直接接着旧计数，提醒里出现「已连续 N 次」虚高。
    """

    class _Win:
        def __init__(self):
            self.alerts = []
            self.resolved = []

        def isVisible(self):
            return True

        def show_alert(self, text, **_kwargs):
            self.alerts.append(str(text))

        def resolve_alert(self, alert_id):
            self.resolved.append(str(alert_id))

        def show_bubble(self, *_args, **_kwargs):
            pass

    def _make_mgr(self, tmp_path):
        return AgentLinkManager(self._Win(), Config(base=tmp_path))

    @staticmethod
    def _retry():
        from pet.agent_event_normalizer import normalize_event
        return normalize_event({"event": "llm/retry", "agent": "codex", "sessionId": "s-1",
                                "errorCode": "RATE_LIMIT", "errorMessage": "429 too many requests"})

    def _feed_and_next_streak(self, mgr):
        """喂一条限流重试，返回 tracker 记账后的连续计数（经 consume 观察）。"""
        out = mgr._model_access_tracker.consume(self._retry())
        assert out is not None, "限流重试必须产出 streak"
        return int(out["consecutiveRetryCount"])

    def test_clear_resets_tracker_streak(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_normalized_event(self._retry())
        mgr._on_normalized_event(self._retry())
        assert self._feed_and_next_streak(mgr) == 3, "前置：tracker 已累计到 3"
        mgr._clear_model_access_alerts()
        assert self._feed_and_next_streak(mgr) == 1, "清理后 tracker streak 必须清零"

    def test_disable_and_reenable_does_not_inherit_old_streak(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr._on_normalized_event(self._retry())
        mgr._on_normalized_event(self._retry())
        # 关闭 ChatGPT 联动：apply_config 走 _clear_model_access_alerts
        cfg = dict(mgr.cfg.get("agent_link", {}))
        cfg["codex"] = False
        mgr.cfg.set("agent_link", cfg)
        mgr.apply_config()
        # 重新开启后再来一次失败：计数必须从 1 开始（不继承旧 streak）
        mgr._on_normalized_event(self._retry())
        assert self._feed_and_next_streak(mgr) == 2, \
            "重启用后不得继承旧 streak，否则提醒计数虚高"

    def test_normalized_event_signal_reaches_consumer(self, tmp_path):
        """守卫：normalized_event 信号必须直连 _on_normalized_event。

        移除 AgentEventRuntime 分发层后这是该信号的唯一消费接线；其余用例
        全部直调 handler，connect 丢失时它们照样全绿——信号级守卫不可省。
        """
        mgr = self._make_mgr(tmp_path)
        mgr.monitors["codex"].normalized_event.emit(self._retry())
        assert self._feed_and_next_streak(mgr) == 2, "经信号发射的重试事件必须被消费记账"


class TestSessionNameTruthfulness:
    """{sessionName} 只注入真实会话显示名，绝不把 sessionId 截短占位冒充（字段真实性）。

    会话元数据（session/meta）未到达时，get_session_display_name() 会回退成
    "ChatGPT · <id8>" 兜底占位——它不是「会话显示名」，不得注入台词模板（渲染端
    对缺失的条件字段会自动隐藏 {sessionName} 占位符）。
    """

    class _Win:
        cats = {"acts": ["写代码"]}
        idles = ["待机呼吸"]

        def isVisible(self):
            return True

        def show_bubble(self, *_args, **_kwargs):
            pass

    class _AlertWin:
        def __init__(self):
            self.alerts = []
            self.resolved = []
            # 有意不带 _bubble_busy_until：_schedule_model_access_dismiss 据此跳过 QTimer

        def isVisible(self):
            return True

        def show_alert(self, text, **_kwargs):
            self.alerts.append(str(text))

        def resolve_alert(self, alert_id):
            self.resolved.append(str(alert_id))

        def show_bubble(self, *_args, **_kwargs):
            pass

    def _make(self, tmp_path, win=None):
        cfg = Config(base=tmp_path)
        # 本类取证 model_access 提醒的字段真实性：门开 1.0，避免门关着时
        # 用「什么都没弹」冒充「字段没被注入」。
        ag = dict(cfg.get("agent_link", {}))
        ag["report_gates"] = _agent_gates(model_access=1.0)
        cfg.set("agent_link", ag)
        return AgentLinkManager(win or self._Win(), cfg)

    def test_id_fallback_is_not_injected_as_session_name(self, tmp_path):
        mgr = self._make(tmp_path)
        sid = "session-0123456789"
        assert mgr.get_session_display_name(sid) == f"ChatGPT · {sid[:8]}"
        cond = mgr._session_conditional({"sessionId": sid})
        assert "sessionName" not in cond, "无元数据时不得把 id 截短占位注入为会话名"
        assert not any("session-" in str(v) for v in cond.values())

    def test_real_session_name_from_meta_is_injected(self, tmp_path):
        mgr = self._make(tmp_path)
        sid = "session-0123456789"
        mgr._on_session_meta("codex", {"sessionId": sid, "projectName": "深海项目", "sessionName": "排障对话"})
        cond = mgr._session_conditional({"sessionId": sid})
        # sessionName 只取会话名自身，绝不拼 projectName（两字段语义独立）
        assert cond["sessionName"] == "排障对话"
        assert cond["projectName"] == "深海项目", "projectName 是独立字段"
        assert mgr._session_name_or_empty(sid) == "排障对话"
        # 组合展示串仍只属于展示 API（气泡前缀/探索气泡），不冒充会话名字段
        assert mgr.get_session_display_name(sid) == "深海项目 · 排障对话"

    def test_model_access_alert_does_not_inject_session_name_without_meta(self, tmp_path):
        mgr = self._make(tmp_path, win=self._AlertWin())
        captured = {}
        mgr._dialogue = lambda key, fallback, **kw: (captured.update(kw), fallback)[1]
        mgr._show_model_access_alert("session-abcdef12", 1)
        assert "sessionName" not in captured, "模型访问失败提醒无会话元数据时不得注入 sessionName"



class TestDetectorAlertThrottle:
    """N2 跨检测器弹窗节流：stuck/pattern/watchdog 同 agent 30s 内只弹一次窗
    （动画照常），升级档位放行，不同 scope 互不影响。"""

    def _make_mgr(self, tmp_path, **gate_overrides):
        class FakeWin:
            def __init__(self):
                self.alerts = []
                self.anims = []
                self._visible = True
                self._bubble_suppressed = False

            def isVisible(self):
                return self._visible

            def request_link_anim(self, anim):
                self.anims.append(str(anim))

            def show_alert(self, text, *, duration_ms=0, sticky=True, **kw):
                # 与 window_alerts.show_alert 一致：设置窗打开期间普通提醒被丢弃。
                if self._bubble_suppressed:
                    return
                self.alerts.append({"text": str(text), "sticky": bool(sticky)})

            def show_bubble(self, text, duration_ms=3000):
                self.alerts.append({"text": str(text), "bubble": True})

        cfg = Config(base=tmp_path)
        # 本类取证 N2 跨检测器节流：stuck/pattern/watchdog 三条检测类概率门开 1.0，
        # 避免文件头 autouse 基线（全 0.0）把「没弹窗」冒充「被节流」。
        gates = {"stuck": 1.0, "pattern": 1.0, "watchdog": 1.0}
        gates.update(gate_overrides)
        ag = dict(cfg.get("agent_link", {}))
        ag["report_gates"] = _agent_gates(**gates)
        cfg.set("agent_link", ag)
        mgr = AgentLinkManager(FakeWin(), cfg)
        mgr._clock = lambda: mgr._throttle_now[0]
        mgr._throttle_now = [1000.0]
        return mgr

    def test_watchdog_suppressed_after_stuck_within_window(self, tmp_path):
        """stuck(severity2) 弹窗后 30s 内 watchdog warning 到达 → 弹窗被抑制。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_stuck_intervention("codex", {"severity": 2})
        assert len(mgr.win.alerts) == 1
        mgr._throttle_now[0] += 10.0
        mgr._on_exploration_warning("sess-1", {"agent_key": "codex", "reasons": ["search"], "steps": []})
        assert len(mgr.win.alerts) == 1, "30s 窗口内 watchdog 弹窗应被抑制"

    def test_watchdog_allowed_after_cooldown_expired(self, tmp_path):
        """超过 30s 后同 agent 再触发 watchdog → 正常弹窗。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_stuck_intervention("codex", {"severity": 2})
        assert len(mgr.win.alerts) == 1
        mgr._throttle_now[0] += 31.0
        mgr._on_exploration_warning("sess-2", {"agent_key": "codex", "reasons": ["search"], "steps": []})
        assert len(mgr.win.alerts) == 2, "冷却结束后 watchdog 应正常弹窗"

    def test_escalation_pattern_control_overrides_previous(self, tmp_path):
        """watchdog 弹窗后 pattern control（升级/控制级）到达 → 放行（覆盖低档）。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_exploration_warning("sess-3", {"agent_key": "codex", "reasons": ["search"], "steps": []})
        assert len(mgr.win.alerts) == 1
        mgr._throttle_now[0] += 5.0
        mgr._on_pattern_control("codex", {"verdict": "REPLAN", "reason": "loop", "class": "search", "count": 8, "window": "10"})
        assert len(mgr.win.alerts) == 2, "升级到 control 应放行（覆盖低档提醒）"

    def test_different_scope_not_throttled(self, tmp_path):
        """不同 agent scope 互不影响：agent B 弹窗不受 agent A 的节流记录约束。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_stuck_intervention("agent-a", {"severity": 2})
        assert len(mgr.win.alerts) == 1
        mgr._throttle_now[0] += 5.0
        mgr._on_exploration_warning("sess-b", {"agent_key": "agent-b", "reasons": ["search"], "steps": []})
        assert len(mgr.win.alerts) == 2, "不同 agent scope 不受节流影响"

    def test_pattern_warning_no_alert_but_records_gate(self, tmp_path):
        """pattern warning 只播动画不弹窗、也不该占用节流槽（非弹窗事件）。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_pattern_warning("codex", {})
        assert mgr.win.alerts == []
        # 随后 stuck severity2（升级）不受影响
        mgr._on_stuck_intervention("codex", {"severity": 2})
        assert len(mgr.win.alerts) == 1

    def test_same_tier_stuck_escalation_is_throttled(self, tmp_path):
        """N2-b：同级重复升级（stuck 档位 2 → 档位 2）应被节流，不再连环换弹。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_stuck_intervention("codex", {"severity": 2})
        assert len(mgr.win.alerts) == 1
        mgr._throttle_now[0] += 5.0
        mgr._on_stuck_intervention("codex", {"severity": 2})
        assert len(mgr.win.alerts) == 1, "同档重复升级应被节流"

    def test_pattern_control_then_stuck_same_tier_is_throttled(self, tmp_path):
        """N2-b：pattern control 已弹窗后，同档 stuck 档位 2 应被节流（对称）。"""
        mgr = self._make_mgr(tmp_path)
        mgr._on_pattern_control("codex", {"verdict": "REPLAN", "reason": "loop",
                                        "class": "search", "count": 8, "window": "10"})
        assert len(mgr.win.alerts) == 1
        mgr._throttle_now[0] += 5.0
        mgr._on_stuck_intervention("codex", {"severity": 2})
        assert len(mgr.win.alerts) == 1, "同档提醒应被节流"

    def test_suppressed_alert_does_not_consume_throttle_slot(self, tmp_path):
        """N2-a：设置窗打开期间提醒被 show_alert 丢弃，不得占用 30s 节流槽。"""
        mgr = self._make_mgr(tmp_path)
        mgr.win._bubble_suppressed = True
        mgr._on_exploration_warning("sess-1", {"agent_key": "codex", "reasons": ["search"], "steps": []})
        assert mgr.win.alerts == [], "设置窗打开期间普通提醒应被丢弃"
        mgr.win._bubble_suppressed = False
        mgr._throttle_now[0] += 1.0
        mgr._on_exploration_warning("sess-1", {"agent_key": "codex", "reasons": ["search"], "steps": []})
        assert len(mgr.win.alerts) == 1, "被丢弃的提醒不该占用节流槽"

    def test_stuck_gate_rejected_alert_does_not_consume_throttle_slot(self, tmp_path):
        """F14：概率门丢弃的提醒不该占 30s 节流槽（stuck 路径）。

        先被概率门拒绝（未展示），随后一条放行的同 scope 提醒必须能正常弹；
        旧实现先记节流槽再判概率门，第二次会被 30s 窗口误压。
        """
        mgr = self._make_mgr(tmp_path, stuck=0.5)
        rolls = iter([0.99, 0.0])
        mgr._rng = lambda: next(rolls)
        mgr._on_stuck_intervention("codex", {"severity": 2})
        assert mgr.win.alerts == [], "概率门拒绝时不得弹窗"
        mgr._throttle_now[0] += 5.0
        mgr._on_stuck_intervention("codex", {"severity": 2})
        assert len(mgr.win.alerts) == 1, "被概率门丢弃的提醒不得占用节流槽"

    def test_pattern_gate_rejected_alert_does_not_consume_throttle_slot(self, tmp_path):
        """F14：pattern.control 同走 stuck 门，被门丢弃的提醒不得占节流槽。"""
        mgr = self._make_mgr(tmp_path, stuck=0.5)
        rolls = iter([0.99, 0.0])
        mgr._rng = lambda: next(rolls)
        payload = {"verdict": "REPLAN", "reason": "loop", "class": "search",
                   "count": 8, "window": "10"}
        mgr._on_pattern_control("codex", payload)
        assert mgr.win.alerts == [], "概率门拒绝时不得弹窗"
        mgr._throttle_now[0] += 5.0
        mgr._on_pattern_control("codex", payload)
        assert len(mgr.win.alerts) == 1, "被概率门丢弃的提醒不得占用节流槽"

    def test_watchdog_gate_rejected_alert_does_not_consume_throttle_slot(self, tmp_path):
        """F14：watchdog.warning 同走 stuck 门，被门丢弃的提醒不得占节流槽。"""
        mgr = self._make_mgr(tmp_path, stuck=0.5)
        rolls = iter([0.99, 0.0])
        mgr._rng = lambda: next(rolls)
        payload = {"agent_key": "codex", "reasons": ["search"], "steps": []}
        mgr._on_exploration_warning("sess-1", payload)
        assert mgr.win.alerts == [], "概率门拒绝时不得弹窗"
        mgr._throttle_now[0] += 5.0
        mgr._on_exploration_warning("sess-1", payload)
        assert len(mgr.win.alerts) == 1, "被概率门丢弃的提醒不得占用节流槽"


# ============================================================================
