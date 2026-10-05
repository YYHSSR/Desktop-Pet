"""ChatGPT Work/Codex rollout integration at the file and menu seams."""
import json

from PySide6.QtWidgets import QApplication

from pet.agent_link import CodexDesktopMonitor, codex_line_state


def append(path, *records):
    with path.open("a", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record) + "\n")


def event(kind, **fields):
    return {"type": "event_msg", "payload": {"type": kind, **fields}}


def test_historical_metadata_is_read_without_replaying_work(tmp_path):
    QApplication.instance() or QApplication([])
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    path = sessions / "rollout-a.jsonl"
    append(path, {"type": "session_meta", "payload": {"id": "session-a", "cwd": "E:/project"}}, event("task_started", turn_id="old"))
    monitor = CodexDesktopMonitor(tmp_path, codex_dir=sessions)
    received = []
    monitor.state_event.connect(received.append)
    monitor._poll()
    assert received == []
    append(path, event("task_started", turn_id="new"), {"type": "response_item", "payload": {"type": "reasoning"}}, event("task_complete"))
    monitor._poll()
    assert [(item.session_id, item.turn_id, item.state) for item in received] == [
        ("session-a", "new", "working"), ("session-a", "new", "thinking"), ("session-a", "new", "idle")]


def test_multiple_rollouts_have_independent_identity(tmp_path):
    QApplication.instance() or QApplication([])
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    for name in ("a", "b"):
        append(sessions / f"rollout-{name}.jsonl", {"type": "session_meta", "payload": {"id": name}})
    monitor = CodexDesktopMonitor(tmp_path, codex_dir=sessions)
    received = []
    monitor.state_event.connect(received.append)
    monitor._poll()
    for name in ("a", "b"):
        append(sessions / f"rollout-{name}.jsonl", event("task_started", turn_id=name))
    monitor._poll()
    assert {(item.session_id, item.turn_id) for item in received} == {("a", "a"), ("b", "b")}


def test_codex_home_is_honored(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "custom-home"))
    monitor = CodexDesktopMonitor(tmp_path)
    assert monitor.codex_base == tmp_path / "custom-home" / "sessions"


def test_approval_and_questions_are_attention_not_completion():
    assert codex_line_state(event("approval_requested")) == "attention"
    assert codex_line_state({"type": "response_item", "payload": {
        "type": "function_call", "name": "functions.request_user_input"}}) == "attention"
    assert codex_line_state(event("task_failed")) == "error"


def test_new_live_rollout_is_not_discarded_before_discovery(tmp_path):
    QApplication.instance() or QApplication([])
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monitor = CodexDesktopMonitor(tmp_path, codex_dir=sessions)
    received = []
    monitor.state_event.connect(received.append)
    monitor._poll()
    append(sessions / "rollout-new.jsonl", {"type": "session_meta", "payload": {"id": "new-session"}},
           event("task_started", turn_id="new-turn"))
    monitor._last_scan = 0
    monitor._poll()
    assert [(item.session_id, item.turn_id, item.state) for item in received] == [
        ("new-session", "new-turn", "working")]


def test_disabling_work_link_clears_busy_state(tmp_path):
    from pet.agent_link import AgentLinkManager
    from pet.config import Config
    QApplication.instance() or QApplication([])
    manager = AgentLinkManager(None, Config(base=tmp_path))
    try:
        manager._on_agent_state("codex", "working", session_id="s", turn_id="t")
        assert manager._last_raw["codex"] == "working"
        assert manager.set_enabled("codex", False)
        assert "codex" not in manager._last_raw
        assert not any(key[0] == "codex" for key in manager._session_states)
        assert manager._next_busy_anim() is None
    finally:
        manager.shutdown()


def test_large_tool_output_does_not_delay_recent_state_for_many_polls(tmp_path):
    QApplication.instance() or QApplication([])
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    path = sessions / "rollout-a.jsonl"
    append(path, {"type": "session_meta", "payload": {"id": "s"}})
    monitor = CodexDesktopMonitor(tmp_path, codex_dir=sessions)
    received = []
    monitor.state_event.connect(received.append)
    monitor._poll()
    append(path, {"type": "response_item", "payload": {
        "type": "function_call_output", "output": "x" * 400000}}, event("task_started", turn_id="t"))
    monitor._poll()
    assert [(item.state, item.turn_id) for item in received] == [("working", "t")]


def test_finished_session_history_is_bounded(tmp_path):
    from pet.agent_link import AgentLinkManager
    from pet.config import Config
    QApplication.instance() or QApplication([])
    manager = AgentLinkManager(None, Config(base=tmp_path))
    try:
        for index in range(300):
            manager._on_agent_state("codex", "idle", session_id=str(index), turn_id=str(index))
        assert len(manager._session_states) <= 256
        assert len(manager._session_turn_ids) <= 256
    finally:
        manager.shutdown()
