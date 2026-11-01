"""Gemini token usage from Antigravity's local conversation databases.

Antigravity keeps one SQLite file per conversation under
~/.gemini/antigravity[-ide]/conversations. Each model call leaves a
gen_metadata row (a protobuf) with the model's display name and its usage;
the step it ended on carries the timestamp. Read-only, no network.

Usage fields, as observed: 1 + 2 prompt tokens, 5 cached prompt tokens,
3 output tokens (thinking + reply).
"""
from datetime import datetime
from pathlib import Path
import sqlite3
from share.desktop.token_report import TokenSource, add
from antigravity_link import fields

FOLDERS = ('.gemini/antigravity/conversations', '.gemini/antigravity-ide/conversations')


def message(data):
    out = {}
    for number, _, value in fields(data):
        out.setdefault(number, []).append(value)
    return out


def first(record, number, default=None):
    values = record.get(number)
    return values[0] if values else default


def text(value):
    return value.decode('utf-8', 'replace') if isinstance(value, bytes) else ''


def step_times(connection):
    times = {}
    for index, metadata in connection.execute('select idx, metadata from steps'):
        if not metadata:
            continue
        stamp = first(message(metadata), 1)
        seconds = first(message(stamp), 1) if isinstance(stamp, bytes) else None
        if isinstance(seconds, int) and seconds > 0:
            times[index] = datetime.fromtimestamp(seconds)
    return times


def generation(data):
    """(model, parts, last step index) from one gen_metadata row, or None."""
    top = first(message(data), 1)
    if not isinstance(top, bytes):
        return None
    record = message(top)
    usage = first(record, 4)
    if not isinstance(usage, bytes):
        return None
    counts = message(usage)
    number = lambda key: first(counts, key, 0) if isinstance(first(counts, key, 0), int) else 0
    parts = (number(1)+number(2), 0, number(5), number(3))
    if not any(parts):
        return None
    model = text(first(record, 21)) or text(first(record, 19)) or '未知模型'
    step = None
    for pair in record.get(20, ()):
        entry = message(pair)
        if text(first(entry, 1)) == 'last_step_index':
            try:
                step = int(text(first(entry, 2)))
            except ValueError:
                pass
    return model, parts, step


class AntigravityTokens(TokenSource):
    NAME = 'Antigravity'
    NOTE = '统计本机 Antigravity 的对话记录（含其中使用的各家模型），Token = 输入 + 缓存读取 + 输出；只读本机文件，不登录、不联网。'

    def __init__(self, folders=None):
        self.folders = folders

    def files(self):
        found = []
        for folder in self.folders or [Path.home()/name for name in FOLDERS]:
            if folder.is_dir():
                found.extend(folder.glob('*.db'))
        return found

    def scan(self, path, previous, stop):
        fallback = datetime.fromtimestamp(path.stat().st_mtime)
        connection = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True, timeout=1)
        try:
            times = step_times(connection)
            days = {}
            for (data,) in connection.execute('select data from gen_metadata order by idx'):
                if stop.is_set():
                    return None
                found = generation(data) if data else None
                if found is None:
                    continue
                model, parts, step = found
                add(days, times.get(step, fallback), model, parts, path.stem)
        finally:
            connection.close()
        return dict(days=days)
