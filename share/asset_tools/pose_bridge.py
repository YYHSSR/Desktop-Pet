"""Offline short pose bridges; body flow and detached light effects stay separate."""
import cv2
import numpy as np
from PIL import Image


def premultiplied(image):
    value = np.asarray(image.convert('RGBA'), dtype=np.float32)/255
    value[..., :3] *= value[..., 3:]
    return value


def straight(value):
    value = np.clip(value, 0, 1)
    alpha = value[..., 3:]
    rgb = np.divide(value[..., :3], alpha, out=np.zeros_like(value[..., :3]), where=alpha > .001)
    return Image.fromarray(np.rint(np.clip(np.dstack((rgb, alpha)), 0, 1)*255).astype(np.uint8))


def separate_effects(image):
    value = premultiplied(image)
    mask = (value[..., 3] > .08).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return value, np.zeros_like(value)
    main = 1+stats[1:, cv2.CC_STAT_AREA].argmax()
    body_mask = labels == main
    distance = cv2.distanceTransform((~body_mask).astype(np.uint8), cv2.DIST_L2, 3)
    for index in range(1, count):
        region = labels == index
        area = stats[index, cv2.CC_STAT_AREA]
        if area > max(1500, stats[main, cv2.CC_STAT_AREA]*.015) or area > 12 and distance[region].min() < 4:
            body_mask |= region
    # Keep the antialiased perimeter attached to its body component.
    body_mask = cv2.dilate(body_mask.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    body = value*body_mask[..., None]
    effects = value*(~body_mask)[..., None]
    return body, effects


def body_flow(source, destination):
    def gray(value):
        backdrop = value[..., :3]+.6*(1-value[..., 3:])
        return cv2.cvtColor(np.rint(np.clip(backdrop, 0, 1)*255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    flow = cv2.calcOpticalFlowFarneback(gray(source), gray(destination), None,
                                      .5, 3, 25, 3, 5, 1.2, 0)
    flow = cv2.GaussianBlur(flow, (9, 9), 1.6)
    length = np.linalg.norm(flow, axis=2)
    flow *= np.minimum(1, 18/np.maximum(length, .001))[..., None]
    return flow


def geometry(value):
    mask = (value[..., 3] > .08).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        raise ValueError('Pose bridge has no character body')
    x, y, width, height, _ = stats[1+stats[1:, cv2.CC_STAT_AREA].argmax()]
    return float(x+width/2), float(y+height), float(height)


def register(value, source_geometry, destination_geometry):
    sx, sy, sh = source_geometry
    dx, dy, dh = destination_geometry
    scale = dh/sh
    matrix = np.array(((scale, 0, dx-sx*scale), (0, scale, dy-sy*scale)), dtype=np.float32)
    return cv2.warpAffine(value, matrix, (value.shape[1], value.shape[0]),
                          flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


def dissolve(t):
    """Colour mix over the middle half only: the bodies move for the whole
    bridge, but the see-through double image lasts just a few frames."""
    t = max(0., min(1., (t-.25)/.5))
    return t*t*(3-2*t)


def pose_bridge(source, destination, count):
    """Endpoints stay exact. Particle positions fade; they are never flow-warped."""
    if source.size != destination.size or count < 2:
        raise ValueError('Pose bridge requires equal canvases and at least two frames')
    a, fx_a = separate_effects(source)
    b, fx_b = separate_effects(destination)
    geometry_a, geometry_b = geometry(a), geometry(b)
    registered_a = register(a, geometry_a, geometry_b)
    forward, backward = body_flow(registered_a, b), body_flow(b, registered_a)
    height, width = a.shape[:2]
    grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    result = [source.copy()]
    for index in range(1, count-1):
        t = index/(count-1)
        eased = t*t*(3-2*t)
        warp_a = cv2.remap(registered_a, grid_x-forward[..., 0]*eased, grid_y-forward[..., 1]*eased,
                           cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        warp_b = cv2.remap(b, grid_x-backward[..., 0]*(1-eased), grid_y-backward[..., 1]*(1-eased),
                           cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        intermediate = tuple(x*(1-eased)+y*eased for x, y in zip(geometry_a, geometry_b))
        mix = dissolve(t)
        body = register(warp_a*(1-mix)+warp_b*mix, geometry_b, intermediate)
        effects = fx_a*(1-eased)+fx_b*eased
        result.append(straight(body+effects*(1-body[..., 3:])))
    result.append(destination.copy())
    return result


def visible_difference(a, b):
    return float(np.mean(np.abs(premultiplied(a)-premultiplied(b))))
