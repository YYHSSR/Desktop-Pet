"""Build only idle and the two walks from the three new original MP4 clips."""
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
from mp4_matte import matte_frame
from share.asset_tools.exact_webp import encode

ASSETS = ROOT/'assets/character'
BUILD = ROOT/'build/mp4-rebuild'
RECIPE = 'mp4-contour-source-rgb-pose-dissolve-v1'
cv2.setNumThreads(1)


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2)+'\n', encoding='utf-8')


def sources():
    files = sorted((ASSETS/'MP4').glob('*.mp4'))
    if len(files) != 3:
        raise ValueError('Expected exactly the idle, left-walk, and right-walk MP4 clips')
    # Names are supplied by the user; generated code and internal IDs stay English.
    names = {'idle': '\u5f85\u673a', 'move-left': '\u5411\u5de6\u8d70\u8d70',
             'move-right': '\u5411\u53f3\u8d70\u8d70'}
    result = {key: next((path for path in files if path.stem == name), None)
              for key, name in names.items()}
    if any(path is None for path in result.values()):
        raise ValueError('The expected idle and directional walking MP4 names are missing')
    return result


def decode(path):
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
            image = matte_frame(Image.fromarray(rgb))
            rgba = np.asarray(image)
            opaque = rgba[..., 3] == 255
            if not np.array_equal(rgba[..., :3][opaque], rgb[opaque]):
                raise ValueError('Matting changed opaque source artwork')
            tinted = (np.ptp(rgb, axis=2) >= 20) & (rgb.min(axis=2) < 235)
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
                        lostTintedPixels=tinted_lost, opaqueRGBMaximumError=0)


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
    records, files, reports = {}, [], {}
    anchor = None
    for key, path in originals.items():
        print('PREPARE '+key, flush=True)
        frames, report = decode(path)
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
                      loop=key == 'idle', sourceSha256=hashes[key], preparation=RECIPE,
                      sourceFrames=report['sourceFrames'], sourceFrameOffset=len(entry),
                      entryBridgeFrames=len(entry), exitBridgeFrames=len(tail),
                      renderScale=1., renderOffset=[0., 0.], renderAnchor='bottom-center',
                      playbackSha256512=encoded['sha256'], playbackBytes512=encoded['bytes'])
        if key != 'idle':
            direction = -1 if key == 'move-left' else 1
            record.update(direction=direction, walk=dict(direction=direction, start=len(entry)+24, end=len(entry)+230))
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
                    referencePose=reference, idle=records['idle'], variants=[],
                    additionalIdleAnimations=[], workAnimations=[],
                    moveAnimations=[records['move-left'], records['move-right']],
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
    write_json(BUILD/'verification.json', dict(passed=True, recipe=RECIPE, actions=3,
                referencePose=reference, originalMP4sPreserved=True, allFramesVerified=True,
                noTextureReconstruction=True, reports=reports))
    print('COMPLETE: three MP4 actions, original RGB, exact shared endpoints.', flush=True)


if __name__ == '__main__':
    main()
