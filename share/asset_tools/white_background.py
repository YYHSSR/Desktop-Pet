"""Remove a flat light video backdrop while keeping white clothes and hair solid.

This is deterministic matting for the supplied flat-background animation clips.
It is not a general image segmentation model or a reconstruction of clipped art.
"""
from collections import deque
import cv2
import numpy as np
from PIL import Image

SEAL = 2        # outline gaps up to twice this many pixels wide stay closed
BACKDROP = 6    # how far (per channel) a pixel may stray from the flat backdrop
POCKET = 12     # the same, for enclosed pockets tinted by the hair around them


def flood(passable):
    """Pixels reachable from the image border through passable pixels."""
    padded = np.pad(passable.astype(np.uint8) * 255, 1, constant_values=255)
    cv2.floodFill(padded, None, (0, 0), 128, flags=4)
    return padded[1:-1, 1:-1] == 128


def matte_white(image):
    rgb = np.asarray(image.convert('RGB')).copy()
    low = rgb.min(axis=2).astype(np.int16)
    chroma = rgb.max(axis=2).astype(np.int16) - low
    light = (low >= 205) & (chroma <= 38)
    # Outside her outline, anything light and near neutral goes with the
    # backdrop (pale glows and the antialiased rim included).
    lenient = ~flood(light)
    # Inside it, only the flat backdrop colour itself may carry the flood:
    # white clothes are tinted and shaded, so a ruffle touching the backdrop
    # is no longer washed out on some frames only.
    border = np.concatenate((rgb[:4].reshape(-1, 3), rgb[-4:].reshape(-1, 3),
                             rgb[:, :4].reshape(-1, 3), rgb[:, -4:].reshape(-1, 3)))
    backdrop_like = np.abs(rgb.astype(np.int16) - np.median(border, axis=0)).max(axis=2) <= BACKDROP
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*SEAL+1, 2*SEAL+1))
    backdrop = flood(backdrop_like & (cv2.dilate((~backdrop_like).astype(np.uint8), kernel) == 0)).astype(np.uint8)
    cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    for _ in range(SEAL+1):
        backdrop = cv2.dilate(backdrop, cross) & backdrop_like
    strict = backdrop == 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(lenient.astype(np.uint8), connectivity=8)
    foreground = lenient.copy()
    if count > 1:
        foreground |= strict & hull(labels == 1 + stats[1:, cv2.CC_STAT_AREA].argmax(), 41)
        # Backdrop pockets closed in by curls (an ahoge loop, gaps in the hair)
        # are ringed by hair; a white ruffle is ringed by more white, and an
        # eye highlight by dark iris. Pockets go, with their tinted rim.
        distance = np.abs(rgb.astype(np.int16) - np.median(border, axis=0)).max(axis=2)
        pockets = ((distance <= POCKET) & foreground).astype(np.uint8)
        pocket_count, pocket_labels, pocket_stats, _ = cv2.connectedComponentsWithStats(pockets, connectivity=4)
        height, width = pockets.shape
        for index in range(1, pocket_count):
            x, y, w, h, area = pocket_stats[index]
            if area < 80:
                continue
            window = (slice(max(0, y-5), min(height, y+h+5)), slice(max(0, x-5), min(width, x+w+5)))
            region = (pocket_labels[window] == index).astype(np.uint8)
            ring = cv2.dilate(region, cross, iterations=3).astype(bool) & ~region.astype(bool)
            if np.median(low[window][ring]) < 100 or np.mean(light[window][ring]) > .6:
                continue
            for _ in range(2):
                region = cv2.dilate(region, cross) & light[window]
            foreground[window][region > 0] = False
    foreground = foreground.astype(np.uint8)
    # Discard only tiny detached compression specks; keep coloured star effects.
    count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground, connectivity=8)
    keep = np.zeros(count, dtype=np.uint8)
    keep[1:] = (stats[1:, cv2.CC_STAT_AREA] >= 7).astype(np.uint8)
    foreground = keep[labels]
    if count > 1:
        main = 1 + stats[1:, cv2.CC_STAT_AREA].argmax()
        x, y, width, height, _ = stats[main]
        # White negative spaces enclosed by hair curls cannot reach the border.
        # Only clear neutral islands outside the central face/clothes area and
        # below the ears. Detached coloured star effects retain their interiors.
        islands = ((foreground > 0) & (low >= 231) & (chroma <= 18)).astype(np.uint8)
        islands_count, island_labels, island_stats, centres = cv2.connectedComponentsWithStats(islands, connectivity=8)
        for index in range(1, islands_count):
            if island_stats[index, cv2.CC_STAT_AREA] < 12:
                continue
            cx, cy = centres[index]
            outside_core = abs(cx - (x + width / 2)) > width * .235
            if cy <= y + height * .24 or not outside_core:
                continue
            region = island_labels == index
            if np.count_nonzero(labels[region] == main) > np.count_nonzero(region) * .9:
                foreground[region] = 0
    alpha = cv2.GaussianBlur(foreground.astype(np.float32), (3, 3), .48)
    # Do not invent a light halo from a blank source-background pixel.
    alpha[(foreground == 0) & (low > 244) & (chroma < 10)] = 0
    alpha[alpha < .025] = 0
    # Unmix the white backing at subpixel edges before writing straight RGBA.
    safe = np.maximum(alpha[..., None], .025)
    colour = np.clip((rgb.astype(np.float32) - 255 * (1 - alpha[..., None])) / safe, 0, 255)
    rgba = np.dstack((colour.astype(np.uint8), np.rint(alpha * 255).astype(np.uint8)))
    rgba[alpha == 0, :3] = 0
    return Image.fromarray(rgba)


def hull(mask, size=15):
    """A body mask with narrow gaps bridged and enclosed holes filled."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    closed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    padded = np.pad(1 - closed, 1, constant_values=1) * 255
    cv2.floodFill(padded, None, (0, 0), 128, flags=4)
    return padded[1:-1, 1:-1] != 128


def bounds(image, largest=False):
    mask = (np.asarray(image.getchannel('A')) > 40).astype(np.uint8)
    if not largest:
        return image.getchannel('A').getbbox()
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return None
    x, y, width, height, _ = stats[1 + stats[1:, cv2.CC_STAT_AREA].argmax()]
    return int(x), int(y), int(x + width), int(y + height)


def backdrop_distance(rgb):
    border = np.concatenate((rgb[:4].reshape(-1, 3), rgb[-4:].reshape(-1, 3),
                             rgb[:, :4].reshape(-1, 3), rgb[:, -4:].reshape(-1, 3)))
    return np.abs(rgb.astype(np.int16) - np.median(border, axis=0)).max(axis=2)


def matte_white_lace(image, tolerance=3, flatness=1., reach=40, broad=9):
    """matte_white, plus sheer white ruffles it takes for backdrop.

    A pale petticoat hem is within a few levels of a white backdrop, so the
    lenient outer flood eats it in blotches that differ every frame. Near her
    outline, only the backdrop itself (flat and within `tolerance` of it) may
    carry the flood here; what it leaves is lace if it is broad, has some
    texture or tint of its own, and is ringed by pale fabric rather than hair
    (a gap between curls) or by open backdrop (a stray speck).
    """
    base = np.asarray(matte_white(image))
    rgb = np.asarray(image.convert('RGB'))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    spread = np.sqrt(np.maximum(cv2.blur(gray*gray, (5, 5)) - cv2.blur(gray, (5, 5))**2, 0))
    flat = (backdrop_distance(rgb) <= tolerance) & (spread <= flatness)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*SEAL+1, 2*SEAL+1))
    backdrop = flood(flat & (cv2.dilate((~flat).astype(np.uint8), kernel) == 0)).astype(np.uint8)
    cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    for _ in range(SEAL+1):
        backdrop = cv2.dilate(backdrop, cross) & flat
    open_ = backdrop > 0
    solid = base[..., 3] > 128
    near = cv2.dilate(solid.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*reach+1, 2*reach+1))) > 0
    lace = near & ~open_ & ~solid & ~flat
    lace = (cv2.morphologyEx(lace.astype(np.uint8), cv2.MORPH_CLOSE,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0) & ~open_ & ~solid
    # The anti-aliased rim is a thin band; a ruffle is broad.
    lace = cv2.morphologyEx(lace.astype(np.uint8), cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (broad, broad))) > 0
    low = rgb.min(axis=2).astype(np.int16)
    light = (low >= 205) & (rgb.max(axis=2).astype(np.int16) - low <= 38)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(lace.astype(np.uint8), connectivity=8)
    keep = np.zeros(count, bool)
    height, width = lace.shape
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if area < 12:
            continue
        window = (slice(max(0, y-4), min(height, y+h+4)), slice(max(0, x-4), min(width, x+w+4)))
        region = (labels[window] == index).astype(np.uint8)
        ring = (cv2.dilate(region, np.ones((3, 3), np.uint8), iterations=3) > 0) & (region == 0)
        body = solid[window][ring]
        if body.mean() >= .3:
            keep[index] = light[window][ring][body].mean() >= .35
    lace = keep[labels]
    alpha = np.maximum(base[..., 3]/255, cv2.GaussianBlur(lace.astype(np.float32), (3, 3), .48)*~open_)
    safe = np.maximum(alpha[..., None], .025)
    colour = np.clip((rgb.astype(np.float32) - 255*(1-alpha[..., None]))/safe, 0, 255)
    result = base.copy()
    grown = alpha*255 > base[..., 3]+1
    result[grown, :3] = colour[grown].astype(np.uint8)
    result[grown, 3] = np.rint(alpha[grown]*255).astype(np.uint8)
    return Image.fromarray(result)


def matte_white_sequence(sources, reach=3, share=.5):
    """matte_white_lace for every frame, then keep fabric that most frames
    around show solid where this frame's own pixel is not the backdrop.
    Streams: only the frames within `reach` either side are held."""
    window = deque()      # (rgb, matte) for the frames around the next output
    pending = 0           # index in the window of the next frame to emit

    def emit(index):
        rgb, matte = window[index]
        solid = np.stack([item[1][..., 3] > 128 for item in window])
        fill = (solid.mean(axis=0) >= share) & ~solid[index] & (backdrop_distance(rgb) > 3)
        frame = matte.copy()
        frame[fill, :3] = rgb[fill]
        frame[fill, 3] = 255
        return Image.fromarray(frame)

    for source in sources:
        rgb = np.asarray(source.convert('RGB'))
        window.append((rgb, np.asarray(matte_white_lace(source))))
        if len(window) > pending+reach:
            yield emit(pending)
            if pending < reach:
                pending += 1
            else:
                window.popleft()
    while pending < len(window):
        yield emit(pending)
        pending += 1
