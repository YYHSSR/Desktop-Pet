"""Claude desktop link: read the plan usage the Claude app already samples locally.

The desktop app keeps plan-usage-history.json in its data folder: every few
minutes it records how much of the 5-hour and the weekly allowance is used
("fh" / "sd", in percent). We only read that file; no sign-in, no network,
no tokens. Reset times are not recorded there, so they are inferred: a
window opens with the first use after the previous one closed, so a rise
from zero or a drop in the percentage brackets when the current window
began; chaining those brackets usually pins the reset to a few minutes.
"""
from datetime import datetime, timedelta
import json
from share.desktop.quota import Meter, QuotaSnapshot, expand, newest
from share.desktop import desktop_integration

SOURCE = 'Claude 桌面端'
CANDIDATES = (
    r'%LOCALAPPDATA%\Claude-Data\claude_*\plan-usage-history.json',   # Microsoft Store build
    r'%APPDATA%\Claude\plan-usage-history.json',                      # classic installer
    r'%LOCALAPPDATA%\AnthropicClaude\plan-usage-history.json',
)
METERS = (('fh', '5 小时'), ('sd', '本周'))
SPANS = {'fh': timedelta(hours=5), 'sd': timedelta(days=7)}
STALE_AFTER = 30*60  # seconds without a new sample before we call it "not updating"


def history_file():
    return newest(path for pattern in CANDIDATES for path in expand(pattern))


def series(samples, key):
    """[(datetime, percent)] oldest first, for samples that carry this meter."""
    points = []
    for sample in samples:
        usage = sample.get('u') if isinstance(sample, dict) else None
        value = usage.get(key) if isinstance(usage, dict) else None
        stamp = sample.get('t')
        if isinstance(value, (int, float)) and not isinstance(value, bool) and isinstance(stamp, (int, float)):
            points.append((datetime.fromtimestamp(stamp/1000), value))
    points.sort(key=lambda point: point[0])
    return points


def window_start(points, span):
    """Bounds (earliest, latest) on when the current window opened, or None."""
    bounds, previous = None, None
    for moment, value in points:
        if value <= 0:
            bounds = None
        elif previous is None:
            bounds = (moment-span, moment)
        elif bounds is None or value < previous[1] or moment > bounds[1]+span:
            # A fresh window opened after the previous sample and after the
            # old window (if any) had closed.
            floor = previous[0] if bounds is None else max(previous[0], bounds[0]+span)
            bounds = (min(floor, moment), moment)
        previous = (moment, value)
    return bounds


def estimated_reset(points, span):
    """Midpoint estimate, only when the bracket is tight enough to be useful."""
    bounds = window_start(points, span)
    if bounds is None or bounds[1]-bounds[0] > span/4:
        return None
    return bounds[0]+(bounds[1]-bounds[0])/2+span


def parse(data):
    """Latest sample with numbers -> (datetime, {key: percent}, {key: reset}); None when absent."""
    samples = data.get('samples') if isinstance(data, dict) else None
    if not isinstance(samples, list):
        return None
    lines = {key: series(samples, key) for key, _ in METERS}
    values = {key: points[-1][1] for key, points in lines.items() if points}
    if not values:
        return None
    updated = max(points[-1][0] for points in lines.values() if points)
    resets = {key: estimated_reset(lines[key], SPANS[key]) for key in values}
    return updated, values, resets


class ClaudeUsageReader:
    """Callable reader; re-parses only when the file changes."""
    def __init__(self, path=None, running=None):
        self.path = path
        self.running = running or (lambda: desktop_integration.is_running('claude.exe'))
        self._cache = (None, None)

    def __call__(self):
        path = self.path or history_file()
        running = self.running()
        if path is None:
            return QuotaSnapshot(SOURCE, running=running,
                                 message='没有找到 Claude 桌面端的额度记录，打开 Claude 桌面端后会自动连接。')
        try:
            stamp = path.stat().st_mtime_ns
            if self._cache[0] != (path, stamp):
                self._cache = ((path, stamp), parse(json.loads(path.read_text(encoding='utf-8'))))
        except (OSError, ValueError) as error:
            return QuotaSnapshot(SOURCE, running=running, message=f'额度记录暂时读不了（{type(error).__name__}）')
        latest = self._cache[1]
        if latest is None:
            return QuotaSnapshot(SOURCE, connected=True, running=running,
                                 message='Claude 桌面端还没有记录额度，稍后再看看。')
        updated, values, resets = latest
        meters = tuple(Meter(title, max(0., min(1., values[key]/100)), resets.get(key), estimated=True)
                       for key, title in METERS if key in values)
        fresh = (datetime.now()-updated).total_seconds() < STALE_AFTER
        message = '已连接 Claude 桌面端' if running and fresh else \
            ('Claude 桌面端未运行，显示最后一次记录' if not running else '记录有一阵没更新了')
        return QuotaSnapshot(SOURCE, connected=True, running=running, message=message,
                             meters=meters, updated_at=updated)
