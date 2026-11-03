"""Build idle, directional walks, and interactive gestures from original MP4s."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from mp4_matte import matte_frame, outlined_foreground
from share.asset_tools.exact_webp import encode

ASSETS = ROOT/'assets/character'
BUILD = ROOT/'build/mp4-rebuild'
RECIPE = 'mp4-contour-source-rgb-pose-dissolve-v1'
GESTURES = ('proud', 'greeting', 'inspiration', 'affection', 'snack', 'tsundere',
            'sleepy', 'annoyed', 'dragon-breath', 'celebrate', 'heart', 'bond-mark',
            'task-process', 'treasure', 'task-receive', 'inspect', 'quota-check', 'trust', 'dragon-pact')
SOFT_EFFECTS = {'dragon-breath', 'dragon-pact'}
DRAG_HOLD_SOURCE_FRAME = 170
DRAG_START_SOURCE_FRAME = 27
DRAG_HOLD_POLICY = 'complete-action-hold-before-return'
cv2.setNumThreads(1)


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2)+'\n', encoding='utf-8')


def sources():
    files = sorted((ASSETS/'MP4').glob('*.mp4'))
    # Names are supplied by the user; generated code and internal IDs stay English.
    names = {'idle': '\u5f85\u673a', 'move-left': '\u5411\u5de6\u8d70\u8d70',
             'move-right': '\u5411\u53f3\u8d70\u8d70',
             'proud': '\u5f97\u610f', 'greeting': '\u62db\u624b-\u6253\u62db\u547c',
             'inspiration': '\u7075\u611f', 'affection': '\u8d34\u8d34',
             'snack': '\u5077\u5403', 'tsundere': '\u50b2\u5a07',
             'sleepy': '\u56f0\u5026', 'annoyed': '\u5c0f\u751f\u6c14',
             'dragon-breath': '\u5e7c\u9f99\u5410\u606f', 'celebrate': '\u5e86\u795d',
             'heart': '\u6bd4\u5fc3', 'bond-mark': '\u7737\u5c5e\u5370\u8bb0',
             'task-process': '\u5904\u7406\u4efb\u52a1', 'treasure': '\u5b9d\u85cf\u6536\u85cf',
             'task-receive': '\u6536\u5230\u4efb\u52a1', 'inspect': '\u653e\u5927\u955c\u67e5\u770b\u7ec6\u8282',
             'quota-check': '\u67e5\u9605\u989d\u5ea6', 'trust': '\u9006\u9cde\u4fe1\u4efb',
             'dragon-pact': '\u9f99\u65cf\u5951\u7ea6', 'drag': '\u62d6\u62fd'}
    result = {key: next((path for path in files if path.stem == name), None)
              for key, name in names.items()}
    if any(path is None for path in result.values()):
        missing = ', '.join(key for key, path in result.items() if path is None)
        raise ValueError('Required character MP4 clips are missing: '+missing)
    return result


def decode(path, *, soft_effects=False):
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError('Unable to open source MP4: '+path.name)
    fps = capture.get(cv2.CAP_PROP_FPS)
    size = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    if abs(fps-24) > .001 or size != (480, 480):
        raise ValueError('This preparation requires the supplied native 480px, 24fps clips')
    frames, preserved, tinted_total, tinted_lost = [], 0, 0, 0
    try:
        while True:
            ok, bgr = capture.read()
            if not ok:
                break
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            image = matte_frame(Image.fromarray(rgb), soft_effects=soft_effects)
            rgba = np.asarray(image)
            opaque = rgba[..., 3] == 255
            if not np.array_equal(rgba[..., :3][opaque], rgb[opaque]):
                raise ValueError('Matting changed opaque source artwork')
            tinted = (np.ptp(rgb, axis=2) >= 20) & (rgb.min(axis=2) < 235)
            if soft_effects:
                # Diffuse exterior glow legitimately has fractional alpha. The
                # retention check still covers the enclosed character artwork.
                tinted &= outlined_foreground(rgb)
            tinted_total += int(tinted.sum())
            tinted_lost += int((tinted & (rgba[..., 3] < 128)).sum())
            preserved += int(opaque.sum())
            canvas = Image.new('RGBA', (512, 512))
            canvas.paste(image, (16, 16))
            frames.append(canvas)
    finally:
        capture.release()
    if len(frames) < 24 or tinted_lost/max(1, tinted_total) > .002:
        raise ValueError('Foreground retention check failed')
    return frames, dict(fps=fps, sourceResolution=list(size), sourceFrames=len(frames),
                        opaqueSourcePixelsPreserved=preserved, tintedPixels=tinted_total,
                        lostTintedPixels=tinted_lost, opaqueRGBMaximumError=0,
                        tintedPixelCheckScope='outlined-character' if soft_effects else 'all-artwork')


def verified_previous(key, path, source_hash, reference, record, report):
    """Reuse only an output covered by the same exact-frame verification."""
    recipe = RECIPE+'-soft-effects' if key in SOFT_EFFECTS else RECIPE
    relative = 'playback-mp4/'+key+'.webp'
    if not isinstance(record, dict) or not isinstance(report, dict):
        return False
    if key == 'drag' and (record.get('dragHoldFrame') != record.get('sourceFrameOffset', 0)+DRAG_HOLD_SOURCE_FRAME
                          or record.get('dragHoldPolicy') != DRAG_HOLD_POLICY):
        return False
    if (record.get('sourceSha256') != source_hash or record.get('preparation') != recipe
            or record.get('referencePose') != reference or record.get('playbackFile') != relative
            or record.get('file') != path.relative_to(ASSETS).as_posix()
            or not report.get('allFramesVerified') or report.get('opaqueRGBMaximumError') != 0
            or report.get('sourceFramesKept') != record.get('sourceFrames')):
        return False
    encoded = report.get('encoded', {})
    target = ASSETS/relative
    return (target.is_file() and target.stat().st_size == record.get('playbackBytes512')
            and encoded.get('sha256') == record.get('playbackSha256512')
            and encoded.get('frames') == record.get('frames')
            and encoded.get('durationMs') == record.get('durationMs')
            and digest(target) == record.get('playbackSha256512'))


def dissolve(source, destination, count):
    """A short whole-pose dissolve; no region warping or invented texture."""
    a, b = np.asarray(source, np.float32)/255, np.asarray(destination, np.float32)/255
    a[..., :3] *= a[..., 3:]
    b[..., :3] *= b[..., 3:]
    result = [source.copy()]
    for index in range(1, count-1):
        t = index/(count-1)
        t = t*t*(3-2*t)
        value = a*(1-t)+b*t
        alpha = value[..., 3:]
        rgb = np.divide(value[..., :3], alpha, out=np.zeros_like(value[..., :3]), where=alpha > .001)
        result.append(Image.fromarray(np.rint(np.clip(np.dstack((rgb, alpha)), 0, 1)*255).astype(np.uint8)))
    result.append(destination.copy())
    return result


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    originals = sources()
    for source, target in ((ASSETS/'manifest.json', BUILD/'previous-manifest.json'),
                           (ROOT/'app/material_catalog.json', BUILD/'previous-material-catalog.json')):
        if source.is_file() and not target.exists():
            shutil.copy2(source, target)
    hashes = {key: digest(path) for key, path in originals.items()}
    try:
        previous = json.loads((ASSETS/'manifest.json').read_text(encoding='utf-8'))
        previous_reports = json.loads((BUILD/'verification.json').read_text(encoding='utf-8'))['reports']
        previous_records = {item['id']: item for item in
                            [previous['idle'], *previous.get('variants', []), *previous.get('moveAnimations', []),
                             *([previous['dragAnimation']] if previous.get('dragAnimation') else [])]}
    except (OSError, ValueError, KeyError, TypeError):
        previous_records, previous_reports = {}, {}
    records, files, reports = {}, [], {}
    anchor = None
    for key, path in originals.items():
        cached, report = previous_records.get(key), previous_reports.get(key)
        reference = hashlib.sha256(anchor.tobytes()).hexdigest() if anchor else None
        if reference and verified_previous(key, path, hashes[key], reference, cached, report):
            if key == 'drag':
                cached = dict(cached, dragStartFrame=cached['sourceFrameOffset']+DRAG_START_SOURCE_FRAME)
            records[key] = cached
            files.append(dict(path=cached['playbackFile'], bytes=cached['playbackBytes512'],
                              sha256=cached['playbackSha256512']))
            reports[key] = dict(report, reusedVerifiedOutput=True)
            print('REUSED '+key+': unchanged source and verified output SHA-256', flush=True)
            continue
        print('PREPARE '+key, flush=True)
        soft_effects = key in SOFT_EFFECTS
        frames, report = decode(path, soft_effects=soft_effects)
        if anchor is None:
            anchor = frames[0].copy()
        # The source clips already share this supplied pose. Do not morph fabric.
        report['originalEndpointDifference'] = [
            float(np.abs(np.asarray(frame, np.float32)-np.asarray(anchor, np.float32)).mean()/255)
            for frame in (frames[0], frames[-1])]
        if max(report['originalEndpointDifference']) > .035:
            raise ValueError('Source endpoints do not match the shared idle pose: '+key)
        # Retain every source frame. Only added entrance/return frames dissolve
        # between complete poses, instead of snapping a source frame to the anchor.
        entry = [] if frames[0].tobytes() == anchor.tobytes() else dissolve(anchor, frames[0], 7)[:-1]
        tail = dissolve(frames[-1], anchor, 10)[1:]
        frames = entry+frames+tail
        report.update(entryFramesAdded=len(entry), returnFramesAdded=len(tail), sourceFramesKept=report['sourceFrames'])
        delays = [round((i+1)*1000/24)-round(i*1000/24) for i in range(len(frames))]
        relative = 'playback-mp4/'+key+'.webp'
        encoded = encode(ASSETS/relative, frames, delays)
        record = dict(id=key, name=path.stem, file=path.relative_to(ASSETS).as_posix(),
                      playbackFile=relative, frames=len(frames), durationMs=sum(delays),
                      loop=key == 'idle', sourceSha256=hashes[key],
                      preparation=RECIPE+'-soft-effects' if soft_effects else RECIPE,
                      sourceFrames=report['sourceFrames'], sourceFrameOffset=len(entry),
                      entryBridgeFrames=len(entry), exitBridgeFrames=len(tail),
                      renderScale=1., renderOffset=[0., 0.], renderAnchor='bottom-center',
                      playbackSha256512=encoded['sha256'], playbackBytes512=encoded['bytes'])
        if key in ('move-left', 'move-right'):
            direction = -1 if key == 'move-left' else 1
            record.update(direction=direction, walk=dict(direction=direction, start=len(entry)+24, end=len(entry)+230))
        if key == 'drag':
            # Finish the inverted action, hold its final pose before the turn
            # upright, then resume the untouched return frames on release.
            record.update(dragHoldFrame=len(entry)+DRAG_HOLD_SOURCE_FRAME,
                          dragStartFrame=len(entry)+DRAG_START_SOURCE_FRAME,
                          releaseFrame=len(entry)+DRAG_HOLD_SOURCE_FRAME+1,
                          dragHoldPolicy=DRAG_HOLD_POLICY)
        records[key] = record
        files.append(dict(path=relative, bytes=encoded['bytes'], sha256=encoded['sha256']))
        report.update(encoded=encoded, allFramesVerified=True)
        reports[key] = report
        preview = Image.new('RGB', (1536, 280), '#253447')
        for column, index in enumerate((0, len(entry)+58, len(entry)+115, len(entry)+173, len(entry)+230, len(frames)-1)):
            tile = frames[index].resize((256, 256), Image.Resampling.LANCZOS)
            preview.paste(tile, (column*256, 12), tile)
        preview.save(BUILD/(key+'-preview.png'))
        print('VERIFIED '+key+': '+str(report['sourceFrames'])+' source frames retained; '+str(len(frames))+' output frames', flush=True)
    reference = hashlib.sha256(anchor.tobytes()).hexdigest()
    for record in records.values():
        record['referencePose'] = reference
    manifest = dict(version=1, character='Gpt', sourceFormat='mp4', preparation=RECIPE,
                    referencePose=reference, idle=records['idle'],
                    variants=[records[key] for key in GESTURES],
                    additionalIdleAnimations=[], workAnimations=[],
                    moveAnimations=[records['move-left'], records['move-right']],
                    dragAnimation=records['drag'],
                    manualMovementActions=True,
                    sourceInventory=[dict(file=path.relative_to(ASSETS).as_posix(), sha256=hashes[key])
                                     for key, path in originals.items()])
    manifest_path = ASSETS/'manifest.json'
    write_json(manifest_path, manifest)
    files.append(dict(path='manifest.json', bytes=manifest_path.stat().st_size, sha256=digest(manifest_path)))
    files.sort(key=lambda item: item['path'])
    identity = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:24]
    tier = dict(id=identity, resolution=512, files=files, bytes=sum(item['bytes'] for item in files))
    write_json(ROOT/'app/material_catalog.json', dict(schema=1, default='light', tiers=dict(light=tier)))
    if any(digest(path) != hashes[key] for key, path in originals.items()):
        raise ValueError('An original MP4 changed during preparation')
    write_json(BUILD/'verification.json', dict(passed=True, recipe=RECIPE, actions=len(records),
                referencePose=reference, originalMP4sPreserved=True, allFramesVerified=True,
                noTextureReconstruction=True, reports=reports))
    print('COMPLETE: '+str(len(records))+' MP4 actions, original RGB, exact shared endpoints.', flush=True)


if __name__ == '__main__':
    main()
