"""Refresh light-tier paths after a lossless resource rename; preserve HD contracts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
from desktop_core import atomic_json
from desktop_services import all_items
from sustained_assets import seam_items
from material_manifest import manifest_path, playback_path, derived_items


def record(path, root):
    with path.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size, sha256=checksum)


def sync(check=False):
    assets = ROOT/'assets/character'
    descriptor = manifest_path(assets)
    data = json.loads(descriptor.read_text(encoding='utf-8-sig'))
    catalog_path = ROOT/'app/material_catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8-sig'))
    old = catalog['tiers']['light']
    animations = [record(playback_path(assets, item), assets) for item in all_items(data)+seam_items(data)+derived_items(data)]
    before = Counter((entry['sha256'], entry['bytes']) for entry in old['files'] if entry['path'].endswith('.webp'))
    after = Counter((entry['sha256'], entry['bytes']) for entry in animations)
    if before != after:
        raise ValueError('动画内容有变化：此工具只同步文件改名；请使用素材构建工具重新生成校验目录。')
    files = sorted(animations+[record(descriptor, assets)], key=lambda entry: entry['path'])
    identity = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    updated = dict(old, id=identity, files=files, bytes=sum(entry['bytes'] for entry in files))
    if check:
        if old != updated:
            raise ValueError('轻量素材目录需要同步，请运行 tools/sync_material_catalog.py')
    elif updated != old:
        catalog['tiers']['light'] = updated
        atomic_json(catalog_path, catalog)
    print(json.dumps(dict(passed=True, animations=len(animations), manifest=descriptor.name,
                          light_id=identity, hd_contract_preserved=True)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    sync(parser.parse_args().check)
