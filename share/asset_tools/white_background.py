"""Remove border-connected light neutral video backgrounds, retaining white interiors.

This is deterministic matting for the supplied flat-background animation clips.
It is not a general image segmentation model or a reconstruction of clipped art.
"""
import cv2
import numpy as np
from PIL import Image


def matte_white(image):
    rgb = np.asarray(image.convert('RGB')).copy()
    low = rgb.min(axis=2).astype(np.int16)
    chroma = rgb.max(axis=2).astype(np.int16) - low
    candidate = ((low >= 205) & (chroma <= 38)).astype(np.uint8) * 255
    padded = np.pad(candidate, 1, constant_values=255)
    cv2.floodFill(padded, None, (0, 0), 128, flags=4)
    foreground = (padded[1:-1, 1:-1] != 128).astype(np.uint8)
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


def bounds(image, largest=False):
    mask = (np.asarray(image.getchannel('A')) > 40).astype(np.uint8)
    if not largest:
        return image.getchannel('A').getbbox()
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return None
    x, y, width, height, _ = stats[1 + stats[1:, cv2.CC_STAT_AREA].argmax()]
    return int(x), int(y), int(x + width), int(y + height)
