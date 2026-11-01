"""Shared building blocks for the Claude and Gemini companion cards.

Each card keeps its own look (QSS and a Palette for painted pieces); this
module only supplies structure: the current-page stack, compact settings
sections behind a segmented switch, and a seven-day history chart.
"""
from dataclasses import dataclass
from PySide6.QtCore import Qt, QRectF, QSize, Signal, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFontMetrics
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSlider, QStackedWidget, QVBoxLayout, QWidget)

WEEKDAYS = '一二三四五六日'


@dataclass(frozen=True)
class Palette:
    accent: str
    accent_soft: str
    text: str
    muted: str
    track: str
    surface: str
    hover: str
    tile: str = '#f5f2f7'


def label(text, role=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if role:
        widget.setProperty('role', role)
    return widget


def button(text, callback, name=None, tooltip=None):
    widget = QPushButton(text)
    if name:
        widget.setObjectName(name)
    if tooltip:
        widget.setToolTip(tooltip)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(callback)
    return widget


class CurrentPageStack(QStackedWidget):
    """A stack whose size follows the visible page, not the tallest one."""
    def sizeHint(self):
        return self.currentWidget().sizeHint() if self.currentWidget() else QSize(260, 120)

    def minimumSizeHint(self):
        return self.currentWidget().minimumSizeHint() if self.currentWidget() else QSize(100, 100)

    def hasHeightForWidth(self):
        return bool(self.currentWidget() and self.currentWidget().hasHeightForWidth())

    def heightForWidth(self, width):
        page = self.currentWidget()
        if page is None:
            return 100
        return page.heightForWidth(width) if page.hasHeightForWidth() else page.sizeHint().height()


class Segmented(QWidget):
    """A small pill switch: 常规 / 动作 / 角色."""
    changed = Signal(int)

    def __init__(self, titles, palette):
        super().__init__()
        self.titles, self.palette, self.index = list(titles), palette, 0
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName('设置分类')

    def set_index(self, index):
        if index != self.index:
            self.index = index
            self.update()
            self.changed.emit(index)

    def mousePressEvent(self, event):
        width = self.width()/len(self.titles)
        self.set_index(max(0, min(len(self.titles)-1, int(event.position().x()//width))))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            step = -1 if event.key() == Qt.Key.Key_Left else 1
            self.set_index((self.index+step) % len(self.titles))
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.palette.track))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 11, 11)
        width = self.width()/len(self.titles)
        p.setBrush(QColor(self.palette.surface))
        p.setPen(QPen(QColor(self.palette.accent_soft), 1))
        p.drawRoundedRect(QRectF(self.index*width+2, 2, width-4, self.height()-4), 9, 9)
        font = p.font()
        font.setPixelSize(11)
        p.setFont(font)
        for index, title in enumerate(self.titles):
            p.setPen(QColor(self.palette.accent if index == self.index else self.palette.muted))
            p.drawText(QRectF(index*width, 0, width, self.height()), Qt.AlignmentFlag.AlignCenter, title)


from .settings_panel import SettingsPanel


def grouped_meters(meters):
    """Fold variants with identical numbers ('X · 高', 'X · 中') into one row."""
    rows = []
    for meter in meters:
        family, _, variant = meter.label.partition(' · ')
        for row in rows:
            if (row['family'] == family and row['used'] == meter.used and row['resets_at'] == meter.resets_at
                    and row['estimated'] == meter.estimated):
                if variant:
                    row['variants'].append(variant)
                break
        else:
            rows.append(dict(family=family, variants=[variant] if variant else [], used=meter.used,
                             resets_at=meter.resets_at, estimated=meter.estimated))
    for row in rows:
        row['label'] = row['family'] + (' · ' + '/'.join(row['variants']) if row['variants'] else '')
    return rows


class QuotaBar(QWidget):
    def __init__(self, palette):
        super().__init__()
        self.palette, self.fill, self.warn = palette, 0., False
        self.setFixedHeight(6)

    def set_fill(self, fill, warn=False):
        self.fill, self.warn = max(0., min(1., fill)), warn
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.palette.track))
        p.drawRoundedRect(QRectF(self.rect()), 3, 3)
        if self.fill > 0:
            p.setBrush(QColor('#d0644e' if self.warn else self.palette.accent))
            p.drawRoundedRect(QRectF(0, 0, max(6., self.width()*self.fill), self.height()), 3, 3)


class QuotaPanel(QWidget):
    """The home app's allowance: link status, plan and one bar per meter.

    mode 'used' shows how much is spent (Claude's 5-hour / weekly figures);
    'remaining' shows what is left (Antigravity's per-model quota).
    """
    ROWS = 6

    def __init__(self, palette, mode='used', empty='尚未连接'):
        super().__init__()
        self.palette, self.mode, self.empty = palette, mode, empty
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 0, 3, 0)
        layout.setSpacing(5)
        head = QHBoxLayout()
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        head.addWidget(self.dot)
        self.status = label(empty, 'section')
        head.addWidget(self.status, 1)
        self.plan = label('', 'muted')
        head.addWidget(self.plan)
        layout.addLayout(head)
        self.message = label('', 'muted', True)
        layout.addWidget(self.message)
        self.rows = []
        for _ in range(self.ROWS):
            box = QWidget()
            column = QVBoxLayout(box)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(2)
            line = QHBoxLayout()
            name, value = label(''), label('', 'muted')
            name.setStyleSheet('font-size:11px;')
            line.addWidget(name, 1)
            line.addWidget(value)
            column.addLayout(line)
            bar = QuotaBar(palette)
            column.addWidget(bar)
            box.hide()
            layout.addWidget(box)
            self.rows.append((box, name, value, bar))
        layout.addStretch()
        self.note = label('', 'muted', True)
        layout.addWidget(self.note)
        self.set_snapshot(None)

    def set_dot(self, colour):
        self.dot.setStyleSheet(f'background:{colour};border-radius:4px;')

    def set_snapshot(self, snapshot):
        from .quota import relative_time, reset_text, reset_tooltip
        if snapshot is None:
            self.set_dot('#c9c2bb')
            self.status.setText(self.empty)
            self.plan.setText('')
            self.message.setText('在“设置 · 常规”里打开“读取本机额度”后会显示在这里。')
            self.note.setText('')
            for box, *_ in self.rows:
                box.hide()
            return
        self.set_dot('#5dbb7a' if snapshot.running else ('#e0b25a' if snapshot.connected else '#c9c2bb'))
        self.status.setText(snapshot.source + (' · 运行中' if snapshot.running else ''))
        self.plan.setText(snapshot.plan or '')
        self.message.setText(snapshot.message)
        rows = grouped_meters(snapshot.meters)[:self.ROWS]
        resets = []
        for index, (box, name, value, bar) in enumerate(self.rows):
            if index >= len(rows):
                box.hide()
                continue
            row = rows[index]
            remaining = 1-row['used']
            shown = row['used'] if self.mode == 'used' else remaining
            name.setText(name.fontMetrics().elidedText(row['label'], Qt.TextElideMode.ElideRight, 190))
            name.setToolTip(row['label'])
            value.setText(f'已用 {round(row["used"]*100)}%' if self.mode == 'used' else f'剩 {round(remaining*100)}%')
            bar.set_fill(shown, warn=remaining < .2)
            when = reset_text(row['resets_at'], approx=row['estimated'])
            box.setToolTip(reset_tooltip(row['resets_at'], row['estimated']))
            if when:
                resets.append(when)
            box.show()
        parts = []
        if resets:
            parts.append(min(resets) if len(set(resets)) > 1 else resets[0])
        if snapshot.updated_at:
            parts.append('更新于 ' + relative_time(snapshot.updated_at))
        self.note.setText(' · '.join(parts))


class QuotaChip(QPushButton):
    """Footer shortcut: a small ring with what is left, e.g. 「额度 69%」."""
    def __init__(self, palette):
        super().__init__()
        self.palette, self.left = palette, None
        self.setObjectName('link')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(74, 20)

    def set_left(self, left, tooltip=''):
        self.left = left
        self.setToolTip(tooltip)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QRectF(3, 4, 12, 12)
        p.setPen(QPen(QColor(self.palette.track), 2.4))
        p.drawEllipse(ring)
        if self.left is not None:
            p.setPen(QPen(QColor('#d0644e' if self.left < .2 else self.palette.accent), 2.4,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(ring, 90*16, -round(360*16*self.left))
        font = p.font()
        font.setPixelSize(10)
        p.setFont(font)
        p.setPen(QColor(self.palette.accent))
        text = '额度 —' if self.left is None else f'额度 {round(self.left*100)}%'
        p.drawText(QRectF(19, 0, self.width()-19, self.height()), Qt.AlignmentFlag.AlignVCenter, text)


class HistoryBars(QWidget):
    """Seven days of focus minutes; today is highlighted, empty days stay as ticks."""
    def __init__(self, palette, unit='分钟'):
        super().__init__()
        self.palette, self.unit = palette, unit
        self.days = []
        self.setMinimumHeight(86)
        self.setMouseTracking(True)

    def set_days(self, days):
        """days: [(date, sessions, minutes)] oldest first."""
        days = list(days)
        if days != self.days:
            self.days = days
            self.update()

    def bar_rects(self):
        if not self.days:
            return []
        top, bottom = 14, self.height()-16
        step = self.width()/len(self.days)
        peak = max(1, max(minutes for _, _, minutes in self.days))
        rects = []
        for index, (_, sessions, minutes) in enumerate(self.days):
            width = min(18, step*.55)
            height = max(3, (bottom-top)*minutes/peak) if minutes else 3
            rects.append(QRectF(step*(index+.5)-width/2, bottom-height, width, height))
        return rects

    def mouseMoveEvent(self, event):
        for (day, sessions, minutes), rect in zip(self.days, self.bar_rects()):
            if rect.adjusted(-6, -40, 6, 16).contains(event.position()):
                self.setToolTip(f'{day.month}月{day.day}日 · {sessions} 轮 · {minutes} {self.unit}')
                return
        self.setToolTip('')

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bottom = self.height()-16
        p.setPen(QPen(QColor(self.palette.track), 1))
        p.drawLine(QPointF(0, bottom+.5), QPointF(self.width(), bottom+.5))
        font = p.font()
        font.setPixelSize(9)
        p.setFont(font)
        metrics = QFontMetrics(font)
        last = len(self.days)-1
        if not any(minutes for _, _, minutes in self.days):
            p.setPen(QColor(self.palette.muted))
            p.drawText(QRectF(0, 0, self.width(), bottom-6), Qt.AlignmentFlag.AlignCenter, '还没有记录，从第一轮专注开始吧')
        for index, ((day, sessions, minutes), rect) in enumerate(zip(self.days, self.bar_rects())):
            today = index == last
            p.setPen(Qt.PenStyle.NoPen)
            colour = QColor(self.palette.accent if today else self.palette.accent_soft)
            if not minutes:
                colour = QColor(self.palette.track)
            p.setBrush(colour)
            p.drawRoundedRect(rect, 3, 3)
            if minutes:
                p.setPen(QColor(self.palette.muted))
                text = str(minutes)
                p.drawText(QRectF(rect.center().x()-20, rect.top()-13, 40, 12), Qt.AlignmentFlag.AlignCenter, text)
            p.setPen(QColor(self.palette.accent if today else self.palette.muted))
            name = '今' if today else WEEKDAYS[day.weekday()]
            p.drawText(QRectF(rect.center().x()-12, bottom+3, 24, metrics.height()), Qt.AlignmentFlag.AlignCenter, name)
