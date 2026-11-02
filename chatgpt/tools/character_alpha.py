"""Restore intermittent cut-out holes using motion-aligned intact artwork.

This is an offline ChatGPT asset repair. The runtime and the other characters
do not import OpenCV or use this character-specific reconstruction.
"""
import cv2
import numpy as np
from PIL import Image

from share.asset_tools.white_background import hull
from share.asset_tools.alpha_repair import steady_blinks, steady_gaps


def seal_fabric(frames):
    """Keep the opaque side ruffles solid, with the outer contour and legs open.

    The supplied matting sometimes loses the same pale fold for a whole clip,
    so adjacent frames alone cannot reconstruct it. Seal only the lower side
    garment inside its existing contour; never bridge the gap between the legs.
    """
    result, total = [], 0
    for frame in frames:
        value = np.asarray(frame.convert('RGBA')).copy()
        alpha = value[..., 3]
        mask = (alpha > 96).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if count < 2:
            result.append(frame)
            continue
        main = 1+stats[1:, cv2.CC_STAT_AREA].argmax()
        x, y, width, height, _ = stats[main]
        yy, xx = np.mgrid[:alpha.shape[0], :alpha.shape[1]]
        garment = ((yy > y+height*.54) & (yy < y+height*.96)
                   & (np.abs(xx-(x+width/2)) > width*.12))
        inside = hull(labels == main, 19)
        # Leave antialiased outer pixels alone; restore actual interior holes.
        interior = cv2.erode(inside.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        missing = (alpha < 224) & interior & garment
        if missing.any():
            painted = cv2.inpaint(value[..., :3].copy(), missing.astype(np.uint8),
                                  3, cv2.INPAINT_TELEA)
            value[missing, :3] = painted[missing]
            value[missing, 3] = 255
            total += int(missing.sum())
        result.append(Image.fromarray(value))
    return result, total


def motion_guide(value):
    """Hide alpha damage from optical flow without changing output artwork."""
    alpha = value[..., 3]
    inside = hull(alpha > 96, 31)
    missing = inside & (alpha < 224)
    colour = cv2.inpaint(value[..., :3].copy(), missing.astype(np.uint8), 3,
                         cv2.INPAINT_TELEA)
    colour[~inside] = 160
    return cv2.resize(cv2.cvtColor(colour, cv2.COLOR_RGB2GRAY), None,
                      fx=.5, fy=.5, interpolation=cv2.INTER_AREA)


def stabilize(frames, trusted=None, offsets=(-16, -8, -3, -1, 1, 3, 8, 16)):
    """Fill only body pixels supported by several nearby motion-aligned frames.

    Existing opaque artwork is exact. Persistent negative spaces remain open;
    silhouette motion is registered before deciding whether fabric is missing.
    """
    if len(frames) < 3:
        return list(frames), dict(restoredPixels=0, restoredFrames=0)
    values = [np.asarray(frame.convert('RGBA')) for frame in frames]
    trusted = [value[..., 3] for value in values] if trusted is None else trusted
    guides = [motion_guide(value) for value in values]
    height, width = values[0].shape[:2]
    grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32),
                                np.arange(height, dtype=np.float32))
    flow_reader = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    result, restored, changed = [], 0, 0
    for index, current in enumerate(values):
        votes = np.zeros((height, width), np.float32)
        colour = np.zeros((height, width, 3), np.float32)
        weight = np.zeros((height, width), np.float32)
        intact_votes = np.zeros((height, width), np.float32)
        intact_colour = np.zeros((height, width, 3), np.float32)
        intact_weight = np.zeros((height, width), np.float32)
        for offset in offsets:
            other = index+offset
            if not 0 <= other < len(values):
                continue
            flow = flow_reader.calc(guides[index], guides[other], None)
            flow = cv2.resize(flow, (width, height), interpolation=cv2.INTER_LINEAR)*2
            donor = cv2.remap(values[other], grid_x+flow[..., 0], grid_y+flow[..., 1],
                              cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            valid = donor[..., 3] > 240
            votes += valid
            contribution = valid.astype(np.float32)/(1+abs(offset))
            colour += donor[..., :3]*contribution[..., None]
            weight += contribution
            intact = valid & (cv2.remap(trusted[other], grid_x+flow[..., 0],
                                        grid_y+flow[..., 1], cv2.INTER_LINEAR,
                                        borderMode=cv2.BORDER_CONSTANT) > 240)
            intact_votes += intact
            contribution = intact.astype(np.float32)/(1+abs(offset))
            intact_colour += donor[..., :3]*contribution[..., None]
            intact_weight += contribution
        inside = hull(current[..., 3] > 96, 31)
        restore = ((current[..., 3] < 224) & inside
                   & (votes >= 2))
        output = current.copy()
        output[restore, :3] = np.rint(colour[restore]/weight[restore, None]).astype(np.uint8)
        output[restore, 3] = 255
        # Prefer actual opaque source fabric over per-frame hidden-colour recovery.
        # This prevents a restored ruffle from changing tint on every frame.
        recolour = (trusted[index] < 224) & inside & (intact_votes >= 2)
        output[recolour, :3] = np.rint(
            intact_colour[recolour]/intact_weight[recolour, None]).astype(np.uint8)
        pixels = int(restore.sum())
        restored += pixels
        changed += bool(pixels)
        result.append(Image.fromarray(output))
    # Reconcile new boundaries before sealing persistently damaged pale folds.
    result, _ = steady_blinks(result)
    result = steady_gaps(result, reach=4, largest=2000, share=.25)
    result, sealed = seal_fabric(result)
    return result, dict(restoredPixels=restored, restoredFrames=changed,
                        sealedFabricPixels=sealed)
