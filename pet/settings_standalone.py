"""Visual reminder previews and placement for the settings process."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

def show_transient_notice(text: str) -> None:
    """独立设置进程内的可见反馈：瞬时 tooltip（非模态、不阻塞、无需点确认）。

    设置进程没有桌宠气泡可挂，模态 QMessageBox 又会卡住预览期间的界面，
    tooltip 是这里最轻的"一定看得见"通道。
    """
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QToolTip

    try:
        QToolTip.showText(QCursor.pos(), str(text))
    except Exception:
        logger.debug("独立设置进程提示展示失败", exc_info=True)

class _StandaloneHost:
    def __init__(self, config):
        self.config = config
        self.win = None
        self._festival = None

    def system_notify(self, title, message, **kwargs):
        show_transient_notice(message)

    def festival_service(self):
        if self._festival is None:
            from .festival_service import FestivalReminderService
            self._festival = FestivalReminderService(self)
        return self._festival

    def shutdown(self):
        if self._festival is not None:
            self._festival.stop()

def preview_festival(dialog) -> None:
    """节日设置页「立即预览」：本地演示今日节日（气泡文案）。"""
    host = getattr(dialog, "_standalone_host", None)
    if host is None:
        return
    host.festival_service().remind_now()

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

def install_standalone_hooks(dialog) -> None:
    if getattr(dialog, "_standalone_host", None) is not None:
        return
    host = _StandaloneHost(dialog.config)
    dialog._standalone_host = host
    dialog.on_festival_now = lambda: preview_festival(dialog)
    dialog.finished.connect(lambda _result: host.shutdown())
