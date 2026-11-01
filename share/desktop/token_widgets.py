"""Today's real local token usage, shown in the compact status card."""
from datetime import date
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QPushButton, QStyle, QStyleOptionButton
from .token_report import compact_tokens


def today_usage(report, today=None):
    return ((report or {}).get('days') or {}).get((today or date.today()).isoformat()) or {}


class TodayTokens(QPushButton):
    activated = Signal()

    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self.report = None
        self.setObjectName('today_tokens')
        self.setFixedHeight(20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f'QPushButton#today_tokens{{background:{theme.footer};border:0;'
                           f'border-radius:9px;padding:0 8px;color:{theme.stat};text-align:left;font-size:11px;}}'
                           f'QPushButton#today_tokens:hover{{background:{theme.soft};}}')
        self.clicked.connect(self.activated)
        self.refresh()

    def set_report(self, report):
        if report is not None and not report.get('error'):
            self.report = report
        self.refresh()
        if report and report.get('error'):
            self.setToolTip('统计暂不可用，保留上次记录；点击查看今日小时用量')

    def refresh(self, today=None):
        record = today_usage(self.report, today)
        total = compact_tokens(record.get('total', 0)) if self.report is not None else '—'
        self.setText(f'今日 Token {total} · 24h')
        self.amount = total
        self.setAccessibleName(f'今日 Token {total}，查看 24 小时用量')
        self.setToolTip('点击查看今日每小时 Token 用量')

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ''
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)
        painter.setPen(QColor(self.theme.primary))
        painter.drawText(QRectF(8, 0, 72, self.height()), Qt.AlignmentFlag.AlignVCenter, '今日 Token')
        painter.setPen(QColor(self.theme.ink))
        painter.drawText(QRectF(79, 0, max(1, self.width()-128), self.height()), Qt.AlignmentFlag.AlignVCenter, self.amount)
        painter.setPen(QColor(self.theme.primary))
        painter.drawText(QRectF(self.width()-48, 0, 40, self.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, '24h ›')
