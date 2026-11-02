"""Prepare the current Gpt originals, common poses and verified native-size playback.

Originals are read only. Generated animation files live in playback/ and build/.
Only the supplied 512px artwork is prepared; no upscaled tier is generated.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import io
import json
import shutil
import struct
import sys
import time

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from share.asset_tools.alpha_repair import recover_cutout, repair, steady_gaps
from share.asset_tools.animation_pack import bridge_lengths, bridged, loop_back, placed
from share.asset_tools.pose_bridge import pose_bridge, visible_difference
from share.asset_tools.white_background import bounds, matte_white
from character_alpha import stabilize

ASSETS = ROOT/'assets/character'
BUILD = ROOT/'build/character-preparation'
RECIPE = 'gpt-motion-aligned-cutouts-held-drag-lossless-v4'
WEIGHTS = {'01': 3., '04': 2.2, '05': 1.8, '08': 2.5, '09': .9, '13': .3,
           '14': 1.1, '18': 0., '22': .25, '25': .15, '17': 1.3, '20': 2.7,
           '21': .1, '24': .65, '26': .2}
# Walks: the source file, direction and the source frames in which she travels.
MOVES = {'move-left': ('移动/向左.webp', '向左走走', -1, 24, 110),
         'move-right': ('移动/向右.webp', '向右走走', 1, 36, 166)}
HOLD_SWAY = 8   # frames of the settled drag pose a long hold sways through
cv2.setNumThreads(1)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def rgba(frame, recover=True):
    frame = frame.convert('RGBA')
    if frame.getchannel('A').getextrema()[0] == 255:
        return matte_white(frame)
    # Supplied cut-outs dropped pale lace, tail scales and wing membrane.
    return recover_cutout(frame) if recover else frame


def geometry(source):
    boxes, bodies = [], []
    for i in sorted(set(range(0, source.n_frames, 12)) | {source.n_frames-1}):
        source.seek(i)
        frame = rgba(source, recover=False)
        boxes.append(bounds(frame))
        bodies.append(bounds(frame, largest=True))
    boxes, bodies = [b for b in boxes if b], [b for b in bodies if b]
    centre = float(np.median([(b[0]+b[2])/2 for b in bodies]))
    baseline = float(np.median([b[3] for b in bodies]))
    height = float(np.median([b[3]-b[1] for b in bodies]))
    scale = min(1.025, 442/max(1, height))
    return dict(centre=centre, baseline=baseline, scale=scale)


def align(frame, transform):
    # One transform per clip prevents frame-to-frame size or baseline jitter.
    factor = transform['scale']
    size = (round(frame.width*factor), round(frame.height*factor))
    frame = frame.convert('RGBa').resize(size, Image.Resampling.LANCZOS).convert('RGBA')
    canvas = Image.new('RGBA', (512, 512))
    canvas.paste(frame, (round(256-transform['centre']*factor), round(488-transform['baseline']*factor)))
    return canvas


def decode(path):
    frames, delays, trusted = [], [], []
    with Image.open(path) as source:
        transform = geometry(source)
        for i in range(source.n_frames):
            source.seek(i); source.load()
            frames.append(align(rgba(source), transform))
            trusted.append(np.asarray(align(rgba(source, recover=False), transform).getchannel('A')))
            delays.append(int(source.info.get('duration', 42)))
    # The supplied cut-outs lose hair or ruffles on some frames; rebuild them.
    frames, report = repair(frames)
    frames, temporal = stabilize(steady_gaps(frames), trusted)
    return frames, delays, dict(transform, repair=report, temporal=temporal)


def chunk(tag, value):
    return tag+struct.pack('<I', len(value))+value+(b'\0' if len(value) % 2 else b'')


def write_webp(path, frames, delays, size):
    """Independent exact frames keep sustained-loop frame indices stable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.preparing.webp')
    u24 = lambda value: int(value).to_bytes(3, 'little')
    with temporary.open('wb') as stream:
        stream.write(b'RIFF\0\0\0\0WEBP')
        stream.write(chunk(b'VP8X', b'\x12\0\0\0'+u24(size-1)+u24(size-1)))
        stream.write(chunk(b'ANIM', struct.pack('<IH', 0, 0)))
        for frame, delay in zip(frames, delays):
            if frame.size != (size, size):
                frame = frame.convert('RGBa').resize((size, size), Image.Resampling.LANCZOS).convert('RGBA')
            buffer = io.BytesIO()
            frame.save(buffer, format='WEBP', lossless=True, exact=True, method=0, quality=75)
            data, at, image = buffer.getvalue(), 12, b''
            while at < len(data):
                length = int.from_bytes(data[at+4:at+8], 'little')
                end = at+8+length+(length % 2)
                if data[at:at+4] == b'VP8L': image += data[at:end]
                at = end
            if not image: raise ValueError('Expected a lossless WebP frame')
            header = u24(0)+u24(0)+u24(size-1)+u24(size-1)+u24(delay)+b'\x02'
            stream.write(chunk(b'ANMF', header+image))
        length = stream.tell()-8
        stream.seek(4); stream.write(struct.pack('<I', length))
    # Verify every encoded frame, not just the header or its first pose.
    with Image.open(temporary) as check:
        if check.n_frames != len(frames) or check.size != (size, size):
            raise ValueError('Prepared frame count or canvas mismatch')
        for i, (expected, delay) in enumerate(zip(frames, delays)):
            check.seek(i); check.load()
            if expected.size != (size, size):
                expected = expected.convert('RGBa').resize((size, size), Image.Resampling.LANCZOS).convert('RGBA')
            if check.convert('RGBA').tobytes() != expected.tobytes() or check.info['duration'] != delay:
                raise ValueError(f'Lossless frame verification failed: {path.name}/{i}')
    for attempt in range(20):
        # A virus scan or indexer may hold the old file for a moment.
        try:
            temporary.replace(path); break
        except PermissionError:
            if attempt == 19: raise
            time.sleep(.5)
    return dict(path=str(path), sha256=digest(path), bytes=path.stat().st_size, frames=len(frames))


def ticks(count):
    return [round((i+1)*1000/24)-round(i*1000/24) for i in range(count)]


def prepare(item, anchor, reference):
    began = time.monotonic()
    key = item['id']
    source_name = item['file'] if (ASSETS/item['file']).is_file() else item['playbackFile']
    source = ASSETS/source_name
    source_hash = digest(source)
    receipt_path = BUILD/(key+'.json')
    if receipt_path.is_file():
        cached = json.loads(receipt_path.read_text(encoding='utf-8'))
        if (cached.get('recipe') == RECIPE and cached.get('reference') == reference
                and cached.get('sourceSha256') == source_hash
                and (key != 'drag' or cached['record'].get('dragLoopFile'))):
            cached['files']=[f for f in cached['files'] if Path(f['path']).is_relative_to(ASSETS)]
            if all(Path(f['path']).is_file() and digest(f['path']) == f['sha256'] for f in cached['files']):
                print('CACHED '+key, flush=True)
                return cached
    print('PREPARE '+key, flush=True)
    frames, delays, transform = decode(source)
    source_frames, source_duration = len(frames), sum(delays)
    if key == 'idle':
        output, timing, place = loop_back(frames, delays)
        entry_count, exit_count = 0, place['exit']
    elif key == 'drag':
        # Pick her up through a quick entrance; the way down leaves from the loop end.
        start = round(source_frames*.26); end = round(source_frames*.64)
        exit_count = bridge_lengths(key, frames[0], frames[end], anchor)[1]
        output = pose_bridge(anchor, frames[0], 4)[:-1]+frames[:end+1]+pose_bridge(frames[end], anchor, exit_count)[1:]
        timing = ticks(3)+delays[:end+1]+ticks(exit_count-1)
        entry_count, place = 4, dict(kept=list(range(end+1)))
    else:
        output, timing, place = bridged(key, frames, delays, anchor)
        entry_count, exit_count = place['entry'], place['exit']
    relative = 'playback/'+key+'.webp'
    files = []
    files.append(write_webp(ASSETS/relative, output, timing, 512))
    record = {k: item[k] for k in ('id','name','line','bubble') if k in item}
    record.update(file=source_name, playbackFile=relative, sourceSha256=source_hash,
                  sourceFrames=source_frames, sourceDurationMs=source_duration,
                  durationMs=sum(timing), frames=len(output), loop=key == 'idle',
                  renderScale=1., renderOffset=[0.,0.], renderAnchor='bottom-center',
                  randomWeight=WEIGHTS.get(key, 0.), preparation=RECIPE,
                  entryBridgeFrames=entry_count, exitBridgeFrames=exit_count,
                  referencePose=reference, sha256=files[0]['sha256'], bytes=files[0]['bytes'])
    if 'direction' in item:
        record.update(direction=item['direction'], walk=dict(
            direction=item['direction'], start=placed(place['kept'], entry_count, item['walkFrames'][0]),
            end=placed(place['kept'], entry_count, item['walkFrames'][1])))
    if key in ('work02', 'work05'):
        # Loop only the central task gesture; entry/return never repeat in the body.
        start = placed(place['kept'], entry_count, round(source_frames*.25))
        end = placed(place['kept'], entry_count, round(source_frames*.78))
        seam_count = 8
        seam_name = 'playback/'+key+'-seam.webp'
        seam = pose_bridge(output[end], output[start], seam_count)
        files.append(write_webp(ASSETS/seam_name, seam, ticks(seam_count), 512))
        record['sustained'] = dict(start=start, end=end, sourceFrames=len(output), seamFile=seam_name, seamFrames=seam_count)
    if key == 'drag':
        start, end = entry_count-1+start, entry_count-1+end
        record.update(dragStartFrame=entry_count-1, dragEndFrame=end, releaseFrame=end)
        # Held long, she stays in the pose the lift settles into (dizzy, wings
        # out): a slight sway through its last frames, never the tail swing
        # again. It leaves from and returns to the release frame.
        start = end-HOLD_SWAY
        held = output[end-1:start-1:-1]+output[start+1:end+1]
        loop_name = 'playback/drag-held.webp'
        files.append(write_webp(ASSETS/loop_name, held, ticks(len(held)), 512))
        record.update(dragLoopStart=start,dragLoopEnd=end,dragLoopFile=loop_name,dragLoopFrames=len(held))
    preview = Image.new('RGB', (1024, 256), '#e8e4ee')
    for column, index in enumerate((0, max(0, entry_count-1) or len(output)//3, len(output)//2, len(output)-1)):
        image = output[index].resize((256,256), Image.Resampling.LANCZOS)
        preview.paste(image, (column*256,0), image)
    preview.save(BUILD/(key+'-preview.jpg'))
    gap = visible_difference(output[0], output[-1])
    result = dict(recipe=RECIPE, reference=reference, sourceSha256=source_hash, source=source_name,
                  transform=transform, record=record, files=files, endpointDifference=gap,
                  seconds=round(time.monotonic()-began,2))
    write_json(receipt_path, result)
    print(f'OK {key}: {len(output)} frames; gap={gap:.6f}', flush=True)
    return result


def main():
    if (ASSETS/'MP4').is_dir() and list((ASSETS/'MP4').glob('*.mp4')):
        from prepare_mp4_character import main as prepare_mp4
        return prepare_mp4()
    BUILD.mkdir(parents=True, exist_ok=True)
    manifest_path = ASSETS/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    backup = BUILD/'source-manifest.json'
    if not backup.exists(): shutil.copy2(manifest_path, backup)
    original_catalog = BUILD/'source-material-catalog.json'
    if not original_catalog.exists(): shutil.copy2(ROOT/'app/material_catalog.json', original_catalog)
    moves = [dict(id=key, name=name, file=file, direction=direction, walkFrames=[first, last])
             for key, (file, name, direction, first, last) in MOVES.items()]
    items = [manifest['idle'], *manifest.get('additionalIdleAnimations',[]), *manifest.get('variants',[]),
             *manifest.get('workAnimations',[]), manifest['quotaAnimation'], manifest['dragAnimation'], *moves]
    unique = {item['id']:item for item in items}
    idle = manifest['idle']
    source = ASSETS/(idle['file'] if (ASSETS/idle['file']).is_file() else idle['playbackFile'])
    # Every clip starts and ends on the first frame of the (trimmed) idle loop.
    anchor = loop_back(*decode(source)[:2])[0][0]
    reference = hashlib.sha256(anchor.tobytes()).hexdigest()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: prepare(item,anchor,reference), unique.values()))
    prepared = {r['record']['id']:r['record'] for r in results}
    for item in prepared.values():
        item['playbackSha256512'] = item.pop('sha256', item.get('playbackSha256512'))
        item['playbackBytes512'] = item.pop('bytes', item.get('playbackBytes512'))
    fresh = dict(version=1, character='Gpt', idle=prepared['idle'],
                 additionalIdleAnimations=[prepared['idle2']],
                 variants=[prepared[i['id']] for i in manifest['variants']],
                 workAnimations=[prepared[i['id']] for i in manifest.get('workAnimations',[])],
                 quotaAnimation=prepared['quota'], dragAnimation=prepared['drag'],
                 moveAnimations=[prepared[key] for key in MOVES],
                 preparation=RECIPE, referencePose=reference,
                 sourceInventory=[dict(file=r['source'],sha256=r['sourceSha256']) for r in results])
    write_json(manifest_path, fresh)
    files=[dict(path=Path(f['path']).relative_to(ASSETS).as_posix(),bytes=f['bytes'],sha256=f['sha256'])
           for result in results for f in result['files']]
    files.append(dict(path='manifest.json',bytes=manifest_path.stat().st_size,sha256=digest(manifest_path)))
    files.sort(key=lambda f:f['path'])
    identity=hashlib.sha256(json.dumps(files,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]
    tier=dict(id=identity,resolution=512,files=files,bytes=sum(f['bytes'] for f in files))
    write_json(ROOT/'app/material_catalog.json',dict(schema=1,default='light',tiers=dict(light=tier)))
    if any(digest(ASSETS/r['source']) != r['sourceSha256'] for r in results):
        raise ValueError('Original artwork changed during preparation')
    write_json(BUILD/'verification.json',dict(passed=True,recipe=RECIPE,actions=len(results),reference=reference,
               allOriginalsPreserved=True,allFramesVerified=True,maximumEndpointDifference=max(r['endpointDifference'] for r in results),
               light=tier['id']))
    print('COMPLETE: originals preserved; 512px frames verified; native playback refreshed.',flush=True)


if __name__ == '__main__':
    main()
