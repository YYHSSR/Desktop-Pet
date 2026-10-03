# -*- coding: utf-8 -*-
"""针对第二轮审查（desktop-pet-第二轮深度审查与提速方案-2026-09-28）优化的自动化测试。

测试覆盖：
1. ByteBudgetLru 多线程高并发访问下的线程安全（无 KeyError，字节记账一致）；
2. 磁盘缓存包含损坏/非数值字段（frames/duration 异常）时优雅降级，不崩溃；
3. 相同素材的在飞元数据探测自动去重，多个并发调用只触发 1 次 FFmpeg 探测；
4. 估算元数据（_duration > 0, exact=False）能被 warm_meta() 成功升级为精确帧数；
5. _PopenCapture 成功捕获 check_output 子进程并接入 Job 孤儿防护与超时。
"""
from __future__ import annotations

import math
import sys
import threading
import time
import types
from pathlib import Path

from PySide6.QtWidgets import QApplication

import pet.frame_cache as frame_cache
import pet.webm_clip as webm_clip


def test_byte_budget_lru_concurrent_access():
    """验证 ByteBudgetLru 内部短锁在多线程高并发读写下保证原子性与预算一致。"""
    cache = frame_cache.ByteBudgetLru(max_bytes=1024)
    errors: list[Exception] = []
    stop_event = threading.Event()

    def _worker(worker_id: int):
        for i in range(200):
            if stop_event.is_set():
                break
            key = f"key_{worker_id}_{i % 20}"
            try:
                cache.put(key, f"val_{i}", byte_size=32)
                cache.get(key)
                if i % 10 == 0:
                    cache.pop(key)
                if i % 50 == 0:
                    _ = len(cache)
                    _ = cache.total_bytes()
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"并发访问发生异常: {errors}"
    assert cache.total_bytes() <= cache.max_bytes()


def test_ensure_meta_handles_invalid_cache_entry_gracefully(tmp_path, monkeypatch):
    """验证损坏的缓存字段（如非整数、NaN、负数）被安全拦截并当作 cache miss 处理。"""
    _app = QApplication.instance() or QApplication([])

    calls: list[str] = []
    fake = types.SimpleNamespace(count_frames_and_secs=lambda path: calls.append(str(path)) or (60, 2.5))
    monkeypatch.setattr(webm_clip, "imageio_ffmpeg", fake)
    monkeypatch.setattr(webm_clip, "_META_CACHE", frame_cache.ByteBudgetLru(10000))

    video = tmp_path / "test_corrupt.webm"
    video.write_bytes(b"dummy")

    st = video.stat()
    cache_key = f"{video}|{st.st_mtime_ns}|{st.st_size}"

    # 注入含有毒数据的磁盘缓存条目
    corrupt_cache = {
        cache_key: {"frames": "not-an-int", "duration": "invalid-float"}
    }
    monkeypatch.setattr(webm_clip, "_get_meta_file_cache", lambda: corrupt_cache)

    clip = webm_clip.WebMClip(video)
    # 调用 warm_meta 不应抛出 ValueError，而应优雅回退到探测
    clip.warm_meta()

    assert len(calls) == 1
    assert clip.frameCount() == 60
    assert clip.duration() == 2.5
    assert clip._frame_count_exact is True


def test_ensure_meta_inflight_deduplication(tmp_path, monkeypatch):
    """验证相同资源的在飞元数据探测自动合并，多线程并发只产生 1 次探测。"""
    _app = QApplication.instance() or QApplication([])

    probe_count = 0
    probe_lock = threading.Lock()
    barrier = threading.Barrier(3)

    def slow_probe(path):
        nonlocal probe_count
        with probe_lock:
            probe_count += 1
        time.sleep(0.05)  # 模拟探针耗时
        return (48, 2.0)

    fake = types.SimpleNamespace(count_frames_and_secs=slow_probe)
    monkeypatch.setattr(webm_clip, "imageio_ffmpeg", fake)
    monkeypatch.setattr(webm_clip, "_META_CACHE", frame_cache.ByteBudgetLru(10000))
    monkeypatch.setattr(webm_clip, "_get_meta_file_cache", lambda: {})

    video = tmp_path / "shared.webm"
    video.write_bytes(b"content")

    clips = [webm_clip.WebMClip(video) for _ in range(3)]

    def _warm(c):
        barrier.wait()
        c.warm_meta()

    threads = [threading.Thread(target=_warm, args=(c,)) for c in clips]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 3 个 clip 并发请求同一文件，探测应仅执行 1 次
    assert probe_count == 1
    for c in clips:
        assert c.frameCount() == 48
        assert c.duration() == 2.0
        assert c._frame_count_exact is True


def test_exact_meta_upgrade_from_estimated_duration(tmp_path, monkeypatch):
    """验证 reader 填入估算元数据后，warm_meta() 能成功补齐精确帧数（exact 升级）。"""
    _app = QApplication.instance() or QApplication([])

    calls = []
    fake = types.SimpleNamespace(count_frames_and_secs=lambda path: calls.append(str(path)) or (120, 5.0))
    monkeypatch.setattr(webm_clip, "imageio_ffmpeg", fake)
    monkeypatch.setattr(webm_clip, "_META_CACHE", frame_cache.ByteBudgetLru(10000))
    monkeypatch.setattr(webm_clip, "_get_meta_file_cache", lambda: {})

    video = tmp_path / "anim.webm"
    video.write_bytes(b"dummy")

    clip = webm_clip.WebMClip(video)
    # 模拟 reader 刚从流头读到非精确数据
    clip._duration = 5.0
    clip._frame_count = 100
    clip._frame_count_exact = False

    # warm_meta() 应不被 _duration > 0 短路，触发精确探测
    clip.warm_meta()

    assert len(calls) == 1
    assert clip.frameCount() == 120
    assert clip._frame_count_exact is True


def test_popen_capture_intercepts_check_output(monkeypatch):
    """验证 _PopenCapture 上下文能够透明拦截 check_output 并记录子进程。"""
    webm_clip._PopenCapture._installed = False
    webm_clip._PopenCapture._install()

    io_mod = sys.modules.get("imageio_ffmpeg._io")
    assert io_mod is not None

    with webm_clip._PopenCapture() as cap:
        out = io_mod.subprocess.check_output([sys.executable, "-c", "print('hello_from_capture')"])
        assert b"hello_from_capture" in out
        assert cap.process is not None
        assert len(cap._procs) >= 1


def test_ensure_meta_waiter_timeout_does_not_steal_ownership(tmp_path, monkeypatch):
    """F06 回归：等待方超时后不得执行探测，亦不得注销原持有者的在飞 Event。"""
    owner_started = threading.Event()
    owner_finish = threading.Event()
    probe_calls = []

    def blocking_probe(path):
        probe_calls.append("owner")
        owner_started.set()
        owner_finish.wait(timeout=2.0)
        return (60, 2.0)

    fake = types.SimpleNamespace(count_frames_and_secs=blocking_probe)
    monkeypatch.setattr(webm_clip, "imageio_ffmpeg", fake)
    monkeypatch.setattr(webm_clip, "_META_CACHE", frame_cache.ByteBudgetLru(10000))
    monkeypatch.setattr(webm_clip, "_get_meta_file_cache", lambda: {})

    video = tmp_path / "test_timeout.webm"
    video.write_bytes(b"content")

    clip_owner = webm_clip.WebMClip(video)
    clip_waiter = webm_clip.WebMClip(video)

    owner_thread = threading.Thread(target=clip_owner.warm_meta)
    owner_thread.start()
    assert owner_started.wait(timeout=1.0) is True

    # 模拟等待方：通过 monkeypatch 把 Event.wait 的超时拦截或快速返回
    orig_wait = threading.Event.wait
    def short_wait(self, timeout=None):
        return orig_wait(self, timeout=0.01)

    monkeypatch.setattr(threading.Event, "wait", short_wait)

    # 等待方调用 warm_meta，超时后立即退出，绝不产生二次探测
    clip_waiter.warm_meta()
    assert len(probe_calls) == 1

    st = video.stat()
    cache_key = f"{str(video)}|{st.st_mtime_ns}|{st.st_size}"

    # 确认在飞事件仍归原 owner 所有（未被 waiter 误删）
    with webm_clip._IN_FLIGHT_META_LOCK:
        assert cache_key in webm_clip._IN_FLIGHT_META_EVENTS

    # 释放 owner 结束探测
    owner_finish.set()
    owner_thread.join(timeout=2.0)

    # 此时 owner 正常清理
    with webm_clip._IN_FLIGHT_META_LOCK:
        assert cache_key not in webm_clip._IN_FLIGHT_META_EVENTS
