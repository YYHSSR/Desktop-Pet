"""Gemini constellation companion: shared engine, independent desktop experience."""
from pathlib import Path
import sys

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(SOURCE_ROOT.parent))
ROOT = Path(getattr(sys, '_MEIPASS', SOURCE_ROOT))

from share.desktop.companion_app import run


def main(argv=None):
    from companion import Companion
    return run(Companion, source_root=SOURCE_ROOT, bundle_root=ROOT, entry=Path(__file__).resolve(), argv=argv)


if __name__ == '__main__':
    raise SystemExit(main())
