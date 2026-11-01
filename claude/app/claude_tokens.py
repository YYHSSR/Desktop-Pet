"""Claude token usage from the Claude Code transcripts kept on this computer.

Claude Code (the CLI and the desktop app's Code tab) appends one JSON line per
event to ~/.claude/projects/<project>/<session>.jsonl; assistant replies carry
the model and its usage. Files only grow, so a refresh continues from the last
whole line it read. One reply can span several lines with the same message
id, so recent ids are remembered to count it once. Read-only, no network.
"""
from collections import deque
from datetime import datetime
import json
import os
import re
from pathlib import Path
from share.desktop.token_report import TokenSource, add

RECENT_IDS = 256


def roots():
    configured = os.environ.get('CLAUDE_CONFIG_DIR')
    folders = [Path(configured)] if configured else []
    folders.append(Path.home()/'.claude')
    return [folder/'projects' for folder in folders]


def model_name(model):
    """'claude-opus-5-5' -> 'Opus 5.5'; unknown names pass through."""
    match = re.match(r'claude-(opus|sonnet|haiku|fable)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$', model or '')
    if not match:
        return model or '未知模型'
    family, major, minor = match.groups()
    return f'{family.title()} {major}' + (f'.{minor}' if minor else '')


def stamp_of(text):
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).astimezone().replace(tzinfo=None)
    except (AttributeError, ValueError):
        return None


class ClaudeCodeTokens(TokenSource):
    NAME = 'Claude Code'
    NOTE = '统计本机 Claude Code（含桌面端 Code 页）的对话记录，Token = 输入 + 缓存写入 + 缓存读取 + 输出；网页和手机上的聊天不在本机，无法计入。'

    def __init__(self, folders=None):
        self.folders = folders

    def files(self):
        found = []
        for folder in self.folders or roots():
            if folder.is_dir():
                found.extend(folder.rglob('*.jsonl'))
        return found

    def scan(self, path, previous, stop):
        size = path.stat().st_size
        if previous and previous.get('offset', 0) <= size and 'days' in previous:
            offset, days = previous['offset'], previous['days']
            recent = deque(previous.get('recent', ()), RECENT_IDS)
        else:
            offset, days, recent = 0, {}, deque(maxlen=RECENT_IDS)
        with path.open('rb') as handle:
            handle.seek(offset)
            for line in handle:
                if not line.endswith(b'\n'):
                    break  # a half-written last line waits for the next refresh
                offset += len(line)
                if b'"usage"' in line and b'"assistant"' in line:
                    self.count(line, days, recent, path)
                if stop.is_set():
                    return None
        return dict(offset=offset, days=days, recent=list(recent))

    @staticmethod
    def count(line, days, recent, path):
        try:
            event = json.loads(line)
        except ValueError:
            return
        message = event.get('message') if isinstance(event, dict) else None
        usage = message.get('usage') if isinstance(message, dict) else None
        model = message.get('model') if isinstance(message, dict) else None
        if event.get('type') != 'assistant' or not isinstance(usage, dict) or not model or model.startswith('<'):
            return
        ident = message.get('id') or event.get('requestId')
        if ident in recent:
            return
        recent.append(ident)
        moment = stamp_of(event.get('timestamp'))
        if moment is None:
            return
        parts = tuple(int(usage.get(key) or 0) for key in
                      ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens'))
        add(days, moment, model_name(model), parts, event.get('sessionId') or path.stem)
