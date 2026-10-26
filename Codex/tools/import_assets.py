"""Import or check character playback assets from a local, extracted material directory."""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from desktop_services import all_items
from sustained_assets import seam_items
from material_manifest import clean_manifest


def missing_assets(root=ROOT):
    assets = Path(root) / 'assets/character'
    manifest = assets / '素材清单.json'
    if not manifest.is_file():
        return [manifest]
    data = json.loads(manifest.read_text(encoding='utf-8'))
    missing = []
    for item in all_items(data) + seam_items(data):
        name = item.get('playbackFile') or item['file']
        target = (assets / name).resolve()
        if not target.is_relative_to(assets.resolve()):
            raise ValueError('素材路径不在角色目录内')
        if not target.is_file():
            missing.append(target)
    return missing


def import_assets(source, destination=ROOT):
    source = Path(source).resolve()
    for relative in ('assets/character', 'outputs/白龙桌宠素材'):
        candidate = source / relative
        if (candidate / '素材清单.json').is_file():
            source = candidate
            break
    target = Path(destination).resolve() / 'assets/character'
    manifest = source / '素材清单.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    pairs = []
    for item in all_items(data) + seam_items(data):
        name = item.get('playbackFile') or item['file']
        src = (source / name).resolve()
        dst = (target / name).resolve()
        if not src.is_relative_to(source) or not dst.is_relative_to(target):
            raise ValueError('素材路径越界')
        if not src.is_file():
            raise FileNotFoundError(src)
        pairs.append((src, dst))
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src != dst:
            shutil.copy2(src, dst)
    target.mkdir(parents=True, exist_ok=True)
    (target / manifest.name).write_bytes(clean_manifest(manifest.read_bytes()))
    return len(pairs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--source', type=Path)
    action.add_argument('--check', action='store_true', help='只检查 assets/character 中的播放素材是否齐全')
    args = parser.parse_args()
    if args.check:
        missing = missing_assets()
        if missing:
            print(f'缺少 {len(missing)} 个角色素材文件，请用 --source <素材目录> 导入。', file=sys.stderr)
            raise SystemExit(1)
        print('角色素材齐全。')
    else:
        print(f'已导入 {import_assets(args.source)} 段播放素材。')
