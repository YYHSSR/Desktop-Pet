# -*- coding: utf-8 -*-
"""节日气泡提醒服务：GUI 线程定时采样、按分钟去重、启动补提醒和手动预览。"""

from __future__ import annotations

import logging
from datetime import date, datetime

from .festival import (
    NO_FESTIVAL_TEXT,
    build_festival_text,
    normalize_festival_config,
    reminder_slot,
    startup_slot,
)
logger = logging.getLogger(__name__)


class FestivalReminderService:
    """节日提醒服务（AppShell 持有，GUI 线程）。"""

    TICK_INTERVAL_MS = 30_000
    BUBBLE_DURATION_MS = 12_000

    def __init__(self, app) -> None:
        from PySide6.QtCore import QTimer

        self._app = app
        # 契约形状由纯逻辑层定义（enabled/cn/solar_terms/west/mode/count/times/...）
        self._cfg: dict = normalize_festival_config(None)
        # 当天已触发的槽位；跨天自动清空（槽位本身含日期，这里只是防集合无界增长）
        self._slot_day: date | None = None
        self._fired: set[str] = set()
        self._timer = QTimer()
        self._timer.setInterval(self.TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

    # ------------------------------------------------------------ 生命周期
    def start(self) -> None:
        self.apply_config()
        self._catch_up()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def is_running(self) -> bool:
        """调度 tick 是否在跑（AppShell 的懒启停门控据此决定重启还是只刷配置）。"""
        return bool(self._timer.isActive())

    def apply_config(self) -> None:
        """重读配置。

        统一走纯逻辑层 normalize_festival_config：清洗/钳制只有一处实现，
        且 config.json 被手改成非法值时回落默认而不是抛异常（本方法在
        start() 路径上执行，抛异常等于功能在启动期直接失败）。
        """
        config = getattr(self._app, "config", None)
        self._cfg = normalize_festival_config(config if config is not None else {})

    # ------------------------------------------------------------ 对外入口
    def remind_now(self) -> None:
        """手动提醒「今日节日」（右键菜单入口）。

        **无视总开关**，由用户主动发起即执行；
        当天没有任何节日/节气时给出明确文案而不是静默无反应。
        """
        self.apply_config()
        now = datetime.now()
        text = build_festival_text(now.date(), self._cfg, 0) or NO_FESTIVAL_TEXT
        self._bubble(text)


    # ------------------------------------------------------------ 调度
    def _catch_up(self, now: datetime | None = None) -> None:
        """启动补提醒：当天有节日且已过首个提醒点时，立即补报一次。

        桌宠不保证常驻，用户可能中午才开机；没有这一步，当天的提醒点
        全部错过后就再也收不到，功能体感等于失效。

        ``now`` 可注入（同 ``_on_tick``）：调用方传 ``None`` 即取当前时刻，
        便于用例覆盖"恰好在提醒分钟内启动"这条只有真机重启才会踩到的路径。
        """
        now = now or datetime.now()
        slot = startup_slot(now, self._cfg)
        if not slot or slot in self._fired:
            return
        self._roll_day(now.date())
        self._fired.add(slot)
        text = build_festival_text(now.date(), self._cfg, 0)
        if text:
            self._bubble(text)
            # 启动时刻恰好落在当天的某个提醒分钟内：把本分钟的正式槽位一并
            # 盖戳。否则紧接着的 _on_tick 会命中同一分钟再播一次（两次气泡 +
            # 只压这一分钟——晚些时候的提醒点仍走各自的正式槽位照常播报。
            due = reminder_slot(now, self._cfg)
            if due:
                self._fired.add(due)

    def _on_tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now()
        if not self._cfg.get("enabled"):
            return
        self._roll_day(now.date())
        slot = reminder_slot(now, self._cfg)
        if not slot or slot in self._fired:
            return
        self._fired.add(slot)
        # 当天第几次提醒：作为文案索引，使同一天多次提醒轮到不同句子。
        index = len(self._fired) - 1
        text = build_festival_text(now.date(), self._cfg, index)
        if text:
            self._bubble(text)

    def _roll_day(self, today: date) -> None:
        if self._slot_day != today:
            self._slot_day = today
            self._fired = set()


    # ------------------------------------------------------------ 提示
    def _bubble(self, text: str) -> None:
        """桌宠气泡展示节日提醒。

        设置窗口打开等场景下 ``win.show_bubble`` 会被抑制，
        而节日提醒是用户主动关注的事件（一天只有一两次），此时退到桌宠气泡位
        直接展示，避免"弹一下就没了"；两者都不可用时再退到系统通知。
        """
        if not text:
            return
        app = self._app
        win = getattr(app, "win", None)
        if win is not None and win.isVisible():
            suppressed = bool(getattr(win, "_bubble_suppressed", False))
            if not suppressed:
                try:
                    win.show_bubble(text, duration_ms=self.BUBBLE_DURATION_MS)
                    return
                except Exception:
                    logger.exception("节日提醒气泡展示失败")
            try:
                bubble = getattr(win, "_speech_bubble", None)
                rect = win.visible_content_rect()
                scale = getattr(win, "scale", 1.0)
                if bubble is not None and rect is not None:
                    bubble.show_text(
                        text,
                        rect,
                        self.BUBBLE_DURATION_MS,
                        pet_scale=scale,
                        subtitle="",
                    )
                    return
            except Exception:
                logger.exception("节日提醒气泡降级展示失败")
        notify = getattr(app, "system_notify", None)
        if callable(notify):
            try:
                notify("节日提醒", text)
            except Exception:
                logger.exception("节日提醒桌面通知失败")
