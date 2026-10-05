"""Locate the pet window for the independent settings process."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

def standalone_pet_geometry(config):
    """读配置目录 runtime 状态文件，返回一只活桌宠窗口的几何矩形。

    设置进程没有 parent 窗口可读几何，只能取桌宠自己留下的运行时标记。
    ``slot_manager.read_live_instances`` 同时认 ``pet-runtime-v2-*.json``（多窗）
    与旧 ``runtime-*.json``，并顺手清掉死进程/损坏的标记。读不到返回 None，
    调用方保持默认位置（不许因为读文件失败而崩）。
    """
    from PySide6.QtCore import QRect

    from . import slot_manager as slot_manager_mod

    try:
        instances = slot_manager_mod.read_live_instances(config.dir)
    except Exception:
        logger.debug("读取桌宠运行时标记失败", exc_info=True)
        return None
    for _pid, x, y, w, h in instances:
        if w > 0 and h > 0:
            return QRect(int(x), int(y), int(w), int(h))
    return None
