"""Canonical ChatGpt entry point; enhanced.py remains a compatible source launcher."""
import sys

if __name__ == '__main__':
    if '--watch-codex' in sys.argv:
        from codex_startup import main
        raise SystemExit(main())
    from enhanced import run
    raise SystemExit(run())
