"""Remove historical project annotations from imported character descriptors."""
import json
import sys
from pathlib import Path

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from share.pet_engine.manifest import MANIFEST_NAME, manifest_path, playback_path


def derived_items(manifest):
    """Physical playback helpers which must never become menu actions."""
    drag = manifest.get('dragAnimation') or {}
    name = drag.get('dragLoopFile')
    if not name:
        return []
    count = drag.get('dragLoopFrames')
    if type(count) is not int or not 1 <= count <= 2000:
        raise ValueError('拖拽循环帧数无效')
    return [dict(id='drag-held', file=name, playbackFile=name,
                 durationMs=round(count*1000/24), name='拖拽循环衔接')]


def clean_manifest(raw):
    data = json.loads(raw)
    obsolete = {'upstreamAnimationVersion', 'qualityBaseline'}
    if not isinstance(data, dict):
        raise ValueError('角色素材清单必须是对象')
    if not obsolete.intersection(data):
        return raw
    for name in obsolete:
        data.pop(name, None)
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
