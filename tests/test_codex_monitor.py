# -*- coding: utf-8 -*-
"""Codex 桌面软件联动监视器测试。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from PySide6.QtCore import QCoreApplication

from pet.agent_link import (
    CodexDesktopMonitor,
    codex_line_state,
    codex_line_tool,
)


def _ensure_app():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_codex_line_state_mapping():
    """验证 codex rollout 各类 JSONL 行到桌宠状态的映射。"""
    # 任务开始
    assert codex_line_state({
        "type": "event_msg",
        "payload": {"type": "task_started", "turn_id": "t1"}
    }) == "working"

    # 任务完成
    assert codex_line_state({
        "type": "event_msg",
        "payload": {"type": "task_complete", "turn_id": "t1"}
    }) == "idle"

    # 任务中断
    assert codex_line_state({
        "type": "event_msg",
        "payload": {"type": "turn_aborted", "reason": "interrupted"}
    }) == "idle"

    # 思考中
    assert codex_line_state({
        "type": "response_item",
        "payload": {"type": "reasoning", "content": "thinking..."}
    }) == "thinking"

    # 工具调用
    assert codex_line_state({
        "type": "response_item",
        "payload": {"type": "custom_tool_call", "name": "exec_command"}
    }) == "working"

    # 函数调用输出
    assert codex_line_state({
        "type": "response_item",
        "payload": {"type": "function_call_output"}
    }) == "working"

    # 子项完成
    assert codex_line_state({
        "type": "event_msg",
        "payload": {"type": "item_completed", "item": {"type": "CommandExecution"}}
    }) == "working"

    # 显式 state 通道优先
    assert codex_line_state({"state": "sleeping"}) == "sleeping"

    # 无关统计/上下文记录忽略
    assert codex_line_state({"type": "token_usage_record"}) == ""
    assert codex_line_state({"type": "turn_context"}) == ""


def test_codex_line_tool_extraction():
    """验证从 codex 记录中提取工具名。"""
    assert codex_line_tool({
        "type": "response_item",
        "payload": {"type": "custom_tool_call", "name": "bash"}
    }) == "bash"

    assert codex_line_tool({
        "type": "response_item",
        "payload": {"type": "function_call", "name": "read_file"}
    }) == "read_file"

    assert codex_line_tool({
        "type": "event_msg",
        "payload": {"type": "item_completed", "item": {"type": "CommandExecution"}}
    }) == "CommandExecution"

    assert codex_line_tool({"type": "other"}) == ""


def test_codex_desktop_monitor_tail(tmp_path: Path):
    """验证 CodexDesktopMonitor 扫描并尾读 rollout jsonl 文件。"""
    _ensure_app()
    sessions_dir = tmp_path / "sessions"
    today_dir = sessions_dir / "2026" / "09" / "29"
    today_dir.mkdir(parents=True)

    rollout_file = today_dir / "rollout-test.jsonl"
    rollout_file.write_text("", encoding="utf-8")

    mon = CodexDesktopMonitor(tmp_path, codex_dir=sessions_dir)
    states = []
    tools = []
    mon.state_changed.connect(lambda k, s: states.append((k, s)))
    mon.activity.connect(lambda k, t: tools.append((k, t)))

    # 首次 poll：建立 tailer 并跳过空文件末尾
    mon._poll(gen=mon._emit_gen)

    # 追加写入 task_started
    with rollout_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": "2026-09-29T12:00:00Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "thread_id": "sess-01",
                "turn_id": "turn-01",
            }
        }) + "\n")
        f.flush()

    mon._poll(gen=mon._emit_gen)
    assert ("codex", "working") in states

    # 追加写入 tool_call
    with rollout_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": "2026-09-29T12:00:05Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec_command",
                "thread_id": "sess-01",
                "turn_id": "turn-01",
            }
        }) + "\n")
        f.flush()

    mon._poll(gen=mon._emit_gen)
    assert ("codex", "exec_command") in tools

    # 追加写入 task_complete
    with rollout_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": "2026-09-29T12:00:10Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "thread_id": "sess-01",
                "turn_id": "turn-01",
                "last_agent_message": "All done!",
            }
        }) + "\n")
        f.flush()

    mon._poll(gen=mon._emit_gen)
    assert ("codex", "idle") in states
