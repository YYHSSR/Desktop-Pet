"""Give every action a common reference pose and a complete star-effect exit.

The bridges themselves come from the shared asset tools, so Claude and
Gemini morph to and from idle the same way.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT.parent), str(ROOT/'build/asset-tools')]
from share.asset_tools.animation_pack import prepare_bridges


def prepare(records=None):
    base = ROOT/'build/animation-base'
    if records is None:
        from prepare_assets import CHOICES
        records = [json.loads((base/(choice[0]+'.json')).read_text(encoding='utf-8')) for choice in CHOICES]
    drag=next(item for item in records if item['id']=='drag')
    prepare_bridges(ROOT, [item for item in records if item['id']!='drag'])
    descriptor=ROOT/'assets/character/character.json'
    data=json.loads(descriptor.read_text(encoding='utf-8'));data['actions'].append(drag)
    descriptor.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    from share.pet_engine.action_catalog import update_pack_policy
    from gemini.app.model import ACTION_WEIGHTS, MENU_ORDER
    from gemini.tools.prepare_drag import prepare as prepare_drag
    prepare_drag()
    update_pack_policy(ROOT, ACTION_WEIGHTS, MENU_ORDER)
    return json.loads((ROOT/'assets/character/character.json').read_text(encoding='utf-8'))['actions']


if __name__ == '__main__':
    prepare()
