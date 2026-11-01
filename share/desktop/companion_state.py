"""Local settings, monotonic focus timer, focus history and action queue shared by companion roles."""
from datetime import date, timedelta
import json
import math
import os
from pathlib import Path
import random
import time
from urllib.parse import urlsplit

# key: (kind, default, *limits). Characters extend this with their own keys.
SCHEMA = {
    'size': ('int', 300, 180, 460),
    'opacity': ('int', 100, 65, 100),
    'on_top': ('bool', True),
    'character_visible': ('bool', True),
    'bubble': ('bool', True),
    'random_actions': ('bool', True),
    'random_interval': ('int', 75, 30, 300),
    'position': ('point', None),
    'instant_switch': ('bool', True),
    'playback_speed': ('quarter', 1.0, .5, 2.0),
    'lock_position': ('bool', False),
    'fullscreen_yield': ('bool', True),
    'card_hide_delay': ('int', 14, 3, 120),
    'nickname': ('text', '', 12),
    'web_url': ('url', ''),
    'ambient_motion': ('bool', True),
    'quota_link': ('bool', True),
}
DEFAULTS = {key: spec[1] for key, spec in SCHEMA.items()}
HISTORY_DAYS = 62


def extended(**extra):
    """The shared schema plus a character's own keys."""
    return dict(SCHEMA, **extra)


def web_address(value):
    """Only complete http(s) pages without credentials; anything else falls back to ''."""
    value = str(value or '').strip()
    if not value or len(value) > 2048 or any(ord(c) < 32 for c in value):
        return ''
    try:
        parts = urlsplit(value)
        parts.port
    except ValueError:
        return ''
    if parts.scheme.lower() not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        return ''
    return value


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalized(raw, schema=SCHEMA):
    result = {key: spec[1] for key, spec in schema.items()}
    if not isinstance(raw, dict):
        return result
    for key, spec in schema.items():
        kind, value = spec[0], raw.get(key)
        if kind == 'int' and _number(value):
            result[key] = max(spec[2], min(spec[3], round(value)))
        elif kind == 'quarter' and _number(value):
            result[key] = max(spec[2], min(spec[3], round(value*4)/4))
        elif kind == 'bool' and isinstance(value, bool):
            result[key] = value
        elif kind == 'point' and isinstance(value, list) and len(value) == 2 and all(type(v) is int for v in value):
            result[key] = value
        elif kind == 'text' and isinstance(value, str):
            result[key] = ''.join(c for c in value if c.isprintable()).strip()[:spec[2]]
        elif kind == 'url' and isinstance(value, str):
            result[key] = web_address(value)
        elif kind == 'choice' and value in spec[2]:
            result[key] = value
    return result


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def load_settings(path, schema=SCHEMA):
    try:
        return normalized(json.loads(Path(path).read_text(encoding='utf-8')), schema)
    except (OSError, ValueError):
        return normalized({}, schema)


def week_key(day):
    """ISO week label such as 2026-W44."""
    year, week, _ = day.isocalendar()
    return f'{year}-W{week:02}'


class FocusLedger:
    """Completed focus rounds per day for the last two months, in one JSON file.

    Older files only knew today (and Gemini's weekly star count); those load
    as today's entry plus a carried-over count for that ISO week.
    """
    def __init__(self, days=None, legacy_week=None):
        self.days = dict(days or {})
        self.legacy_week = legacy_week  # (week_key, extra rounds) from the old format

    @staticmethod
    def _count(value):
        return max(0, min(10**6, value)) if type(value) is int else 0

    @classmethod
    def load(cls, path):
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        days = {}
        history = data.get('history')
        if isinstance(history, dict):
            for key, value in history.items():
                try:
                    date.fromisoformat(key)
                except (TypeError, ValueError):
                    continue
                if isinstance(value, list) and len(value) == 2:
                    sessions, minutes = cls._count(value[0]), cls._count(value[1])
                    if sessions or minutes:
                        days[key] = (sessions, minutes)
        today = data.get('date')
        try:
            date.fromisoformat(today)
        except (TypeError, ValueError):
            today = None
        if today and today not in days:
            sessions, minutes = cls._count(data.get('sessions')), cls._count(data.get('minutes'))
            if sessions or minutes:
                days[today] = (sessions, minutes)
        legacy = None
        week = data.get('week')
        if isinstance(week, str) and not isinstance(history, dict):
            known = days.get(today, (0, 0))[0] if today and week_key(date.fromisoformat(today)) == week else 0
            extra = cls._count(data.get('week_stars'))-known
            if extra > 0:
                legacy = (week, extra)
        elif isinstance(data.get('legacy_week'), list) and len(data['legacy_week']) == 2:
            key, extra = data['legacy_week']
            if isinstance(key, str) and cls._count(extra):
                legacy = (key, cls._count(extra))
        return cls(days, legacy)

    def today(self, day):
        return self.days.get(day.isoformat(), (0, 0))

    def add(self, day, minutes):
        sessions, total = self.today(day)
        self.days[day.isoformat()] = (sessions+1, total+max(0, int(minutes)))
        return sessions+1

    def week_total(self, day):
        monday = day-timedelta(days=day.weekday())
        total = sum(self.days.get((monday+timedelta(days=i)).isoformat(), (0, 0))[0]
                    for i in range(day.weekday()+1))
        if self.legacy_week and self.legacy_week[0] == week_key(day):
            total += self.legacy_week[1]
        return total

    def recent(self, day, count=7):
        """[(date, sessions, minutes)] oldest first, ending today."""
        return [(d, *self.days.get(d.isoformat(), (0, 0)))
                for d in (day-timedelta(days=offset) for offset in range(count-1, -1, -1))]

    def totals(self):
        return (sum(s for s, _ in self.days.values()), sum(m for _, m in self.days.values()))

    def streak(self, day):
        """Consecutive days ending today (or yesterday) with at least one round."""
        start = day if self.today(day)[0] else day-timedelta(days=1)
        count = 0
        while self.days.get((start-timedelta(days=count)).isoformat(), (0, 0))[0]:
            count += 1
        return count

    def record(self, day):
        cutoff = (day-timedelta(days=HISTORY_DAYS)).isoformat()
        history = {key: list(value) for key, value in sorted(self.days.items()) if key >= cutoff}
        sessions, minutes = self.today(day)
        # Old keys stay so a previous build still reads today's count.
        result = dict(date=day.isoformat(), sessions=sessions, minutes=minutes,
                      week=week_key(day), week_stars=self.week_total(day), history=history)
        if self.legacy_week and self.legacy_week[0] == week_key(day):
            result['legacy_week'] = list(self.legacy_week)
        return result


class FocusClock:
    def __init__(self):
        self.state = 'idle'
        self.duration = 25 * 60
        self.left = self.duration
        self.started = None

    def start(self, minutes, now=None):
        self.duration = max(1, min(180, int(minutes))) * 60
        self.left = self.duration
        self.started = time.monotonic() if now is None else now
        self.state = 'running'

    def remaining(self, now=None):
        now = time.monotonic() if now is None else now
        return max(0., self.left - (max(0., now-self.started) if self.state == 'running' else 0))

    def pause(self, now=None):
        if self.state != 'running':
            return
        self.left = self.remaining(now)
        self.state = 'paused'

    def resume(self, now=None):
        if self.state != 'paused':
            return
        self.started = time.monotonic() if now is None else now
        self.state = 'running'

    def reset(self):
        self.state = 'idle'
        self.left = self.duration
        self.started = None

    def poll(self, now=None):
        if self.state == 'running' and self.remaining(now) <= 0:
            self.left = 0
            self.state = 'finished'
            return True
        return False


class ActionDirector:
    """Completion reminders wait; random actions never interrupt a pose.

    A person's own choice either waits for the current tail (queued, latest
    wins) or, with interrupt=True, takes over at once; the sprite then
    crossfades the two live animations.
    """
    def __init__(self, actions, idle='idle', rng=None):
        self.actions = actions
        self.idle = idle
        self.current = idle
        self.pending = None
        self.queued = None
        self.rng = rng or random.Random()

    def request(self, key, *, automatic=False, completion=False, dragging=False, interrupt=False):
        if key not in self.actions:
            return None
        if completion and (dragging or self.current != self.idle):
            self.pending = key
            if self.queued == key:
                self.queued = None
            return None
        if dragging or self.current != self.idle:
            manual = not automatic and not completion
            if manual and interrupt and not dragging:
                if key == self.current:
                    return None
                self.current, self.queued = key, None
                return key
            if manual:
                self.queued = key
            return None
        self.current = key
        return key

    def finished(self):
        if self.pending:
            self.current, self.pending = self.pending, None
        else:
            self.current, self.queued = self.queued or self.idle, None
        return self.current
