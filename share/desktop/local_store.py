"""One companion's own files: settings, focus history and diagnostics."""
from datetime import datetime
import os
from pathlib import Path
from .companion_state import SCHEMA, FocusLedger, atomic_json, load_settings

LOG_LIMIT = 256*1024


class LocalStore:
    def __init__(self, root, schema=SCHEMA):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.schema = schema
        self.settings_path = self.root/'settings.json'
        self.record_path = self.root/'focus.json'
        self.log_path = self.root/'diagnostics.log'

    def settings(self):
        return load_settings(self.settings_path, self.schema)

    def save_settings(self, settings):
        atomic_json(self.settings_path, settings)

    def ledger(self):
        return FocusLedger.load(self.record_path)

    def save_ledger(self, ledger, today):
        atomic_json(self.record_path, ledger.record(today))

    def log(self, text):
        """Append a diagnostic line; the file is capped so it cannot grow forever."""
        try:
            if self.log_path.is_file() and self.log_path.stat().st_size > LOG_LIMIT:
                os.replace(self.log_path, self.log_path.with_suffix('.old.log'))
            with self.log_path.open('a', encoding='utf-8') as stream:
                stream.write(f'[{datetime.now():%Y-%m-%d %H:%M:%S}] {text.rstrip()}\n')
        except OSError:
            pass
