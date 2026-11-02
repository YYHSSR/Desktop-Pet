"""Temporal clean-up for animations whose transparency was cut frame by frame.

A generated clip is cut out one frame at a time, so a white ruffle or a lock
of hair can vanish for a frame and come back, which reads as flicker on the
desktop; a few clips even lose the back of the hair for a dozen frames.
Long gaps are rebuilt by flowing the nearest complete frames together; short
blinks are patched from the frames either side.
"""
import cv2
import numpy as np
from PIL import Image
from .pose_bridge import pose_bridge, premultiplied, straight
from .white_background import hull

DROPOUT = .92   # a frame this much smaller than its neighbourhood lost part of the body
REACH = 16      # how far to look for a complete frame on either side
NEIGHBOURS = 8
MIN_BLINK = 16  # pixels; smaller specks are compression noise or edge shimmer


def solid_area(frame):
    return int(np.count_nonzero(np.asarray(frame.getchannel('A')) > 128))


def dropout_frames(frames):
    area = np.array([solid_area(frame) for frame in frames], float)
    bad = []
    for index in range(len(frames)):
        around = np.concatenate((area[max(0, index-NEIGHBOURS):index], area[index+1:index+1+NEIGHBOURS]))
        if len(around) and area[index] < DROPOUT*np.percentile(around, 75):
            bad.append(index)
    return bad


def fill_from(frame, guide):
    """Lay the frame over its guide, but only inside the frame's own outline."""
    current, reference = premultiplied(frame), premultiplied(guide)
    inside = cv2.GaussianBlur(hull(current[..., 3] > .3, 31).astype(np.float32), (7, 7), 1.5)[..., None]
    return straight(current+reference*inside*(1-current[..., 3:]))


def refill_dropouts(frames):
    """Rebuild frames that lost a large part of the body from complete neighbours."""
    bad = set(dropout_frames(frames))
    result = list(frames)
    spans = []
    for index in sorted(bad):
        before = next((i for i in range(index-1, max(-1, index-REACH-1), -1) if i not in bad), None)
        after = next((i for i in range(index+1, min(len(frames), index+REACH+1)) if i not in bad), None)
        if before is None and after is None:
            continue
        if spans and spans[-1][:2] == (before, after):
            spans[-1][2].append(index)
        else:
            spans.append((before, after, [index]))
    for before, after, indices in spans:
        if before is None or after is None:
            # At either end of the clip only one complete frame is available.
            source = frames[after if before is None else before]
            for index in indices:
                result[index] = fill_from(frames[index], source)
            continue
        guides = pose_bridge(frames[before], frames[after], after-before+1)
        for index in indices:
            result[index] = fill_from(frames[index], guides[index-before])
    return result, sorted(bad)


def components(mask, minimum=MIN_BLINK):
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(count, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= minimum
    return keep[labels]


def steady_blinks(frames):
    """Patch pixels that drop out (or pop in as white backdrop) for one or two frames."""
    if len(frames) < 3:
        return list(frames), 0
    rgba = np.stack([np.asarray(frame.convert('RGBA')) for frame in frames])
    alpha = rgba[..., 3]
    result = rgba.copy()
    patched = 0
    for index in range(1, len(frames)-1):
        for width in (1, 2):
            after = index+width
            if after >= len(frames):
                continue
            before, span = index-1, slice(index, after)
            hole = (alpha[before] > 200) & (alpha[after] > 200) & np.all(alpha[span] < 96, axis=0)
            # Only backdrop-coloured pop-ins: coloured sparkles may live one frame.
            colour = rgba[span, ..., :3]
            backdrop = np.all((colour.min(axis=-1) > 215) & (np.ptp(colour, axis=-1) < 30), axis=0)
            ghost = (alpha[before] < 40) & (alpha[after] < 40) & np.all(alpha[span] > 200, axis=0) & backdrop
            hole, ghost = components(hole), components(ghost)
            if not hole.any() and not ghost.any():
                continue
            a, b = rgba[before][hole].astype(np.float32), rgba[after][hole].astype(np.float32)
            for step, frame_index in enumerate(range(index, after), 1):
                t = step/(width+1)
                weight = a[:, 3]*(1-t)+b[:, 3]*t
                mixed = (a[:, :3]*a[:, 3:]*(1-t)+b[:, :3]*b[:, 3:]*t)/np.maximum(weight, 1)[:, None]
                result[frame_index][hole] = np.rint(np.concatenate((mixed, weight[:, None]), axis=1)).astype(np.uint8)
                result[frame_index][ghost, 3] = np.rint(alpha[before][ghost]*(1-t)+alpha[after][ghost]*t).astype(np.uint8)
            patched += int(hole.sum()+ghost.sum())
    return [Image.fromarray(value) for value in result], patched


def repair(frames, passes=3):
    """Refill until no frame is missing a part (a rebuilt frame becomes a guide
    for its neighbours), then steady the blinks. Returns frames and a report."""
    refilled = set()
    for _ in range(passes):
        frames, dropouts = refill_dropouts(frames)
        if not dropouts or refilled.issuperset(dropouts) and len(refilled) > len(dropouts):
            break
        refilled.update(dropouts)
    frames, patched = steady_blinks(frames)
    return frames, dict(refilledFrames=sorted(refilled), patchedPixels=patched)


def enclosed(mask, body, outside=.12):
    """Components of mask ringed by the body, not pockets of the backdrop that
    the outline hull happens to close over (between the horns, under a wing)."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(count, bool)
    height, width = mask.shape
    cross = np.ones((3, 3), np.uint8)
    for index in range(1, count):
        x, y, w, h, _ = stats[index]
        window = (slice(max(0, y-3), min(height, y+h+3)), slice(max(0, x-3), min(width, x+w+3)))
        region = (labels[window] == index).astype(np.uint8)
        ring = (cv2.dilate(region, cross, iterations=2) > 0) & (region == 0)
        keep[index] = np.mean(~body[window][ring]) <= outside
    return keep[labels]


def components_under(mask, area, connectivity=4):
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=connectivity)
    keep = np.zeros(count, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] < area
    return keep[labels]


def recover_cutout(image):
    """Reopen artwork that a supplied cut-out made transparent.

    The Gpt clips arrive already cut out, and the cutter took the pale lace
    petticoat, tail scales and wing membrane for backdrop in blotches that
    change every frame. The lossy encoder kept their colours beneath alpha 0,
    except in fully transparent 4x4 blocks, which it flattened. A hole inside
    her outline whose hidden colour is tinted artwork is made solid again;
    flattened, blank or white (real backdrop) holes stay open.
    """
    value = np.asarray(image.convert('RGBA'))
    rgb, alpha = value[..., :3], value[..., 3]
    body = hull(alpha > 76, 31)
    hole = enclosed(body & (alpha < 200), body)
    median = cv2.medianBlur(rgb, 5)
    speck = np.abs(rgb.astype(np.int16)-median.astype(np.int16)).max(axis=-1) > 32
    colour = np.where(speck[..., None], median, rgb)
    channels = colour.astype(np.int16)
    low, high = channels.min(axis=-1), channels.max(axis=-1)
    backdrop = (low >= 238) & (high-low <= 12)
    height, width = alpha.shape
    rows, columns = height//4*4, width//4*4
    blocks = rgb[:rows, :columns].reshape(rows//4, 4, columns//4, 4, 3).astype(np.int16)
    flat = np.zeros_like(alpha, bool)
    flat[:rows, :columns] = np.repeat(np.repeat(
        (blocks.max(axis=(1, 3))-blocks.min(axis=(1, 3))).max(axis=-1) <= 8, 4, 0), 4, 1)
    # Her palette is lavender and white: green is never the strongest channel,
    # while the encoder's leftovers drift grey-green.
    off_palette = channels[..., 1] > np.minimum(channels[..., 0], channels[..., 2])+6
    lost = flat | (high < 70) | (high-low <= 5) | off_palette
    restore = hole & ~backdrop & ~lost
    # A white highlight inside the lace is art; a wide white gap is backdrop.
    restore |= hole & backdrop & components_under(hole & backdrop, 40)
    # Small leftovers inside reopened lace are filled; wide ones are real gaps.
    leftover = hole & ~restore
    specks = leftover & components_under(leftover, 60)
    if specks.any():
        # Their hidden colour is gone: paint them in from the artwork around.
        x, y, w, h = cv2.boundingRect(body.astype(np.uint8))
        window = (slice(y, y+h), slice(x, x+w))
        trusted = ((alpha >= 200) | restore) & body
        painted = colour.astype(np.uint8).copy()
        painted[window] = cv2.inpaint(np.ascontiguousarray(painted[window]),
                                      (~trusted[window]).astype(np.uint8), 3, cv2.INPAINT_TELEA)
        colour = np.where(specks[..., None], painted, colour)
    restore |= specks
    gap = ~body | (body & (alpha < 200) & ~hole) | (leftover & ~specks)
    # The cutter's own fringe along a real gap is encoder noise.
    restore &= cv2.dilate(gap.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) == 0
    restore &= ~components_under(restore, 6, connectivity=8)
    # Luma keeps the hidden texture; lossy chroma there turns blotchy, so the
    # tint comes from the intact artwork around it.
    ycc = cv2.cvtColor(cv2.medianBlur(colour.astype(np.uint8), 3), cv2.COLOR_RGB2YCrCb).astype(np.float32)
    weight = ((alpha >= 250) & body).astype(np.float32)
    support = cv2.GaussianBlur(weight, (0, 0), 6)
    tint = cv2.GaussianBlur(ycc[..., 1:]*weight[..., None], (0, 0), 6)/np.maximum(support, 1e-3)[..., None]
    ycc[..., 1:] = np.where((restore & (support > .02))[..., None], tint, ycc[..., 1:])
    result = value.copy()
    result[restore, :3] = cv2.cvtColor(np.clip(np.rint(ycc), 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2RGB)[restore]
    result[restore, 3] = 255
    return Image.fromarray(result)


def steady_gaps(frames, reach=3, largest=400, share=.4):
    """Close small holes that most nearby frames show solid; never open any."""
    rgba = np.stack([np.asarray(frame.convert('RGBA')) for frame in frames])
    alpha = rgba[..., 3]
    result = rgba.copy()
    for index in range(len(frames)):
        first, last = max(0, index-reach), min(len(frames), index+reach+1)
        solid = (alpha[first:last] > 128).mean(axis=0)
        holes = (alpha[index] < 128) & hull(alpha[index] > 76, 31)
        todo = holes & components_under(holes, largest+1) & (solid >= share)
        for other in sorted(range(first, last), key=lambda other: (abs(other-index), other)):
            if other == index or not todo.any():
                continue
            take = todo & (alpha[other] > 128)
            result[index][take] = rgba[other][take]
            todo &= ~take
    return [Image.fromarray(value) for value in result]
