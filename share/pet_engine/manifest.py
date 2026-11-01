"""Canonical character descriptor name with legacy package compatibility."""
from pathlib import Path

MANIFEST_NAME = 'manifest.json'
LEGACY_MANIFEST_NAME = '素材清单.json'


def manifest_path(root):
    root = Path(root)
    canonical = root / MANIFEST_NAME
    if canonical.is_file():
        return canonical
    legacy = root / LEGACY_MANIFEST_NAME
    return legacy if legacy.is_file() else canonical


def playback_path(root, item):
    root = Path(root).resolve()
    path = (root / (item.get('playbackFile') or item['file'])).resolve()
    if not path.is_relative_to(root):
        raise ValueError('素材路径不在角色目录内')
    return path
