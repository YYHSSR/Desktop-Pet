"""Contour-aware white-backdrop removal for the new opaque MP4 artwork.

Keep the decoded source RGB inside the character. No texture synthesis,
inpainting, hidden-colour recovery, or cross-frame RGB borrowing is used.
"""
import cv2
import numpy as np
from PIL import Image


def outside_background(passable):
    padded = np.pad(passable.astype(np.uint8)*255, 1, constant_values=255)
    cv2.floodFill(padded, None, (0, 0), 128, flags=4)
    return padded[1:-1, 1:-1] == 128


def outlined_foreground(rgb):
    """Protect pale interiors enclosed by the character's darker drawn lines."""
    outline = cv2.morphologyEx((rgb.min(axis=2) < 225).astype(np.uint8), cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    return ~outside_background(outline == 0)


def matte_frame(image, *, soft_effects=False):
    rgb = np.asarray(image.convert('RGB'))
    low, chroma = rgb.min(axis=2), np.ptp(rgb, axis=2)
    neutral = (low >= 245) & (chroma <= 9)
    # Seal only single-pixel breaks in drawn outlines, before the border flood.
    # Pale areas enclosed by those outlines remain opaque original artwork.
    barrier = cv2.morphologyEx((~neutral).astype(np.uint8), cv2.MORPH_CLOSE,
                               cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    solid = ~outside_background(barrier == 0)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(solid.astype(np.uint8), connectivity=8)
    if count < 2:
        raise ValueError('No character foreground found in MP4 frame')
    main = 1+stats[1:, cv2.CC_STAT_AREA].argmax()
    body_x, body_y, body_w, body_h, _ = stats[main]
    keep = np.zeros(count, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= 6
    solid = keep[labels]
    # Enclosed negative spaces between outer curls have tinted dark borders.
    # Bright cloth highlights and the central face/body must remain opaque.
    count, labels, stats, centres = cv2.connectedComponentsWithStats(
        (neutral & solid).astype(np.uint8), connectivity=4)
    for index in range(1, count):
        x, y, width, height, area = stats[index]
        if area < 10:
            continue
        cx, cy = centres[index]
        if abs(cx-(body_x+body_w/2)) < body_w*.20 and cy > body_y+body_h*.15:
            continue
        window = (slice(max(0, y-3), min(rgb.shape[0], y+height+3)),
                  slice(max(0, x-3), min(rgb.shape[1], x+width+3)))
        region = labels[window] == index
        ring = (cv2.dilate(region.astype(np.uint8), np.ones((3, 3), np.uint8),
                            iterations=2) > 0) & ~region
        colour = rgb[window][ring].astype(np.float32)
        if len(colour) and np.median(colour.min(axis=1)) < 225 and np.median(np.ptp(colour, axis=1)) > 14:
            solid[window][region] = False
    alpha = cv2.GaussianBlur(solid.astype(np.float32), (3, 3), .45)
    alpha[(~solid) & neutral] = 0
    if soft_effects:
        # Dark drawn outlines enclose the pale cloth. Only exterior low-contrast
        # pixels need a gradual white key for the breath's diffuse purple glow.
        exterior = ~outlined_foreground(rgb)
        alpha[exterior] = np.minimum(alpha[exterior], (255-low[exterior].astype(np.float32))/60)
    alpha[alpha < .03] = 0
    # Remove the white backing only at soft boundary pixels. Opaque RGB is exact.
    colour = np.clip((rgb.astype(np.float32)-255*(1-alpha[..., None]))
                     / np.maximum(alpha[..., None], .03), 0, 255)
    value = np.dstack((np.rint(colour).astype(np.uint8), np.rint(alpha*255).astype(np.uint8)))
    value[alpha == 0, :3] = 0
    return Image.fromarray(value)
