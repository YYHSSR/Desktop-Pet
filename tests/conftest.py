# -*- coding: utf-8 -*-
"""Shared Qt lifecycle cleanup and nonblocking modal-dialog fixtures."""


import pytest


@pytest.fixture(autouse=True)
def _no_modal_message_boxes(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    # 纯防卡桩：warning/information/critical/about 的返回值无分支用途，统一 no-op。
    for method in ("warning", "information", "critical", "about"):
        monkeypatch.setattr(QMessageBox, method, staticmethod(lambda *a, **k: None))
    # question() 是分支型 API（调用方按返回值走 Yes/No 分支，如 pet/agent_link.py
    # set_enabled），返回 None 不是合法 StandardButton、会改变分支语义。这里默认
    # 返回 StandardButton.No（安全拒绝，等同用户点“否”）；需要 Yes/No 特定答案的
    # 测试必须局部 monkeypatch（test_agent_link / test_proactive 已如此）。
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )


@pytest.fixture(autouse=True)
def _close_qt_top_level_widgets():
    """在测试后收口仍存活的应用级后台资源与 collision IPC 会话。"""
    yield
    # 内存取证（DSPET_MEM_DEBUG）是进程级开关 + 常驻 ticker 线程：用例打开后
    # 不复位会让后续用例凭空多一条 60s 日志线（且 reader 登记表跨用例残留）。
    try:
        from pet import mem_debug as _mem_debug_mod
        _mem_debug_mod._reset_for_tests()
    except Exception:
        pass
    # webm_clip 的「会话结束」闸门是进程级 latch（issue #111）：测试里置位后
    # 不复位会让后续用例静默拒绝一切 reader 启动（报错点离真因很远）。
    try:
        from pet import webm_clip as _webm_clip_mod
        _webm_clip_mod._reset_session_ending_for_tests()
    except Exception:
        pass
    # collision IPC：stop 仍存活的 CollisionIpcSession（finally 语义）。
    # 会话若在测试里未 stop，其 QThread 被 GC 时仍在跑 → 后续无关测试的
    # processEvents 处 native abort（QThread: Destroyed while thread is still
    # running，崩溃点漂移、Linux exit 139 根因）。
    try:
        from pet.collision_ipc import _stop_live_sessions_for_tests
        _stop_live_sessions_for_tests()
    except Exception:
        pass
    try:
        from pet.agent_link import AgentLinkManager, BaseAgentMonitor
        AgentLinkManager._shutdown_live_for_tests()
        BaseAgentMonitor._shutdown_live_for_tests()
    except Exception:
        pass
    # AppShell / 多窗共享子系统：共享服务的 QTimer 与信号连接的
    # timer/bridge 从 Qt C++ 侧强引用住整个 shell 对象图（Python gc 回收不掉），
    # 解释器退出 GC 才最终化 → 原生访问违规（test_single_process_shared 的
    # flag_on 族逐用例单独跑亦复现，崩溃点 "Garbage-collecting / no Python
    # frame"）。按同族防线逐对象停表 + 过继 QApplication。
    try:
        from pet.multi_window_shared import SharedSubsystems
        SharedSubsystems._shutdown_live_for_tests()
    except Exception:
        pass
    try:
        from pet.app import AppShell
        AppShell._shutdown_live_for_tests()
    except Exception:
        pass
    try:
        from pet.library import MovieLibrary
        MovieLibrary._shutdown_live_for_tests()
    except Exception:
        pass

    # 回来后仍会跨线程 emit；先 stop() 换代作废其结果，再销毁顶层窗口，
    # 否则 deleteLater + processEvents 收尾时 worker 向已销毁 QObject emit
    # （macOS 全量套件 segfault：conftest._close_qt_top_level_widgets + socket 线程）。
    # 销毁残留顶层窗口（QDialog/QWidget）：只用 deleteLater，绝不用 close()。
    # close() 会触发 closeEvent → _write_config → warm_click_sound_effects 的
    # 副作用（t4 曾因此崩溃）；deleteLater 走 DeferredDelete，Qt 安全销毁且不
    # 触发 closeEvent。清理掉泄漏的 C++ 对话框，避免其悬空事件在后续测试的
    # processEvents 引爆（崩溃点漂移、access violation）。
    # 逐对象定向派发自己排的 DeferredDelete，绝不调用共享 QApplication 的全局
    # processEvents()。全局冲刷会把其他测试遗留的排队事件（跨线程 queued 调用、
    # 历史 timer、别处排的删除任务）一并派发到正在销毁/已销毁的原生对象上，
    # 把历史 QObject 生命周期集中引爆在当前测试 —— 这正是全量套件偶发
    # 0xC0000005 access violation、且崩溃点随当前测试漂移的机制
    # 因此使用接收者定向的 DeferredDelete，避免进程级队列冲刷。
    try:
        import shiboken6
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            for widget in list(app.topLevelWidgets()):
                try:
                    if not shiboken6.isValid(widget):
                        continue  # C++ 侧已销毁的半死窗口：跳过
                    widget.deleteLater()
                    # 接收者定向：只处理这一个对象的 DeferredDelete，不触碰共享队列里
                    # 其他对象的删除任务与排队事件。
                    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
                except RuntimeError:
                    pass
    except Exception:
        pass


@pytest.fixture(scope="session", autouse=True)
def _close_webm_readers_at_session_end():
    """session 结束强收口所有 webm reader（测试债 #2 防线）。

    全量套件偶发 Windows access violation 的根因是 webm_clip `_reader`
    线程/ffmpeg 进程在测试收尾时未死干净、与解释器进程退出竞态。本 fixture
    在所有测试 teardown 之后做有界收口，目标：套件结束时无 webm-reader-*
    线程存活。只做收口，不改产品代码行为。

    收口对象（两类都覆盖）：
    1. 孤儿注册表（_ORPHAN_REGISTRY.holders()）：模块级强引用持有所有
       「退役池非空」的 clip —— 对每个 clip 调公开 cleanup()；
    2. 仍存活的 webm-reader-* 线程（clip 从未 stop、不在注册表中）：从
       threading 枚举反向定位其 owner clip（reader 线程的 _target 是
       clip._reader 绑定方法，__self__ 即 clip），再调公开 cleanup()。

    每轮 cleanup 后 reap 注册表（有界 join，正常 terminate 后毫秒级退出），
    轮数只作病态场景兜底；仍有存活线程则告警（防线不因自身变红）。
    """
    yield
    import logging
    import threading

    logger = logging.getLogger("pytest.conftest.webm")
    try:
        from pet import webm_clip as webm_clip_mod

        registry = webm_clip_mod._ORPHAN_REGISTRY

        def _clips_with_live_readers():
            clips = set(registry.holders())
            for t in threading.enumerate():
                if t.is_alive() and t.name.startswith("webm-reader-"):
                    owner = getattr(getattr(t, "_target", None), "__self__", None)
                    if owner is not None:
                        clips.add(owner)
            return clips

        for _ in range(5):
            clips = _clips_with_live_readers()
            if not clips:
                break
            for clip in clips:
                try:
                    clip.cleanup()
                except Exception:
                    pass  # clip 已随 Qt C++ 侧销毁等：交由 GC/产品自身兜底
            registry.reap()
        survivors = [
            t.name for t in threading.enumerate()
            if t.is_alive() and t.name.startswith("webm-reader-")
        ]
        if survivors:
            logger.warning(
                "session 结束仍有 %d 个 webm reader 线程存活: %s",
                len(survivors), survivors,
            )
    except Exception:
        pass  # 防线 fixture：任何异常都不应让套件本身变红
    # 会话结束闸门是进程级 latch（issue #111）：在最靠后的收口点再复位一次，
    # 保证无论哪个用例置位过都不会串到后续用例（那会让 reader 静默拒绝启动，
    # 报错点离真因很远）。
    try:
        from pet import webm_clip as _webm_clip_mod
        _webm_clip_mod._reset_session_ending_for_tests()
    except Exception:
        pass
