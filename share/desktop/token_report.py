"""Local token statistics and hourly chart for the Claude and Gemini cards.

Each character supplies a TokenSource that reads files its home app already
keeps (Claude Code transcripts, Antigravity conversation databases). The
ledger caches per-file tallies, so a refresh only re-reads files that grew or
changed, and it runs on a background thread. Nothing is sent anywhere.

A tally is plain JSON: {'YYYY-MM-DD': {'hours': [24 ints], 'models':
{model: [input, cache_write, cache_read, output, messages]}, 'sessions': [ids]}}.
"""
from datetime import datetime
import json
import threading
import time
from pathlib import Path
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget
from .companion_state import atomic_json

PARTS = ('输入', '缓存写入', '缓存读取', '输出')
CACHE_VERSION = 1
WEEKDAYS = '一二三四五六日'


# ---- tallies ----
def add(days, moment, model, parts, session=None):
    """Count one model reply: parts = (input, cache_write, cache_read, output)."""
    day = days.setdefault(moment.strftime('%Y-%m-%d'), {'hours': [0]*24, 'models': {}, 'sessions': []})
    day['hours'][moment.hour] += sum(parts)
    row = day['models'].setdefault(model, [0, 0, 0, 0, 0])
    for index, value in enumerate(parts):
        row[index] += int(value)
    row[4] += 1
    if session and session not in day['sessions']:
        day['sessions'].append(session)


def merge(target, days):
    for key, day in days.items():
        into = target.setdefault(key, {'hours': [0]*24, 'models': {}, 'sessions': set()})
        into['hours'] = [a+b for a, b in zip(into['hours'], day['hours'])]
        for model, row in day['models'].items():
            have = into['models'].setdefault(model, [0, 0, 0, 0, 0])
            into['models'][model] = [a+b for a, b in zip(have, row)]
        into['sessions'].update(day['sessions'])


def compact_tokens(value):
    value = int(value or 0)
    for size, unit in ((10**9, 'B'), (10**6, 'M'), (10**3, 'K')):
        if value >= size:
            text = f'{value/size:.1f}'.rstrip('0').rstrip('.')
            return text+unit
    return str(value)


def summarize(days, source, now=None):
    """The usage snapshot the card shows, from merged tallies."""
    now = now or datetime.now()
    out, sessions, models = {}, set(), {}
    for key, day in days.items():
        totals = {model: sum(row[:4]) for model, row in day['models'].items()}
        parts = [sum(row[i] for row in day['models'].values()) for i in range(4)]
        out[key] = dict(total=sum(totals.values()), hours=list(day['hours']), models=totals, parts=parts,
                        messages=sum(row[4] for row in day['models'].values()), sessions=len(day['sessions']))
        sessions.update(day['sessions'])
        for model, total in totals.items():
            models[model] = models.get(model, 0)+total
    return dict(source=source, updated=now, days=out, sessions=len(sessions),
                active_days=sum(1 for day in out.values() if day['total']),
                total=sum(day['total'] for day in out.values()),
                messages=sum(day['messages'] for day in out.values()),
                favorite=max(models, key=models.get) if models else None, models=models)


class TokenSource:
    """Override files() and scan(); scan returns a new cache entry with 'days'."""
    NAME = ''
    NOTE = ''

    def files(self):
        return []

    def scan(self, path, previous, stop):
        raise NotImplementedError


class TokenLedger:
    def __init__(self, source, cache_path):
        self.source = source
        self.cache_path = Path(cache_path)
        self.entries = None

    def load(self):
        try:
            data = json.loads(self.cache_path.read_text(encoding='utf-8'))
            if data.get('version') == CACHE_VERSION and data.get('source') == self.source.NAME:
                return dict(data.get('files') or {})
        except (OSError, ValueError, AttributeError):
            pass
        return {}

    def refresh(self, stop=None):
        stop = stop or threading.Event()
        if self.entries is None:
            self.entries = self.load()
        entries, changed = {}, False
        for path in self.source.files():
            if stop.is_set():
                return None
            try:
                status = path.stat()
            except OSError:
                continue
            key, signature = str(path), [status.st_size, status.st_mtime_ns]
            previous = self.entries.get(key)
            if previous is not None and previous.get('sig') == signature:
                entries[key] = previous
                continue
            try:
                entry = self.source.scan(path, previous, stop)
            except Exception:  # one unreadable file must not hide the rest
                entry = previous
            if entry is None:
                continue
            entry['sig'] = signature
            entries[key] = entry
            changed = True
        changed = changed or set(entries) != set(self.entries)
        self.entries = entries
        if changed:
            try:
                atomic_json(self.cache_path, dict(version=CACHE_VERSION, source=self.source.NAME, files=entries))
            except OSError:
                pass
        days = {}
        for entry in entries.values():
            merge(days, entry.get('days') or {})
        report = summarize(days, self.source.NAME)
        report['files'] = len(entries)
        return report


class TokenWatcher(QObject):
    """Refresh on a background thread; deliver the report on the GUI thread."""
    changed = Signal(object)
    _done = Signal(object)

    def __init__(self, source, cache_path, interval_ms=10*60*1000, parent=None):
        super().__init__(parent)
        self.ledger = TokenLedger(source, cache_path)
        self.report = None
        self.thread = None
        self.stopping = threading.Event()
        self.pending = False
        self.last = 0.
        self._done.connect(self.finished, Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.refresh)

    def start(self):
        self.refresh()
        self.timer.start()

    def request(self, min_gap=60.):
        """A refresh unless one just happened (opening the report page)."""
        if time.monotonic()-self.last >= min_gap:
            self.refresh()

    def refresh(self):
        if self.stopping.is_set():
            return
        if self.thread is not None and self.thread.is_alive():
            self.pending = True
            return
        self.last = time.monotonic()
        self.thread = threading.Thread(target=self.work, name='token-report', daemon=True)
        self.thread.start()

    def work(self):
        try:
            report = self.ledger.refresh(self.stopping)
        except Exception as error:  # never take the pet down
            report = dict(source=self.ledger.source.NAME, error=type(error).__name__, days={}, updated=datetime.now())
        if report is not None and not self.stopping.is_set():
            self._done.emit(report)

    def finished(self, report):
        self.report = report
        self.changed.emit(report)
        if self.pending:
            self.pending = False
            self.refresh()

    def stop(self):
        self.stopping.set()
        self.timer.stop()

    def wait(self, timeout=2.):
        if self.thread is not None:
            self.thread.join(timeout)


# ---- report page widgets ----
def smooth_path(points):
    path = QPainterPath(points[0])
    for a, b in zip(points, points[1:]):
        middle = (a.x()+b.x())/2
        path.cubicTo(QPointF(middle, a.y()), QPointF(middle, b.y()), b)
    return path


class HourChart(QWidget):
    """Tokens per hour as a soft area curve; hovering reads an hour out."""
    hovered = Signal(str)

    def __init__(self, palette, compact=False):
        super().__init__()
        self.compact = compact
        self.palette, self.values, self.hover = palette, [0]*24, None
        self.setMinimumHeight(118)
        self.setMaximumHeight(220)
        self.setMouseTracking(True)

    def set_values(self, values):
        values = list(values or [0]*24)
        if values != self.values:
            self.values = values
            self.update()

    def plot(self):
        left, top = (3, 3) if self.compact else (34, 8)
        return QRectF(left, top, max(1, self.width()-left-6), max(1, self.height()-top-18))

    def points(self):
        area, peak = self.plot(), max(1, max(self.values))
        step = area.width()/23
        return [QPointF(area.left()+i*step, area.bottom()-area.height()*v/peak) for i, v in enumerate(self.values)]

    def mouseMoveEvent(self, event):
        area = self.plot()
        hour = round((event.position().x()-area.left())/(area.width()/23))
        hour = max(0, min(23, hour))
        if hour != self.hover:
            self.hover = hour
            self.hovered.emit(f'{hour:02}:00–{hour+1:02}:00 · {compact_tokens(self.values[hour])} Token')
            self.update()

    def leaveEvent(self, event):
        self.hover = None
        self.hovered.emit('')
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area, peak = self.plot(), max(self.values)
        font = p.font()
        font.setPixelSize(8 if self.compact else 9)
        p.setFont(font)
        for fraction in ((0,) if self.compact else ((0, .5, 1) if peak else (0,))):
            y = area.bottom()-area.height()*fraction
            p.setPen(QPen(QColor(self.palette.track), 1, Qt.PenStyle.DashLine if fraction else Qt.PenStyle.SolidLine))
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QColor(self.palette.muted))
            p.drawText(QRectF(0, y-7, area.left()-5, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       compact_tokens(round(peak*fraction)))
        for hour in ((0, 12, 23) if self.compact else (0, 6, 12, 18, 23)):
            x = area.left()+area.width()*hour/23
            width = 20 if self.compact else 28
            x = max(0, min(self.width()-width, x-width/2))
            text = ('00时' if hour == 0 else '24时' if hour == 23 else '12') if self.compact else f'{hour:02}'
            p.drawText(QRectF(x, area.bottom()+3, width, 12), Qt.AlignmentFlag.AlignCenter, text)
        if not peak:
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, '暂无记录' if self.compact else '这一天还没有 Token 记录')
            return
        points = self.points()
        line = smooth_path(points)
        fill = QPainterPath(line)
        fill.lineTo(points[-1].x(), area.bottom())
        fill.lineTo(points[0].x(), area.bottom())
        fill.closeSubpath()
        gradient = QLinearGradient(0, area.top(), 0, area.bottom())
        top = QColor(self.palette.accent)
        top.setAlphaF(.32)
        bottom = QColor(self.palette.accent)
        bottom.setAlphaF(.02)
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, bottom)
        p.fillPath(fill, gradient)
        p.setPen(QPen(QColor(self.palette.accent), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(line)
        if self.hover is not None:
            point = points[self.hover]
            p.setPen(QPen(QColor(self.palette.accent_soft), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(point.x(), area.top()), QPointF(point.x(), area.bottom()))
            p.setPen(QPen(QColor(self.palette.surface), 2))
            p.setBrush(QColor(self.palette.accent))
            p.drawEllipse(point, 4, 4)
