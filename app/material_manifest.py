"""Remove historical project annotations from imported character descriptors."""
import json


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
