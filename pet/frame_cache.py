# -*- coding: utf-8 -*-
"""字节预算 + LRU 的通用小缓存（ByteBudgetLru）。

供 webm_clip 等「字节预算 + LRU」的进程内小缓存使用。纯 Python 实现，
不依赖 Qt。
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any


class ByteBudgetLru:
    """通用「字节预算 + LRU」缓存。

    - 字节预算为硬上界：put/``__setitem__`` 后超限逐出最久未用（LRU），
      任何时刻 ``total_bytes() <= max_bytes()``（len>1 守卫防止逐空）；
    - 单条超预算不入缓存（防大条目独占预算造成小条目插入后立即被逐出的
      抖动）；
    - get() 命中刷新 LRU 序；key/value 可为任意可哈希对象与值；
    - 缺省字节按 ``len(key) + 128`` 保守估算（key 需支持 len()，为 str
      键场景设计；其它键请显式传 byte_size）。

    线程安全：内部持有短锁保护所有读写操作，杜绝并发 get 与逐出时的 KeyError。
    """

    _OVERHEAD_ESTIMATE = 128

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max(1, int(max_bytes))
        # key -> (value, byte_size)：逐条记账，替换/逐出时按各自字节扣减
        self._data: OrderedDict[Any, tuple[Any, int]] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def get(self, key):
        """取条目并刷新 LRU 序；未命中返回 None。"""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            try:
                self._data.move_to_end(key)
            except KeyError:
                return None
            return entry[0]

    def put(self, key, value, byte_size: int | None = None) -> None:
        """插入/替换条目（等价 ``cache[key] = value``，可显式给字节数）。

        缺省按 ``len(key) + 128`` 保守估算。单条超预算不入缓存（防御性
        移除同 key 旧条目，绝不留下按旧记账的陈旧条目）；超限后逐出
        最久未用，预算为硬上界。
        """
        if byte_size is None:
            byte_size = len(key) + self._OVERHEAD_ESTIMATE
        byte_size = max(1, int(byte_size))
        with self._lock:
            old = self._data.pop(key, None)
            if old is not None:
                self._bytes -= old[1]
            if byte_size > self._max_bytes:
                return  # 超预算条目不缓存（同 key 旧条目已在上面移除）
            self._data[key] = (value, byte_size)
            self._bytes += byte_size
            while self._bytes > self._max_bytes and len(self._data) > 1:
                _, victim = self._data.popitem(last=False)
                self._bytes -= victim[1]

    def __setitem__(self, key, value) -> None:
        self.put(key, value)

    def pop(self, key, default=None):
        """移除条目并返回其值；不存在返回 default。"""
        with self._lock:
            entry = self._data.pop(key, None)
            if entry is None:
                return default
            self._bytes -= entry[1]
            return entry[0]

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._bytes = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __contains__(self, key) -> bool:
        with self._lock:
            return key in self._data

    def __iter__(self):
        """迭代 key（dict 兼容；审计/调试用）。"""
        with self._lock:
            return iter(list(self._data.keys()))

    def keys(self):
        with self._lock:
            return list(self._data.keys())

    def total_bytes(self) -> int:
        with self._lock:
            return self._bytes

    def max_bytes(self) -> int:
        return self._max_bytes
