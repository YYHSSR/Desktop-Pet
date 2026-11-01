"""Prepare the replacement drag clip and refresh both offline material tiers.

The supplied source stays untouched. Existing HD files are read from the verified
local cache, copied into build/, and only the drag clip and manifest are changed.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT.parent), str(ROOT/'app'), str(ROOT/'build/asset-tools')]
from PIL import Image
from share.asset_tools.animation_pack import transform_for, align
from share.asset_tools.white_background import matte_white
from desktop_services import all_items
from sustained_assets import seam_items
from material_manifest import manifest_path, playback_path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path, root):
    return dict(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size, sha256=digest(path))


def spec(files, resolution):
    files = sorted(files, key=lambda x:x['path'])
    identity = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    return dict(id=identity, resolution=resolution, files=files, bytes=sum(x['bytes'] for x in files))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def prepare():
    assets = ROOT/'assets/character'
    manifest = json.loads(manifest_path(assets).read_text(encoding='utf-8-sig'))
    catalog_path = ROOT/'app/material_catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    raw = assets/'互动/拖拽.webp'
    receipt = ROOT/'build/interaction-assets/drag.json'
    target = assets/'playback/drag.webp'; target.parent.mkdir(exist_ok=True)
    source_hash = digest(raw)
    cached = json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else {}
    if not (target.exists() and cached.get('sourceSha256') == source_hash and cached.get('sha256') == digest(target)):
        frames, durations = [], []
        with Image.open(raw) as source:
            transform = transform_for(source, effects_crop=True)
            for index in range(source.n_frames):
                source.seek(index); source.load()
                frame = align(matte_white(source), transform)
                # Match the existing Gpt 512px body's feet (y=477).
                canvas = Image.new('RGBA', (512,512)); canvas.paste(frame, (0,-11))
                frames.append(canvas); durations.append(int(source.info.get('duration',42)))
        frames[0].save(target, save_all=True, append_images=frames[1:], duration=durations,
                       loop=0, quality=94, alpha_quality=100, method=4)
        cached = dict(sourceSha256=source_hash, sha256=digest(target), durationMs=sum(durations))
        receipt.parent.mkdir(parents=True,exist_ok=True); write(receipt,cached)
        print('PREPARED light drag', flush=True)
    manifest['idle']['name'] = '待机'
    for item in manifest.get('additionalIdleAnimations',[]):
        item['name'] = '待机变化' if item['id']=='idle2' else item.get('name',item['id'])
    drag = manifest['dragAnimation']
    drag.update(file='互动/拖拽.webp', playbackFile='playback/drag.webp', name='拖拽',
                durationMs=cached['durationMs'], originalDurationMs=cached['durationMs'])
    write(assets/'manifest.json', manifest)
    light_files = [record(playback_path(assets,x),assets) for x in all_items(manifest)+seam_items(manifest)]
    light_files.append(record(assets/'manifest.json',assets))
    light_spec = spec(light_files,512)

    # Reuse immutable HD art without writing into the user's installed cache.
    old_hd = catalog['tiers']['hd']; hd = ROOT/'build/materials/hd'
    old_root = Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'BailongEnhanced/materials/hd'/old_hd['id']
    if not old_root.is_dir(): old_root = hd
    for item in old_hd['files']:
        source, dest = old_root/item['path'], hd/item['path']
        if not source.is_file() or digest(source) != item['sha256']:
            raise ValueError('HD source verification failed: '+item['path'])
        dest.parent.mkdir(parents=True,exist_ok=True)
        if source.resolve()!=dest.resolve(): shutil.copy2(source,dest)
    hd_manifest_path = manifest_path(hd)
    hd_manifest = json.loads(hd_manifest_path.read_text(encoding='utf-8-sig'))
    hd_drag = playback_path(hd,hd_manifest['dragAnimation'])
    frames, durations = [], []
    with Image.open(target) as source:
        for index in range(source.n_frames):
            source.seek(index); source.load()
            frames.append(source.convert('RGBa').resize((720,720),Image.Resampling.LANCZOS).convert('RGBA'))
            durations.append(int(source.info.get('duration',42)))
    frames[0].save(hd_drag,save_all=True,append_images=frames[1:],duration=durations,
                   loop=0,quality=94,alpha_quality=100,method=4)
    hd_manifest['dragAnimation']['durationMs'] = cached['durationMs']
    hd_manifest['character'] = 'Gpt'
    names = {x['id']:x.get('name') for x in all_items(manifest)}
    for item in all_items(hd_manifest):
        if names.get(item['id']): item['name'] = names[item['id']]
    write(hd_manifest_path,hd_manifest)
    hd_files = [record(hd/item['path'],hd) for item in old_hd['files']]
    catalog['tiers'] = dict(light=light_spec,hd=spec(hd_files,720))
    write(catalog_path,catalog)
    light = ROOT/'build/materials/light'; light.mkdir(parents=True,exist_ok=True)
    for item in light_spec['files']:
        target_path = light/item['path'];target_path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(assets/item['path'],target_path)
    print(json.dumps(dict(passed=True,light=light_spec['id'],hd=catalog['tiers']['hd']['id'],
                          source_preserved=digest(raw)==source_hash)),flush=True)


if __name__=='__main__': prepare()
