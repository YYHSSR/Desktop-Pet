"""Read-only quota snapshots from a companion's home application.

Each character supplies a reader that turns local files the desktop app
already keeps into a QuotaSnapshot. Nothing here signs in, sends network
requests or touches tokens; a missing or unreadable source just reports
"not connected". The watcher polls cheaply and only re-reads when the
source file changes.
"""
from dataclasses import dataclass, field
from datetime import datetime
import math
import os
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, Signal


@dataclass(frozen=True)
class Meter:
    label: str
    used: float                      # 0..1 of the allowance already spent
    resets_at: datetime | None = None
    estimated: bool = False          # resets_at was inferred, not reported

    @property
    def remaining(self):
        return max(0., 1.-self.used)


@dataclass(frozen=True)
class QuotaSnapshot:
    source: str
    connected: bool = False
    running: bool | None = None      # is the home app open right now
    message: str = ''
    meters: tuple = ()
    plan: str | None = None
    updated_at: datetime | None = None
    extra: dict = field(default_factory=dict, compare=False)

    def meter(self, label):
        return next((m for m in self.meters if m.label == label), None)

    @property
    def lowest_remaining(self):
        return min((m.remaining for m in self.meters), default=None)


def newest(paths):
    """The most recently written existing file among candidates."""
    found = [Path(p) for p in paths if p and Path(p).is_file()]
    return max(found, key=lambda p: p.stat().st_mtime, default=None)


def expand(pattern):
    """Expand %VARS% and a single '*' directory wildcard."""
    pattern = os.path.expandvars(pattern)
    if '*' not in pattern:
        return [Path(pattern)]
    head, _, tail = pattern.partition('*')
    base = Path(head).parent
    prefix = Path(head).name
    if not base.is_dir():
        return []
    rest = tail.lstrip('\\/')
    return [child/rest for child in base.iterdir() if child.name.startswith(prefix) and child.is_dir()]


def relative_time(moment, now=None):
    if moment is None:
        return '—'
    now = now or datetime.now()
    seconds = (now-moment).total_seconds()
    if seconds < 90:
        return '刚刚'
    if seconds < 3600:
        return f'{int(seconds//60)} 分钟前'
    if moment.date() == now.date():
        return moment.strftime('今天 %H:%M')
    return moment.strftime('%m-%d %H:%M')


def reset_text(moment, now=None, approx=False):
    """A countdown such as 「2小时05分后重置」; 「约」 marks an inferred time."""
    if moment is None:
        return ''
    now = now or datetime.now()
    seconds = (moment-now).total_seconds()
    if seconds <= 0:
        return '已到重置时间'
    prefix = '约' if approx else ''
    minutes = max(1, math.ceil(seconds/60))
    if minutes < 60:
        return f'{prefix}{minutes}分钟后重置'
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f'{prefix}{hours}小时{minutes:02}分后重置'
    days, hours = divmod(hours, 24)
    return f'{prefix}{days}天{hours}小时后重置'


def reset_tooltip(moment, approx=False):
    if moment is None:
        return ''
    return ('估算：' if approx else '') + moment.strftime('%m-%d %H:%M 重置')


class QuotaWatcher(QObject):
    """Poll a reader on a timer; emit only when the snapshot actually changes."""
    changed = Signal(object)

    def __init__(self, reader, interval_ms=60000, parent=None):
        super().__init__(parent)
        self.reader = reader
        self.snapshot = None
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.poll)

    def start(self):
        self.poll()
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def poll(self):
        try:
            snapshot = self.reader()
        except Exception as error:  # a broken source must never take the pet down
            snapshot = QuotaSnapshot(source='', message=f'读取额度失败：{type(error).__name__}')
        if snapshot != self.snapshot:
            previous, self.snapshot = self.snapshot, snapshot
            self.changed.emit((previous, snapshot))
        return snapshot
