# -*- coding: utf-8 -*-
"""批5.2 spike：进程内双窗（feature flag 默认关）的机器可验测试。

覆盖批5.2 修复轮（DISPATCH_batch52_fix1）处置清单与验收：
- P0-1：spawn 偏移链（env DSH_PET_SPAWN_OFFSET_INDEX → 主窗 spawn_offset）接线；
- P0-2：flag 关右键退出不注入窗级「退出这只」（走 app.quit 逐位一致）；
- P1-1：每窗各持一个 CollisionIpcSession（runtime_id 不同、互不为 peer-self）；
- P1-2/P2-6：flag 取进程级快照，第二窗标记也是 versioned；
- P1-3：「退出这只」退主窗后实例提升，托盘/灵动岛动作仍指向存活实例；
- P1-5：「退出这只」关闭该窗从属聊天窗/设置窗（防 writer 复活）；
- P1-7：close_root 改为 per-root 屏障（关 A 窗 writer 期间 B 窗 save 不被拒）；
- T-3：close_root 直接单测；
- switch_character：热切换只重建本窗自持的 collision_ipc/broker_facade。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

import pytest
from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

import pet.app as app_mod
import pet.slot_manager as slot_manager_mod
from pet import catalog
from pet.app import AppShell, PetInstance, _read_spawn_offset_env
from pet.collision_ipc import CollisionIpcSession
from pet.config import APP_DIR_NAME, Config
from pet.window import PetWindow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


class _FakeLib:
    def pause_warm(self):
        pass

    def resume_warm(self):
        pass


class _FakeAgentLink:
    def __init__(self):
        self.shutdown_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1


class _FakeWindow:
    """窗级退出/切换所需的薄替身：记录调用，不触碰真实 Qt 窗口。

    T-2：不硬编码 versioned=True——remove_runtime_marker 读取进程级 flag 快照
    ``_single_process_spawn``（真实 PetWindow 在 _build_window 里同样被写入）。
    """

    def __init__(self):
        self.calls = []
        self.lib = _FakeLib()
        self.agent_link_manager = _FakeAgentLink()
        self.is_shown = True
        # P1-2：进程级 flag 快照（默认 = flag 关）。工厂/测试需按 shell 快照设置。
        self._single_process_spawn = False

    def save_position(self):
        self.calls.append("save")

    def close(self):
        self.calls.append("close")

    def remove_runtime_marker(self):
        self.calls.append("marker_del")
        slot_manager_mod.delete_runtime_marker(
            self.cfg.dir, self.cfg.instance_id)

    def detach_collision_session(self):
        self.calls.append("detach_collision")

    def isVisible(self):
        return self.is_shown

    def hide(self, notify=False):
        self.is_shown = False

    def show(self):
        self.is_shown = True

    def deleteLater(self):
        pass


class _FanoutMovie:
    """与 DecodeFanoutHub fan-out 接缝兼容的最小替身（批5.3 生命周期断言用）。"""

    def __init__(self, path: str):
        self.path = path
        self.playback_speed = 1.0
        self._publish_sink = None
        self._feed_source = None


def _make_primary_with_slot(tmp_path):
    """建一个持有 slot-0 锁的主窗 AppShell（spawn 第二个实例会拿到 slot-1）。"""
    config = Config(tmp_path)
    config.set("experimental_single_process_spawn", True)
    config.save()
    slot_id, slot_handle = slot_manager_mod.acquire_pet_slot(
        config.dir, preferred_slot=0)
    shell = AppShell(QApplication.instance(), config,
                     slot_handle=slot_handle, slot_id=slot_id)
    return shell, config, slot_handle


def _stop_sessions(*insts):
    """测试收口：停掉本测试内启动的进程内碰撞会话（未 start 的为 no-op）。"""
    for inst in insts:
        try:
            inst.collision_ipc.stop()
        except Exception:
            pass


def test_spawn_flag_off_keeps_process_launcher(tmp_path, app, monkeypatch):
    """flag 关：spawn_pet 走旧的 launch_new_pet 进程路径（逐位一致）。"""
    config = Config(tmp_path)
    config.set("experimental_single_process_spawn", False)
    config.save()
    shell = AppShell(QApplication.instance(), config,)

    launched = []
    monkeypatch.setattr(app_mod, "launch_new_pet", lambda index: launched.append(index))
    shell.spawn_pet()
    shell.spawn_pet()
    assert launched == [1, 2]
    assert len(shell.instances) == 1


def _alive_pid() -> int:
    # 用当前测试进程的 pid（一定存活），用于构造"活着"的标记
    return os.getpid()


def test_switch_character_rebuilds_own_session_and_broker(tmp_path, app, monkeypatch):
    """C2 地雷随「不再共享」消解：热切换只重建本窗自持的 collision_ipc /
    broker_facade（旧会话被停、新会话被 start、对象 id 变化），不碰其它窗。"""
    config = Config(tmp_path)
    shell = AppShell(QApplication.instance(), config,)

    monkeypatch.setattr(
        app_mod.PetInstance, "_create_library", lambda self, cid: _FakeLib())

    def fake_build_window(self, character_id, lib=None, build_tray=True):
        win = _FakeWindow()
        win.cfg = self.config
        win._single_process_spawn = self.shell._single_process_spawn
        self.win = win
        return win

    monkeypatch.setattr(app_mod.PetInstance, "_build_window", fake_build_window)

    # 主窗先有一个窗口
    win0 = _FakeWindow()
    win0.cfg = config
    shell.instance.win = win0

    # 第二个窗（独立会话/资源）：其 collision_ipc/broker 不应被 touch
    sec = PetInstance(shell, Config(tmp_path, instance_id="slot-1"),)
    sec_win = _FakeWindow()
    sec_win.cfg = sec.config
    sec.win = sec_win
    shell._instances.append(sec)

    old_ipc = shell.instance.collision_ipc
    old_broker = shell.instance.broker_facade
    ipc_stop = []
    broker_shutdown = []
    monkeypatch.setattr(old_ipc, "stop", lambda: ipc_stop.append(1))
    monkeypatch.setattr(old_broker, "stop_all", lambda: broker_shutdown.append(1))
    sec_ipc_id = id(sec.collision_ipc)
    sec_broker_id = id(sec.broker_facade)

    char_ids = catalog.list_available_characters()
    current = str(config.get("character", catalog.DEFAULT_CHARACTER))
    target = next((c for c in char_ids if c != current), "not-default-character")

    shell.instance.switch_character(target)

    # 本窗旧碰撞会话被停并被重建（对象 id 变化）；进程级共享 hub 不被重建
    #（各窗共用，批5.3）。
    assert ipc_stop == [1], "switch_character 应停本窗旧碰撞会话"
    assert broker_shutdown == [], \
        "switch_character 不应关进程级共享解码 hub（批5.3 各窗共用）"
    assert shell.instance.collision_ipc is not old_ipc, "本窗 collision_ipc 应重建"
    assert shell.instance.broker_facade is old_broker, \
        "进程级解码 hub 不被重建（各窗共用同一份）"
    assert shell.instance.collision_ipc._thread.isRunning(), "新会话应被 start"
    # 其它窗的会话/资源未被动
    assert id(sec.collision_ipc) == sec_ipc_id
    assert id(sec.broker_facade) == sec_broker_id
    assert shell.instance.win is not win0

    # 收口：停新会话（避免遗留运行中的独占 QLocal server）
    _stop_sessions(shell.instance, sec)


def test_runtime_marker_versioned_name_avoids_legacy_glob(tmp_path, app):
    """R4：flag 开时标记用版本化新名（不被旧 'runtime-*.json' glob 匹配），
    且新版读取侧同时认新旧两种命名。"""
    config = Config(tmp_path)
    config.set("experimental_single_process_spawn", True)
    config.save()

    ver_path = slot_manager_mod.runtime_marker_path(
        config.dir, config.instance_id, versioned=True)
    # 新名不匹配旧 glob（旧 glob 只认 'runtime-*.json' 前缀）
    assert ver_path.name.startswith("pet-runtime-v2-")
    assert len(list(config.dir.glob("runtime-*.json"))) == 0, \
        "新窗（flag 开）不得写入旧格式标记"

    # 写新标记
    slot_manager_mod.write_runtime_marker(
        config.dir, config.instance_id, 10, 10, 100, 100, versioned=True)
    assert ver_path.exists()

    # 新版读取侧：旧名（活 pid 的旧标记）与新名都会被读到
    leg = config.dir / f"runtime-{_alive_pid()}.json"
    leg.write_text(json.dumps({"pid": _alive_pid(), "x": 1, "y": 1, "w": 5, "h": 5}),
                   encoding="utf-8")

    live = slot_manager_mod.read_live_instances(config.dir)
    assert len(live) == 2


def test_runtime_marker_versioned_off_keeps_legacy_name(tmp_path, app):
    """R4：flag 关时仍用旧名 runtime-<pid>.json（与现状逐位一致）。"""
    config = Config(tmp_path)
    config.set("experimental_single_process_spawn", False)
    config.save()
    leg = slot_manager_mod.runtime_marker_path(
        config.dir, config.instance_id, versioned=False)
    assert leg.name == f"runtime-{os.getpid()}.json"


def test_spawn_offset_env_wired_to_primary_instance(tmp_path, app, monkeypatch):
    """P0-1：spawn 偏移链接线（env → 主窗 spawn_offset），flag 关 spawn 子进程
    仍与母桌宠错开落位。"""
    monkeypatch.setenv("DSH_PET_SPAWN_OFFSET_INDEX", "3")
    assert _read_spawn_offset_env() == 3
    monkeypatch.setenv("DSH_PET_SPAWN_OFFSET_INDEX", "-2")
    assert _read_spawn_offset_env() == 0
    monkeypatch.setenv("DSH_PET_SPAWN_OFFSET_INDEX", "")  # 空串
    assert _read_spawn_offset_env() == 0
    monkeypatch.delenv("DSH_PET_SPAWN_OFFSET_INDEX", raising=False)
    assert _read_spawn_offset_env() == 0

    # env → AppShell(spawn_offset=...) → PetInstance._spawn_offset
    offset = _read_spawn_offset_env()
    config = Config(tmp_path)
    shell = AppShell(QApplication.instance(), config,
                     spawn_offset=offset)
    assert shell.instance._spawn_offset == 0  # 无 env 时默认 0
    shell2 = AppShell(QApplication.instance(), Config(tmp_path),
                      spawn_offset=5)
    assert shell2.instance._spawn_offset == 5


def test_exit_flag_off_does_not_inject_on_exit_window(tmp_path, app, monkeypatch):
    """P0-2/T-4：flag 关右键退出等价——on_exit_window 不注入，
    _request_quit 走旧 app.quit 分支（逐位一致）。"""
    config = Config(tmp_path)
    config.set("experimental_single_process_spawn", False)
    config.save()
    shell = AppShell(QApplication.instance(), config,)
    inst = shell.instance
    win = _FakeWindow()
    win.cfg = config
    inst.win = win
    inst._wire_window(win)
    # flag 关：不注入窗级「退出这只」
    assert win.on_exit_window is None

    # _request_quit 在 on_exit_window 缺失时走 app.quit
    quit_calls = []
    _app = QApplication.instance()
    monkeypatch.setattr(_app, "quit", lambda: quit_calls.append(1))
    win._active_context_menu = None
    PetWindow._request_quit(win)
    assert quit_calls == [1], "flag 关右键退出应走 app.quit（与现状逐位一致）"


def test_exit_flag_on_injects_on_exit_window(tmp_path, app, monkeypatch):
    """P0-2：flag 开注入窗级「退出这只」；_request_quit 走窗级退出分支。"""
    config = Config(tmp_path)
    config.set("experimental_single_process_spawn", True)
    config.save()
    shell = AppShell(QApplication.instance(), config,)
    inst = shell.instance
    win = _FakeWindow()
    win.cfg = config
    win._single_process_spawn = True
    inst.win = win
    inst._wire_window(win)
    assert callable(win.on_exit_window), "flag 开应注入窗级「退出这只」"

    # _request_quit 走窗级分支（on_exit_window 被调用，而非 app.quit）
    exit_calls = []
    win.on_exit_window = lambda: exit_calls.append(1)
    win._active_context_menu = None
    quit_calls = []
    _app = QApplication.instance()
    monkeypatch.setattr(_app, "quit", lambda: quit_calls.append(1))
    PetWindow._request_quit(win)
    assert exit_calls == [1], "flag 开右键退出应走窗级「退出这只」"
    assert quit_calls == [], "flag 开右键退出不应走 app.quit"


# --------------------------------------------------------------------------
# P1-7 / T-3：close_root per-root 屏障
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# T-1：两窗各持 session → runtime_id 不同、互不为 peer-self（P1-1）
# --------------------------------------------------------------------------
def _pump(seconds: float) -> None:
    app = QApplication.instance() or QApplication([])
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
        time.sleep(0.005)


def test_two_windows_distinct_runtime_ids_not_peer_self(tmp_path, app):
    """T-1：主窗与第二窗各 attach 各自 session → runtime_id 不同，且同进程
    多 session 经 _local_election_names 收敛成一个协调者 + 两个独立成员
    （互不为 peer-self，与多进程双开等价，P1-1）。"""
    from pet import collision

    name = f"sp52-{uuid.uuid4().hex[:8]}"
    primary = CollisionIpcSession(Config(tmp_path, instance_id=""), server_name=name)
    second = CollisionIpcSession(Config(tmp_path, instance_id="slot-1"), server_name=name)
    assert primary.runtime_id != second.runtime_id, "两窗 runtime_id 必须不同"
    # runtime_id 由各自 instance_id 派生（前缀区分主窗/第二窗）
    assert primary.runtime_id.startswith("instance-pid")
    assert second.runtime_id.startswith("slot-1-pid")

    flags = collision.FLAG_VISIBLE | collision.FLAG_COLLISION_ENABLED

    def _state(seq, x):
        return {"seq": seq, "ts": time.monotonic(), "x": x, "y": 0.0,
                "w": 100, "h": 100, "radius_x": 40.0, "radius_y": 40.0,
                "vx": 0.0, "vy": 0.0, "flags": flags}

    primary.start()
    second.start()
    try:
        # 等都收敛出一个协调者（server 非空的那侧）
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            _pump(0.1)
            if primary._worker.server is not None or second._worker.server is not None:
                break
        coord_session = primary if primary._worker.server is not None else second
        client_session = second if coord_session is primary else primary
        assert coord_session._worker.server is not None
        _pump(0.5)  # 客户端连接/握手

        # 两窗都上报 state → 各自成为协调者成员表里的独立成员（互不为 peer-self）
        coord_session.submit_state(_state(1, x=10.0))
        client_session.submit_state(_state(1, x=20.0))
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            _pump(0.05)
            if (primary.runtime_id in coord_session._worker.members
                    and second.runtime_id in coord_session._worker.members):
                break
        assert primary.runtime_id in coord_session._worker.members
        assert second.runtime_id in coord_session._worker.members
        assert len(coord_session._worker.members) >= 2, \
            "两窗必须是两个独立成员，而不是共享一个成员槽位"
    finally:
        primary.stop()
        second.stop()


def test_spawn_in_process_slot_scan_cap_raises(tmp_path, app, monkeypatch):
    """P2-1：slot 扫描超过 128 上限抛 SlotManagerError（不许无限循环）。"""
    shell, config, primary_handle = _make_primary_with_slot(tmp_path)
    monkeypatch.setattr(slot_manager_mod, "acquire_pet_slot",
                        lambda *a, **k: (_ for _ in ()).throw(
                            slot_manager_mod.SlotLockError("busy")))
    with pytest.raises(slot_manager_mod.SlotManagerError):
        shell.spawn_in_process_window(1)
    slot_manager_mod._unlock_file(primary_handle)


def test_in_process_spawn_shares_process_hub(tmp_path, app, monkeypatch):
    """批5.3：P1-6 移除——进程内多窗与``decode_broker_enabled``的互斥声明作废。
    新窗与主窗共用同一进程级``DecodeFanoutHub``（experimental_shared_decode 默认
    开 且 experimental_single_process_spawn 开 → hub 启用），不再有「停用新窗
    broker（不 bind）」的限制。"""
    config = Config(tmp_path)
    config.set("experimental_single_process_spawn", True)
    config.set("experimental_shared_decode", True)
    config.save()
    slot_id, slot_handle = slot_manager_mod.acquire_pet_slot(config.dir, preferred_slot=0)
    shell = AppShell(QApplication.instance(), config,
                     slot_handle=slot_handle, slot_id=slot_id)
    # 双门开 → 进程级 hub 启用
    assert shell._decode_hub.enabled is True
    assert shell.instance.broker_facade.enabled is True

    def fake_build_window(self, character_id, lib=None, build_tray=True):
        win = _FakeWindow()
        win.cfg = self.config
        win._single_process_spawn = self.shell._single_process_spawn
        self.win = win
        return win

    monkeypatch.setattr(app_mod.PetInstance, "_build_window", fake_build_window)
    monkeypatch.setattr(app_mod.PetInstance, "_apply_spawn_offset", lambda self: None)

    second = shell.spawn_in_process_window(1)
    assert second is not shell.instance
    # 新窗与主窗共用同一进程级 hub（不是停用/独立 broker）
    assert second.broker_facade is shell.instance.broker_facade
    assert second.broker_facade.enabled is True

    _stop_sessions(second)
    second.win.close()
    slot_manager_mod._unlock_file(second.slot_handle)
    second.slot_handle = None
    slot_manager_mod._unlock_file(slot_handle)


def test_in_process_spawn_hub_disabled_when_shared_decode_off(tmp_path, app, monkeypatch):
    """experimental_shared_decode 关 → 进程级 hub 不激活（各窗独立解码）。"""
    config = Config(tmp_path)
    config.set("experimental_single_process_spawn", True)
    config.set("experimental_shared_decode", False)
    config.save()
    slot_id, slot_handle = slot_manager_mod.acquire_pet_slot(config.dir, preferred_slot=0)
    shell = AppShell(QApplication.instance(), config,
                     slot_handle=slot_handle, slot_id=slot_id)
    assert shell._decode_hub.enabled is False
    assert shell.instance.broker_facade.enabled is False
    assert shell.instance.broker_facade.shareable_start("idle", _FanoutMovie("x.webm")) == "local"
    slot_manager_mod._unlock_file(slot_handle)


# ---------------------------------------------------------------- N-1 修复回归
# GLM 复审（REVIEW_batch52_fix1_glm53）阻塞项 N-1：flag 快照必须在 PetWindow
# 构造期就生效——__init__ 尾部的 _restore_position 会写/读 runtime 标记，
# 构造返回后再注入会让 flag 开的窗用旧名写初始标记（两窗互踩）。


class _FakeClip(QObject):
    frameChanged = Signal(int)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self.speed = 1.0
        self._pm = QPixmap(100, 100)
        self._pm.fill()

    def stop(self):
        self._running = False

    def start(self):
        self._running = True

    def jumpToFrame(self, frame_index):
        return frame_index <= 0

    def set_playback_speed(self, speed):
        self.speed = speed

    def currentPixmap(self):
        return self._pm

    def currentFrameNumber(self):
        return 0

    def frameCount(self):
        return 1

    def duration(self):
        return 1.0

    def currentTimeSeconds(self):
        return 0.0


class _FakeAnimLib:
    def __init__(self):
        names = [catalog.IDLE, catalog.TURN, catalog.MOVES[0],
                 catalog.CLICKS[0], catalog.DRAG]
        self._clips = {n: _FakeClip() for n in names}
        self.manifest = {}
        self.folder_map = {}
        self.folder_files = None
        self.no_mirror = set()

    def names(self):
        return list(self._clips)

    def movies(self):
        return dict(self._clips)

    def movie(self, name):
        return self._clips[name]

    def frames(self, name):
        return 1

    def duration(self, name):
        return 1.0


def test_real_window_construction_writes_versioned_marker_when_flag_on(tmp_path, app):
    """N-1（红→绿回归）：flag 开时真实 PetWindow 构造期就写 v2 名标记，
    绝不写旧名（修复前：构造期快照未注入 → 写旧名 runtime-<pid>.json）。"""
    from pet.window import PetWindow

    config = Config(tmp_path)
    config.save()  # 确保 config.dir 已建（生产路径由启动流程建，测试需显式）
    win = PetWindow(_FakeAnimLib(), config, single_process_spawn=True)
    try:
        v2 = slot_manager_mod.runtime_marker_path(
            config.dir, config.instance_id, versioned=True)
        assert v2.exists(), "flag 开的窗构造后必须已写 v2 标记（N-1）"
        legacy = [p for p in config.dir.glob("runtime-*.json")]
        assert legacy == [], f"flag 开的窗不得写旧名标记，实际: {legacy}"
    finally:
        win.close()
        win.deleteLater()


def test_real_window_construction_writes_legacy_marker_when_flag_off(tmp_path, app):
    """N-1 对照：flag 关（默认）构造后写旧名标记（与 HEAD 逐位一致）。"""
    from pet.window import PetWindow

    config = Config(tmp_path)
    config.save()  # 同上：先建 config.dir
    win = PetWindow(_FakeAnimLib(), config)
    try:
        legacy = config.dir / f"runtime-{os.getpid()}.json"
        assert legacy.exists(), "flag 关的窗构造后必须写旧名标记"
        v2 = list(config.dir.glob("pet-runtime-v2-*.json"))
        assert v2 == [], f"flag 关的窗不得写 v2 标记，实际: {v2}"
    finally:
        win.close()
        win.deleteLater()


def test_switch_character_new_window_gets_new_session(tmp_path, app, monkeypatch):
    """T-6 补全（attach 半边）：热切换先重建本窗会话再建窗——_build_window
    执行时 self.collision_ipc 必须已是新会话（PetWindow 构造期 attach 它）。"""
    config = Config(tmp_path)
    shell = AppShell(QApplication.instance(), config,)
    monkeypatch.setattr(
        app_mod.PetInstance, "_create_library", lambda self, cid: _FakeLib())

    seen_sessions = []

    def fake_build_window(self, character_id, lib=None, build_tray=True):
        seen_sessions.append(self.collision_ipc)
        win = _FakeWindow()
        win.cfg = self.config
        self.win = win
        return win

    monkeypatch.setattr(app_mod.PetInstance, "_build_window", fake_build_window)
    win0 = _FakeWindow()
    win0.cfg = config
    shell.instance.win = win0
    old_ipc = shell.instance.collision_ipc

    char_ids = catalog.list_available_characters()
    current = str(config.get("character", catalog.DEFAULT_CHARACTER))
    target = next((c for c in char_ids if c != current), "not-default-character")
    shell.instance.switch_character(target)

    assert seen_sessions, "switch_character 应重建窗口"
    assert seen_sessions[-1] is not old_ipc, "建窗时必须已是新会话"
    assert seen_sessions[-1] is shell.instance.collision_ipc

    _stop_sessions(shell.instance)


def test_non_primary_switch_builds_no_tray(tmp_path, app, monkeypatch):
    """T-6 补全（托盘半边）：非主窗热切换 build_tray=False，绝不动共享托盘。"""
    config = Config(tmp_path)
    shell = AppShell(QApplication.instance(), config,)
    monkeypatch.setattr(
        app_mod.PetInstance, "_create_library", lambda self, cid: _FakeLib())

    build_tray_calls = []

    def fake_build_window(self, character_id, lib=None, build_tray=True):
        build_tray_calls.append(build_tray)
        win = _FakeWindow()
        win.cfg = self.config
        self.win = win
        return win

    monkeypatch.setattr(app_mod.PetInstance, "_build_window", fake_build_window)

    primary_win = _FakeWindow()
    primary_win.cfg = config
    shell.instance.win = primary_win
    sec = PetInstance(shell, Config(tmp_path, instance_id="slot-1"),)
    sec_win = _FakeWindow()
    sec_win.cfg = sec.config
    sec.win = sec_win
    shell._instances.append(sec)

    char_ids = catalog.list_available_characters()
    current = str(sec.config.get("character", catalog.DEFAULT_CHARACTER))
    target = next((c for c in char_ids if c != current), "not-default-character")
    sec.switch_character(target)

    assert build_tray_calls == [False], \
        f"非主窗热切换不得触碰托盘，实际 build_tray 序列: {build_tray_calls}"

    _stop_sessions(shell.instance, sec)


# ---------------------------------------------------------------- 新 slot 落种
def test_seed_slot_config_follows_main_settings(tmp_path):
    """新 slot 首次多开：配置跟随主设置（剔除每窗状态键，落种含 user_customized=False）。"""
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    main_cfg = {"character": "shenshen", "no_move": False,
                "rx": 0.5, "ry": 0.9, "screen_name": "X", "facing": "left"}
    (config_dir / "config.json").write_text(
        json.dumps(main_cfg), encoding="utf-8")

    assert slot_manager_mod.seed_slot_config_from_main(config_dir, 2) is True
    seeded = json.loads(
        (config_dir / "config-slot-2.json").read_text(encoding="utf-8"))
    assert seeded["no_move"] is False  # 跟随主设置
    assert seeded["character"] == "shenshen"
    assert seeded.get("user_customized") is False  # 落种默认不置位
    for k in ("rx", "ry", "screen_name", "facing"):
        assert k not in seeded, f"每窗状态键 {k} 不得继承"


def test_seed_slot_config_applies_spawn_inherit_logic(tmp_path):
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(json.dumps({
        "scale": 1.0,
        "spawn_inherit_size": False,
        "spawn_scale": 0.5,
    }), encoding="utf-8")

    assert slot_manager_mod.seed_slot_config_from_main(config_dir, 7) is True
    seeded = json.loads(
        (config_dir / "config-slot-7.json").read_text(encoding="utf-8"))
    # 关闭继承大小 → 用主配置为小肥鱼选定的 spawn_scale；继承灵动岛 → enabled=True
    assert seeded["scale"] == 0.5
    assert seeded["spawn_inherit_size"] is False
    assert seeded["spawn_scale"] == 0.5
    assert seeded.get("user_customized") is False


def test_seed_slot_config_refreshes_non_customized_slot(tmp_path):
    """批 C：slot 存在但 user_customized 为假（含旧存档无此键）→ 按当前主设置重新刷新。"""
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({"character": "shenshen", "spawn_inherit_size": True}),
        encoding="utf-8")
    # 旧存档（无 user_customized 键）按假处理 → 应被刷新成主设置。
    existing = {"character": "other", "custom": 1}
    (config_dir / "config-slot-3.json").write_text(json.dumps(existing), encoding="utf-8")

    assert slot_manager_mod.seed_slot_config_from_main(config_dir, 3) is True
    refreshed = json.loads(
        (config_dir / "config-slot-3.json").read_text(encoding="utf-8"))
    assert refreshed["character"] == "shenshen"  # 跟随主设置
    assert refreshed.get("user_customized") is False


def test_seed_slot_config_preserves_customized_slot(tmp_path):
    """批 C：slot 存在且 user_customized 为真 → 整个跳过，一个键都不碰。"""
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({"character": "shenshen"}), encoding="utf-8")
    existing = {"character": "other", "custom": 1, "user_customized": True}
    (config_dir / "config-slot-4.json").write_text(json.dumps(existing), encoding="utf-8")

    assert slot_manager_mod.seed_slot_config_from_main(config_dir, 4) is False
    assert json.loads((config_dir / "config-slot-4.json").read_text(
        encoding="utf-8")) == existing


def test_seed_slot_config_refresh_preserves_slot_position(tmp_path):
    """批 C：落种/刷新永不写位置键——刷新不覆盖 slot 自己拖动后自存的位置。"""
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    # 主配置的位置键是另一个值；刷新后 slot 应保留自己的位置，不被主配置覆盖。
    (config_dir / "config.json").write_text(json.dumps({
        "character": "shenshen",
        "rx": 0.1, "ry": 0.2, "screen_name": "MAIN", "facing": "left",
    }), encoding="utf-8")
    existing = {"character": "other",
                "rx": 0.6, "ry": 0.7, "screen_name": "SLOT", "facing": "right"}
    (config_dir / "config-slot-5.json").write_text(json.dumps(existing), encoding="utf-8")

    assert slot_manager_mod.seed_slot_config_from_main(config_dir, 5) is True
    refreshed = json.loads(
        (config_dir / "config-slot-5.json").read_text(encoding="utf-8"))
    assert refreshed["rx"] == 0.6
    assert refreshed["ry"] == 0.7
    assert refreshed["screen_name"] == "SLOT"
    assert refreshed["facing"] == "right"


def test_multi_process_start_seed_then_config_roundtrip(tmp_path):
    """批 C：多进程启动路径（main 先 seed 再构造 Config）落种含 spawn 逻辑，Config 可读回。"""
    config_dir = tmp_path / APP_DIR_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps({
        "scale": 1.0,
        "spawn_inherit_size": False,
        "spawn_scale": 0.5,
    }), encoding="utf-8")

    # 与 main() 的 seed → Config(instance_id) 次序一致。
    assert slot_manager_mod.seed_slot_config_from_main(config_dir, 2) is True
    cfg = Config(base=tmp_path, instance_id="slot-2")
    assert cfg.get("scale") == 0.5
    assert cfg.get("spawn_inherit_size") is False
    assert cfg.get("spawn_scale") == 0.5
    assert cfg.get("user_customized") is False


def test_spawn_in_process_window_routes_through_shared_seed(tmp_path, app, monkeypatch):
    """批 C：进程内 spawn 调用点统一走共享落种函数（传对 slot_id），并产出 spawn 逻辑。"""
    shell, config, primary_handle = _make_primary_with_slot(tmp_path)
    real_seed = slot_manager_mod.seed_slot_config_from_main
    calls = []

    def spy(seed_dir, seed_slot):
        calls.append((str(seed_dir), seed_slot))
        return real_seed(seed_dir, seed_slot)

    def fake_build_window(self, character_id, lib=None, build_tray=True):
        win = _FakeWindow()
        win.cfg = self.config
        win._single_process_spawn = self.shell._single_process_spawn
        self.win = win
        return win

    monkeypatch.setattr(slot_manager_mod, "seed_slot_config_from_main", spy)
    monkeypatch.setattr(app_mod.PetInstance, "_build_window", fake_build_window)
    monkeypatch.setattr(app_mod.PetInstance, "_apply_spawn_offset", lambda self: None)
    monkeypatch.setattr(
        app_mod.PetInstance, "_check_autostart_wanted", lambda self: None)

    second = shell.spawn_in_process_window(1)

    assert calls, "进程内 spawn 调用点应经共享落种函数"
    # 共享落种函数收到的是主窗配置根 + 新 slot id
    assert calls[0][1] == 1
    # spawn 产物 slot 配置存在且落种 mark 默认假
    seed_path = config.dir.parent / APP_DIR_NAME / "config-slot-1.json"
    assert seed_path.exists()
    seeded = json.loads(seed_path.read_text(encoding="utf-8"))
    assert seeded.get("user_customized") is False

    _stop_sessions(second)
    second.win.close()
    slot_manager_mod._unlock_file(second.slot_handle)
    second.slot_handle = None
    slot_manager_mod._unlock_file(primary_handle)


# --------------------------------------------------------------------------
# 批 B：clear_spawned_pets 单进程模式（进程内子窗）前置关闭
# --------------------------------------------------------------------------
def test_clear_spawned_pets_closes_in_process_children_no_residue(
        tmp_path, app, monkeypatch):
    """批 B：单进程模式下 clear_spawned_pets 先关闭进程内「非主窗」子肥鱼窗口、
    删除其 runtime 标记，主窗保留；重复调用幂等无残留。

    子肥鱼在单进程模式是进程内窗口（PID=主进程），会被文件级清理的
    pid==os.getpid() 自我保护跳过而永远不会被关；修复后先按进程内子窗登记表
    （self._instances）枚举并关闭，再走文件级清理杀多进程子进程。
    """
    shell, config, primary_handle = _make_primary_with_slot(tmp_path)

    # 主窗窗身 + 主窗 runtime 标记（主肥鱼不清，须保留）
    primary = shell.instance
    primary_win = _FakeWindow()
    primary_win.cfg = config
    primary_win._single_process_spawn = True
    primary.win = primary_win
    primary_marker = slot_manager_mod.runtime_marker_path(
        config.dir, config.instance_id, versioned=True)
    primary_marker.write_text(
        json.dumps({"pid": os.getpid(), "x": 0, "y": 0, "w": 100, "h": 100}),
        encoding="utf-8")

    # 第二个实例（进程内子窗，同 pid=主进程）
    slot_id, slot_handle = slot_manager_mod.acquire_pet_slot(
        config.dir, preferred_slot=1)
    sec = PetInstance(shell, Config(base=tmp_path, instance_id="slot-1"), slot_handle=slot_handle, slot_id=slot_id)
    sec_win = _FakeWindow()
    sec_win.cfg = sec.config
    sec_win._single_process_spawn = True
    sec.win = sec_win
    shell._instances.append(sec)
    sec_marker = slot_manager_mod.runtime_marker_path(
        config.dir, sec.config.instance_id, versioned=True)
    sec_marker.write_text(
        json.dumps({"pid": os.getpid(), "x": 100, "y": 100, "w": 100, "h": 100}),
        encoding="utf-8")

    # 子窗会话/broker 打桩（避免真实 QLocal/共享 hub 收口的副作用）
    monkeypatch.setattr(sec.collision_ipc, "stop", lambda: None)

    # 确认对话框返回 Yes
    monkeypatch.setattr(
        app_mod.QMessageBox, "question",
        lambda *a, **kw: app_mod.QMessageBox.StandardButton.Yes)

    assert len(shell.instances) == 2
    shell.clear_spawned_pets()
    # 批 E：进程内子窗关闭改为 QTimer.singleShot(0) 逐只链式执行，需转事件循环收口。
    _pump(0.5)

    # 子窗被关闭并移除；主窗保留
    assert len(shell.instances) == 1
    assert shell.instance is primary
    assert sec not in shell.instances
    assert sec_win.calls == ["save", "marker_del", "close"]
    # 子窗 v2 标记被删；主窗标记保留（主肥鱼仍在跑）
    assert not sec_marker.exists()
    assert primary_marker.exists()
    # 子窗 slot 锁已释放
    assert sec.slot_handle is None

    # 幂等：再跑一遍无残留、不报错
    shell.clear_spawned_pets()
    _pump(0.2)
    assert len(shell.instances) == 1
    assert shell.instance is primary
    assert primary_marker.exists()

    slot_manager_mod._unlock_file(primary_handle)


def test_clear_spawned_pets_multi_process_flag_off_no_in_process_children(
        tmp_path, app, monkeypatch):
    """批 B：多进程模式（flag 关）clear_spawned_pets 无进程内子窗时，前置路径
    为空操作，随后文件级清理照常跑通、主窗保留（幂等、不误关主窗）。"""
    import pet.child_pet_cleanup as cleanup_mod

    config = Config(tmp_path)
    config.set("experimental_single_process_spawn", False)
    config.save()
    shell = AppShell(QApplication.instance(), config,)

    primary_win = _FakeWindow()
    primary_win.cfg = config
    shell.instance.win = primary_win

    # 模拟多进程子肥鱼：一个 v2 存活标记（假 PID）+ slot 数据
    root = config.dir
    (root / "config-slot-1.json").write_text("{}", encoding="utf-8")
    v2 = root / "pet-runtime-v2-555-slot-1.json"
    v2.write_text(json.dumps({"pid": 555}), encoding="utf-8")

    terminated = []
    alive = {555}
    # 批 H：杀前有 exe 身份核验（防 pid 复用误杀），假 pid 打桩为本程序
    monkeypatch.setattr(cleanup_mod, "_is_pet_process", lambda pid: True)
    monkeypatch.setattr(
        cleanup_mod, "_pid_alive", lambda pid: pid in alive)

    def fake_terminate(pid):
        terminated.append(pid)
        alive.discard(pid)  # 批 G：杀后确认——进程真的退出

    monkeypatch.setattr(
        cleanup_mod, "_terminate_pet_process", fake_terminate)
    monkeypatch.setattr(
        app_mod.QMessageBox, "question",
        lambda *a, **kw: app_mod.QMessageBox.StandardButton.Yes)
    infos = []
    monkeypatch.setattr(
        app_mod.QMessageBox, "information",
        lambda *a, **kw: infos.append(a))

    # 无进程内子窗（flag 关），只有主窗
    assert len(shell.instances) == 1
    shell.clear_spawned_pets()
    # 批 G：文件级清理移到后台线程（taskkill 不冻 UI），完成经事件循环复位。
    _pump(0.5)

    # 多进程子进程被文件级收尾杀掉；批 F 起 slot 数据保留；主窗保留
    assert terminated == [555]
    assert not v2.exists()
    assert (root / "config-slot-1.json").exists()
    assert len(shell.instances) == 1
    assert shell.instance is shell.instances[0]
    assert infos == [], "批 I：结果弹窗已移除（结果写日志）"
    assert shell._clear_spawned_pending is False


# --------------------------------------------------------------------------
# 批 E：清除子肥鱼——进程内子窗 QTimer.singleShot(0) 链式关闭（不冻 UI）
# --------------------------------------------------------------------------
def _add_child_instance(shell, tmp_path, config, preferred_slot, monkeypatch):
    """建一个进程内子窗实例（fake window + 会话打桩），返回 (inst, win)。"""
    slot_id, handle = slot_manager_mod.acquire_pet_slot(
        config.dir, preferred_slot=preferred_slot)
    inst = PetInstance(shell, Config(base=tmp_path, instance_id=f"slot-{slot_id}"), slot_handle=handle, slot_id=slot_id)
    win = _FakeWindow()
    win.cfg = inst.config
    win._single_process_spawn = True
    inst.win = win
    shell._instances.append(inst)
    monkeypatch.setattr(inst.collision_ipc, "stop", lambda: None)
    return inst, win


def test_clear_spawned_pets_chained_close_defers_until_event_loop(
        tmp_path, app, monkeypatch):
    """批 E：子窗关闭经 QTimer.singleShot(0) 逐只执行——clear_spawned_pets
    同步返回时尚未触碰任何子窗（每只之间让出事件循环，UI 不冻结/不出黑框），
    事件循环转起来后才逐只关完，全部关完再执行文件级清理并弹一次结果框。"""
    shell, config, primary_handle = _make_primary_with_slot(tmp_path)
    children = [
        _add_child_instance(shell, tmp_path, config, slot, monkeypatch)
        for slot in (1, 2)
    ]

    monkeypatch.setattr(
        app_mod.QMessageBox, "question",
        lambda *a, **kw: app_mod.QMessageBox.StandardButton.Yes)
    infos = []
    monkeypatch.setattr(
        app_mod.QMessageBox, "information",
        lambda *a, **kw: infos.append(a))

    shell.clear_spawned_pets()
    # 同步返回：关闭被 singleShot(0) 延后，一只都还没关（旧实现同步关 N 只）。
    assert all(win.calls == [] for _inst, win in children)
    assert infos == []

    _pump(0.5)
    for inst, win in children:
        assert win.calls == ["save", "marker_del", "close"]
        assert inst not in shell.instances
        assert inst.slot_handle is None
    assert infos == [], "批 I：结果弹窗已移除（结果写日志）"
    assert shell._clear_spawned_pending is False
    assert shell.instance is shell.instances[0]
    slot_manager_mod._unlock_file(primary_handle)


def test_clear_spawned_pets_repeat_click_during_chain_is_idempotent(
        tmp_path, app, monkeypatch):
    """批 E：链式关闭进行中重复点击「一键退出」→ 忽略（不重复关闭）。
    批 I：确认框已移除（操作不删数据可重新生成），questions 应恒为空。"""
    shell, config, primary_handle = _make_primary_with_slot(tmp_path)
    children = [
        _add_child_instance(shell, tmp_path, config, slot, monkeypatch)
        for slot in (1, 2)
    ]

    questions = []
    monkeypatch.setattr(
        app_mod.QMessageBox, "question",
        lambda *a, **kw: (questions.append(1),
                          app_mod.QMessageBox.StandardButton.Yes)[1])
    infos = []
    monkeypatch.setattr(
        app_mod.QMessageBox, "information",
        lambda *a, **kw: infos.append(a))

    shell.clear_spawned_pets()
    shell.clear_spawned_pets()  # 链式进行中重复点击
    assert questions == [], "批 I：无确认框"

    _pump(0.5)
    assert infos == [], "批 I：结果弹窗已移除"
    assert shell._clear_spawned_pending is False
    for _inst, win in children:
        assert win.calls == ["save", "marker_del", "close"], "每只只关一次"
    slot_manager_mod._unlock_file(primary_handle)


def test_clear_spawned_pets_chain_skips_removed_or_destroyed_child(
        tmp_path, app, monkeypatch):
    """批 E：链式过程中子窗已销毁/已关闭（弱引用失效或不在登记表）→ 跳过不报错，
    其余子窗照常关完，清理与结果框照常收口。"""
    shell, config, primary_handle = _make_primary_with_slot(tmp_path)
    gone, gone_win = _add_child_instance(shell, tmp_path, config, 1, monkeypatch)
    kept, kept_win = _add_child_instance(shell, tmp_path, config, 2, monkeypatch)

    monkeypatch.setattr(
        app_mod.QMessageBox, "question",
        lambda *a, **kw: app_mod.QMessageBox.StandardButton.Yes)
    infos = []
    monkeypatch.setattr(
        app_mod.QMessageBox, "information",
        lambda *a, **kw: infos.append(a))

    shell.clear_spawned_pets()
    # 链式执行前该子窗已自行关闭（移出登记表）：快照仍在，但存活校验应跳过。
    shell._instances.remove(gone)

    _pump(0.5)
    assert gone_win.calls == [], "已销毁/已关闭的子窗不应再被触碰"
    assert kept_win.calls == ["save", "marker_del", "close"]
    assert infos == [], "批 I：结果弹窗已移除"
    assert shell._clear_spawned_pending is False, "收口后必须复位进行中标记"

    if gone.slot_handle is not None:
        slot_manager_mod._unlock_file(gone.slot_handle)
        gone.slot_handle = None
    slot_manager_mod._unlock_file(primary_handle)


def test_clear_spawned_pets_defers_heavy_teardown_to_reaper_thread(
        tmp_path, app, monkeypatch):
    """批 G：链式「退出子肥鱼」把每窗的重资源回收（writer 关闭 / agent
    shutdown / 碰撞会话停止——各有界阻塞秒级）挪到进程级 reaper 线程执行；
    UI 线程只保留关窗/摘标记/释放锁等毫秒级步骤，主桌宠不再冻结。"""

    shell, config, primary_handle = _make_primary_with_slot(tmp_path)
    inst, win = _add_child_instance(shell, tmp_path, config, 1, monkeypatch)

    heavy_threads = []
    monkeypatch.setattr(
        inst.collision_ipc, "stop",
        lambda: heavy_threads.append(
            ("collision", threading.current_thread().name)))
    monkeypatch.setattr(
        win.agent_link_manager, "shutdown",
        lambda: heavy_threads.append(
            ("agent", threading.current_thread().name)))
    monkeypatch.setattr(
        app_mod.QMessageBox, "question",
        lambda *a, **kw: app_mod.QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(app_mod.QMessageBox, "information", lambda *a, **kw: None)

    shell.clear_spawned_pets()
    _pump(0.5)

    # UI 必做步骤照常同步完成（关窗/摘标记/移除登记表）
    assert win.calls == ["save", "marker_del", "close"]
    assert inst not in shell.instances
    # 重回收全部发生，且都在 reaper 线程而非 UI 主线程
    labels = sorted(label for label, _t in heavy_threads)
    assert labels == ["agent", "collision"]
    assert all(t == "pet-teardown-reaper" for _label, t in heavy_threads)
    # defer 模式下关窗前摘下 agent 引用：closeEvent 不在 UI 线程重复 join
    assert win.agent_link_manager is None
    assert shell._clear_spawned_pending is False

    slot_manager_mod._unlock_file(primary_handle)


def test_clear_spawned_entry_wired_only_on_primary(tmp_path, app, monkeypatch):
    """批 G：「退出子肥鱼」入口只挂给主肥鱼（instance_id 为空）；子肥鱼窗
    该回调为 None——否则子鱼进程里 pid==os.getpid() 只跳过自己，会把主鱼
    当子鱼 taskkill 掉（实机事故）。"""
    shell, config, primary_handle = _make_primary_with_slot(tmp_path)
    try:
        main_win = _FakeWindow()
        main_win.cfg = config
        shell.instance._wire_window(main_win)
        assert callable(main_win.on_clear_spawned_pets), "主肥鱼必须有入口"

        inst, _win = _add_child_instance(shell, tmp_path, config, 1, monkeypatch)
        child_win = _FakeWindow()
        child_win.cfg = inst.config
        inst._wire_window(child_win)
        assert child_win.on_clear_spawned_pets is None, "子肥鱼不得有入口"
    finally:
        slot_manager_mod._unlock_file(primary_handle)


def test_runtime_marker_written_on_first_show(tmp_path, app):
    """批 G：窗口首次显示即登记 runtime 标记——没被拖动过的新生小肥鱼也有
    标记，「退出子肥鱼」按标记枚举时不会漏掉它。"""
    from tests.test_collision_window import FakeCollisionSession, FakeLibrary

    from pet.window import PetWindow

    config = Config(tmp_path)
    config.set("collision_enabled", False)
    config.save()
    win = PetWindow(FakeLibrary(), config,
                    collision_session=FakeCollisionSession("pet_marker_boot"))
    win.show()
    QApplication.instance().processEvents()
    # 默认（flag 关）写旧名 runtime-<pid>.json
    marker = config.dir / f"runtime-{os.getpid()}.json"
    assert marker.exists(), "首次显示必须登记 runtime 标记"
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()
    win.close()


def test_second_instance_avoids_live_overlap(app, tmp_path):
    """后启动的实例检测到存活实例占位后向左错开。"""
    from tests.test_window_pause import FakeLibrary
    from pet.window import PetWindow

    cfg_a = Config(base=tmp_path)
    cfg_a.save()
    win_a = PetWindow(FakeLibrary(), cfg_a)
    rect_a = (win_a.x(), win_a.y(), win_a._w, win_a._h)
    marker = cfg_a.dir / f"runtime-{os.getppid()}.json"
    marker.write_text(json.dumps(
        {"pid": os.getppid(), "x": rect_a[0], "y": rect_a[1], "w": rect_a[2], "h": rect_a[3]},
    ), encoding="utf-8")

    cfg_b = Config(base=tmp_path, instance_id="slot-1")
    win_b = PetWindow(FakeLibrary(), cfg_b)
    try:
        assert win_b.x() < win_a.x()
    finally:
        win_a.close()
        win_b.close()
    app.processEvents()


def test_runtime_marker_written_and_stale_cleaned(app, tmp_path):
    """实例启动后写入 runtime 标记；死进程的标记被顺手清理。"""
    from tests.test_window_pause import FakeLibrary
    from pet.window import PetWindow

    cfg = Config(base=tmp_path)
    cfg.save()
    stale = cfg.dir / "runtime-99999999.json"
    stale.write_text(json.dumps({"pid": 99999999, "x": 0, "y": 0, "w": 100, "h": 100}),
                     encoding="utf-8")
    win = PetWindow(FakeLibrary(), cfg)
    try:
        own = cfg.dir / f"runtime-{os.getpid()}.json"
        assert own.exists()
        assert not stale.exists()
    finally:
        win.close()
    app.processEvents()


def test_character_alias_roundtrip(tmp_path):
    """角色别名：设置 → 读取 → 空名恢复默认，且持久化到配置文件。"""
    cfg = Config(base=tmp_path)
    assert cfg.character_alias("shenshen") == ""

    cfg.set_character_alias("shenshen", "大肥鱼")
    assert cfg.character_alias("shenshen") == "大肥鱼"

    cfg2 = Config(base=tmp_path)
    assert cfg2.character_alias("shenshen") == "大肥鱼"

    cfg2.set_character_alias("shenshen", "")
    assert cfg2.character_alias("shenshen") == ""

    cfg2.set_character_alias("shenshen", "x" * 40)
    assert len(cfg2.character_alias("shenshen")) == 24


def test_character_display_name_prefers_alias(tmp_path):
    """显示名统一解析：用户别名优先，未设置时回退目录显示名。"""
    cfg = Config(base=tmp_path)
    assert cfg.character_display_name("shenshen") == catalog.character_display_name("shenshen")

    cfg.set_character_alias("shenshen", "小鲸鱼")
    assert cfg.character_display_name("shenshen") == "小鲸鱼"

    cfg.set_character_alias("shenshen", "")
    assert cfg.character_display_name("shenshen") == catalog.character_display_name("shenshen")


def _section_titles(dialog):
    from pet.modern_settings_dialog import SettingsSection
    from PySide6.QtWidgets import QLabel
    titles = []
    for section in dialog.findChildren(SettingsSection):
        labels = [l.text() for l in section.findChildren(QLabel) if l.text()]
        if labels:
            titles.append(labels[0])
    return titles


def test_spawn_section_hidden_from_settings(app, tmp_path):
    from pet.modern_settings_dialog import ModernSettingsDialog

    cfg = Config(base=tmp_path)
    dialog = ModernSettingsDialog(cfg, standalone=True)
    try:
        assert "多开" not in _section_titles(dialog), "「多开」实验分组必须隐藏"
    finally:
        dialog.close()
        app.processEvents()


def test_spawn_config_value_preserved_on_save(app, tmp_path):
    from pet.modern_settings_dialog import ModernSettingsDialog

    cfg = Config(base=tmp_path)
    cfg.set("experimental_single_process_spawn", True)
    dialog = ModernSettingsDialog(cfg, standalone=True)
    try:
        dialog._save()
    finally:
        dialog.close()
        app.processEvents()
    assert cfg.get("experimental_single_process_spawn") is True


def test_spawn_config_round_trip_default_false(app, tmp_path):
    from pet.modern_settings_dialog import ModernSettingsDialog

    cfg = Config(base=tmp_path)
    dialog = ModernSettingsDialog(cfg, standalone=True)
    try:
        dialog._save()
    finally:
        dialog.close()
        app.processEvents()
    assert cfg.get("experimental_single_process_spawn") is False
