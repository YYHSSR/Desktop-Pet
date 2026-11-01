"""Run isolated Gemini tests and verify all prepared animation frames."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-assets', action='store_true')
    args = parser.parse_args()
    output = ROOT/'build/checks'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='gemini-tests-') as folder:
        env = os.environ.copy()
        env.update(LOCALAPPDATA=folder, APPDATA=str(Path(folder)/'roaming'),
                   QT_QPA_PLATFORM='offscreen', PYTHONIOENCODING='utf-8')
        run = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT/'tests'), '-v'],
                             env=env, cwd=ROOT, capture_output=True, timeout=120)
    log = (run.stdout+run.stderr).decode('utf-8', errors='replace')
    (output/'tests.log').write_text(log, encoding='utf-8')
    print(log, end='')
    count = re.search(r'Ran (\d+) tests?', log)
    result = dict(passed=run.returncode == 0, tests=int(count[1]) if count else 0)
    if not args.skip_assets and result['passed']:
        sys.path.insert(0, str(ROOT.parent))
        from share.pet_engine.character_pack import CharacterPack
        result['assets'] = CharacterPack(ROOT/'assets/character').verify()
        print(f'PASS transparent assets: {len(result["assets"])} actions')
    (output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
