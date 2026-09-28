# -*- coding: utf-8 -*-
"""灵动岛 AppShell 接线测试：碰撞体生命周期/挂起、no-chat 变体守卫。

审查补票（P0-1/P0-2/P1-6）：碰撞体重开必须换新 session；pet.chat 被排除的
打包变体不能崩；碰撞体随桌宠可见性挂起。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from pet.app import AppShell
from pet.chat.service import ChatService
from pet.collision_ipc import _stop_live_sessions_for_tests
from pet.config import Config


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_shell(tmp_path: Path, **island_cfg) -> AppShell:
    """最小 AppShell 桩：__new__ 绕过完整初始化，只接灵动岛链路。"""
    cfg = Config(base=tmp_path)
    cfg.set("dynamic_island", {
        "enabled": True, "x": 400, "y": 300,
        **island_cfg,
    })
    shell = AppShell.__new__(AppShell)
    shell.config = cfg
    shell.island = None
    shell.island_collision = None
    shell.instance = None
    shell._instances = []
    return shell


def _teardown_shell(shell) -> None:
    try:
        body = getattr(shell, "island_collision", None)
        if body is not None:
            body.stop()
    finally:
        island = getattr(shell, "island", None)
        if island is not None:
            island.hide()
            island.deleteLater()
        ChatService.unregister_global_finished(shell._on_global_chat_finished)
        _stop_live_sessions_for_tests()
        QApplication.processEvents()


def test_shell_creates_island_and_local_collision_body(tmp_path):
    """接线全景：岛创建、本进程碰撞体启动、几何/可见性回调接好。"""
    app = _qapp()
    shell = _make_shell(tmp_path)
    try:
        shell._sync_dynamic_island()
        island = shell.island
        body = shell.island_collision
        assert island is not None and island.isVisible()
        assert body is not None and body._running is True
        # 几何变化钩子与可见性回调都指向碰撞体
        assert island.on_geometry_changed == body.submit
        assert island.on_pet_visibility_changed == body.set_own_pet_visible
        # pets_provider 返回本进程全部桌宠窗口（无窗时为空）
        assert body._pets_provider() == []
    finally:
        _teardown_shell(shell)
        app.processEvents()


def test_collision_body_restart_after_disable(tmp_path):
    """关→开果冻墙：本地碰撞体停/开都干净（无定时器、无 IPC session 语义）。"""
    app = _qapp()
    shell = _make_shell(tmp_path)
    try:
        shell._sync_dynamic_island()
        body = shell.island_collision
        # 关掉碰撞（设置里关果冻墙）
        cfg = dict(shell.config.get("dynamic_island"))
        cfg["collision_enabled"] = False
        shell._sync_island_collision(cfg)
        assert body._running is False
        # 再打开 → 重新运行
        cfg["collision_enabled"] = True
        shell._sync_island_collision(cfg)
        assert body._running is True
    finally:
        _teardown_shell(shell)
        app.processEvents()


def test_island_survives_no_chat_packaging_variant(tmp_path, monkeypatch):
    """P0-2 回归：pet.chat 被排除的打包变体里创建灵动岛不得抛异常。"""
    app = _qapp()
    monkeypatch.setitem(sys.modules, "pet.chat.service", None)  # 模拟变体排除
    shell = _make_shell(tmp_path)
    try:
        shell._sync_dynamic_island()  # 不应抛 ModuleNotFoundError
        assert shell.island is not None
        # 未注册全局订阅（无 chat 可订）
        assert shell._on_global_chat_finished not in ChatService._global_finished_listeners
    finally:
        _teardown_shell(shell)
        app.processEvents()


def test_retired_balance_path_leaves_cache_untouched_on_island_expansion(tmp_path):
    app = _qapp()
    shell = _make_shell(tmp_path)
    cache = shell.config.dir / "balance_cache.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"historical cache")
    try:
        assert not hasattr(shell, "_balance_worker")
        shell._sync_dynamic_island()
        shell.island.expand_card()
        app.processEvents()
        assert cache.read_bytes() == b"historical cache"
        assert not hasattr(shell.island, "_tier_tick_timer")
    finally:
        _teardown_shell(shell)


