"""Run isolated Claude tests and verify all prepared animation frames."""
import argparse
import hashlib
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
    with tempfile.TemporaryDirectory(prefix='claude-tests-') as folder:
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
        originals = ROOT/'assets/character'
        inventory = json.loads((originals/'manifest.json').read_text(encoding='utf-8-sig'))
        result['originals'] = []
        for item in inventory['files']:
            path = originals/item['file']
            with path.open('rb') as stream:
                checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            if path.stat().st_size != item['bytes'] or checksum != item['sha256']:
                raise ValueError('Original changed: '+item['file'])
            result['originals'].append(item['file'])
        descriptor = json.loads((originals/'character.json').read_text(encoding='utf-8'))
        actions = {item['id']: item for item in descriptor['actions']}
        if (len(actions) != 9 or 'doze' in actions or descriptor.get('drag') != 'drag'
                or actions['flower'].get('sourceEndFrame') is not None
                or actions['flower'].get('holdTailMs', 0) != 0
                or actions['idle']['source'] != '陪伴/抱书静候.webp'):
            raise ValueError('Claude action selection is incorrect')
        source_checksums = {item['file']: item['sha256'] for item in inventory['files']}
        if any(item['sourceSha256'] != source_checksums[item['source']] for item in actions.values()):
            raise ValueError('Playback source metadata does not match the original inventory')
        print(f'PASS transparent assets: {len(result["assets"])} actions')
    (output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
