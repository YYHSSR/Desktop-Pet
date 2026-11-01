"""Offline transparent animation preparation shared by new companion roles."""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from .white_background import matte_white, bounds

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def transform_for(source, effects_crop=False):
    boxes, bodies = [], []
    indexes = sorted(set(range(0, source.n_frames, 10)) | {source.n_frames - 1})
    for index in indexes:
        source.seek(index)
        frame = matte_white(source)
        box, body = bounds(frame), bounds(frame, largest=True)
        if box and body:
            boxes.append(box)
            bodies.append(body)
    if not bodies:
        raise ValueError('No visible character after background removal')
    union = (min(b[0] for b in boxes), min(b[1] for b in boxes),
             max(b[2] for b in boxes), max(b[3] for b in boxes))
    centre = float(np.median([(b[0] + b[2]) / 2 for b in bodies]))
    baseline = max(b[3] for b in bodies)
    height = float(np.median([b[3] - b[1] for b in bodies]))
    fitting = ((min(b[0] for b in bodies), min(b[1] for b in bodies),
                max(b[2] for b in bodies), max(b[3] for b in bodies)) if effects_crop else union)
    scale = min(438 / height, 238 / max(1, centre - fitting[0], fitting[2] - centre),
                470 / max(1, baseline - fitting[1]))
    if not effects_crop:
        scale = min(scale, 18 / max(1, union[3]-baseline))
    return dict(scale=scale, centre=centre, baseline=baseline, union=union, effectsCrop=effects_crop)


def align(frame, transform):
    box = transform['union']
    scale = transform['scale']
    # Premultiplied filtering avoids a dark fringe around alpha when resizing.
    cropped = frame.crop(box).convert('RGBa')
    resized = cropped.resize((max(1, round(cropped.width * scale)),
                              max(1, round(cropped.height * scale))), Image.Resampling.LANCZOS).convert('RGBA')
    canvas = Image.new('RGBA', (512, 512))
    position = (round(256 + (box[0] - transform['centre']) * scale),
                round(488 + (box[1] - transform['baseline']) * scale))
    canvas.paste(resized, position)
    if transform.get('effectsCrop'):
        # Snow/star particles may reach the edge; fade them through a gutter
        # instead of reducing the entire character to fit a particle field.
        rgba = np.asarray(canvas).copy()
        yy, xx = np.mgrid[:512, :512]
        edge = np.minimum.reduce((xx, yy, 511-xx, 511-yy))
        feather = np.clip(edge/10, 0, 1)
        feather = feather*feather*(3-2*feather)
        rgba[..., 3] = np.rint(rgba[..., 3]*feather).astype(np.uint8)
        canvas = Image.fromarray(rgba)
    return canvas


def loop_cut(frames, durations):
    features = [np.asarray(frame.resize((40, 40)), dtype=np.float32) / 255 for frame in frames]
    count = len(frames)
    pairs = ((float(np.mean((features[a] - features[b]) ** 2)), a, b)
             for a in range(0, min(24, count // 6), 2)
             for b in range(max(count * 3 // 4, count - 48), count, 2))
    score, start, end = min(pairs)
    selected = frames[start:end]
    timing = durations[start:end]
    overlap = 5
    # A short overlap after selecting matching poses, with uninterrupted timing.
    seam = [Image.blend(selected[-overlap + i], selected[i], (i + 1) / overlap)
            for i in range(overlap)]
    return selected[overlap:-overlap] + seam, timing[overlap:], dict(
        startFrame=start, endFrame=end, overlapFrames=overlap, poseDifference=round(score, 6))



from .pose_bridge import pose_bridge, visible_difference
RECIPE = "registered-body-flow-windowed-dissolve-best-cut-adaptive"
EFFECT_EXITS = ('catch', 'flower', 'sparkles')  # particles need time to settle
CUT_WINDOW = 12             # frames searched at each end for the pose nearest idle


def nearest(frames, anchor, indices):
    """The index whose pose is closest to the anchor (scored at quarter size)."""
    small = anchor.resize((128, 128))
    scores = {i: visible_difference(frames[i].resize((128, 128)), small) for i in indices}
    return min(scores, key=scores.get), scores


def best_cut(frames, anchor):
    """Trim at most CUT_WINDOW frames from either end when that clearly
    shortens the morph to and from the idle pose."""
    window = min(CUT_WINDOW, len(frames)//6)
    start, scores = nearest(frames, anchor, range(window+1))
    if scores[start] > scores[0]*.88:
        start = 0
    end, scores = nearest(frames, anchor, range(len(frames)-1-window, len(frames)))
    if scores[end] > scores[len(frames)-1]*.88:
        end = len(frames)-1
    return start, end


def bridge_lengths(key, first, last, anchor):
    """Longer bridges for poses further from idle, so the morph never rushes."""
    entry = max(9, min(18, round(8+70*visible_difference(anchor, first))))
    exit_count = max(12, min(22, round(10+80*visible_difference(last, anchor))))
    return entry, (max(exit_count, 22) if key in EFFECT_EXITS else exit_count)

def timing(count):
    return [round((i+1)*1000/24)-round(i*1000/24) for i in range(count)]


def preview(frames, path):
    sheet = Image.new('RGB', (1024, 256), '#f8f5fb')
    for column, index in enumerate((0, len(frames)//3, len(frames)*2//3, len(frames)-1)):
        frame = frames[index].resize((256, 256), Image.Resampling.LANCZOS)
        sheet.paste(frame, (column*256, 0), frame)
    sheet.save(path, quality=95)


def prepare_bridges(root, records):
    ROOT = Path(root)
    assets = ROOT/'assets/character'
    base = ROOT/'build/animation-base'
    playback = assets/'playback'
    with Image.open(base/'idle.webp') as source:
        source.seek(0)
        anchor = source.convert('RGBA')
    reference = hashlib.sha256(anchor.tobytes()).hexdigest()
    previews = ROOT/'build/transition-previews'
    previews.mkdir(parents=True, exist_ok=True)
    result = []
    for item in records:
        key = item['id']
        target, receipt = playback/(key+'.webp'), playback/(key+'.json')
        base_path = base/(key+'.webp')
        base_checksum = digest(base_path)
        if receipt.exists() and target.exists():
            previous = json.loads(receipt.read_text(encoding='utf-8'))
            if (previous.get('transitionRecipe') == RECIPE and previous.get('baseSha256') == base_checksum
                    and previous.get('referencePose') == reference and previous['sha256'] == digest(target)):
                result.append(previous)
                print('CACHED bridge '+key, flush=True)
                continue
        print('BRIDGE '+key, flush=True)
        frames, durations = [], []
        with Image.open(base_path) as source:
            for index in range(source.n_frames):
                source.seek(index)
                source.load()
                frames.append(source.convert('RGBA'))
                durations.append(int(source.info.get('duration', 42)))
        if key == 'idle':
            count = 14
            tail = pose_bridge(frames[-count], anchor, count)
            output, output_timing = frames[:-count]+tail, durations
            entry_count, exit_count = 0, count
            preview(tail, previews/(key+'-loop.jpg'))
        else:
            start, end = best_cut(frames, anchor)
            frames, durations = frames[start:end+1], durations[start:end+1]
            entry_count, exit_count = bridge_lengths(key, frames[0], frames[-1], anchor)
            entrance = pose_bridge(anchor, frames[0], entry_count)
            exit_frames = pose_bridge(frames[-1], anchor, exit_count)
            output = entrance[:-1]+frames+exit_frames[1:]
            output_timing = timing(entry_count-1)+durations+timing(exit_count-1)
            preview(entrance, previews/(key+'-entry.jpg'))
            preview(exit_frames, previews/(key+'-exit.jpg'))
        temporary = target.with_suffix('.preparing.webp')
        output[0].save(temporary, save_all=True, append_images=output[1:], duration=output_timing,
                       loop=0, quality=94, alpha_quality=100, method=4)
        temporary.replace(target)
        with Image.open(target) as check:
            frame_count = check.n_frames
            first = check.convert('RGBA')
            check.seek(frame_count-1)
            check.load()
            last = check.convert('RGBA')
            gap = visible_difference(first, last)
            if gap > .012:
                raise ValueError('Reference pose does not close: '+key)
        record = dict(item, sha256=digest(target), bytes=target.stat().st_size,
                      frames=frame_count, durationMs=sum(output_timing), transitionRecipe=RECIPE,
                      baseSha256=base_checksum, referencePose=reference,
                      entryBridgeFrames=entry_count, exitBridgeFrames=exit_count,
                      endpointDifference=round(gap, 6))
        if key != 'idle':
            record['bridgeCut'] = [start, end]
        receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        result.append(record)
        print(f'OK bridge {key}: gap={gap:.6f}, frames={frame_count}', flush=True)
    manifest = json.loads((assets/'character.json').read_text(encoding='utf-8'))
    manifest['actions'] = result
    manifest['referencePose'] = reference
    (assets/'character.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result


