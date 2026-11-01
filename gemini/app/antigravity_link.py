"""Antigravity IDE link: read the model quota Antigravity caches locally.

Antigravity keeps the account's user status (plan, per-model quota with the
remaining fraction and reset time) in its VS Code style state database. We
open that SQLite file read-only and decode only the quota and plan fields;
the account e-mail and the stored OAuth token are never read or kept.
"""
from datetime import datetime
import base64
import os
from pathlib import Path
import sqlite3
import struct
from share.desktop.quota import Meter, QuotaSnapshot
from share.desktop import desktop_integration

SOURCE = 'Antigravity'
STATE_DB = r'%APPDATA%\Antigravity IDE\User\globalStorage\state.vscdb'
FALLBACK_DB = r'%APPDATA%\Antigravity\User\globalStorage\state.vscdb'
STATUS_KEY = 'antigravityUnifiedStateSync.userStatus'
EXECUTABLES = ('Antigravity IDE.exe', 'Antigravity.exe')


# ---- a tiny protobuf wire-format reader (only what the status needs) ----
def _varint(buffer, index):
    value = shift = 0
    while True:
        byte = buffer[index]
        index += 1
        value |= (byte & 0x7f) << shift
        shift += 7
        if byte < 0x80:
            return value, index
        if shift > 63:
            raise ValueError('varint too long')


def fields(buffer):
    """[(number, wire_type, value)]; raises ValueError when it is not a message."""
    index, result = 0, []
    while index < len(buffer):
        key, index = _varint(buffer, index)
        number, kind = key >> 3, key & 7
        if number == 0:
            raise ValueError('field 0')
        if kind == 0:
            value, index = _varint(buffer, index)
        elif kind == 1:
            value, index = buffer[index:index+8], index+8
        elif kind == 2:
            size, index = _varint(buffer, index)
            value, index = buffer[index:index+size], index+size
        elif kind == 5:
            value, index = buffer[index:index+4], index+4
        else:
            raise ValueError('unsupported wire type')
        if index > len(buffer):
            raise ValueError('truncated')
        result.append((number, kind, value))
    return result


def message(value):
    try:
        return fields(value) if value else None
    except (ValueError, IndexError):
        return None


def text(value):
    try:
        decoded = value.decode('utf-8')
    except UnicodeDecodeError:
        return None
    return decoded if decoded.isprintable() else None


def inner_status(blob):
    """The stored value wraps the real status as a base64 string; unwrap it."""
    stack = [base64.b64decode(blob)]
    while stack:
        for number, kind, value in message(stack.pop()) or []:
            if kind != 2:
                continue
            candidate = text(value)
            if candidate and len(candidate) > 200:
                try:
                    return base64.b64decode(candidate, validate=True)
                except ValueError:
                    pass
            if message(value):
                stack.append(value)
    return None


def quota_of(entry):
    """(remaining_fraction, reset_datetime) when a submessage looks like quota info."""
    for number, kind, value in entry:
        if kind != 2:
            continue
        sub = message(value)
        if not sub:
            continue
        fraction = next((struct.unpack('<f', v)[0] for n, k, v in sub if n == 1 and k == 5), None)
        stamp = next((message(v) for n, k, v in sub if n == 2 and k == 2), None)
        seconds = next((v for n, k, v in stamp or [] if n == 1 and k == 0), None)
        if fraction is not None and 0 <= fraction <= 1.0001 and seconds and seconds > 1_500_000_000:
            return fraction, datetime.fromtimestamp(seconds)
    return None


def decode(blob):
    """-> (plan or None, [(model label, remaining, reset)]) from the stored status value."""
    status = inner_status(blob)
    if status is None:
        return None, []
    models, plan = [], None
    seen = set()

    def walk(buffer, depth=0):
        nonlocal plan
        entries = message(buffer)
        if not entries or depth > 8:
            return
        label = next((text(v) for n, k, v in entries if n == 1 and k == 2 and message(v) is None), None)
        if label and label.startswith('g1-'):
            names = [text(v) for n, k, v in entries if n == 2 and k == 2]
            plan = next((name for name in names if name), plan)
        quota = quota_of(entries) if label else None
        if quota and label not in seen and '@' not in label:
            seen.add(label)
            models.append((label, *quota))
            return
        for number, kind, value in entries:
            if kind == 2 and message(value):
                walk(value, depth+1)

    walk(status)
    return plan, models


def short_label(label):
    """'Gemini 3.8 Flash (High)' -> 'Gemini 3.8 Flash · 高'."""
    names = {'(High)': '高', '(Medium)': '中', '(Low)': '低', '(Thinking)': '思考'}
    for suffix, word in names.items():
        if label.endswith(suffix):
            return label[:-len(suffix)].strip()+' · '+word
    return label


class AntigravityQuotaReader:
    def __init__(self, path=None, running=None):
        self.path = Path(os.path.expandvars(path)) if path else None
        self.running = running or (lambda: desktop_integration.is_running(*EXECUTABLES))
        self._cache = (None, None)

    def database(self):
        if self.path:
            return self.path if self.path.is_file() else None
        for candidate in (STATE_DB, FALLBACK_DB):
            path = Path(os.path.expandvars(candidate))
            if path.is_file():
                return path
        return None

    def read_blob(self, path):
        connection = sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True, timeout=.3)
        try:
            row = connection.execute('SELECT value FROM ItemTable WHERE key = ?', (STATUS_KEY,)).fetchone()
        finally:
            connection.close()
        value = row[0] if row else None
        return value.decode('ascii', 'ignore') if isinstance(value, bytes) else value

    def __call__(self):
        running = self.running()
        path = self.database()
        if path is None:
            return QuotaSnapshot(SOURCE, running=running, message='没有找到 Antigravity，安装并登录后会自动连接。')
        try:
            stamp = path.stat().st_mtime_ns
            if self._cache[0] != (path, stamp):
                blob = self.read_blob(path)
                self._cache = ((path, stamp), (decode(blob) if blob else (None, []), stamp))
        except (OSError, sqlite3.Error, ValueError) as error:
            return QuotaSnapshot(SOURCE, running=running, message=f'Antigravity 额度暂时读不了（{type(error).__name__}）')
        (plan, models), stamp = self._cache[1]
        if not models:
            return QuotaSnapshot(SOURCE, connected=True, running=running, plan=plan,
                                 message='Antigravity 还没有同步额度，打开 IDE 后再看看。')
        meters = tuple(Meter(short_label(label), max(0., min(1., 1-remaining)), reset)
                       for label, remaining, reset in models)
        message = '已连接 Antigravity' if running else 'Antigravity 未运行，显示最后一次同步'
        return QuotaSnapshot(SOURCE, connected=True, running=running, message=message, meters=meters,
                             plan=plan, updated_at=datetime.fromtimestamp(stamp/1e9))
