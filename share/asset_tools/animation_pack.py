"""Offline transparent animation preparation shared by new companion roles."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from .exact_webp import encode
from .pose_bridge import pose_bridge, visible_difference
from .white_background import matte_white, bounds


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def transform_for(source, effects_crop=False, travel=False):
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
    if travel:
        # A walk swings wide: keep her the idle's height and let the hair
        # brush the feathered canvas edge instead of shrinking her.
        scale = min(438 / height, 470 / max(1, baseline - fitting[1]))
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


RECIPE = "trimmed-hold-adaptive-bridge-best-cut-v2"
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
    """Short when the pose already matches, longer the further it must travel,
    so a bridge never rushes and never idles at the shared pose."""
    entry = max(4, min(16, round(4+110*visible_difference(anchor, first))))
    exit_count = max(8, min(22, round(6+130*visible_difference(last, anchor))))
    return entry, (max(exit_count, 18) if key in EFFECT_EXITS else exit_count)


STILL = .004    # mean change per frame (96 px) below which a frame is held


def trim_still(frames, durations, kept=None, keep=2):
    """Drop held frames at either end: a clip that waits before it moves, or
    holds its last pose, reads as a pause at the shared pose."""
    kept = list(range(len(frames))) if kept is None else list(kept)
    small = [np.asarray(frame.resize((96, 96)), np.float32)/255 for frame in frames]
    moving = [float(np.mean(np.abs(b-a))) >= STILL for a, b in zip(small, small[1:])]
    lead = next((i for i, value in enumerate(moving) if value), len(moving))
    tail = next((i for i, value in enumerate(reversed(moving)) if value), len(moving))
    first, last = max(0, lead-keep), len(frames)-1-max(0, tail-keep)
    if last-first < 24:
        return list(frames), list(durations), kept
    return frames[first:last+1], durations[first:last+1], kept[first:last+1]


def bridged(key, frames, durations, anchor, kept=None):
    """Trim held ends, cut nearest the shared pose, bridge in and out.

    Returns the frames, their timing and a placement record: `kept` lists the
    source frame behind every body frame, which starts at index entry-1."""
    frames, durations, kept = trim_still(frames, durations, kept)
    start, end = best_cut(frames, anchor)
    frames, durations, kept = frames[start:end+1], durations[start:end+1], kept[start:end+1]
    entry, exit_count = bridge_lengths(key, frames[0], frames[-1], anchor)
    entrance, tail = pose_bridge(anchor, frames[0], entry), pose_bridge(frames[-1], anchor, exit_count)
    output = entrance[:-1]+frames+tail[1:]
    output_timing = timing(entry-1)+durations+timing(exit_count-1)
    return output, output_timing, dict(entry=entry, exit=exit_count, kept=kept)


def loop_back(frames, durations):
    """Idle: trim held ends, then bridge the last pose back to the first, which
    becomes the shared pose every clip starts and ends on."""
    frames, durations, kept = trim_still(frames, durations)
    count = max(6, min(14, round(4+110*visible_difference(frames[-1], frames[0]))))
    return frames+pose_bridge(frames[-1], frames[0], count)[1:], durations+timing(count-1), dict(exit=count, kept=kept)


def placed(kept, entry, source_frame):
    """Where a source frame lands in a bridged clip (nearest kept frame)."""
    position = min(range(len(kept)), key=lambda i: abs(kept[i]-source_frame))
    return entry-1+position


def timing(count):
    return [round((i+1)*1000/24)-round(i*1000/24) for i in range(count)]


def preview(frames, path):
    sheet = Image.new('RGB', (1024, 256), '#f8f5fb')
    for column, index in enumerate((0, len(frames)//3, len(frames)*2//3, len(frames)-1)):
        frame = frames[index].resize((256, 256), Image.Resampling.LANCZOS)
        sheet.paste(frame, (column*256, 0), frame)
    sheet.save(path, quality=95)


def held_loop(frames, window, shortest=24):
    """The stretch inside `window` whose two ends match best, for a held drag."""
    first, last = window
    small = {i: frames[i].resize((128, 128)) for i in range(first, last+1)}
    _, start, end = min((visible_difference(small[a], small[b]), a, b)
                        for a in range(first, last+1-shortest) for b in range(a+shortest, last+1))
    return start, end


def read_frames(path):
    frames, durations = [], []
    with Image.open(path) as source:
        for index in range(source.n_frames):
            source.seek(index)
            source.load()
            frames.append(source.convert('RGBA'))
            durations.append(int(source.info.get('duration', 42)))
    return frames, durations


def write_frames(path, frames, durations, lossless):
    if lossless:
        return encode(path, frames, durations)
    temporary = path.with_suffix('.preparing.webp')
    frames[0].save(temporary, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, quality=94, alpha_quality=100, method=4)
    temporary.replace(path)
    return dict(frames=len(frames), durationMs=sum(durations), bytes=path.stat().st_size, sha256=digest(path))


def prepare_bridges(root, records, *, lossless=False, walks=None, drag=None, hold=None):
    """Bridge every clip to the idle's first pose and write the playback pack.

    walks maps a key to (direction, first, last): the base frames during which
    she travels. drag is (key, window): the base frames searched for a held
    loop; her pickup plays up to that loop and letting go leaves from its end.
    hold is (key, release, sway): the whole base clip is kept, a pickup plays
    up to the release frame even when let go early, a long hold sways through
    the `sway` frames before it, and letting go plays the clip's own way down.
    """
    root = Path(root)
    assets = root/'assets/character'
    base = root/'build/animation-base'
    playback = assets/'playback'
    previews = root/'build/transition-previews'
    previews.mkdir(parents=True, exist_ok=True)
    walks = walks or {}
    recipe = RECIPE+('-exact' if lossless else '')
    idle_key = next(item['id'] for item in records if item.get('loop'))
    idle_frames, idle_timing, idle_place = loop_back(*read_frames(base/(idle_key+'.webp')))
    anchor = idle_frames[0]
    reference = hashlib.sha256(anchor.tobytes()).hexdigest()

    def one(item):
        key = item['id']
        target, receipt = playback/(key+'.webp'), playback/(key+'.json')
        base_checksum = digest(base/(key+'.webp'))
        settings = dict(walk=walks.get(key), drag=drag[1] if drag and drag[0] == key else None)
        if hold and hold[0] == key:
            settings['hold'] = list(hold[1:])
        if receipt.exists() and target.exists():
            previous = json.loads(receipt.read_text(encoding='utf-8'))
            held = previous.get('dragLoopFile')
            if (previous.get('transitionRecipe') == recipe and previous.get('baseSha256') == base_checksum
                    and previous.get('referencePose') == reference and previous.get('bridgeSettings') == settings
                    and previous['sha256'] == digest(target)
                    and (not held or (assets/held).is_file() and digest(assets/held) == previous['dragLoopSha256'])):
                print('CACHED bridge '+key, flush=True)
                return previous
        print('BRIDGE '+key, flush=True)
        record = dict(item, transitionRecipe=recipe, baseSha256=base_checksum, referencePose=reference,
                      bridgeSettings=settings)
        if key == idle_key:
            output, output_timing = idle_frames, idle_timing
            record.update(entryBridgeFrames=0, exitBridgeFrames=idle_place['exit'],
                          bridgeCut=[idle_place['kept'][0], idle_place['kept'][-1]])
        elif settings.get('hold'):
            frames, durations = read_frames(base/(key+'.webp'))
            release, sway = settings['hold']
            exit_count = bridge_lengths(key, frames[0], frames[-1], anchor)[1]
            output = pose_bridge(anchor, frames[0], 4)[:-1]+frames+pose_bridge(frames[-1], anchor, exit_count)[1:]
            output_timing = timing(3)+durations+timing(exit_count-1)
            # Back and forth through the settled frames, ending on the release frame.
            held = frames[release-1:release-sway-1:-1]+frames[release-sway+1:release+1]
            held_name = 'playback/'+key+'-held.webp'
            looped = write_frames(assets/held_name, held, timing(len(held)), True)
            record.update(entryBridgeFrames=4, exitBridgeFrames=exit_count, bridgeCut=[0, len(frames)-1],
                          dragStartFrame=3, dragLoopEnd=3+release, releaseFrame=3+release, liftCompletes=True,
                          dragLoopFile=held_name, dragLoopFrames=looped['frames'], dragLoopSha256=looped['sha256'],
                          dragLoopBytes=looped['bytes'], dragLoopSourceRange=[release-sway, release])
        elif settings['drag']:
            frames, durations = read_frames(base/(key+'.webp'))
            start, end = held_loop(frames, settings['drag'])
            exit_count = bridge_lengths(key, frames[0], frames[end], anchor)[1]
            output = pose_bridge(anchor, frames[0], 4)[:-1]+frames[:end+1]+pose_bridge(frames[end], anchor, exit_count)[1:]
            output_timing = timing(3)+durations[:end+1]+timing(exit_count-1)
            held = pose_bridge(frames[end], frames[start], 9)[1:]+frames[start+1:end+1]
            held_name = 'playback/'+key+'-held.webp'
            looped = write_frames(assets/held_name, held, timing(len(held)), True)
            record.update(entryBridgeFrames=4, exitBridgeFrames=exit_count, bridgeCut=[0, end],
                          dragStartFrame=3, dragLoopEnd=3+end, dragLoopFile=held_name,
                          dragLoopFrames=looped['frames'], dragLoopSha256=looped['sha256'],
                          dragLoopBytes=looped['bytes'], dragLoopSourceRange=[start, end])
        else:
            output, output_timing, place = bridged(key, *read_frames(base/(key+'.webp')), anchor)
            record.update(entryBridgeFrames=place['entry'], exitBridgeFrames=place['exit'],
                          bridgeCut=[place['kept'][0], place['kept'][-1]])
            if settings['walk']:
                direction, first, last = settings['walk']
                record['walk'] = dict(direction=direction, start=placed(place['kept'], place['entry'], first),
                                      end=placed(place['kept'], place['entry'], last))
        written = write_frames(target, output, output_timing, lossless)
        with Image.open(target) as check:
            first = check.convert('RGBA')
            check.seek(check.n_frames-1)
            check.load()
            gap = visible_difference(first, check.convert('RGBA'))
        if gap > .012:
            raise ValueError('Reference pose does not close: '+key)
        record.update(sha256=written['sha256'], bytes=written['bytes'], frames=written['frames'],
                      durationMs=written['durationMs'], endpointDifference=round(gap, 6))
        preview(output, previews/(key+'.jpg'))
        receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(f'OK bridge {key}: gap={gap:.6f}, frames={written["frames"]}', flush=True)
        return record

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(one, records))
    manifest = json.loads((assets/'character.json').read_text(encoding='utf-8'))
    manifest['actions'] = result
    manifest['referencePose'] = reference
    (assets/'character.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result
