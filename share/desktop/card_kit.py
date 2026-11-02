"""Shared building blocks for the Claude and Gemini companion cards.

Each card keeps its own look (QSS and a Palette for painted pieces); this
module only supplies structure: the current-page stack, compact settings
sections behind a segmented switch, and a seven-day history chart.
"""
from dataclasses import dataclass
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

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


