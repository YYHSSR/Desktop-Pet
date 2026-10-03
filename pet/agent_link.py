# -*- coding: utf-8 -*-
"""多 Agent 状态感知与动作联动监视器模块（Codex / Cursor）。

设计原则（手册 §8）：
1. 绝不使用 mtime 盲轮询；
2. 统一事件协议：<config.dir>/agent-events/<agent>.jsonl，采用有界 Byte-Offset Tail 毫秒级增量读取；
3. 状态词汇统一：idle / thinking / working / attention / sleeping / error；
4. 状态 -> 桌宠动作映射：
   - thinking -> 写代码 (或 深度思考碎碎念)
   - working -> 原地敲击桌面互动
   - attention -> 气泡提示 ("需要你看一眼～")
   - error -> 气泡提示 ("好像遇到报错了…")
   - sleeping -> 待机
   - idle -> 待机
5. 低功耗：功能默认全关，每个 Agent 独立开关；隐藏时全线 pause()，显示时 resume()；
6. 只读本地事件，不写外部配置或发送审批决策。
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
import weakref
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal

from .report_gates import should_report_event
from .agent_event_protocol import parse_agent_event
from .agent_event_normalizer import normalize_event
from .model_access_tracker import ModelAccessTracker

from .persona_phrases import PhrasePicker
from .persona_template import CONDITIONAL_PARAMETERS
from .speech_bubble_text import truncate_bubble_text

log = logging.getLogger("dsh-pet-standalone")

_LIVE_AGENT_LINK_MANAGERS: weakref.WeakSet = weakref.WeakSet()
_LIVE_AGENT_MONITORS: weakref.WeakSet = weakref.WeakSet()

VALID_STATES = {"idle", "thinking", "working", "attention", "sleeping", "error"}
DEFAULT_EVENT_STATE_MAP = {
    "session/created": "idle", "session/disposed": "idle",
    "task_started": "working", "task_complete": "idle", "turn_aborted": "idle",
    "tool/call": "working", "tool/result": "working", "execution/failed": "error",
    "thinking": "thinking", "working": "working", "attention": "attention",
    "error": "error", "idle": "idle", "sleeping": "sleeping",
}


def normalize_event_state(event_name: str, explicit_state: str = "") -> str:
    """根据事件名或显式 state 字段规范化为标准状态词汇。

    返回空串表示「不认识的事件，忽略」——绝不把未知事件默认当成 working
    （Cursor 等的 transcript 行类型繁杂，默认 working 会导致过度触发）。
    """
    if explicit_state and explicit_state in VALID_STATES:
        return explicit_state
    return DEFAULT_EVENT_STATE_MAP.get(event_name, "")


def cursor_line_state(data: dict) -> str:
    """Cursor agent-transcripts 真实格式（{role, message:{content:[...]}}）→ 状态。

    - role=user：用户刚发话 → thinking
    - role=assistant 且 content 含 tool_use → working
    - role=assistant 纯文本（回合结束）→ idle
    其他一律忽略（""）。显式 state/event 字段（统一协议通道）优先。
    """
    explicit = str(data.get("state", "") or "")
    if explicit:
        return normalize_event_state("", explicit)
    role = str(data.get("role", "") or "").lower()
    if role == "user":
        return "thinking"
    if role == "assistant":
        content = data.get("message", {})
        if isinstance(content, dict):
            content = content.get("content")
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    return "working"
        return "idle"
    return normalize_event_state(str(data.get("type") or data.get("event") or ""))


def cursor_line_tool(data: dict) -> str:
    """从 Cursor transcript 行提取 tool_use 的工具名（content 块里的 name）。取不到返回 ""。"""
    if not isinstance(data, dict):
        return ""
    if str(data.get("role", "") or "").lower() != "assistant":
        return ""
    content = data.get("message", {})
    if isinstance(content, dict):
        content = content.get("content")
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                return str(c.get("name", "") or "").strip()
    return ""


def cursor_transcript_session_id(path: Path) -> str:
    """从 Cursor 转写路径取会话 id。

    现行布局：``.../agent-transcripts/<uuid>/<uuid>.jsonl``，会话 id 是父目录名。
    旧布局：``.../agent-transcripts/<name>.jsonl``，会话 id 是文件名（不含后缀）。
    """
    parent = path.parent
    if parent.name != "agent-transcripts" and parent.parent.name == "agent-transcripts":
        if parent.name != "subagents":
            return parent.name
    return path.stem


def codex_line_state(data: dict) -> str:
    """OpenAI Codex rollout JSONL 记录（event_msg / response_item 等）→ 状态。

    - type=event_msg, payload.type=task_started → working
    - type=event_msg, payload.type=task_complete → idle
    - type=event_msg, payload.type=turn_aborted → idle
    - type=response_item, payload.type=reasoning → thinking
    - type=response_item, payload.type in (custom_tool_call, function_call) → working
    - type=response_item, payload.type in (custom_tool_call_output, function_call_output) → working
    - type=event_msg, payload.type=item_completed 且 item.type in (CommandExecution, McpToolCall) → working
    """
    if not isinstance(data, dict):
        return ""
    explicit = str(data.get("state", "") or "")
    if explicit:
        return normalize_event_state("", explicit)
    d_type = str(data.get("type", "") or "")
    payload = data.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    p_type = str(payload.get("type", "") or "")

    if d_type == "event_msg":
        if p_type in ("approval_requested", "request_user_input", "user_input_requested"):
            return "attention"
        if p_type in ("task_failed", "error"):
            return "error"
        if p_type == "task_started":
            return "working"
        if p_type in ("task_complete", "turn_aborted"):
            return "idle"
        if p_type == "item_completed":
            item = payload.get("item")
            if isinstance(item, dict) and item.get("type") in ("CommandExecution", "McpToolCall"):
                return "working"
        return ""

    if d_type == "response_item":
        if p_type == "reasoning":
            return "thinking"
        if p_type in ("custom_tool_call", "function_call") and str(payload.get("name") or "").split(".")[-1] in {"request_user_input", "request_user_input_async"}:
            return "attention"
        if p_type in ("custom_tool_call", "function_call", "custom_tool_call_output", "function_call_output"):
            return "working"
        return ""

    return normalize_event_state(str(data.get("event") or d_type or ""))


def codex_line_tool(data: dict) -> str:
    """从 Codex rollout 记录提取工具名。取不到返回空字符串。"""
    if not isinstance(data, dict):
        return ""
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return ""
    p_type = str(payload.get("type", "") or "")
    if p_type in ("custom_tool_call", "function_call"):
        return str(payload.get("name") or payload.get("call_id") or "").strip()
    if p_type == "item_completed":
        item = payload.get("item")
        if isinstance(item, dict):
            return str(item.get("type") or item.get("name") or "").strip()
    return ""


class ByteOffsetTailer:
    """有界 Byte-Offset 文件增量行读取器。

    特性：
    - 记录上次读取的 byte offset；
    - 启动时若 offset 为 0 且文件已有内容，执行 backfill 防护（移动到末尾），防止重放历史事件；
    - 文件截断/轮转（当前大小 < offset）时安全重置到头部；
    - 单次读取最大字节数有界（如 64KB），防止大文件卡顿；
    - 零外部依赖，毫秒级读取。
    """

    def __init__(self, file_path: Path | str, max_chunk_bytes: int = 65536) -> None:
        self.file_path = Path(file_path)
        self.offset: int = 0
        self.max_chunk_bytes = max_chunk_bytes
        self._initial_backfill_done = False
        self._partial: bytes = b""  # 跨读取边界的未完成行缓冲（防止半行被丢弃）
        self._discard_until_newline = False  # 超长行丢弃模式：跳到下一个换行再恢复
        self._file_id: tuple[int, ...] | None = None  # 文件身份（Win: ino+ctime_ns / POSIX: dev+ino），识别同路径轮转新文件

    def reset(self) -> None:
        self.offset = 0
        self._initial_backfill_done = False
        self._partial = b""
        self._discard_until_newline = False
        self._file_id = None

    def read_new_lines(self) -> list[str]:
        """读取文件自上次 offset 以来的全部完整新增行。

        半行处理：若读取末尾不是换行符（行被 chunk 截断或写入方尚未写完），
        未完成部分存入 _partial，下次读取时拼回——绝不把半行当整行解析。"""
        if not self.file_path.is_file():
            return []

        try:
            st = self.file_path.stat()
            size = st.st_size
            # 文件身份识别（应对 bridge rename 轮转出同路径新文件）：
            # Windows 用 (ino, ctime_ns)——ctime 是创建时间，追加不变、轮转变化；
            # POSIX 的 ctime 是 inode 变更时间（每次追加都变），只能用 (dev, ino)。
            if os.name == "nt":
                file_id = (st.st_ino, st.st_ctime_ns)
            else:
                file_id = (st.st_dev, st.st_ino)
        except (OSError, AttributeError):
            return []

        # 启动时的首次初始化：若未指定 offset 则跳至当前末尾（backfill 防护）
        if not self._initial_backfill_done:
            self._initial_backfill_done = True
            self.offset = size
            self._file_id = file_id
            self._partial = b""
            return []

        # 文件被截断，或被轮换成同路径的新文件（bridge rename 后新文件可能
        # 在下次轮询前就长到不小于旧 offset，只看 size 会永久跳过新文件前部）
        if size < self.offset or (self._file_id is not None and file_id != self._file_id):
            self.offset = 0
            self._partial = b""
            self._discard_until_newline = False  # 旧文件的超长行丢弃状态不得泄漏进新文件
        self._file_id = file_id

        if size == self.offset:
            return []

        bytes_to_read = min(size - self.offset, self.max_chunk_bytes)
        try:
            with open(self.file_path, "rb") as f:
                f.seek(self.offset)
                chunk = f.read(bytes_to_read)
                self.offset = f.tell()
        except OSError as exc:
            log.warning("读取 tail 文件失败 %s: %s", self.file_path, exc)
            return []

        chunk = self._partial + chunk

        # 超长行丢弃模式：上个 chunk 已确认某行超过上限，跳到下一个换行再恢复
        if self._discard_until_newline:
            idx = chunk.find(b"\n")
            if idx == -1:
                return []
            chunk = chunk[idx + 1:]
            self._discard_until_newline = False

        if chunk and not chunk.endswith(b"\n"):
            # 末尾是不完整的半行：留到下次拼接
            idx = chunk.rfind(b"\n")
            if idx == -1:
                self._partial = chunk
                chunk = b""
            else:
                self._partial = chunk[idx + 1:]
                chunk = chunk[: idx + 1]
            # 防呆：单行超过上限时进入丢弃模式（跳过该超长行剩余部分，
            # 避免把它的"后半截"误当成一条新事件解析）
            if len(self._partial) > self.max_chunk_bytes:
                log.warning("tail 行超过 %d 字节上限，丢弃该超长行: %s", self.max_chunk_bytes, self.file_path)
                self._partial = b""
                self._discard_until_newline = True
        else:
            self._partial = b""

        # utf-8-sig：兼容 PowerShell Add-Content -Encoding UTF8 在文件首行写入的 BOM
        text = chunk.decode("utf-8-sig", errors="replace")
        lines = text.splitlines()
        return [line.strip() for line in lines if line.strip()]


@dataclass(frozen=True)
class AgentEvent:
    """监视器向管理器传递的状态/工具事件及其启动代次。"""

    agent: str
    kind: str
    gen: int = 0
    state: str = ""
    tool: str = ""
    session_id: str = ""
    turn_id: str = ""


class BaseAgentMonitor(QObject):
    """Agent 监视器抽象基类。"""

    state_changed = Signal(str, str)  # (agent_key, state)
    activity = Signal(str, str)       # (agent_key, 工具名) —— 过程汇报用，仅事件带工具名时发
    # Worker 事件载荷：保留上面的旧信号作为测试/外部兼容 API，管理器使用
    # 带代次的事件信号做接收端校验。
    state_event = Signal(object)
    activity_event = Signal(object)
    approval_requested = Signal(str, object)  # (agent_key, payload) —— 审批请求（含 rpcId 时可交互）
    approval_resolved = Signal(str, object)   # (agent_key, payload) —— 审批已结束，气泡应消失
    question_requested = Signal(str, object)  # (agent_key, payload) —— ask_user_question 阻塞交互
    question_resolved = Signal(str, object)   # (agent_key, payload) —— 问题已解决，气泡应消失
    # 原始桥接记录转发（供 stuck_detector 等消费）：(agent_key, record)
    raw_record = Signal(str, object)
    # Unified protocol output; legacy signals below remain the compatibility API.
    normalized_event = Signal(object)
    # 硬失败（execution/failed）：ChatGPT 已决定本轮不再继续，不经行为分析直接提醒
    execution_failed = Signal(str, object)   # (agent_key, payload)
    # 会话元数据更新（session/meta 事件）：(agent_key, record)
    session_meta = Signal(str, object)
    # 模型访问失败提醒（model_access 事件，errorCode 为服务端限流码）：(agent_key, record)
    model_access = Signal(str, object)
    # LLM API 错误（llm_error 事件，errorCode=真实码如 bad_response_status_code，
    # errorKind=api）：(agent_key, record)
    llm_error = Signal(str, object)
    # 用户介入信号（user_action 事件）：用户 ChatGPT 审批/回答 → 桌宠应关闭对应弹窗
    user_action = Signal(str, object)
    def __init__(self, agent_key: str, config_dir: Path, parent=None) -> None:
        super().__init__(parent)
        _LIVE_AGENT_MONITORS.add(self)
        self.agent_key = agent_key
        self.config_dir = Path(config_dir)
        self.events_dir = self.config_dir / "agent-events"
        self.events_file = self.events_dir / f"{agent_key}.jsonl"
        self._running = False
        self._paused = False
        self._tailer = ByteOffsetTailer(self.events_file)
        self._worker: threading.Thread | None = None
        self._worker_stop = threading.Event()
        self._gen = 0
        self._emit_gen = 0
        self._mkdir_on_start = True
        self._outbox: list[tuple] = []
        self._outbox_lock = threading.Lock()
        self._OUTBOX_CAP = 500
        # QObject 的 destroyed 槽在 PySide6 下不可靠地调用 bound method；
        # 连接无 receiver 的 callable，避免窗口销毁后遗留 daemon worker。
        self._destroyed_conn = self.destroyed.connect(
            lambda *_: BaseAgentMonitor._destroyed_guard(self)
        )
        self._destroy_guard_ran = False
        self._destroy_guard_lock = threading.Lock()

    def is_running(self) -> bool:
        return self._running and not self._paused

    def start(self) -> bool:
        if self._worker is not None and self._worker.is_alive():
            log.warning("Agent 监视器 [%s] 旧 worker 未退出，拒绝重启", self.agent_key)
            return False
        if self._destroyed_conn is None:
            self._destroyed_conn = self.destroyed.connect(
                lambda *_: BaseAgentMonitor._destroyed_guard(self)
            )
        with self._destroy_guard_lock:
            self._destroy_guard_ran = False
        self._worker_stop.set()
        self._worker_stop = threading.Event()
        self._gen += 1
        self._emit_gen = self._gen
        self._running = True
        self._paused = False
        if self._mkdir_on_start:
            self.events_dir.mkdir(parents=True, exist_ok=True)
        self._tailer.reset()
        gen = self._gen
        self._worker = threading.Thread(
            target=self._work_loop, args=(gen,), daemon=True,
            name=f"agent-monitor-{self.agent_key}",
        )
        self._worker.start()
        log.info("Agent 监视器 [%s] 已启动", self.agent_key)
        return True

    def begin_stop(self) -> None:
        """作废当前代次并发出停止信号，不阻塞 GUI。"""
        self._emit_gen = -1
        self._running = False
        self._paused = False
        with self._outbox_lock:
            self._outbox.clear()
        self._worker_stop.set()

    def finish_stop(self, deadline: float | None = None) -> None:
        worker = self._worker
        if worker is not None and worker.is_alive():
            remaining = self._STOP_JOIN_TIMEOUT_S if deadline is None else max(
                0.0, deadline - time.monotonic()
            )
            worker.join(timeout=remaining)
            if worker.is_alive():
                log.warning("Agent 监视器 [%s] worker 退出超时", self.agent_key)
        conn = getattr(self, "_destroyed_conn", None)
        if conn is not None:
            try:
                self.destroyed.disconnect(conn)
            except RuntimeError:
                pass
            self._destroyed_conn = None

    def stop(self) -> None:
        self.begin_stop()
        self.finish_stop()
        log.info("Agent 监视器 [%s] 已停止", self.agent_key)

    @classmethod
    def _shutdown_live_for_tests(cls) -> None:
        """收口测试直接创建且未显式停止的 monitor worker。"""
        for monitor in tuple(_LIVE_AGENT_MONITORS):
            try:
                monitor.stop()
            except Exception:
                log.debug("测试收口 Agent monitor 失败", exc_info=True)

    def pause(self) -> None:
        if self._running:
            self._paused = True

    def resume(self) -> None:
        if self._running and self._paused:
            self._paused = False
            with self._outbox_lock:
                pending = list(self._outbox)
                self._outbox.clear()
            for signal, args in pending:
                signal.emit(*args)

    @staticmethod
    def _destroyed_guard(mon: "BaseAgentMonitor") -> None:
        with mon._destroy_guard_lock:
            if mon._destroy_guard_ran:
                return
            mon._destroy_guard_ran = True
        try:
            # 本函数只从 destroyed 信号回调进入（见 __init__/start 的连接），此时
            # C++ 对象正处于析构中途，再对本信号 disconnect 会触发 PySide6 的
            # "Failed to disconnect" 告警，并在解释器退出时的 GC 场景下诱发原生
            # 访问违规（Windows 0xC0000005）。连接由 Qt 在对象析构时自动清理；
            # 这里只需作废引用以断开 Python 引用环（lambda 捕获 self）。
            if getattr(mon, "_destroyed_conn", None) is not None:
                mon._destroyed_conn = None
            mon._worker_stop.set()
            mon._emit_gen = -1
            mon._running = False
            mon._paused = False
            worker = mon._worker
            if worker is not None and worker.is_alive():
                threading.Thread(
                    target=BaseAgentMonitor._reap_worker,
                    args=(worker, mon._STOP_JOIN_TIMEOUT_S, mon.agent_key),
                    daemon=True, name=f"agent-monitor-reap-{mon.agent_key}",
                ).start()
        except Exception:
            log.debug("Agent 监视器 [%s] 销毁兜底异常", mon.agent_key, exc_info=True)

    @staticmethod
    def _reap_worker(worker: threading.Thread, timeout: float, agent_key: str) -> None:
        worker.join(timeout=timeout)
        if worker.is_alive():
            log.warning("Agent 监视器 [%s] 销毁兜底 worker 退出超时", agent_key)

    def _emit_state(self, state: str, gen: int, session_id: str = "", turn_id: str = "") -> None:
        event = AgentEvent(self.agent_key, "state", gen=gen, state=state, session_id=session_id, turn_id=turn_id)
        self._emit_pair(
            self.state_changed, (self.agent_key, state),
            self.state_event, (event,), state=state,
        )

    def _emit_tool(self, tool: str, gen: int, session_id: str = "") -> None:
        event = AgentEvent(self.agent_key, "tool", gen=gen, tool=tool, session_id=session_id)
        self._emit_pair(
            self.activity, (self.agent_key, tool),
            self.activity_event, (event,), state=None,
        )

    def _emit_pair(self, legacy_signal, legacy_args: tuple,
                   event_signal, event_args: tuple, *, state: str | None) -> None:
        """Emit legacy + generation-aware signals as one pause-buffered unit."""
        if not (self._paused and self._running):
            legacy_signal.emit(*legacy_args)
            event_signal.emit(*event_args)
            return
        with self._outbox_lock:
            if state is not None:
                for signal, args in reversed(self._outbox):
                    if signal is self.state_event and args[0].state == state:
                        return
            while len(self._outbox) + 2 > self._OUTBOX_CAP:
                for i, (signal, _) in enumerate(self._outbox):
                    if signal in (self.activity, self.activity_event):
                        del self._outbox[i]
                        break
                else:
                    if state is None:
                        return
                    break
            self._outbox.extend(((legacy_signal, legacy_args), (event_signal, event_args)))

    def _emit(self, signal, args: tuple) -> None:
        if self._paused and self._running:
            with self._outbox_lock:
                if len(self._outbox) >= self._OUTBOX_CAP:
                    for i, (sig, _) in enumerate(self._outbox):
                        if sig in (self.activity, self.activity_event):
                            del self._outbox[i]
                            break
                    else:
                        if signal in (self.activity, self.activity_event):
                            return
                self._outbox.append((signal, args))
            return
        signal.emit(*args)

    _POLL_INTERVAL_S = 1.5
    _STOP_JOIN_TIMEOUT_S = 2.0

    def _work_loop(self, gen: int) -> None:
        # 首轮等待一个周期，避免测试直调 _poll 与 worker 争抢 tailer。
        self._worker_started()
        while not self._worker_stop.wait(self._POLL_INTERVAL_S):
            if self._paused:
                continue
            try:
                self._poll(gen=gen)
            except Exception:
                log.debug("Agent 监视器 [%s] 轮询异常", self.agent_key, exc_info=True)

    def _worker_started(self) -> None:
        """供具体监视器在 worker 线程初始化其独占状态。"""

    def _emit_unified_event(self, data: dict) -> None:
        try:
            event = parse_agent_event(data, source_hint=self.agent_key, agent_name_hint=self.agent_key)
            normalized = normalize_event(event)
            if normalized is not None:
                self._emit(self.normalized_event, (normalized,))
        except Exception:
            log.debug("统一 AgentEvent 解析失败", exc_info=True)

    def _poll(self, gen: int | None = None) -> None:
        emit_gen = self._emit_gen if gen is None else gen
        for line in self._tailer.read_new_lines():
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            nested = data.get("data")
            if isinstance(nested, dict):
                data = {**data, **nested}
            self._emit_unified_event(data)
            self._emit(self.raw_record, (self.agent_key, data))
            event = str(data.get("event") or "")
            signal = {
                "approval/request": self.approval_requested,
                "approval/requested": self.approval_requested,
                "approval/decided": self.approval_resolved,
                "approval/resolved": self.approval_resolved,
                "question/requested": self.question_requested,
                "question/resolved": self.question_resolved,
                "execution/failed": self.execution_failed,
                "model_access": self.model_access,
                "llm_error": self.llm_error,
                "user_action": self.user_action,
            }.get(event)
            if signal is not None:
                self._emit(signal, (self.agent_key, data))
            if data.get("type") == "session/meta":
                self._emit(self.session_meta, (self.agent_key, data))
            session = str(data.get("sessionId") or data.get("session_id") or "")
            turn = str(data.get("turnId") or data.get("turn_id") or data.get("turn") or "")
            tool = str(data.get("tool") or "").strip()
            if tool:
                self._emit_tool(tool, emit_gen, session_id=session)
            state = normalize_event_state(event, str(data.get("state") or ""))
            if state:
                self._emit_state(state, emit_gen, session_id=session, turn_id=turn)


class CursorMonitor(BaseAgentMonitor):
    """Cursor 桌面端监视器。

    只读 tail ``~/.cursor/projects/**/agent-transcripts/`` 下的官方转写：
    现行是 ``<会话 id>/<会话 id>.jsonl``，同时保留旧的平铺 ``*.jsonl``。
    子代理目录 ``subagents/`` 不读。每个文件一个会话 id，交给管理器做多会话聚合。
    转写正文（用户提示、助手回复、工具参数）不进入统一事件，只留状态和工具名。
    """

    _TRANSCRIPT_GLOBS = (
        "**/agent-transcripts/*.jsonl",
        "**/agent-transcripts/*/*.jsonl",
    )

    def __init__(self, config_dir: Path, parent=None, base_dir: Path | None = None) -> None:
        super().__init__("cursor", config_dir, parent)
        self.cursor_base = base_dir or (Path.home() / ".cursor" / "projects")
        self._tailers: dict[str, ByteOffsetTailer] = {}
        self._turn_seq: dict[str, int] = {}
        self._turn_current: dict[str, str] = {}
        self._scan_interval = 15.0  # 目录发现降频：15s 一次（tail 仍 1.5s）
        self._last_scan = 0.0

    def _discover_transcripts(self, now: float) -> None:
        one_day_ago = now - 86400
        found: list[tuple[float, Path]] = []
        seen: set[str] = set()
        for pattern in self._TRANSCRIPT_GLOBS:
            for path in self.cursor_base.glob(pattern):
                if path.parent.name == "subagents":
                    continue
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    st = path.stat()
                except OSError:
                    continue
                if st.st_mtime >= one_day_ago:
                    found.append((st.st_mtime, path))
        found.sort(key=lambda item: item[0], reverse=True)
        candidates = {str(path) for _, path in found[:50]}
        for stale in [key for key in self._tailers if key not in candidates]:
            del self._tailers[stale]
            self._turn_seq.pop(stale, None)
            self._turn_current.pop(stale, None)
        for key in candidates:
            if key not in self._tailers:
                self._tailers[key] = ByteOffsetTailer(key)

    def _turn_id_for(self, file_key: str, data: dict) -> str:
        """同一转写文件里，每条 user 行开启新回合；后续行沿用该回合 id。"""
        if str(data.get("role", "") or "").lower() == "user":
            seq = self._turn_seq.get(file_key, 0) + 1
            self._turn_seq[file_key] = seq
            self._turn_current[file_key] = str(seq)
        return self._turn_current.get(file_key, "")

    def _poll(self, gen: int | None = None) -> None:
        # 统一 jsonl 通道（agent-events/cursor.jsonl）
        super()._poll(gen=gen)
        emit_gen = self._emit_gen if gen is None else gen

        if not self.cursor_base.is_dir():
            return

        now = time.time()
        # 目录发现降频：避免每 1.5s 递归 glob 整个 projects 目录。
        # 新转写文件最长一个扫描间隔才被纳入 tail，backfill 会跳到文件末尾，
        # 发现间隙内写入的事件会错过。
        if now - self._last_scan >= self._scan_interval:
            self._last_scan = now
            try:
                self._discover_transcripts(now)
            except Exception as exc:
                log.debug("Cursor monitor 扫描异常: %s", exc)

        for file_key, tailer in list(self._tailers.items()):
            session_id = cursor_transcript_session_id(Path(file_key))
            for line in tailer.read_new_lines():
                try:
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        continue
                    tool = cursor_line_tool(data)
                    turn_id = self._turn_id_for(file_key, data)
                    role = str(data.get("role", "") or "").lower()
                    if tool:
                        event_name = "tool/call"
                        payload: dict = {"tool": tool}
                    elif role == "user":
                        event_name = "UserPromptSubmit"
                        payload = {}
                    elif role == "assistant":
                        event_name = "assistant/message"
                        payload = {}
                    else:
                        event_name = str(data.get("type") or data.get("event") or "")
                        payload = {}
                    if event_name:
                        self._emit_unified_event({
                            "source": "cursor",
                            "agentName": "Cursor",
                            "sessionId": session_id,
                            "turn": turn_id,
                            "event": event_name,
                            "data": payload,
                            "timestamp": time.time(),
                        })
                    if tool:
                        self._emit_tool(tool, emit_gen, session_id=session_id)
                    norm = cursor_line_state(data)
                    if not norm:
                        continue
                    self._emit_state(norm, emit_gen, session_id=session_id, turn_id=turn_id)
                except Exception:
                    pass


class CodexDesktopMonitor(BaseAgentMonitor):
    """Read ChatGPT Work/Codex local rollouts without changing app data.

    The format is a local implementation detail, not a public ChatGPT API.
    Historical activity is skipped; session metadata establishes identity.
    """

    def __init__(self, config_dir: Path, parent=None, codex_dir: Path | None = None) -> None:
        super().__init__("codex", config_dir, parent)
        from .chatgpt_desktop import codex_sessions_dir
        self.codex_base = codex_dir if codex_dir is not None else codex_sessions_dir()
        self._tailers: dict[str, ByteOffsetTailer] = {}
        self._contexts: dict[str, dict] = {}
        self._scan_interval = 15.0
        self._last_scan = 0.0
        self._activated_at = time.time()
        self._discovered_once = False

    def _worker_started(self) -> None:
        self._tailers.clear()
        self._contexts.clear()
        self._last_scan = 0.0
        self._activated_at = time.time()
        self._discovered_once = False

    def _read_metadata(self, path: Path) -> dict:
        context = {"session": path.stem, "turn": "", "project": ""}
        try:
            with path.open("rb") as stream:
                line = stream.readline(262144)
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(max(0, size - 262144))
                tail = stream.read(262144)
            data = json.loads(line.decode("utf-8-sig"))
            payload = data.get("payload")
            if data.get("type") == "session_meta" and isinstance(payload, dict):
                context["session"] = str(payload.get("session_id") or payload.get("id") or path.stem)
                context["project"] = Path(str(payload.get("cwd") or "")).name
            for raw in reversed(tail.splitlines()):
                try:
                    record = json.loads(raw)
                except ValueError:
                    continue
                fields = record.get("payload") if isinstance(record, dict) else None
                if not isinstance(fields, dict):
                    continue
                if (record.get("type") in {"turn_context", "token_usage_record"}
                        or fields.get("type") == "task_started") and fields.get("turn_id"):
                    context["turn"] = str(fields["turn_id"])
                    break
        except (OSError, ValueError, AttributeError):
            pass
        return context

    @staticmethod
    def _rollout_lines(tailer: ByteOffsetTailer):
        """Drain at most 1 MiB per file/poll while bounding each line to 64 KiB.

        Large tool outputs are skipped without delaying subsequent state lines
        for one polling interval per 64 KiB fragment.
        """
        for _ in range(16):
            before = tailer.offset
            yield from tailer.read_new_lines()
            if tailer.offset == before:
                break

    def _poll(self, gen: int | None = None) -> None:
        super()._poll(gen=gen)
        emit_gen = self._emit_gen if gen is None else gen
        now = time.time()
        if not self._discovered_once or now - self._last_scan >= self._scan_interval:
            self._last_scan = now
            try:
                import heapq
                def recent_files():
                    for path in self.codex_base.glob("**/rollout-*.jsonl"):
                        try:
                            stat = path.stat()
                            if stat.st_mtime >= now - 86400:
                                yield (stat.st_mtime, str(path), stat.st_ctime)
                        except OSError:
                            continue
                candidates = {key: created for _, key, created in heapq.nlargest(50, recent_files())}
                for stale in set(self._tailers) - candidates.keys():
                    context = self._contexts.pop(stale, {})
                    self._tailers.pop(stale, None)
                    # Inactive/deleted files must not latch an agent busy forever.
                    if context.get("state") in ("working", "thinking", "attention"):
                        self._emit_state("sleeping", emit_gen, context.get("session", ""), context.get("turn", ""))
                for key, created in candidates.items():
                    if key in self._tailers:
                        continue
                    tailer = ByteOffsetTailer(key)
                    # A newly created session after activation is live, including
                    # records written before its first discovery poll.
                    # Filesystem birth timestamps can be coarser than time.time.
                    if self._discovered_once and created >= int(self._activated_at):
                        tailer._initial_backfill_done = True
                    self._tailers[key] = tailer
                    self._contexts[key] = self._read_metadata(Path(key))
                self._discovered_once = True
            except OSError:
                log.debug("ChatGPT rollout discovery failed", exc_info=True)

        for key, tailer in tuple(self._tailers.items()):
            context = self._contexts[key]
            for line in self._rollout_lines(tailer):
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(data, dict):
                    continue
                payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
                kind = str(payload.get("type") or "")
                if data.get("type") == "session_meta":
                    context.update(self._read_metadata(Path(key)))
                    continue
                session = str(payload.get("thread_id") or payload.get("session_id") or context["session"])
                turn = str(payload.get("turn_id") or context["turn"])
                if data.get("type") == "turn_context" or kind == "task_started":
                    context["turn"] = turn
                elif data.get("type") == "token_usage_record" and not context["turn"]:
                    context["turn"] = turn
                tool = codex_line_tool(data)
                state = codex_line_state(data)
                if not tool and not state:
                    continue
                # Don't retain prompt text, reasoning, tool arguments or outputs.
                adapted = {"source": "codex", "agentName": "ChatGPT", "sessionId": session,
                           "turn": turn, "event": kind, "tool": tool,
                           "projectName": context["project"], "timestamp": data.get("timestamp") or now}
                self._emit(self.raw_record, (self.agent_key, adapted))
                self._emit_unified_event(adapted)
                if tool:
                    self._emit_tool(tool, emit_gen, session_id=session)
                if state:
                    context["state"] = state
                    self._emit_state(state, emit_gen, session_id=session, turn_id=turn)


class CustomAgentMonitor(BaseAgentMonitor):
    """自定义联动 Agent 监视器（agent_link.custom_agents 配置驱动）。"""

    """只读监听用户指定路径的统一协议 JSONL 事件文件（docs/AGENT_LINK_PROTOCOL.md §4）：
    不创建目录、不写任何外部位置、无需授权弹窗；文件不存在时静默空转等待，
    出现后自动开始增量读取（backfill 防护跳过历史内容）。"""

    def __init__(self, agent_key: str, config_dir: Path, events_path: str, parent=None) -> None:
        super().__init__(agent_key, config_dir, parent)
        self.events_file = Path(events_path).expanduser()
        self.events_dir = self.events_file.parent
        self._tailer = ByteOffsetTailer(self.events_file)
        self._mkdir_on_start = False

    def start(self) -> bool:
        # 覆写基类 start：基类会 mkdir 事件目录，这里只读监听外部文件，
        # 不替用户在任意路径创建目录
        ok = super().start()
        if not ok:
            return False
        log.info("Agent 监视器 [%s] 已启动 (%s)", self.agent_key, self.events_file)
        return True


# ----------------------------------------------------------------------
# Agent 联动总调度管理器
# ----------------------------------------------------------------------

class AgentLinkManager(QObject):
    """多 Agent 联动总调度管理器。

    批6-5 拆分后本类只保留装配与编排：
    - 装配：2 内置 + 配置驱动的自定义监视器、StuckDetector / BehaviorPatternDetector /
      ExplorationWatchdog，并完成信号接线；
    - 监视器生命周期：pause / resume / shutdown / apply_config；
    - set_enabled：保存监听开关并启停只读监视器；
    - 对既有调用面（PetWindow / AppShell / ProactiveScreenWatcher / 测试）的薄转发。
    去抖/节流/完成确认与气泡/动画调度都在本类内实现。
    挂载于 PetWindow，持有内置及自定义监视器，并根据状态驱动桌宠动作与气泡。
    """

    # 联动气泡展示名
    AGENT_NAMES = {"codex": "ChatGPT", "cursor": "Cursor"}
    # 过程汇报：工具名 → 用户可读文案（不展示原始命令/路径）
    TOOL_LABELS = {
        "read": "正在读文件", "write": "正在写文件", "edit": "正在改代码",
        "notebookedit": "正在改代码", "bash": "正在跑命令", "shell": "正在跑命令",
        "pwsh": "正在跑命令", "powershell": "正在跑命令",
        "grep": "正在搜索", "glob": "正在搜索", "search": "正在搜索",
        "memory_search": "正在翻记忆",
        "exec_command": "正在跑命令", "apply_patch": "正在改代码",
        "functions.exec": "正在调用工具", "commandexecution": "正在跑命令",
        "mcptoolcall": "正在调用工具",
        "webfetch": "正在查网页", "websearch": "正在查网页",
        "fetch": "正在查网页", "browser": "正在查网页", "web_fetch": "正在查网页",
        "web_search": "正在查网页", "read_page": "正在读网页",
        "task": "正在派活给子代理", "todowrite": "正在列计划",
    }
    _UNKNOWN_TOOL_LABEL = "正在调用工具"
    _ACTIVITY_MIN_INTERVAL = 10.0    # 同 Agent 过程气泡最小间隔
    _ACTIVITY_GLOBAL_MIN = 8.0       # 全局最小间隔（多 Agent 并发防刷屏）
    _ACTIVITY_SAME_LABEL = 60.0      # 同一工具文案 60s 内不重复
    _ACTIVITY_TEXT_LIMIT = 80        # 过程汇报气泡文案上限（超出截断加「…」）
    _BUSY_STATES = ("working", "thinking")
    _SESSION_HISTORY_CAP = 256
    _DONE_CONFIRM_MS = 800   # busy→idle 稳定确认窗口（过滤 working→idle→working 抖动）
    _DONE_COOLDOWN_S = 5.0   # 同 Agent 完成气泡最小间隔（最后一道保险）

    def __init__(self, window: Any, config: Any, *, min_interval: float = 2.0,
                 clock: Callable[[], float] = time.time,
                 rng: Callable[[], float] = random.random) -> None:
        super().__init__(window if hasattr(window, "winId") else None)
        self.win = window
        self.cfg = config
        self.config_dir = config.dir
        self._shutdown = False
        _LIVE_AGENT_LINK_MANAGERS.add(self)
        # 状态节流：同一 Agent 相同状态去抖；同 Agent 两次动作切换最小间隔
        # （Cursor 等 transcript 密集写入时防止动画"抽搐"）
        self._min_interval = float(min_interval)
        self._clock = clock
        # 汇报抽稀随机源（可注入：测试用确定序列，避免 60% 抽样导致用例不确定）
        self._rng = rng
        self._last_applied: dict[str, tuple[str, float]] = {}
        # 原始状态流（不受去抖/节流影响）：用于 busy→idle 完成检测。
        # 不能用 _last_applied 做完成判定——节流会丢掉紧跟其后的 idle，导致完成通知丢失。
        self._last_raw: dict[str, str] = {}
        self._done_pending: dict[str, QTimer] = {}   # agent → 稳定确认定时器
        self._done_cooldown: dict[str, float] = {}   # agent → 上次完成气泡时刻
        self._saw_alert: set[str] = set()            # busy 周期内出现过 attention/error 的 Agent
        self._saw_error: set[str] = set()            # busy 周期内真正出现过 error 的 Agent
        self._link_seq = 0                           # 联动动作轮换计数
        # 过程汇报气泡：agent → (上次文案, 时刻)；全局最后一条时刻
        self._last_activity: dict[str, tuple[str, float]] = {}
        self._activity_global_last = 0.0
        self._phrase_picker = PhrasePicker()
        # Latest raw upstream record, exposed to dialogue templates.  This is
        # intentionally data-driven: newly added bridge fields become usable
        # without another per-event adapter change.
        self._dialogue_context: dict[str, Any] = {}
        # 最近一条工具记录（tool/call，含 target/callId/step/ok），按 agent 缓存：
        # 过程汇报气泡与 tool 信号同轮触发，用它把 target 等字段显式送进气泡，
        # 不再依赖「恰好是最后一条记录」的隐式上下文。
        self._last_tool_records: dict[str, dict[str, Any]] = {}
        self._model_access_tracker = ModelAccessTracker()
        # 待处理阻塞型交互：interaction_id → {"agent_key", "kind": "approval"|"question",
        # "text": str, "tool"?: str, "questions"?: list, "rpc_id"?, "approval_id"?,
        # "session_id"?, "alert_id"}。审批 / 用户问题都是「阻塞 Agent 等待用户输入」的
        # 交互，统一处理：气泡「一直挂到 resolved」。
        # interaction_id 优先用 rpcId（同一审批/问题的稳定标识），无 rpcId 时用
        # agent+kind+本地序号（降级提示路径）——**同一 agent 的多个审批各自独立
        # 存储**，不再以 agent_key 为键互相覆盖。按钮回调捕获 interaction_id，
        # 点「同意」只对对应那条审批生效；resolved 也按 rpcId 精确匹配关闭，
        # 绝不错放行/错关闭其他并发的审批。
        self._pending_interactions: dict[str, dict] = {}
        self._interaction_seq = 0  # 无 rpcId 的降级提示交互本地序号
        # 多会话/回合状态聚合（F08）：(agent_key, session_id) -> state；(agent_key, session_id) -> latest_turn_id
        self._session_states: dict[tuple[str, str], str] = {}
        self._session_turn_ids: dict[tuple[str, str], str] = {}

        self.monitors: dict[str, BaseAgentMonitor] = {
            "codex": CodexDesktopMonitor(self.config_dir, self),
            "cursor": CursorMonitor(self.config_dir, self),
        }
        # 自定义联动 Agent：配置驱动的只读监视器（key/path 已在 config 清洗时
        # 保证合法唯一）；显示名合并进实例级 agent_names，类级 AGENT_NAMES
        # 保持仅内置（modern_settings_dialog 等按内置枚举处不受影响）。
        # 注意：运行中新增/修改 custom_agents 需重启桌宠生效。
        self.agent_names: dict[str, str] = dict(self.AGENT_NAMES)
        for item in (self.cfg.get("agent_link", {}).get("custom_agents") or []):
            key = str(item.get("key") or "")
            if not key or key in self.monitors:
                continue
            self.monitors[key] = CustomAgentMonitor(
                key, self.config_dir, str(item.get("path") or ""), self,
            )
            self.agent_names[key] = str(item.get("name") or key)

        # 工具失败检测适用于提供工具结果的本地事件来源。
        from .stuck_detector import StuckDetector
        self._stuck_detector = StuckDetector(self)
        self._stuck_detector.intervention_recommended.connect(self._on_stuck_intervention)
        self._stuck_detector.stuck_resolved.connect(self._on_stuck_resolved)

        # 行为模式检测：双窗口规则识别
        # 慢性循环 / 短时爆发 / 纯探索无产出。与 stuck_detector（失败评分）互补。
        from .behavior_detector import BehaviorPatternDetector
        self._behavior_detector = BehaviorPatternDetector(self)
        self._behavior_detector.pattern_warning.connect(self._on_pattern_warning)
        self._behavior_detector.pattern_control.connect(self._on_pattern_control)

        # Agent Exploration Loop Watchdog：按 session/step 聚合全部探索行为。
        from .exploration_watchdog import ExplorationWatchdog
        self._exploration_watchdog = ExplorationWatchdog(self)
        self._exploration_watchdog.warning.connect(self._on_exploration_warning)
        # 会话元数据缓存：sessionId → { sessionName, projectName, agentName }
        self._session_meta_cache: dict[str, dict] = {}
        self._exploration_alerts: dict[str, str] = {}
        self._exploration_names: dict[str, str] = {}

        for mon in self.monitors.values():
            mon.raw_record.connect(self._remember_dialogue_record)
            mon.raw_record.connect(self._stuck_detector.feed_record)
            mon.raw_record.connect(self._behavior_detector.feed_record)
            mon.raw_record.connect(self._exploration_watchdog.feed_record)
            mon.raw_record.connect(self._on_exploration_lifecycle)
            mon.raw_record.connect(self._on_interaction_lifecycle)
            mon.normalized_event.connect(self._on_normalized_event)
            mon.state_event.connect(self._on_agent_state_event)
            mon.activity_event.connect(self._on_agent_activity_event)
            mon.approval_requested.connect(self._on_approval_request)
            mon.approval_resolved.connect(self._on_approval_resolved)
            mon.question_requested.connect(self._on_question_request)
            mon.question_resolved.connect(self._on_question_resolved)
            mon.execution_failed.connect(self._on_execution_failed)
            mon.session_meta.connect(self._on_session_meta)
            mon.model_access.connect(self._on_model_access)
            mon.llm_error.connect(self._on_llm_error)
            mon.user_action.connect(self._on_user_action)
        # 检测器提醒跨模块节流（N2）：stuck / pattern / exploration watchdog 三个
        # 检测器各有独立 cooldown，但同一 busy 周期可能先后各自弹窗造成连环换弹。
        # 按 agent/session 记最近一次**任一**检测器弹窗时刻与档位，窗口内同档
        # 或更低档的提醒只播动画、不再弹窗（更高档升级放行）。_clock 与其它计时同域。
        self._detector_alert_at: dict[str, tuple[float, int]] = {}
        # 模型访问失败提醒缓存：session_key → { "count": int, "_ts": float, "_first_ts": float, "_dismissed": bool }
        self._model_access_cache: dict[str, dict] = {}
        self._model_access_timers: dict[str, QTimer] = {}   # session_key → 自动收起定时器
        self._model_access_retry_counts: dict[tuple[str, str], int] = {}
        self._model_access_anonymous_seq = 0
        # LLM API 错误缓存：session_key → { "_ts": float, "_dismissed": bool }
        self._llm_error_cache: dict[str, dict] = {}
        self._llm_error_timers: dict[str, QTimer] = {}
        # 探索 Watchdog 控制请求的「在飞会话」集合：同一会话的重复点击只发一次。
        # 联动动作链：一次性动作播完后若仍有 Agent 在忙，由 window 回调取下一个动作
        if hasattr(self.win, "set_link_next_provider"):
            self.win.set_link_next_provider(self._next_busy_anim)

        self.apply_config()

    def _on_normalized_event(self, event) -> None:
        """Consume semantic events for streak tracking and interaction cleanup."""
        from .agent_event_normalizer import InteractionResolvedEvent, RetryEvent
        if isinstance(event, RetryEvent):
            streak = self._model_access_tracker.consume(event)
            if streak:
                self._model_access_retry_counts[(event.source, event.session_id)] = int(streak["consecutiveRetryCount"])
            return
        # The tracker resets its streak on successful/lifecycle events.
        if getattr(event, "session_id", ""):
            self._model_access_tracker.consume(event)
            self._model_access_retry_counts.pop((event.source, event.session_id), None)
        if not isinstance(event, InteractionResolvedEvent):
            return
        candidates = []
        for iid, item in self._pending_interactions.items():
            if item.get("kind") != event.kind or item.get("agent_key") != event.source:
                continue
            if event.session_id and str(item.get("session_id") or "") != event.session_id:
                continue
            identities = (event.request_id, event.rpc_id, event.approval_id, event.call_id)
            item_ids = (str(item.get("request_id") or ""), str(item.get("rpc_id") or ""), str(item.get("approval_id") or ""), str(item.get("call_id") or ""))
            if any(value and value == candidate for value in identities for candidate in item_ids):
                candidates.append(iid)
        if len(candidates) == 1:
            self._resolve_interaction(candidates[0])
        elif len(candidates) > 1:
            self._resolve_interaction(candidates[0])
        else:
            log.debug("interaction/resolved unmatched source=%s session=%s", event.source, event.session_id)

    def apply_config(self) -> None:
        """根据配置启停各个 Agent 监视器。

        注意用 _running（生命周期状态）而非 is_running()（会被 pause 置 False）——
        否则"隐藏期间关配置"不会真正 stop，恢复显示时又会被 resume 拉起。"""
        agent_cfg = self.cfg.get("agent_link", {})
        if not any(bool(agent_cfg.get(key)) for key in ("codex", "cursor")):
            self._clear_model_access_alerts()
        for key, monitor in self.monitors.items():
            should_run = bool(agent_cfg.get(key, False))
            if should_run and not monitor._running:
                monitor.start()
            elif not should_run and monitor._running:
                monitor.stop()
        # 卡住检测：开关 + 阈值/窗口/冷却参数同步（ChatGPT 联动开启才有效）
        self._stuck_detector.set_enabled(bool(agent_cfg.get("stuck_detect", True)))
        self._stuck_detector.get_config_overrides(agent_cfg if isinstance(agent_cfg, dict) else {})
        # 行为模式检测：开关 + 双窗口/step/冷却参数同步
        self._behavior_detector.set_enabled(bool(agent_cfg.get("pattern_detect", True)))
        self._behavior_detector.get_config_overrides(agent_cfg if isinstance(agent_cfg, dict) else {})
        self._exploration_watchdog.configure(agent_cfg if isinstance(agent_cfg, dict) else {})


    def _warn_if_agent_absent(self, agent_key: str) -> None:
        """开启了联动但本机没装对应 Agent 时给用户提示（不然勾了永远没反应）。"""
        # 自定义 Agent：事件文件尚未出现时提示路径，避免"勾了没反应"的困惑
        mon = self.monitors.get(agent_key)
        if isinstance(mon, CustomAgentMonitor):
            if mon.events_file.exists() or not hasattr(self.win, "show_bubble"):
                return
            self.win.show_bubble(
                f"已开启 {self.agent_names.get(agent_key, agent_key)} 联动监听，"
                f"但事件文件还没出现——{mon.events_file} 有事件我才能感知到哦",
                duration_ms=6000,
            )
            return
        hints = {
            "codex": ("ChatGPT Work / Codex", self.monitors["codex"].codex_base),
            "cursor": ("Cursor", Path.home() / ".cursor" / "projects"),
        }
        item = hints.get(agent_key)
        if not item:
            return
        name, marker = item
        if not marker.exists() and hasattr(self.win, "show_bubble"):
            self.win.show_bubble(
                self._dialogue("agent.missing", f"已开启 {name} 联动监听，尚未找到本地会话；请先在应用中运行一次工作任务。", name=name),
                duration_ms=6000,
            )


    def set_enabled(self, agent_key: str, enabled: bool) -> bool:
        """保存只读监听开关；未知来源返回 False，调用方回滚勾选态。"""
        if agent_key not in self.monitors:
            return False

        ag_cfg = dict(self.cfg.get("agent_link", {}))
        ag_cfg[agent_key] = bool(enabled)
        self.cfg.set("agent_link", ag_cfg)
        self.cfg.save()
        self.apply_config()
        if not enabled:
            self._cancel_done_check(agent_key)
            self._last_raw.pop(agent_key, None)
            self._last_applied.pop(agent_key, None)
            for states in (self._session_states, self._session_turn_ids):
                for key in [key for key in states if key[0] == agent_key]:
                    states.pop(key, None)
            for iid in list(self.pending_interactions_for(agent_key)):
                self._resolve_interaction(iid)
        if enabled:
            self._warn_if_agent_absent(agent_key)
        return True

    def pause(self) -> None:
        """桌宠隐藏时暂停所有监视器，丢弃待播联动动作，并取消所有完成确认计时器
        （否则隐藏期间计时器到期会在隐藏窗口上切动画/弹气泡）。"""
        for mon in self.monitors.values():
            mon.pause()
        self._stuck_detector.pause()
        self._behavior_detector.pause()
        # 探索看门狗随隐藏暂停：隐藏期继续跑只会让提醒在显示层被丢弃
        # （_poll_long_think 发射前置位已上报标志），永久丢失；暂停后恢复时
        # 计时锚点整体后移，隐藏时长不计入任何时长判定（产品决策：方案A）。
        self._exploration_watchdog.pause()
        if hasattr(self.win, "clear_pending_link_anim"):
            self.win.clear_pending_link_anim()
        for key in list(self._done_pending):
            self._cancel_done_check(key)

    def resume(self) -> None:
        """桌宠恢复显示时恢复活动的监视器。"""
        for mon in self.monitors.values():
            mon.resume()
        self._stuck_detector.resume()
        self._behavior_detector.resume()
        self._exploration_watchdog.resume()

    def shutdown(self) -> None:
        """窗口销毁/角色切换时停止所有 monitor worker，且作废安装回调。"""
        self._shutdown = True
        for mon in self.monitors.values():
            mon.begin_stop()
        active = [
            mon for mon in self.monitors.values()
            if mon._worker is not None and mon._worker.is_alive()
        ]
        if active:
            deadline = time.monotonic() + BaseAgentMonitor._STOP_JOIN_TIMEOUT_S
            for mon in active:
                mon.finish_stop(deadline)
        # 停掉 manager 自带的全部单发定时器（完成确认/模型访问失败收起/LLM 错误收起）：
        # 下方会把 Python 持有的 manager 过继给 QApplication，对象将存活到进程
        # 退出——若不停表，滞留定时器会在后续无关时刻触发槽函数。
        for timer_dict in (self._done_pending, self._model_access_timers, self._llm_error_timers):
            for timer in timer_dict.values():
                try:
                    timer.stop()
                except RuntimeError:
                    pass
            timer_dict.clear()
        # parent=None（测试桩/多窗代理）时 C++ 对象是 Python 持有的：wrapper 经
        # 信号连接/闭包成环，只能等循环 GC——而 GC 可能在任意线程（含 monitor
        # worker 线程）触发，跨线程删除带 QTimer 子对象/信号连接的 QObject 会
        # 腐化 Qt 事件队列（CI Windows 在 conftest processEvents access
        # violation、macOS bus error 的根因）。过继给 QApplication（主线程、
        # 与进程同寿）后，C++ 侧不再随 wrapper 的 GC 删除，wrapper 何时何线程
        # 回收都只是空壳析构。真窗口场景由父链销毁在先，RuntimeError 兜底跳过。
        AgentLinkManager._adopt_to_app_for_gc(self)

    @staticmethod
    def _adopt_to_app_for_gc(obj: "AgentLinkManager") -> None:
        """把 parent=None（测试桩/多窗代理）的 C++ 对象过继给 QApplication。

        仅接管 Python 侧生命周期，不改变业务状态：过继后 wrapper 在任何线程
        被循环 GC 回收时，C++ 侧都只是空壳析构，不会跨线程删除带 QTimer
        子对象/信号连接的 QObject（CI Windows interpreter 退出 access
        violation、macOS bus error 的根因，见 shutdown 注释）。真窗口场景由
        父链销毁在先，RuntimeError 兜底跳过。
        """
        try:
            app = QCoreApplication.instance()
            if obj.parent() is None and app is not None and obj.thread() is app.thread():
                obj.setParent(app)
        except RuntimeError:
            pass

    @classmethod
    def _shutdown_live_for_tests(cls) -> None:
        """收口未由测试显式持有的管理器，避免后台回写线程跨用例存活。"""
        for manager in tuple(_LIVE_AGENT_LINK_MANAGERS):
            try:
                manager.shutdown()
            except Exception:
                log.debug("测试收口 AgentLinkManager 失败", exc_info=True)

    def _gen_current(self, agent_key: str, gen: int) -> bool:
        mon = self.monitors.get(agent_key)
        return mon is not None and gen == mon._emit_gen

    def _on_agent_state_event(self, event: AgentEvent) -> None:
        self._on_agent_state(
            event.agent,
            event.state,
            event.gen,
            session_id=getattr(event, "session_id", ""),
            turn_id=getattr(event, "turn_id", ""),
        )

    def _on_agent_activity_event(self, event: AgentEvent) -> None:
        self._on_agent_activity(event.agent, event.tool, event.gen)


    def _on_agent_state(self, agent_key: str, state: str, gen: int = 0,
                        session_id: str = "", turn_id: str = "") -> None:
        """接收 Agent 状态变更并调度桌宠动作/气泡（带多会话聚合、去抖与节流）。"""
        if not self._gen_current(agent_key, gen):
            return

        sess_key = (agent_key, session_id or "default")

        # 迟到旧回合过滤（F08）：若同一 session 已进入新 turn_id，丢弃旧 turn_id 的 idle/done 事件
        if turn_id:
            last_turn = self._session_turn_ids.get(sess_key)
            if last_turn and last_turn != turn_id and state in ("idle", "sleeping"):
                log.debug("忽略迟到回合的结束事件: session=%s, turn=%s, current=%s", session_id, turn_id, last_turn)
                return
            self._session_turn_ids[sess_key] = turn_id

        # 更新当前会话状态
        self._session_states[sess_key] = state
        # Retain recent closed turns for late-event filtering without letting
        # completed session history grow for the lifetime of the pet.
        if len(self._session_states) > self._SESSION_HISTORY_CAP:
            for old_key, old_state in tuple(self._session_states.items()):
                if old_key != sess_key and old_state in ("idle", "sleeping"):
                    self._session_states.pop(old_key, None)
                    self._session_turn_ids.pop(old_key, None)
                    if len(self._session_states) <= self._SESSION_HISTORY_CAP:
                        break

        # 兜底：该 session 已待机时清理该 session 相关的 pending interaction
        if state in ("idle", "sleeping"):
            for iid in [i for i, v in self._pending_interactions.items()
                        if v.get("agent_key") == agent_key
                        and (not session_id or v.get("session_id") in ("", session_id))]:
                item = self._pending_interactions.pop(iid, None)
                if item is not None:
                    alert_id = item.get("alert_id", "")
                    if alert_id and hasattr(self.win, "resolve_alert"):
                        self.win.resolve_alert(alert_id)
                    elif hasattr(self.win, "hide_bubble"):
                        self.win.hide_bubble()

        # 计算该 Agent 下全部已知会话的宏观聚合状态（F08 核心）
        agent_session_states = [v for k, v in self._session_states.items() if k[0] == agent_key]
        if any(s in self._BUSY_STATES for s in agent_session_states):
            macro_state = "working" if any(s == "working" for s in agent_session_states) else "thinking"
        elif any(s == "attention" for s in agent_session_states):
            macro_state = "attention"
        elif any(s == "error" for s in agent_session_states):
            macro_state = "error"
        else:
            macro_state = "idle"

        # 桌宠隐藏：动画/声音不呈现，但状态簿记（_last_raw / 成本 / 完成确认
        # 调度）照常推进——岛反馈面可用时气泡经 _show_link_bubble 改道灵动岛
        # （无注入时维持丢弃）。此前整段 return 会连簿记一起丢，隐藏期间
        # start/done 反馈气泡全部消失（岛反馈面引入后用户实测）。
        hidden = not hasattr(self.win, "isVisible") or not self.win.isVisible()

        mark = getattr(self.win, "mark_activity", None)
        if callable(mark) and not hidden:
            mark()

        now = self._clock()
        # --- 原始状态流（绕开去抖/节流）：busy→idle 完成检测 ---
        # 不能用 _last_applied 判定完成——节流会丢掉紧跟的 idle，导致完成通知丢失。
        prev_raw = self._last_raw.get(agent_key)
        self._last_raw[agent_key] = macro_state
        if macro_state in self._BUSY_STATES:
            self._cancel_done_check(agent_key)
            self._saw_alert.discard(agent_key)
            if prev_raw != "error":
                self._saw_error.discard(agent_key)
        elif macro_state in ("attention", "error") and prev_raw in self._BUSY_STATES:
            self._saw_alert.add(agent_key)
            if macro_state == "error":
                self._saw_error.add(agent_key)
            # attention/error 同样进入完成确认（800ms 内回忙则取消——例如
            # SubagentStop 后主 Agent 继续干活、工具报错后重试）。
            if macro_state == "error":
                self._schedule_done_check(agent_key)
        elif macro_state in ("idle", "sleeping") and prev_raw in (*self._BUSY_STATES, "attention"):
            # working/thinking → idle：疑似任务完成，800ms 稳定确认
            # （过滤 working→idle→working 抖动；确认期间回忙则取消）
            self._schedule_done_check(agent_key)

        # 去抖：同一 Agent 连续相同状态只生效第一次
        last = self._last_applied.get(agent_key)
        if last is not None and last[0] == macro_state:
            return
        # 节流：同一 Agent 两次动作/气泡切换最小间隔
        if last is not None and (now - last[1]) < self._min_interval and macro_state not in ("attention", "error"):
            return
        self._last_applied[agent_key] = (macro_state, now)

        log.debug("Agent 状态变更 [%s]: macro=%s (session=%s, s=%s)", agent_key, macro_state, session_id, state)

        # 状态 -> 桌宠行为映射（手册 §8.2）
        if macro_state in ("thinking", "working"):
            # busy 动作池轮换（写代码/吃Token 为主，每第 3 次插播短摸鱼），
            # 经 request_link_anim 平滑衔接：正在播的一次性动作不被打断。
            # 隐藏中不切动画（零功耗语义），气泡仍经改道上岛。
            anim = self._next_link_anim_rotation()
            if anim and not hidden and hasattr(self.win, "request_link_anim"):
                self.win.request_link_anim(anim)
            self._maybe_notify_start(agent_key, prev_raw, macro_state)
        elif macro_state == "attention":
            # 避免「需要看一眼」和「完成通知」双气泡；独立出现的才立即提醒
            name = self.agent_names.get(agent_key, agent_key)
            self._show_link_bubble(self._dialogue("agent.attention", "主人，Agent 这边需要你看一眼～", agent_key=agent_key, name=name), important=True)
        elif macro_state == "error":
            if prev_raw not in self._BUSY_STATES:
                name = self.agent_names.get(agent_key, agent_key)
                self._show_link_bubble(self._dialogue("agent.error", "Agent 执行好像遇到报错了…", agent_key=agent_key, name=name), important=True)
        elif macro_state in ("sleeping", "idle"):
            # 回到待机：一次性动作播完自然回，待机/移动中立即回（隐藏中不切）
            if not hidden:
                if hasattr(self.win, "request_link_idle"):
                    self.win.request_link_idle()
                elif hasattr(self.win, "switch_clip") and getattr(self.win, "idles", None):
                    self.win.switch_clip(self.win.idles[0])

    # ------------------------------------------------------------------
    # 联动动作池（写代码/吃Token 交替为主，每第 3 次插播短摸鱼）
    # ------------------------------------------------------------------
    _LINK_MAIN = ("写代码", "吃Token")
    _LINK_BREAK = ("轻快记录", "漂浮踏步")
    _LINK_MAIN_KEYWORDS = ("代码", "工作", "写", "打字", "敲")
    _LINK_BREAK_KEYWORDS = ("记录", "踏步", "伸懒腰")

    def any_busy(self) -> bool:
        """Return whether an enabled monitor currently reports active work.

        ``_last_raw`` intentionally keeps the latest state after a monitor is
        stopped, so it must be paired with the monitor lifecycle flag here.
        Using ``is_running()`` would incorrectly treat a paused monitor as
        disabled; ``_running`` is the lifecycle state used by ``apply_config``
        and is therefore the authoritative check for the idle-FPS gate.
        """
        return any(
            bool(getattr(monitor, "_running", False))
            and self._last_raw.get(agent_key) in self._BUSY_STATES
            for agent_key, monitor in self.monitors.items()
        )

    def _next_link_anim_rotation(self) -> str | None:
        """下一个联动动作：主动作严格交替；每第 3 次插播摸鱼（独立节奏）。"""
        acts = list(getattr(self.win, "cats", {}).get("acts", []) or [])
        main = [a for a in self._LINK_MAIN if a in acts]
        brk = [a for a in self._LINK_BREAK if a in acts]
        # 不同角色包的动作名不统一：精确名缺失时按语义关键词回退。
        if not main:
            main = [a for a in acts if any(k in a for k in self._LINK_MAIN_KEYWORDS)]
        if not brk:
            brk = [a for a in acts if any(k in a for k in self._LINK_BREAK_KEYWORDS)]
        # 角色包至少有一个动作时，确保 Agent 忙碌期间始终有可见反馈。
        if not main and not brk:
            main = acts
        if not main and not brk:
            return None
        self._link_seq += 1
        if brk and self._link_seq % 3 == 0:
            return brk[(self._link_seq // 3 - 1) % len(brk)]
        if main:
            return main[(self._link_seq - 1) % len(main)]
        return brk[(self._link_seq - 1) % len(brk)]

    def _next_busy_anim(self) -> str | None:
        """window 动画结束回调用：仍有 Agent 在忙 → 下一个联动动作；否则 None。
        全员空闲时重置轮换计数——下一个任务从「写代码」重新开始。"""
        if any(s in self._BUSY_STATES for s in self._last_raw.values()):
            return self._next_link_anim_rotation()
        self._link_seq = 0
        return None

    # 进程名 → Agent：该 Agent 联动开启且正忙时，主动识屏跳过它的窗口
    # （联动气泡已在汇报进度，识屏再评一句就是重复打扰）。
    AGENT_PROCESS_HINTS = {
        "codex": ("codex.exe", "chatgpt.exe"),
        "cursor": ("cursor.exe",),
    }
    AGENT_TITLE_HINTS = {
        "codex": ("codex",),
    }

    def busy_agent_owns_process(self, process_name: str, title: str = "") -> bool:
        """前台窗口是否属于「联动开启且正在忙」的 Agent（进程名或窗口标题命中）。"""
        agent_cfg = self.cfg.get("agent_link", {})
        p = str(process_name or "").lower()
        t = str(title or "").lower()
        for agent_key, procs in self.AGENT_PROCESS_HINTS.items():
            if p and p in procs and agent_cfg.get(agent_key) \
                    and self._last_raw.get(agent_key) in self._BUSY_STATES:
                return True
        for agent_key, needles in self.AGENT_TITLE_HINTS.items():
            if t and any(n in t for n in needles) and agent_cfg.get(agent_key) \
                    and self._last_raw.get(agent_key) in self._BUSY_STATES:
                return True
        return False

    # ------------------------------------------------------------------
    # 联动气泡（开始干活可选 / 任务完成通知）
    # ------------------------------------------------------------------
    _THINKING_DEFAULTS: dict[str, str] = {}

    def _remember_dialogue_record(self, agent_key: str, record: object) -> None:
        """Expose the latest upstream record to phrase templates."""
        if not isinstance(record, dict):
            return
        context = dict(record)
        context.setdefault("agent_key", agent_key)
        context.setdefault("agent", agent_key)
        context.setdefault("agent_name", self.agent_names.get(agent_key, agent_key))
        self._dialogue_context = context
        if str(context.get("tool") or "").strip() or str(context.get("event") or "") == "tool/call":
            self._last_tool_records[agent_key] = context

    def _dialogue(self, key: str, fallback: str, *, agent_key: str = "", **values) -> str:
        """Render an event with explicit aliases plus latest upstream fields.

        ``agent_key``（默认 ""=非 Agent/全局场景）用于统一预设路由：
        custom 模式下按 ``agents[agent_key][key] → global[key] → 内置`` 取文案；
        传空时只读 global（兼容旧单层自定义台词）。
        """
        merged = dict(self._dialogue_context)
        merged.update(values)
        # 条件参数（CONDITIONAL_PARAMETERS）：上游未提供/为空/为 null 时渲染端
        # 自动隐藏对应占位符，不原样露出 {xxx}。
        autohide = CONDITIONAL_PARAMETERS.get(key, ())
        mode = str(self.cfg.get("dialogue_mode", "legacy") or "legacy")
        if mode == "custom":
            return self._phrase_picker.custom_for_agent(self.cfg.get("dialogue_phrases", {}), agent_key, key,
                                                        fallback, autohide=autohide, **merged)
        return self._phrase_picker.get(mode, key, fallback, autohide=autohide, **merged)

    def _session_conditional(self, record: dict) -> dict[str, str]:
        """从记录提取条件会话字段（缺失/为空不注入，渲染端自动隐藏占位符）。

        返回 sessionName（会话名）/ projectName（项目名）/ label（会话标签），
        三者语义独立：sessionName 只取会话自己的名字，绝不拼进 projectName
        （否则 {sessionName} 与 {projectName} 两字段语义重复）。sessionId 存在
        且记录缺字段时，从会话元数据缓存补齐（只补真实字段，不编造展示串）。
        注意 label 同名双义：activity.*/approval.tool 的 label 是工具标签，
        由调用点显式传入——那些调用点不要用本方法返回值覆盖 label。
        """
        record = record if isinstance(record, dict) else {}
        vals: dict[str, str] = {}
        for field in ("projectName", "sessionName", "label"):
            value = str(record.get(field) or "").strip()
            if value:
                vals[field] = value
        session_id = str(record.get("sessionId") or "").strip()
        if session_id:
            if "sessionName" not in vals:
                session_name = self._session_name_or_empty(session_id)
                if session_name:
                    vals["sessionName"] = session_name
            if "projectName" not in vals:
                meta = self._session_meta_cache.get(session_id) or {}
                project_name = str(meta.get("projectName") or "").strip()
                if project_name:
                    vals["projectName"] = project_name
        return vals

    def _thinking_text(self, agent_key: str) -> str:
        """thinking 气泡文案：统一预设 agents delta/global > 旧 per-Agent 自定义 > 内置默认。"""
        agent_cfg = self.cfg.get("agent_link", {})
        name = self.agent_names.get(
            agent_key,
            self.agent_names.get(agent_key, agent_key),
        )

        # 1) 统一预设（dialogue_mode=custom 且配置了 agents/global 时优先）
        mode = str(self.cfg.get("dialogue_mode", "legacy") or "legacy")
        if mode == "custom":
            preset = self.cfg.get("dialogue_phrases", {})
            if isinstance(preset, dict) and ("global" in preset or "agents" in preset):
                custom = self._phrase_picker.custom_for_agent(
                    preset, agent_key, "thinking", "",
                    name=name,
                )
                if custom:
                    return custom

        # 2) 旧 per-Agent / 全局自定义（agent_link.thinking_texts / thinking_text）
        custom = (agent_cfg.get("thinking_texts") or {}).get(agent_key, "").strip()
        if not custom:
            custom = str(agent_cfg.get("thinking_text", "") or "").strip()
        if custom:
            return custom.replace("{name}", name)

        # 3) 内置默认
        if agent_key in self._THINKING_DEFAULTS:
            fallback = self._THINKING_DEFAULTS[agent_key]
            return self._dialogue("thinking", fallback, agent_key=agent_key, name=name)

        return self._dialogue(
            "thinking",
            f"{name} 正在深度烧烤……",
            agent_key=agent_key,
            name=name,
        )

    def _report_allowed(self, agent_cfg: dict, event_key: str) -> bool:
        """事件汇报概率门：按事件聚合类别取该类通过概率并抽稀。

        - 门值 ``0.0`` → 该类完全不汇报；``1.0`` → 全部汇报；
        - 未知事件**不抽稀**（直接放行），新事件上线不会被静默丢弃；
        - 只作用于**出气泡**这一步：检测器本身与 ``raw_record`` 链路不受影响。
        """
        gates = agent_cfg.get("report_gates", {})
        if not isinstance(gates, dict):
            gates = {}
        return should_report_event(gates, event_key, self._rng())

    def _maybe_notify_start(self, agent_key: str, prev_raw: str | None, state: str = "working") -> None:
        """开始干活气泡：仅「非 busy → busy」时提示（thinking↔working 互跳不弹）。
        低优先级：气泡位被占时直接丢弃。thinking 状态用更有趣的文案。"""
        agent_cfg = self.cfg.get("agent_link", {})
        if not self._report_allowed(agent_cfg, "thinking" if state == "thinking" else "start"):
            return
        if prev_raw in self._BUSY_STATES:
            return
        name = self.agent_names.get(agent_key, agent_key)
        if state == "thinking":
            self._show_link_bubble(self._thinking_text(agent_key), important=False, duration_ms=3000)
        else:
            self._show_link_bubble(
                self._dialogue("start", f"{name} 开始干活啦～", agent_key=agent_key, name=name),
                important=False, duration_ms=3000,
            )

    def _on_agent_activity(self, agent_key: str, tool: str, gen: int = 0) -> None:
        """过程汇报气泡（可选，默认关）：「ChatGPT 正在读文件…」这类。
        白名单工具映射 + 三重限流（同 Agent 10s / 同文案 60s / 全局 8s）。"""
        if not self._gen_current(agent_key, gen):
            return
        mark = getattr(self.win, "mark_activity", None)
        if callable(mark):
            mark()
        agent_cfg = self.cfg.get("agent_link", {})
        label = self.TOOL_LABELS.get(str(tool).strip().lower(), self._UNKNOWN_TOOL_LABEL)
        now = self._clock()
        last = self._last_activity.get(agent_key)
        if last is not None:
            if last[0] == label and now - last[1] < self._ACTIVITY_SAME_LABEL:
                return
            if now - last[1] < self._ACTIVITY_MIN_INTERVAL:
                return
        if now - self._activity_global_last < self._ACTIVITY_GLOBAL_MIN:
            return
        # 事件汇报概率门（过程汇报默认 0.6）：只作用在出气泡这一步，且**不记账**——
        # 抽稀丢弃不更新 _last_activity/_activity_global_last，否则概率会与三重
        # 节流叠加、把过程汇报过度衰减。raw_record 链路不经过本函数，检测类
        # 消费者（卡住/行为/探索/对话记忆）不受影响。
        if not self._report_allowed(agent_cfg, "activity.default"):
            return
        self._last_activity[agent_key] = (label, now)
        self._activity_global_last = now
        name = self.agent_names.get(agent_key, agent_key)
        # 低优先级：气泡位被占直接丢弃，不与重要气泡竞争
        tool_key = str(tool).strip().lower()
        if tool_key in {"read", "read_page"}:
            key = "activity.read"
        elif tool_key in {"grep", "glob", "search", "websearch", "web_search", "webfetch", "fetch", "browser", "web_fetch"}:
            key = "activity.search"
        elif tool_key in {"edit", "write", "notebookedit"}:
            key = "activity.edit"
        elif tool_key in {"bash", "shell", "pwsh", "powershell"}:
            key = "activity.run"
        else:
            key = "activity.default"
        # tool 信号与 tool/call 记录同轮到达（监视器 _poll 先发 raw_record 再发
        # activity），按 agent 取最近一条工具记录，把 target/callId/step/ok 显式
        # 送进气泡；缺失的字段不传，占位符保持原样（不注入空串撑脏文案）。
        tool_record = self._last_tool_records.get(agent_key) or {}
        # tool/call 记录字段：command/argsKey/callId/step + 会话字段（缺失不注入，
        # 渲染端自动隐藏占位符）。target/ok 不在 tool/call 记录里，不读取。
        # label 同名双义：activity 的 label=工具标签，须后写覆盖会话标签。
        values: dict[str, Any] = dict(self._session_conditional(tool_record))
        for field in ("command", "argsKey", "callId", "step"):
            value = tool_record.get(field)
            if value not in (None, ""):
                values[field] = value
        values["name"] = name
        values["tool"] = str(tool).strip()
        values["label"] = label
        # 源头截断：用户自定义文案模板可能带很长的命令/参数，过程汇报气泡只做
        # 一句提示，超过 _ACTIVITY_TEXT_LIMIT 字就截断加「…」（不进分页/滚动）。
        text = truncate_bubble_text(
            self._dialogue(key, f"{name} {label}…", agent_key=agent_key, **values),
            self._ACTIVITY_TEXT_LIMIT,
        )
        self._show_link_bubble(text, important=False, duration_ms=2600)

    def _on_approval_request(self, agent_key: str, payload: dict) -> None:
        """审批记录必须携带稳定身份。只显示提醒，用户在所属应用中决定。"""
        agent_cfg = self.cfg.get("agent_link", {})
        if not self._report_allowed(agent_cfg, "approval.command"):
            return
        payload = payload if isinstance(payload, dict) else {}
        # 可关联身份门禁：无 rpcId/approvalId/requestId/callId 一律不弹窗。
        if not (payload.get("rpcId") or payload.get("approvalId")
                or payload.get("requestId") or payload.get("callId")):
            log.debug("approval/request 缺可关联身份，忽略（不弹窗）: %s", str(payload)[:200])
            return
        name = self.agent_names.get(agent_key, agent_key)
        tool = str(payload.get("toolName") or payload.get("tool") or "").strip()
        command = str(payload.get("command") or "").strip()
        session_id = str(payload.get("sessionId") or "")
        session_display = self.get_session_display_name(session_id) if session_id else ""
        prefix = f"{session_display} · " if session_display and session_display != f"ChatGPT · {session_id[:8]}" else ""
        # 条件会话字段 + 原始工具名（缺失不注入，渲染端自动隐藏占位符）
        conditional = self._session_conditional(payload)
        if tool:
            conditional["toolName"] = tool
        if command:
            # 命令全文优先：折叠换行/空白成单行，超长截断加省略号（气泡是图片气泡）
            formatted = self._format_command(command)
            text = self._dialogue(
                "approval.command", f"{prefix}{name} 请求执行：{formatted}，请选择：",
                command=formatted, name=name, **conditional,
            )
        else:
            tool_lower = tool.lower().removeprefix("functions.")
            label = self.TOOL_LABELS.get(tool_lower, "")
            if label:
                text = self._dialogue(
                    "approval.tool", f"{prefix}{name} 在请求审批：{label}，请选择：",
                    label=label, name=name, **conditional,
                )
            elif tool:
                text = self._dialogue("approval.tool", f"{prefix}{name} 有审批等你决定（{tool}）：",
                                      label=tool, name=name, **conditional)
            else:
                text = self._dialogue("approval.generic", f"{prefix}{name} 有审批等你决定：",
                                      name=name, **conditional)
            if not label and not tool:
                text = self._dialogue("approval.generic", text, name=name, **conditional)
        self._register_interaction(
            agent_key, kind="approval", text=text, tool=tool, command=command,
            interactive=False,
            rpc_id=payload.get("rpcId"),
            approval_id=payload.get("approvalId"),
            request_id=payload.get("requestId"),
            # callId 是审批收尾的精确身份：登记端必须存下，_on_approval_resolved
            # 的 callId 分支才能配对关闭。当前桥接版本的审批帧实际不带 callId
            # （此分支面向旧版/自定义桥的防御路径，常态走 rpcId/approvalId 关闭）。
            call_id=payload.get("callId"),
            session_id=session_id,
        )

    @staticmethod
    def _format_command(command: str, max_len: int = 160) -> str:
        """把命令折叠成单行并安全截断，供气泡展示。

        - 连续空白/换行折叠成单个空格（气泡图片不保留换行）
        - 超过 max_len 截断并追加省略号，避免撑爆气泡
        """
        text = " ".join(str(command).split())
        if len(text) > max_len:
            text = text[:max_len].rstrip() + "…"
        return text


    def _on_question_request(self, agent_key: str, payload: dict) -> None:
        """问题记录必须携带稳定身份。只显示提醒，用户在所属应用中回答。"""
        agent_cfg = self.cfg.get("agent_link", {})
        if not self._report_allowed(agent_cfg, "question.one"):  # 与审批同门（审批与提问类）
            return
        payload = payload if isinstance(payload, dict) else {}
        # 可关联身份门禁：rpcId（mux）或 callId（tool/call 兜底）任一非空才登记。
        if not (payload.get("rpcId") or payload.get("callId")):
            log.debug("question/requested 缺可关联身份，忽略（不弹窗）: %s", str(payload)[:200])
            return
        name = self.agent_names.get(agent_key, agent_key)
        questions = payload.get("questions") or []
        if not isinstance(questions, list):
            questions = []
        session_id = str(payload.get("sessionId") or "")
        session_display = self.get_session_display_name(session_id) if session_id else ""
        prefix = f"{session_display} · " if session_display and session_display != f"ChatGPT · {session_id[:8]}" else ""
        conditional = self._session_conditional(payload)
        self._register_interaction(
            agent_key, kind="question", text=self._question_text(name, questions, prefix=prefix,
                                                                 conditional=conditional),
            questions=questions,
            interactive=False,
            rpc_id=payload.get("rpcId"),
            call_id=payload.get("callId"),
            session_id=session_id,
        )

    def _question_text(self, name: str, questions: list, *, prefix: str = "",
                       conditional: dict | None = None) -> str:
        """把 questions 载荷排版成气泡文案（单行紧凑）。

        泡泡是图片气泡：normalize_bubble_text 会把换行折叠成空格，且 sticky 只
        显示第一页——所以选项用「 / 」内联拼接而非强行多行，保证「永久选项弹窗」
        在小气泡里完整可见（交互模式下按钮本身也展示了选项）。"""
        conditional = conditional or {}
        if not questions:
            return self._dialogue("question.empty", f"{prefix}{name} 在等你回答一个问题，快去看一下～",
                                  name=name, **conditional)
        if len(questions) > 1:
            if self._questions_all_have_options(questions):
                return self._dialogue("question.many", f"{prefix}{name} 有 {len(questions)} 个问题等你回答，快去看一下～",
                                      count=len(questions), name=name, **conditional)
            # 含自由文本分支：整批必须回 ChatGPT 界面输入，引导不随台词被覆盖
            return self._with_input_hint(self._dialogue(
                "question.many",
                f"{prefix}{name} 有 {len(questions)} 个问题等你回答"
                "（含文本输入，请到 ChatGPT 界面输入文本回答）～",
                count=len(questions), name=name, **conditional,
            ))
        q = questions[0]
        if not isinstance(q, dict):
            q = {}
        body = str(q.get("question") or "（问题）")
        header = str(q.get("header") or "").strip()
        if header:
            body = f"{header}：{body}"
        opts = q.get("options") or []
        labels = []
        for o in opts:
            label = str(o.get("label") or "") if isinstance(o, dict) else str(o)
            if label:
                labels.append(label)
        multi = "（可多选）" if q.get("multiSelect") else ""
        if labels:
            return f"{name} 在问你：{body}（{' / '.join(labels)}）{multi}请选择一个："
        if multi:
            return f"{name} 在问你：{body}（可多选）快去选一下～"
        # 无选项 = 需要自由输入文本：气泡必须明确引导回 ChatGPT 界面输入。
        # 引导是结构性操作提示，不随表达风格台词（legacy/whale_maid/custom）被覆盖。
        text = self._dialogue(
            "question.one",
            f"{name} 在问你：{body}，需要你输入，请到 ChatGPT 界面输入文本回答～",
            body=body, name=name, **conditional,
        )
        return self._with_input_hint(text)

    def _with_input_hint(self, text: str) -> str:
        """台词缺「回 ChatGPT 输入」引导时补上，避免自定义/预设文案丢掉操作指引。"""
        if "ChatGPT 界面输入" in str(text):
            return text
        return f"{text}（请到 ChatGPT 界面输入文本回答）"

    def _interaction_key(self, agent_key: str, kind: str, rpc_id) -> str:
        """生成稳定交互 id：有 rpcId 用 rpcId（同一审批/问题的稳定标识），
        无 rpcId（旧路径降级提示）用 agent+kind+本地序号保证唯一。"""
        if rpc_id:
            return f"{kind}:{rpc_id}"
        self._interaction_seq += 1
        return f"{kind}:{agent_key}:hint{self._interaction_seq}"

    def _register_interaction(self, agent_key: str, *, kind: str, text: str, **extra) -> str | None:
        """按来源、会话和请求身份登记只读提醒。"""
        rpc_id = extra.get("rpc_id")
        iid = self._interaction_key(agent_key, kind, rpc_id)
        # Isolate malformed or
        # concurrent transports that reuse it across sessions.
        if iid in self._pending_interactions and rpc_id:
            iid = f"{iid}:{str(extra.get('session_id') or '')}"
        alert_id = f"interaction:{iid}"
        self._pending_interactions[iid] = {
            "kind": kind, "text": text, "alert_id": alert_id,
            "agent_key": agent_key, **extra,
        }
        # 交互打断算"需要主人看一眼"：任务完成后不误说"干完活啦"
        self._saw_alert.add(agent_key)
        # 常驻气泡：不自动消失，等 resolved / 离线 / 空闲再收尾
        self._show_interaction_bubble(iid)
        return iid

    def _on_approval_resolved(self, agent_key: str, payload: dict | None = None) -> None:
        """按稳定请求身份关闭提醒；不发送审批决策。"""
        payload = payload if isinstance(payload, dict) else {}
        call_id = payload.get("callId")
        if call_id:
            call_id = str(call_id)
            for iid, item in self._pending_interactions.items():
                if (item.get("kind") == "approval"
                        and str(item.get("call_id") or "") == call_id):
                    self._resolve_interaction(iid)
                    return
            return  # 带 callId 但未匹配：陈旧已解决帧，不动其他审批
        rpc_id = payload.get("rpcId")
        approval_id = payload.get("approvalId")
        if rpc_id:
            for iid, item in self._pending_interactions.items():
                if item.get("kind") == "approval" and item.get("rpc_id") == rpc_id:
                    self._resolve_interaction(iid)
                    return
            return  # 带 id 但未匹配：陈旧已解决帧，不动其他审批
        if approval_id:
            for iid, item in self._pending_interactions.items():
                if item.get("kind") == "approval" and item.get("approval_id") == approval_id:
                    self._resolve_interaction(iid)
                    return
            return  # 同上：带 approvalId 未匹配即陈旧帧，不兜底
        # 无 id 的旧路径 approval/decided：只对「无 rpc_id 的纯提示」兜底关闭。
        # 交互审批（带 rpc_id）由 mux approval/resolved 帧精确关闭——若这里
        # 对交互审批兜底，用户点了 A 后 ChatGPT 回发的 A 的 decided（无 id）会把
        # 还在等待的 B 误关（表现为第二个弹窗延迟 0.5~1s 后自动消失）。
        candidates = [iid for iid, item in self._pending_interactions.items()
                      if item.get("kind") == "approval" and item.get("agent_key") == agent_key
                      and not item.get("rpc_id")]
        if len(candidates) == 1:
            self._resolve_interaction(candidates[0])

    def _on_question_resolved(self, agent_key: str, payload: dict | None = None) -> None:
        """问题结束（question/resolved）：按 rpcId/callId 精确关闭对应交互记录。

        与审批同理：带 id 的 resolved 帧只关闭自己那一条；带 id 但未匹配的
        帧是陈旧已解决帧，绝不回退关闭其他 pending 问题；兜底（无 id 的旧
        路径）仅对无 rpc_id 的纯提示问题生效，交互问题由 mux 帧精确关闭。"""
        payload = payload if isinstance(payload, dict) else {}
        call_id = payload.get("callId")
        if call_id:
            call_id = str(call_id)
            session_id = str(payload.get("sessionId") or "")
            for iid, item in self._pending_interactions.items():
                if (item.get("kind") == "question"
                        and str(item.get("call_id") or "") == call_id
                        and (not session_id or str(item.get("session_id") or "") == session_id)):
                    self._resolve_interaction(iid)
                    return
            return  # 带 callId 但未匹配：陈旧已解决帧，不动其他问题
        rpc_id = payload.get("rpcId")
        if rpc_id:
            session_id = str(payload.get("sessionId") or "")
            for iid, item in self._pending_interactions.items():
                if (item.get("kind") == "question" and str(item.get("rpc_id") or "") == str(rpc_id)
                        and (not session_id or str(item.get("session_id") or "") == session_id)):
                    self._resolve_interaction(iid)
                    return
            return  # 带 id 但未匹配：陈旧已解决帧，不动其他问题
        candidates = [iid for iid, item in self._pending_interactions.items()
                      if item.get("kind") == "question" and item.get("agent_key") == agent_key
                      and not item.get("rpc_id")]
        if len(candidates) == 1:
            self._resolve_interaction(candidates[0])

    def _resolve_interaction(self, interaction_id: str) -> None:
        """阻塞型交互结束：按 interaction_id 精确清掉该条记录，并让提醒队列自然推进。

        注意：队列（window.show_alert）自己会逐条展示，这里用 resolve_alert
        按 alert_id 精确定位关闭，避免 hide_bubble 误关其他 agent/其他并发审批
        的提醒。"""
        item = self._pending_interactions.pop(interaction_id, None)
        if item is None:
            return
        alert_id = item.get("alert_id", "")
        if alert_id and hasattr(self.win, "resolve_alert"):
            self.win.resolve_alert(alert_id)
        elif hasattr(self.win, "hide_bubble"):
            self.win.hide_bubble()

    def pending_interactions_for(self, agent_key: str) -> dict[str, dict]:
        """返回该 agent 的全部 pending 交互（interaction_id → item）。

        同一 agent 可同时存在多条阻塞交互（多个并发审批/问题），以稳定
        interaction_id 索引；本方法供上层/测试按 agent 检索。"""
        return {iid: item for iid, item in self._pending_interactions.items()
                if item.get("agent_key") == agent_key}

    def dismiss_all_interactions(self) -> None:
        """清空全部待处理阻塞交互并关闭气泡（ChatGPT 离线/重启时交互必然失效）。"""
        self._clear_model_access_alerts()
        if not self._pending_interactions and not getattr(self.win, "_sticky_bubble_active", False):
            return
        self._pending_interactions.clear()
        if hasattr(self.win, "clear_alerts"):
            self.win.clear_alerts()
        elif hasattr(self.win, "hide_bubble"):
            self.win.hide_bubble()

    def dismiss_all_approvals(self) -> None:
        """兼容别名：等价 dismiss_all_interactions。"""
        self.dismiss_all_interactions()

    def _show_interaction_bubble(self, interaction_id: str) -> None:
        """把某条 pending 阻塞交互以 sticky 气泡挂上（可交互时内嵌按钮）。

        走提醒消息队列（show_alert）：审批/问题入队后一次只展示一个，
        队列非空时其他弹窗不覆盖；resolved 时经 resolve_alert 弹下一条。
        以 interaction_id 精确定位，保证并发审批各自的气泡互不干扰。"""
        pending = self._pending_interactions.get(interaction_id)
        if not pending:
            return
        if not hasattr(self.win, "show_alert"):
            if hasattr(self.win, "show_bubble"):
                # 旧桩/无 show_alert 的窗口：退化为普通气泡，绝不因签名差异崩溃
                try:
                    buttons = None
                    if buttons:
                        self.win.show_bubble(pending["text"], sticky=True, buttons=buttons)
                    else:
                        self.win.show_bubble(pending["text"], sticky=True)
                except TypeError:
                    self.win.show_bubble(pending["text"])
            return
        buttons = None
        self._show_alert_compat(
            pending["text"], subtitle="", buttons=buttons or None, sticky=True,
            alert_id=pending.get("alert_id", ""), priority=0, alert_type=pending.get("kind", "approval"),
        )

    def _show_alert_compat(self, text: str, **kwargs) -> None:
        """Use enriched alert metadata while remaining compatible with test/old windows."""
        try:
            self.win.show_alert(text, **kwargs)
        except TypeError:
            legacy = dict(kwargs)
            for key in ("priority", "alert_type", "metadata"):
                legacy.pop(key, None)
            self.win.show_alert(text, **legacy)



    @staticmethod
    def _questions_all_have_options(questions: list) -> bool:
        """整批问题是否全部带可点选选项（是否可完全在气泡内回答完）。"""
        if not questions:
            return False
        return all(
            isinstance(q, dict) and bool(q.get("options"))
            for q in questions
        )


    def _show_approval_bubble(self, agent_key: str) -> None:
        """兼容别名：把该 agent 的全部 pending 审批/问题气泡挂上（等价
        _show_interaction_bubble，按 agent 遍历其所有交互）。"""
        for iid in list(self._pending_interactions):
            if self._pending_interactions[iid].get("agent_key") == agent_key:
                self._show_interaction_bubble(iid)

    def _schedule_done_check(self, agent_key: str) -> None:
        self._cancel_done_check(agent_key)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(self._DONE_CONFIRM_MS)
        timer.timeout.connect(lambda k=agent_key: self._fire_done(k))
        self._done_pending[agent_key] = timer
        timer.start()

    def _cancel_done_check(self, agent_key: str) -> None:
        timer = self._done_pending.pop(agent_key, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def _fire_done(self, agent_key: str) -> None:
        """800ms 稳定确认到期：期间回忙则不算完成；配置/冷却在弹出前再查。"""
        self._done_pending.pop(agent_key, None)
        # 隐藏中：不切动画不出声，气泡改道灵动岛反馈面（岛反馈面可用时；
        # pause_agent_link_for_hide 让监视器隐藏期保持运行，本兜底必须感知，
        # 否则 done 气泡在隐藏期被静默吞掉）。
        hidden = not hasattr(self.win, "isVisible") or not self.win.isVisible()
        if self._last_raw.get(agent_key) in self._BUSY_STATES:
            return
        agent_cfg = self.cfg.get("agent_link", {})
        if not self._report_allowed(agent_cfg, "done.success"):
            # 报告被禁用时不展示完成气泡。
            return
        now = self._clock()
        if now - self._done_cooldown.get(agent_key, 0.0) < self._DONE_COOLDOWN_S:
            return
        self._done_cooldown[agent_key] = now
        name = self.agent_names.get(agent_key, agent_key)
        if agent_key in self._saw_alert:
            # busy 期间出现过 attention/error：不暗示"成功完成"
            text = self._dialogue("done.attention", f"{name} 那边停了，结果怎么样要主人自己看一眼哦", agent_key=agent_key, name=name)
        else:
            text = self._dialogue("done.success", f"{name} 干完活啦，去看看成果吧～", agent_key=agent_key, name=name)
        self._saw_alert.discard(agent_key)
        if hidden:
            # 隐藏中：不切待机动画；气泡改道灵动岛反馈面（_show_link_bubble
            # 内置改道；岛反馈面不可用时丢弃）。
            from . import window_alerts as _window_alerts

            _window_alerts.redirect_hidden_bubble(self.win, text, duration_ms=4500)
            return
        # 仅当没有其他 Agent 仍在忙时恢复（避免 A 完成顶掉 B 的工作动画）。
        # 必须走 request_link_idle（它会清 _link_anim_current 并尊重一次性动作），
        # 不能裸 _switch——否则残留的 link 状态会把以后的普通同名动作劫持进联动链。
        if not any(k != agent_key and s in self._BUSY_STATES
                   for k, s in self._last_raw.items()):
            if hasattr(self.win, "request_link_idle"):
                self.win.request_link_idle()
            elif hasattr(self.win, "switch_clip") and getattr(self.win, "idles", None):
                self.win.switch_clip(self.win.idles[0])
            self._last_applied[agent_key] = ("idle", now)
        self._show_link_bubble(text, important=True)



    def _show_link_bubble(self, text: str, *, important: bool, duration_ms: int = 4500,
                          _retried: int = 0) -> None:
        """联动气泡：提醒消息队列非空时一律让路（审批/问题/失败/卡住优先）。

        无提醒队列时：普通气泡直接让路丢弃；重要气泡每 2.5s 重试至多 4 次
        （约 10s 窗口），仍被占才放弃——主动识屏长答复可能占位 15-20s。"""
        if not hasattr(self.win, "show_bubble"):
            return
        # 桌宠隐藏时 show_bubble/show_alert 会静默丢弃：改道灵动岛反馈面
        # （AppShell 经 hidden_bubble_redirect 注入；无注入/岛不可用维持丢弃）。
        # 审批/问题等交互气泡不经本函数，仍需桌宠可见。
        is_visible = getattr(self.win, "isVisible", None)
        if callable(is_visible) and not is_visible():
            from . import window_alerts as _window_alerts

            if _window_alerts.redirect_hidden_bubble(self.win, text, duration_ms=duration_ms):
                return
        # 提醒消息队列激活：任何其他弹窗（含重要气泡）都不覆盖提醒
        if getattr(self.win, "_alert_current", None) is not None or \
                getattr(self.win, "_alert_queue", None):
            return
        if not important and getattr(self.win, "_sticky_bubble_active", False):
            # 兼容旧路径：审批等一直挂着的气泡优先
            return
        busy_until = getattr(self.win, "_bubble_busy_until", 0.0)
        # window.hold_bubble 以 time.monotonic() 写入 _bubble_busy_until，这里必须
        # 用同一时钟域比较——曾误用 time.time()（epoch 秒），在真实桌宠上恒判
        # "未被占用"，让位/重试门禁失效（普通气泡顶掉识屏占位、重要气泡不排队
        # 重试直接覆盖）。同步修正于 PR57 合并后审计（F1）。
        if time.monotonic() < busy_until:
            if not important or _retried >= 4:
                return
            QTimer.singleShot(2500, self,
                              lambda t=text, n=_retried: self._show_link_bubble(
                                  t, important=True, _retried=n + 1))
            return
        self.win.show_bubble(text, duration_ms=duration_ms)

    # ------------------------------------------------------------------
    # 卡住检测（stuck_detector）反应：建议介入动画 + 持续提醒气泡
    # ------------------------------------------------------------------
    _STUCK_WORRIED_KEYWORDS = ("焦急", "着急", "气急败坏", "抓狂", "拍打", "敲桌", "烦恼", "抓狂")
    _STUCK_REMINDER_MS = 20000   # 建议介入提醒持续 20s（非 sticky，避免与审批/问题常驻气泡冲突）
    # N2：跨检测器弹窗节流窗口——同 agent/session 30s 内任一检测器弹过窗，
    # 其余检测器本次只播动画不弹窗（避免 stuck/pattern/watchdog 连环换弹）。
    _DETECTOR_ALERT_COOLDOWN_S = 30.0

    def _detector_alert_gate(self, scope_key: str, *, level: int = 1) -> bool:
        """跨检测器弹窗节流：返回 True 表示本次允许弹窗（并记录触发时刻/档位）。

        - 同 scope 窗口内已弹过同档或更高档提醒：本次抑制（避免连环换弹）；
        - 真正更高档（level 更大）的升级放行并刷新记录，让"情况恶化"的更强提醒
          能覆盖低档提醒；
        - scope 由调用方给出（stuck / pattern / watchdog 都用 agent 键，故同一
          Agent 的各检测器共用一个槽位）；不同 scope 互不影响；
        - 本 gate 只做「记账」判定，调用方必须先过事件汇报概率门：被概率门抽稀
          丢弃的提醒没有展示，不得占用 30s 节流槽；
        - 设置窗口打开期间 show_alert 会直接丢弃普通提醒（N2-a）：此时不记账也
          不放行，避免被丢掉的提醒白占节流槽。
        """
        if getattr(self.win, "_bubble_suppressed", False):
            return False
        now = self._clock()
        last = self._detector_alert_at.get(scope_key)
        if last is not None:
            last_at, last_level = last
            if now - last_at < self._DETECTOR_ALERT_COOLDOWN_S and level <= last_level:
                return False
        self._detector_alert_at[scope_key] = (now, level)
        return True

    def _pick_stuck_anim(self) -> str | None:
        """从当前角色动作池里按语义挑选「焦急」动画；缺素材静默跳过。"""
        acts = list(getattr(self.win, "cats", {}).get("acts", []) or [])
        for kw in self._STUCK_WORRIED_KEYWORDS:
            for a in acts:
                if kw in a:
                    return a
        return None

    def _on_stuck_intervention(self, agent_key: str, payload: dict) -> None:
        """卡住评分达到阈值：档位 1 播焦急动画；档位 2 再弹一次持续提醒气泡。"""
        if not hasattr(self.win, "isVisible") or not self.win.isVisible():
            return
        payload = payload if isinstance(payload, dict) else {}
        severity = int(payload.get("severity", 0) or 0)
        anim = self._pick_stuck_anim()
        if anim and hasattr(self.win, "request_link_anim"):
            self.win.request_link_anim(anim)
        if severity < 2:
            return  # 档位 1：只播动画，不弹气泡
        # 档位 2：持续提醒（可自定义文案；{name} 占位 = Agent 显示名）
        from .stuck_detector import stuck_reminder_text
        name = self.agent_names.get(agent_key, agent_key)
        agent_cfg = self.cfg.get("agent_link", {})
        custom = str((agent_cfg.get("stuck_reminder_text") or "") if isinstance(agent_cfg, dict) else "")
        text = stuck_reminder_text(name, custom)
        # 事件汇报概率门（检测类）：档位 1 的动画不受影响，只有气泡受门控制。
        # 概率门判定必须在 N2 节流记账之前：被抽稀丢弃的提醒并没有展示，不该
        # 占用 30s 节流槽，否则同 scope 的下一条提醒会被误压（F14）。
        if not self._report_allowed(agent_cfg, "stuck.reminder"):
            return
        # N2 跨检测器节流：档位 2 属控制级（level=2），比普通 watchdog 提醒高、
        # 可覆盖低档；但同 scope 已弹过同档提醒（pattern control / 上一次档位 2）
        # 时由 gate 抑制，避免连环换弹。
        if not self._detector_alert_gate(agent_key, level=2):
            return
        if hasattr(self.win, "show_alert"):
            self.win.show_alert(self._dialogue("stuck.reminder", text, name=name), duration_ms=self._STUCK_REMINDER_MS, sticky=False)
        elif hasattr(self.win, "show_bubble"):
            self.win.show_bubble(text, duration_ms=self._STUCK_REMINDER_MS)

    def _on_stuck_resolved(self, agent_key: str) -> None:
        """卡住解除（Agent 空闲 / 离线 / 任务完成）：回正常动画链。"""
        if not hasattr(self.win, "isVisible") or not self.win.isVisible():
            return
        if any(s in self._BUSY_STATES for k, s in self._last_raw.items() if k != agent_key):
            return  # 其他 Agent 仍在忙，不打断其工作动画
        if hasattr(self.win, "request_link_idle"):
            self.win.request_link_idle()

    # ------------------------------------------------------------------
    # 行为模式检测（behavior_detector）：双窗口行为模式预警/控制
    # ------------------------------------------------------------------
    _PATTERN_REMINDER_MS = 15000  # 行为模式提醒持续 15s（非 sticky）

    def _on_pattern_warning(self, agent_key: str, payload: dict) -> None:
        """行为模式预警（⚠️）：播焦急动画，不弹气泡。"""
        if not hasattr(self.win, "isVisible") or not self.win.isVisible():
            return
        anim = self._pick_stuck_anim()
        if anim and hasattr(self.win, "request_link_anim"):
            self.win.request_link_anim(anim)

    def _on_pattern_control(self, agent_key: str, payload: dict) -> None:
        """行为模式控制（🛑）：播焦急动画 + 弹气泡。
        payload 的 verdict 恒为 REPLAN（可选 Judge 机制已移除），只提醒、不打断 Agent。"""
        if not hasattr(self.win, "isVisible") or not self.win.isVisible():
            return
        payload = payload if isinstance(payload, dict) else {}
        anim = self._pick_stuck_anim()
        if anim and hasattr(self.win, "request_link_anim"):
            self.win.request_link_anim(anim)
        # 构建提醒文案
        verdict = str(payload.get("verdict", "") or "")
        reason = str(payload.get("reason", "") or "")
        fine_cls = str(payload.get("class", "") or "")
        count = payload.get("count", 0)
        window = str(payload.get("window", "") or "")
        name = self.agent_names.get(agent_key, agent_key)
        if verdict in ("STOP", "ASK_USER"):
            text = (
                f"{name} 行为模式异常（{reason}），"
                f"Judge 建议{'停止' if verdict == 'STOP' else '询问你'}。"
                f"最近 {window} 内 {fine_cls} 出现 {count} 次，可能已陷入低效循环。"
                f"建议人工检查。"
            )
        elif verdict == "REPLAN":
            text = (
                f"{name} 可能陷入低效循环：最近 {window} 内 {fine_cls} 出现 {count} 次，"
                f"建议重新规划任务方向。"
            )
        else:
            text = (
                f"{name} 行为模式需要留意：最近 {window} 内 {fine_cls} 出现 {count} 次。"
            )
        key = "pattern.control" if verdict in ("STOP", "ASK_USER", "REPLAN") else "pattern.warning"
        text = self._dialogue(key, text, name=name, reasons=reason)
        agent_cfg = self.cfg.get("agent_link", {})
        # 事件汇报概率门（检测类）：动画照旧，只有气泡受门控制。判定先于 N2
        # 节流记账——被抽稀丢弃的提醒没有展示，不该占 30s 节流槽（F14）。
        if not self._report_allowed(agent_cfg, key):
            return
        # N2 跨检测器节流：pattern control 属控制级（level=2），可覆盖普通
        # watchdog 提醒；同档重复则被 gate 抑制。
        if not self._detector_alert_gate(agent_key, level=2):
            return
        if hasattr(self.win, "show_alert"):
            self.win.show_alert(text, duration_ms=self._PATTERN_REMINDER_MS, sticky=False)
        elif hasattr(self.win, "show_bubble"):
            self.win.show_bubble(text, duration_ms=self._PATTERN_REMINDER_MS)

    # ------------------------------------------------------------------
    # Agent Exploration Loop Watchdog
    # ------------------------------------------------------------------
    _EXPLORATION_REMINDER_MS = 18000
    # 控制级提醒常驻（sticky，duration 对 sticky 无效）：用户必须点按钮才结束。
    _EXPLORATION_CONTROL_PRIORITY = 2
    # 旧控制器.request 最长阻塞 30s；只能在后台线程调用。

    @staticmethod
    def _exploration_control_alert_id(session_key: str) -> str:
        return f"exploration-control:{session_key}"


    def _on_exploration_warning(self, session_key: str, payload: dict) -> None:
        if not hasattr(self.win, "isVisible") or not self.win.isVisible():
            return
        payload = payload if isinstance(payload, dict) else {}
        is_control = str(payload.get("level") or "warning").strip().lower() == "control"
        agent_cfg = self.cfg.get("agent_link", {})
        # 事件汇报概率门（检测类）：循环检测 warning 按门抽稀；control 级是常驻
        # 可操作气泡，不经过概率门。判定先于 N2 节流记账——被抽稀丢弃的提醒
        # 没有展示，不该占 30s 节流槽（F14）。
        if not is_control and not self._report_allowed(agent_cfg, "watchdog.warning"):
            return
        # N2 跨检测器节流：warning 是非升级普通提醒（level=1）；control 属控制级
        # （level=2），可覆盖 30s 窗口内的普通提醒，同档重复仍被抑制（防连环换弹）。
        # scope 是 agent 键：stuck/pattern 用同一把键，故同一 Agent 的各检测器
        # 共用一个槽位；payload 缺 agent_key 时按 session 兜底隔离。
        scope_key = str(payload.get("agent_key") or "") or f"session:{session_key}"
        if not self._detector_alert_gate(scope_key, level=2 if is_control else 1):
            return
        reasons = self._format_exploration_reasons(payload.get("reasons", []), payload.get("steps", []))
        name = self._exploration_name(payload, session_key)
        if is_control:
            self._show_exploration_control(session_key, payload, name, reasons)
            return
        text = self._dialogue(
            "watchdog.warning", f"{name} 近期存在重复探索行为：{reasons}，暂不打断运行。",
            name=name, reasons=reasons,
        )
        if hasattr(self.win, "show_alert"):
            self._show_alert_compat(text, duration_ms=self._EXPLORATION_REMINDER_MS,
                                sticky=False, alert_id=f"exploration-warning:{session_key}",
                                priority=2, alert_type="watchdog-warning",
                                metadata={"sessionId": session_key, "riskScore": payload.get("risk", 0),
                                          "riskReasons": payload.get("reasons", []),
                                          "targetCount": payload.get("targetCount", 0),
                                          "targets": payload.get("targets", [])})
        elif hasattr(self.win, "show_bubble"):
            self.win.show_bubble(text, duration_ms=self._EXPLORATION_REMINDER_MS)

    def _show_exploration_control(self, session_key: str, payload: dict, name: str, reasons: str) -> None:
        """持续提醒，用户可打开应用检查或忽略提醒。"""
        text = self._dialogue(
            "watchdog.control",
            f"{name} 疑似陷入无效探索循环：{reasons}。请到所属应用检查任务方向。",
            name=name, reasons=reasons,
        )
        alert_id = self._exploration_control_alert_id(session_key)
        # 记进 lifecycle 表：会话结束时连同控制气泡一起收起，避免留下死按钮。
        self._exploration_alerts[session_key] = alert_id
        buttons = self._exploration_control_buttons(session_key, payload, alert_id)
        metadata = {"sessionId": session_key, "riskScore": payload.get("risk", 0),
                    "riskReasons": payload.get("reasons", []),
                    "targetCount": payload.get("targetCount", 0),
                    "targets": payload.get("targets", []),
                    "goal": payload.get("goal", "")}
        if hasattr(self.win, "show_alert"):
            self._show_alert_compat(text, duration_ms=0, sticky=True, buttons=buttons,
                                    alert_id=alert_id, priority=self._EXPLORATION_CONTROL_PRIORITY,
                                    alert_type="control", metadata=metadata)
            return
        if hasattr(self.win, "show_bubble"):
            try:
                self.win.show_bubble(text, sticky=True, buttons=buttons)
            except TypeError:
                # 旧桩/旧窗口不支持按钮：退化为限时提醒，绝不因签名差异崩溃。
                self.win.show_bubble(text, duration_ms=self._EXPLORATION_REMINDER_MS)

    def _exploration_control_buttons(self, session_key: str, payload: dict,
                                    alert_id: str) -> list[tuple[str, object]]:
        buttons = [("忽略", lambda: self._dismiss_exploration_control(alert_id))]
        return buttons


    def _dismiss_exploration_control(self, alert_id: str) -> None:
        if hasattr(self.win, "resolve_alert"):
            self.win.resolve_alert(alert_id)
        elif hasattr(self.win, "hide_bubble"):
            self.win.hide_bubble()


    def _on_exploration_lifecycle(self, agent_key: str, record: dict) -> None:
        """Invalidate watchdog UI work when the real session ends."""
        if not isinstance(record, dict):
            return
        session = str(record.get("sessionId") or record.get("session_id") or agent_key)
        event = str(record.get("event") or "")
        ended = (event in {"turn/start", "turn/end", "task_complete", "execution/failed"} or
                 (event == "AgentStatus" and record.get("state") in {"idle", "sleeping"}))
        if ended:
            sessions = {session}
            # AgentStatus has no sessionId and represents the aggregate ChatGPT
            # agent. In that case invalidate every session owned by this agent.
            if event == "AgentStatus" and session == agent_key:
                sessions.update(self._exploration_alerts)
            for key in sessions:
                self._dismiss_exploration(key)

    # 阻塞交互兜底清理（approval / question 共用）。
    # 审批/问题等待期间 Agent 不会走到 turn/end（ChatGPT 仍处于 running）；
    # 一旦出现 turn/end、task_complete、execution/failed、thread_rolled_back
    # 或 AgentStatus idle/sleeping，说明会话已结束/回合已结束/Agent 已停止，
    # 任何仍 pending 的阻塞交互必然失效（ChatGPT 漏发 resolved 的异常场景），
    # 据此精确清掉对应会话（无 sessionId 时清该 agent 全部）的交互弹窗，
    # 防止真实异常也留下永久弹窗。带 rpcId/approvalId 的真实审批由
    # approval/resolved 正常关闭，不受影响。
    _INTERACTION_END_EVENTS = {
        "turn/end", "task_complete", "turn_aborted", "execution/failed", "thread_rolled_back",
    }

    def _on_interaction_lifecycle(self, agent_key: str, record: dict) -> None:
        """会话/turn 结束或 Agent 停止时，清掉对应会话/agent 的 pending 阻塞交互。"""
        if not isinstance(record, dict):
            return
        event = str(record.get("event") or "")
        if event == "turn_aborted":
            self._saw_alert.add(agent_key)
        session = str(record.get("sessionId") or record.get("session_id") or "")
        ended = (event in self._INTERACTION_END_EVENTS or
                 (event == "AgentStatus" and str(record.get("state") or "") in {"idle", "sleeping"}))
        if not ended:
            return
        for iid in [i for i, v in self._pending_interactions.items()
                    if v.get("agent_key") == agent_key
                    and (not session or not v.get("session_id") or v.get("session_id") == session)]:
            self._resolve_interaction(iid)

    def _dismiss_exploration(self, session_key: str) -> None:
        alert_id = self._exploration_alerts.pop(session_key, "")
        if alert_id and hasattr(self.win, "resolve_alert"):
            self.win.resolve_alert(alert_id)

    # ------------------------------------------------------------------
    # 会话元数据缓存与显示名称解析
    # ------------------------------------------------------------------
    def _on_session_meta(self, agent_key: str, record: dict) -> None:
        """接收 bridge 发来的 session/meta 事件，写入元数据缓存。"""
        if not isinstance(record, dict):
            return
        session_id = str(record.get("sessionId") or "")
        if not session_id:
            return
        self._session_meta_cache[session_id] = {
            "sessionName": str(record.get("sessionName") or ""),
            "projectName": str(record.get("projectName") or ""),
            "agentName": str(record.get("agentName") or ""),
        }
        log.debug("session_meta cached: %s → %s", session_id[:12], self._session_meta_cache[session_id])

    # ------------------------------------------------------------------
    # 模型访问失败提醒
    # ------------------------------------------------------------------
    # alert_id 带 sessionId：多 session 并发模型访问失败时互不顶替。
    # show_alert 的 duration_ms 对 sticky 项无效，寿命由 _model_access_timer 自行管理。
    _MODEL_ACCESS_COOLDOWN_S = 8.0          # 同 session 8 秒内合并为一次
    _MODEL_ACCESS_DURATION_MS = 15000       # 基础展示 15 秒
    _MODEL_ACCESS_MAX_LIFETIME_MS = 30000   # 同一 session 从首次触发起最长保留 30 秒
    _MODEL_ACCESS_PRIORITY = 1              # 高于普通状态气泡和 Watchdog（3）；审批(0)可抢占

    @staticmethod
    def _model_access_alert_id(session_key: str) -> str:
        return f"model-access:{session_key}"

    def _on_model_access(self, agent_key: str, record: dict) -> None:
        """处理模型访问失败事件：合并同 session 短时间内连续报错，弹窗提醒。"""
        if not hasattr(self.win, "isVisible") or not self.win.isVisible():
            return
        if not isinstance(record, dict):
            return
        # 汇报概率门放在**记账之前**：被抽稀掉的一次不应写入 _model_access_cache，
        # 否则「关掉模型访问失败提醒」会连带压掉随后的通用失败横幅（缓存里的活跃
        # 提醒会触发抑制分支），用户看到的是一类静音把另一类也吞了。
        if not self._report_allowed(self.cfg.get("agent_link", {}), "model_access.one"):
            return
        session_id = str(record.get("sessionId") or "")
        if not session_id:
            self._model_access_anonymous_seq += 1
            session_key = f"{agent_key}:anonymous:{self._model_access_anonymous_seq}"
        else:
            session_key = session_id
        now = self._clock()
        cache = self._model_access_cache
        existing = cache.get(session_key)
        supplied_count = record.get("consecutiveRetryCount")
        if supplied_count is None and session_id:
            supplied_count = self._model_access_retry_counts.get((agent_key, session_id), 0)
        try:
            supplied_count = int(supplied_count) if supplied_count is not None else 0
        except (TypeError, ValueError):
            supplied_count = 0
        if existing and now - existing.get("_ts", 0) < self._MODEL_ACCESS_COOLDOWN_S:
            # Prefer the bridge's actual streak; legacy payloads increment locally.
            existing_count = int(existing.get("count", 1) or 1)
            existing["count"] = max(existing_count, supplied_count) if supplied_count else existing_count + 1
            existing["_ts"] = now
            existing["_dismissed"] = False
            self._remember_model_access_record_fields(existing, record)
            self._show_model_access_alert(session_key, existing["count"])
            return
        entry = {
            "count": max(1, supplied_count),
            "_ts": now,
            "_first_ts": now,
            "_dismissed": False,
        }
        self._remember_model_access_record_fields(entry, record)
        cache[session_key] = entry
        self._show_model_access_alert(session_key, entry["count"])

    def _remember_model_access_record_fields(self, entry: dict, record: dict) -> None:
        """把限流记录的条件字段缓存进条目，供弹窗模板条件注入（缺失自动隐藏）。"""
        record = record if isinstance(record, dict) else {}
        for field in ("errorCode", "errorMessage", "consecutiveRetryCount", "retry"):
            value = record.get(field)
            if value not in (None, ""):
                entry[field] = value

    def _show_model_access_alert(self, session_key: str, count: int) -> None:
        """展示模型访问失败提醒弹窗，高优先级，带「知道了」按钮，15 秒自动收起。"""
        fallback = (
            "ChatGPT 模型访问失败，本次请求未完成；请稍后重试。"
            if count <= 1 else
            f"ChatGPT 模型访问失败，已连续 {count} 次；请稍后重试。"
        )
        key = "model_access.many" if count > 1 else "model_access.one"
        entry = self._model_access_cache.get(session_key) or {}
        conditional: dict[str, Any] = {}
        for field in ("errorCode", "errorMessage", "consecutiveRetryCount", "retry"):
            value = entry.get(field)
            if value not in (None, ""):
                conditional[field] = value
        session_name = self._session_name_or_empty(session_key)
        if session_name and session_name.strip():
            conditional["sessionName"] = session_name.strip()
        text = self._dialogue(key, fallback, count=count, **conditional)
        # PhrasePicker's built-in persona text is intentionally allowed to use
        # different wording; only an unavailable/empty renderer falls back.
        if not str(text or '').strip():
            text = fallback
        buttons = [("知道了", lambda sk=session_key: self._dismiss_model_access_alert(sk))]
        if hasattr(self.win, "show_alert"):
            self.win.show_alert(
                text,
                duration_ms=0,             # sticky 项忽略 duration，寿命由 timer 管理
                sticky=True,
                buttons=buttons,
                alert_id=self._model_access_alert_id(session_key),
                priority=self._MODEL_ACCESS_PRIORITY,
                alert_type="model_access",
                metadata={"sessionId": session_key},
            )
        elif hasattr(self.win, "show_bubble"):
            self.win.show_bubble(text, duration_ms=self._MODEL_ACCESS_DURATION_MS)
        # 自动收起：默认 15s；如被合并刷新，则按「首次触发 + 30s」硬上限收敛。
        self._schedule_model_access_dismiss(session_key)

    def _schedule_model_access_dismiss(self, session_key: str) -> None:
        """排定模型访问失败提醒的自动收起时间。

        优先按最近一次触发 + 15s；但不超过该 session 首次触发 + 30s 硬上限，
        避免合并刷新把弹窗无限续命。无 QTimer 环境（测试桩）时跳过。"""
        if not hasattr(self.win, "_bubble_busy_until"):
            return  # 测试桩无 QTimer 环境：跳过自动收起，由 dismiss 兜底
        entry = self._model_access_cache.get(session_key)
        if not entry:
            return
        now = self._clock()
        cap_remaining = self._MODEL_ACCESS_MAX_LIFETIME_MS / 1000.0 - (now - entry.get("_first_ts", now))
        base_remaining = self._MODEL_ACCESS_DURATION_MS / 1000.0 - (now - entry.get("_ts", now))
        delay_s = max(0.2, min(base_remaining, cap_remaining))
        self._cancel_model_access_timer(session_key)
        # win 可能是非 QObject 的测试桩：parent 传 None，定时器由本管理器持有生命周期
        parent = self.win if isinstance(self.win, QObject) else None
        timer = QTimer(parent)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda sk=session_key: self._dismiss_model_access_alert(sk))
        self._model_access_timers[session_key] = timer
        timer.start(int(delay_s * 1000))

    def _cancel_model_access_timer(self, session_key: str) -> None:
        timer = self._model_access_timers.pop(session_key, None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
            timer.deleteLater()

    def _clear_model_access_alerts(self) -> None:
        """清理全部模型访问失败提醒、计数和定时器。"""
        session_keys = set(self._model_access_cache) | set(self._model_access_timers)
        self._model_access_cache.clear()
        # tracker 内部按 (source, sessionId) 留存的连续 streak 也要清：只清外部
        # 镜像的话，重新开启联动后同一会话的新失败会接着旧计数，提醒里出现
        # 「已连续 N 次」虚高。全量 clear 比按镜像键逐个 reset 更稳——镜像键
        # 未必覆盖 tracker 的全部键。
        self._model_access_tracker.clear()
        self._model_access_retry_counts.clear()
        for session_key in list(self._model_access_timers):
            self._cancel_model_access_timer(session_key)
        for session_key in session_keys:
            if hasattr(self.win, "resolve_alert"):
                self.win.resolve_alert(self._model_access_alert_id(session_key))

    def _dismiss_model_access_alert(self, session_key: str) -> None:
        """用户点击「知道了」或超时自动收起：清理缓存并关闭提醒。"""
        cache = self._model_access_cache
        entry = cache.pop(session_key, None)
        if entry:
            entry["_dismissed"] = True
        self._cancel_model_access_timer(session_key)
        alert_id = self._model_access_alert_id(session_key)
        if hasattr(self.win, "resolve_alert"):
            self.win.resolve_alert(alert_id)

    @staticmethod
    def _llm_error_alert_id(session_key: str) -> str:
        return f"llm-error:{session_key}"

    def _on_llm_error(self, agent_key: str, record: dict) -> None:
        """处理 LLM API 错误事件（llm_error，errorKind=api）：弹窗提醒。

        errorCode 是上游真实错误码（如 bad_response_status_code），不再替换成
        分类别名；errorKind 承载分类语义（api=AI 服务错误，非模型访问失败）。
        """
        if not hasattr(self.win, "isVisible") or not self.win.isVisible():
            return
        if not isinstance(record, dict):
            return
        session_key = str(record.get("sessionId") or agent_key)
        now = self._clock()
        cache = self._llm_error_cache
        # LLM API 错误不合并，每次错误都提醒（但用冷却时间防刷屏）
        existing = cache.get(session_key)
        if existing and now - existing.get("_ts", 0) < self._MODEL_ACCESS_COOLDOWN_S:
            return  # 冷却期内忽略
        cache[session_key] = {
            "_ts": now,
            "_dismissed": False,
        }
        error_message = str(record.get("errorMessage") or "AI 服务不可用")
        error_code = str(record.get("errorCode") or "UNKNOWN")
        error_kind = str(record.get("errorKind") or "api")
        fallback = f"AI 服务错误（{error_code}）：{error_message}"
        key = "llm_error.api"
        text = self._dialogue(key, fallback)
        buttons = [("知道了", lambda sk=session_key: self._dismiss_llm_error_alert(sk))]
        if hasattr(self.win, "show_alert"):
            self.win.show_alert(
                text,
                duration_ms=0,
                sticky=True,
                buttons=buttons,
                alert_id=self._llm_error_alert_id(session_key),
                priority=self._MODEL_ACCESS_PRIORITY,
                alert_type="llm_error",
                metadata={"sessionId": session_key, "errorCode": error_code, "errorKind": error_kind},
            )
        elif hasattr(self.win, "show_bubble"):
            self.win.show_bubble(text, duration_ms=self._MODEL_ACCESS_DURATION_MS)
        self._schedule_llm_error_dismiss(session_key)

    def _schedule_llm_error_dismiss(self, session_key: str) -> None:
        """排定 LLM 错误提醒的自动收起时间。"""
        if not hasattr(self.win, "_bubble_busy_until"):
            return
        entry = self._llm_error_cache.get(session_key)
        if not entry:
            return
        delay_s = self._MODEL_ACCESS_DURATION_MS / 1000.0
        self._cancel_llm_error_timer(session_key)
        parent = self.win if isinstance(self.win, QObject) else None
        timer = QTimer(parent)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda sk=session_key: self._dismiss_llm_error_alert(sk))
        self._llm_error_timers[session_key] = timer
        timer.start(int(delay_s * 1000))

    def _cancel_llm_error_timer(self, session_key: str) -> None:
        timer = self._llm_error_timers.pop(session_key, None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
            timer.deleteLater()

    def _dismiss_llm_error_alert(self, session_key: str) -> None:
        """用户点击「知道了」或超时自动收起：清理缓存并关闭提醒。"""
        cache = self._llm_error_cache
        entry = cache.pop(session_key, None)
        if entry:
            entry["_dismissed"] = True
        self._cancel_llm_error_timer(session_key)
        alert_id = self._llm_error_alert_id(session_key)
        if hasattr(self.win, "resolve_alert"):
            self.win.resolve_alert(alert_id)

    def _on_user_action(self, agent_key: str, record: dict) -> None:
        """用户介入信号（user_action 事件）：ChatGPT 审批决定/回答 → 关闭对应弹窗。

        action 类型：
        - approval_decided / approval_resolved：审批已决定
        - question_resolved：用户已回答问题
        """
        if not hasattr(self.win, "isVisible") or not self.win.isVisible():
            return
        if not isinstance(record, dict):
            return

        action = str(record.get("action") or "")
        session_key = str(record.get("sessionId") or agent_key)

        # 按 action 类型关闭对应交互弹窗
        if action == "approval_decided":
            approval_id = str(record.get("approvalId") or "")
            rpc_id = str(record.get("rpcId") or "")
            self._close_interaction_by_id("approval", rpc_id, approval_id, session_key)
        elif action == "approval_resolved":
            approval_id = str(record.get("approvalId") or "")
            rpc_id = str(record.get("rpcId") or "")
            self._close_interaction_by_id("approval", rpc_id, approval_id, session_key)
        elif action == "question_resolved":
            call_id = str(record.get("callId") or "")
            rpc_id = str(record.get("rpcId") or "")
            self._close_interaction_by_id("question", rpc_id, call_id, session_key)


    def _close_interaction_by_id(self, kind: str, rpc_id: str, id_: str, session_key: str) -> None:
        """按 kind + identity + session 精确关闭交互弹窗。"""
        for iid, item in self._pending_interactions.items():
            if item.get("kind") != kind:
                continue
            item_session = str(item.get("session_id") or "")
            if session_key and item_session and item_session != session_key:
                continue
            if rpc_id and (item.get("rpc_id") == rpc_id or item.get("request_id") == rpc_id):
                self._resolve_interaction(iid)
                return
            if id_ and (item.get("approval_id") == id_ or item.get("call_id") == id_):
                self._resolve_interaction(iid)
                return
        if kind not in ("approval", "question"):
            return
        for iid, item in self._pending_interactions.items():
            if item.get("kind") == kind and item.get("agent_key") == session_key and not item.get("rpc_id"):
                self._resolve_interaction(iid)
                return

    def get_session_display_name(self, session_id: str) -> str:
        """解析会话的人类可读展示名（「projectName · sessionName」组合串）。

        仅用于气泡前缀、探索气泡等**展示**场景；台词模板里的 ``{sessionName}``
        字段必须走 ``_session_name_or_empty()``（只取会话名），不要用本方法返回值
        注入，避免 {sessionName} 与 {projectName} 语义重复。

        降级链：cache 中的 projectName+sessionName → cache.agentName → 截短 sessionId → 完整 sessionId。
        控制请求（interrupt/replan）仍严格使用 sessionId，此处仅用于展示。
        """
        meta = self._session_meta_cache.get(session_id)
        if meta:
            project_name = str(meta.get("projectName") or "")
            session_name = str(meta.get("sessionName") or "")
            # 优先用 projectName + sessionName 组合（更精确）
            if project_name and session_name:
                return f"{project_name} · {session_name}"
            if session_name:
                return session_name
            agent_name = str(meta.get("agentName") or "")
            if agent_name:
                return agent_name
        # 降级：截短 sessionId，避免暴露完整内部标识
        short_id = session_id[:8] if len(session_id) > 8 else session_id
        return f"ChatGPT · {short_id}"

    def _session_name_or_empty(self, session_id: str) -> str:
        """台词注入用会话名：只取会话自己的名字（session/meta 的 sessionName）。

        ``get_session_display_name()`` 返回的「projectName · sessionName」组合串
        是给气泡前缀/探索气泡用的人类可读展示名；台词模板的 ``{sessionName}``
        字段语义 = 会话名自身，``{projectName}`` 是独立字段——绝不用组合串冒充
        会话名（否则两字段语义重复，用户在模板里无法单独引用）。无真实会话名时
        返回空串，由条件渲染（autohide）隐藏占位符，也不把 sessionId 截短占位冒充。
        """
        meta = self._session_meta_cache.get(session_id) or {}
        return str(meta.get("sessionName") or "").strip()

    def _exploration_name(self, payload: dict, session_key: str) -> str:
        """返回探索气泡中显示的会话名称，优先使用元数据缓存。"""
        # 优先从 payload 中已有的 agent_name 获取
        raw = str((payload or {}).get("agent_name") or
                  (payload or {}).get("agent_key") or "").strip()
        if raw and raw in self.AGENT_NAMES:
            name = self.AGENT_NAMES[raw]
            self._exploration_names[session_key] = name
            return name
        # 通过 sessionId 查找元数据缓存
        display = self.get_session_display_name(session_key)
        if display and display != f"ChatGPT · {session_key[:8]}":
            self._exploration_names[session_key] = display
            return display
        # 最终回退：agent 名称或默认 ChatGPT
        name = self.agent_names.get(raw.lower(), raw) or "ChatGPT"
        self._exploration_names[session_key] = name
        return name

    @staticmethod
    def _format_exploration_reasons(reasons, steps=None) -> str:
        labels = {
            "W6 同类重复": "最近 6 步反复使用同类探索工具",
            "W10 同类重复": "最近 10 步反复使用同类探索工具",
            "W6 target 重复": "最近 6 步反复访问同一目标",
            "W10 target 重复": "最近 10 步反复访问同一目标",
            "W6 fingerprint 重复": "最近 6 步出现相同工具调用",
            "W10 fingerprint 重复": "最近 10 步出现相同工具调用",
            "W6 探索密集且 target 单一": "最近 6 步探索集中在少数目标",
            "W10 探索密集且无行动": "最近 10 步没有 Edit、Run 或 Test",
        }
        values = [labels.get(str(item), str(item)) for item in (reasons or [])
                  if "diversity" not in str(item) and "有 Edit" not in str(item)
                  and "target 重复" not in str(item)]
        targets = []
        evidence = []
        for step in (steps or []):
            if not isinstance(step, dict):
                continue
            targets.extend(str(item) for item in (step.get("targets") or []) if item)
            for detail in (step.get("events") or []):
                if isinstance(detail, dict):
                    status = str(detail.get("evidenceStatus") or "")
                    if status:
                        evidence.append(status)
        # Targets are already normalized by the watchdog; display only the
        # basename to keep the pet popup readable and avoid exposing paths.
        import ntpath
        counts = Counter(ntpath.basename(item.replace("/", "\\")) for item in targets)
        if len(counts) == 2 and sum(counts.values()) >= 3:
            pair = "、".join(f"{name} {count} 次" for name, count in counts.most_common())
            values.insert(0, f"最近步骤在两个目标之间反复切换：{pair}")
        elif len(counts) == 1 and next(iter(counts.values())) >= 3:
            name, count = next(iter(counts.items()))
            values.insert(0, f"最近步骤重复访问同一目标：{name} {count} 次")
        if evidence and all(item == "same" for item in evidence):
            values.append("读取结果与之前相同，未发现新的可比较证据")
        elif evidence and "new" in evidence:
            values.append("近期至少获得过新的结果证据")
        return "；".join(dict.fromkeys(values[:3])) or "探索目标和调用方式重复"

    # ------------------------------------------------------------------
    # 硬失败（execution/failed）：ChatGPT 已决定本轮不再继续，直接提醒
    # ------------------------------------------------------------------
    _FAIL_ANIM_KEYWORDS = ("失败", "冒烟", "晕", "倒下", "昏", "扑街", "求救", "哭了", "委屈")
    _FAIL_REMINDER_MS = 6000

    def _pick_fail_anim(self) -> str | None:
        """从当前角色动作池里按语义挑选「失败/冒烟」动画；缺素材静默跳过。"""
        acts = list(getattr(self.win, "cats", {}).get("acts", []) or [])
        for kw in self._FAIL_ANIM_KEYWORDS:
            for a in acts:
                if kw in a:
                    return a
        return None

    def _on_execution_failed(self, agent_key: str, payload: dict) -> None:
        """硬失败直接提醒：不经行为分析，播失败动画 + 气泡告知本轮运行失败。

        payload 来自 bridge 的 execution/failed（脱敏）：只含 failureType /
        retryExhausted / retries / errorCode / errorMessage，不带 400 错误正文。
        failureType 取值（与活动/过程事件的 tool 字段解耦）：
          - model_retry_exhausted：模型请求链连续重试后仍失败
          - tool_failed：工具调用最终失败
        模型访问失败抑制只认真正的模型访问失败（errorCode 属限流类码或消息含限流关键字），
        重试耗尽失败不并入模型访问失败抑制——那是另一条语义（failure.retry），不重复提醒。
        """
        agent_cfg = self.cfg.get("agent_link", {})
        if not self._report_allowed(agent_cfg, "failure.generic"):
            return
        if not hasattr(self.win, "isVisible") or not self.win.isVisible():
            return
        payload = payload if isinstance(payload, dict) else {}
        name = self.agent_names.get(agent_key, agent_key)

        session_key = str(payload.get("sessionId") or agent_key)
        active_model_access = self._model_access_cache.get(session_key)

        error_code = str(payload.get("errorCode") or "").strip().upper()
        error_message = str(payload.get("errorMessage") or payload.get("errorText") or "").lower()

        MODEL_ACCESS_ERROR_CODES = {
            "429",
            "RATE_LIMIT",
            "TOO_MANY_REQUESTS",
            "RESOURCE_EXHAUSTED",
        }

        is_model_access_failure = (
                error_code in MODEL_ACCESS_ERROR_CODES
                or "429" in error_message
                or "rate limit" in error_message
        )

        if active_model_access and not active_model_access.get("_dismissed") and is_model_access_failure:
            return

        # 失败动画（若角色素材有）；没有就保持当前动作，仅弹气泡
        anim = self._pick_fail_anim()
        if anim and hasattr(self.win, "request_link_anim"):
            self.win.request_link_anim(anim)
        failure_type = str(payload.get("failureType") or "").strip()
        retry_exhausted = bool(payload.get("retryExhausted"))
        # execution/failed 记录条件字段（缺失不注入，渲染端自动隐藏占位符）
        conditional: dict[str, Any] = {}
        for field in ("failureType", "errorCode", "errorMessage", "retries", "retryExhausted"):
            value = payload.get(field)
            if value not in (None, ""):
                conditional[field] = value
        conditional.update(self._session_conditional(payload))
        if retry_exhausted or failure_type == "model_retry_exhausted":
            text = self._dialogue("failure.retry", f"{name} 本轮运行失败——模型请求多次重试后仍未成功，需要检查或重新运行", name=name, **conditional)
        elif failure_type == "tool_failed":
            text = self._dialogue("failure.tool", f"{name} 本轮运行失败——工具执行最终失败，需要检查或重新运行", name=name, **conditional)
        else:
            text = self._dialogue("failure.generic", f"{name} 本轮运行失败，需要检查或重新运行", name=name, **conditional)
        if hasattr(self.win, "show_alert"):
            self.win.show_alert(text, duration_ms=self._FAIL_REMINDER_MS, sticky=False)
        elif hasattr(self.win, "show_bubble"):
            self.win.show_bubble(text, duration_ms=self._FAIL_REMINDER_MS)
