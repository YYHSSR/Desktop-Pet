# -*- coding: utf-8 -*-
"""Cursor 桌面端转写联动监视器测试。"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from pet.agent_link import (
    AgentLinkManager,
    CursorMonitor,
    cursor_line_state,
    cursor_line_tool,
    cursor_transcript_session_id,
)
from pet.config import Config


def _ensure_app():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_cursor_line_state_and_tool():
    assert cursor_line_state({
        "role": "user",
        "message": {"content": [{"type": "text", "text": "hi"}]},
    }) == "thinking"
    assert cursor_line_state({
        "role": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Shell"}]},
    }) == "working"
    assert cursor_line_tool({
        "role": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Shell"}]},
    }) == "Shell"
    assert cursor_line_state({
        "role": "assistant",
        "message": {"content": [{"type": "text", "text": "done"}]},
    }) == "idle"
    assert cursor_line_state({"random": True}) == ""
    assert cursor_line_tool({"role": "user"}) == ""


def test_cursor_transcript_session_id_layouts(tmp_path: Path):
    nested = tmp_path / "projects" / "slug" / "agent-transcripts" / "sess-1" / "sess-1.jsonl"
    flat = tmp_path / "projects" / "slug" / "agent-transcripts" / "legacy.jsonl"
    sub = tmp_path / "projects" / "slug" / "agent-transcripts" / "sess-1" / "subagents" / "child.jsonl"
    assert cursor_transcript_session_id(nested) == "sess-1"
    assert cursor_transcript_session_id(flat) == "legacy"
    assert cursor_transcript_session_id(sub) == "child"


def test_cursor_nested_transcript_tail_keeps_prompt_out(tmp_path: Path):
    """现行嵌套转写能被尾读，统一事件里没有提示正文。"""
    _ensure_app()
    projects = tmp_path / "projects"
    session_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    folder = projects / "slug" / "agent-transcripts" / session_id
    folder.mkdir(parents=True)
    transcript = folder / f"{session_id}.jsonl"
    transcript.write_text("", encoding="utf-8")
    sub = folder / "subagents"
    sub.mkdir()
    (sub / "child.jsonl").write_text("", encoding="utf-8")

    mon = CursorMonitor(tmp_path, base_dir=projects)
    states = []
    events = []
    tools = []
    normalized = []
    mon.state_changed.connect(lambda key, state: states.append((key, state)))
    mon.state_event.connect(events.append)
    mon.activity.connect(lambda key, tool: tools.append((key, tool)))
    mon.normalized_event.connect(normalized.append)

    mon._poll(gen=mon._emit_gen)
    assert str(transcript) in mon._tailers
    assert all("subagents" not in key.replace("\\", "/") for key in mon._tailers)

    secret = "secret prompt must not leave the transcript"
    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "role": "user",
            "message": {"content": [{"type": "text", "text": secret}]},
        }) + "\n")
        handle.write(json.dumps({
            "role": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "Read"}]},
        }) + "\n")

    mon._poll(gen=mon._emit_gen)
    assert ("cursor", "thinking") in states
    assert ("cursor", "working") in states
    assert ("cursor", "Read") in tools
    assert [event.session_id for event in events] == [session_id, session_id]
    assert [event.turn_id for event in events] == ["1", "1"]
    blob = json.dumps([
        {"event": getattr(item, "event", ""), "data": getattr(item, "data", {})}
        for item in normalized
    ], ensure_ascii=False)
    assert secret not in blob
    assert "Read" in blob


def test_cursor_two_sessions_do_not_clear_each_other(tmp_path: Path):
    """一个 Cursor 会话结束时，另一个仍在干活的会话保持 working。"""
    _ensure_app()

    class DummyWin:
        def __init__(self):
            self.anims = []
            self.cats = {"acts": ["写代码", "吃Token"]}

        def isVisible(self):
            return True

        def mark_activity(self):
            return None

        def request_link_anim(self, name):
            self.anims.append(name)

        def request_link_idle(self):
            self.anims.append("idle")

        def show_bubble(self, text, duration_ms=3000, important=False):
            return None

    projects = tmp_path / "projects"

    def make(session_id: str) -> Path:
        folder = projects / "slug" / "agent-transcripts" / session_id
        folder.mkdir(parents=True)
        path = folder / f"{session_id}.jsonl"
        path.write_text("", encoding="utf-8")
        return path

    file_a = make("sess-a")
    file_b = make("sess-b")
    cfg = Config(base=tmp_path)
    win = DummyWin()
    mgr = AgentLinkManager(win, cfg, min_interval=0.0)
    mon = mgr.monitors["cursor"]
    mon.cursor_base = projects
    try:
        mon._poll(gen=mon._emit_gen)

        def append(path: Path, row: dict) -> None:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")

        user = {"role": "user", "message": {"content": [{"type": "text", "text": "go"}]}}
        tool = {"role": "assistant", "message": {"content": [{"type": "tool_use", "name": "Shell"}]}}
        done = {"role": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}}
        append(file_a, user)
        append(file_a, tool)
        append(file_b, user)
        append(file_b, tool)
        mon._poll(gen=mon._emit_gen)
        assert mgr._session_states[("cursor", "sess-a")] == "working"
        assert mgr._session_states[("cursor", "sess-b")] == "working"
        assert mgr._last_raw["cursor"] == "working"

        append(file_a, done)
        mon._poll(gen=mon._emit_gen)
        assert mgr._session_states[("cursor", "sess-a")] == "idle"
        assert mgr._session_states[("cursor", "sess-b")] == "working"
        assert mgr._last_raw["cursor"] == "working"
    finally:
        mgr.shutdown()
