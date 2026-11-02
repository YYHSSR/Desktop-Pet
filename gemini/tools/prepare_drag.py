"""Prepare a short-entry native drag clip plus a relaxed sustained loop."""
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
from share.asset_tools.animation_pack import bridge_lengths,digest,timing,preview
from share.asset_tools.pose_bridge import pose_bridge,visible_difference
from share.asset_tools.exact_webp import encode

RECIPE='gemini-short-entry-independent-drag-relaxed-held-exact-v3'


def prepare():
    assets=ROOT/'assets/character';descriptor=assets/'character.json'
    data=json.loads(descriptor.read_text(encoding='utf-8'))
    item=next(action for action in data['actions'] if action['id']==data['drag'])
    base=json.loads((ROOT/'build/animation-base/drag.json').read_text(encoding='utf-8'))
    base_path=ROOT/'build/animation-base/drag.webp'
    if digest(base_path)!=base['sha256'] or digest(assets/base['source'])!=base['sourceSha256']:
        raise ValueError('Drag source or matte cache checksum mismatch')
    # The idle playback's first frame is the pose every clip starts and ends on.
    with Image.open(assets/'playback/idle.webp') as image:anchor=image.convert('RGBA')
    reference=hashlib.sha256(anchor.tobytes()).hexdigest()
    target=assets/'playback/drag.webp';held_name='playback/drag-held.webp';held_path=assets/held_name
    output=ROOT/'build/drag-preparation';output.mkdir(parents=True,exist_ok=True)
    receipt=output/'held-loop.json';record=None
    if receipt.is_file() and held_path.is_file() and target.is_file():
        previous=json.loads(receipt.read_text(encoding='utf-8'))
        if (previous.get('recipe')==RECIPE and previous.get('baseSha256')==base['sha256']
                and previous.get('referencePose')==reference and previous['record']['sha256']==digest(target)
                and previous['record']['dragLoopSha256']==digest(held_path)):
            record=previous['record']
    if record is None:
        frames=[];durations=[]
        with Image.open(base_path) as image:
            for index in range(image.n_frames):
                image.seek(index);image.load();frames.append(image.convert('RGBA'));durations.append(int(image.info['duration']))
        physical=round((len(frames)-1)*.25)
        loop_start=round((len(frames)-1)*.75);loop_end=round((len(frames)-1)*.96)
        entrance=pose_bridge(anchor,frames[physical],4)
        exit_count=bridge_lengths('drag',frames[physical],frames[-1],anchor)[1]
        tail=pose_bridge(frames[-1],anchor,exit_count)
        main=entrance[:-1]+frames[physical:]+tail[1:]
        main_timing=timing(3)+durations[physical:]+timing(exit_count-1)
        encoded=encode(target,main,main_timing)
        held=pose_bridge(frames[loop_end],frames[loop_start],9)[1:]+frames[loop_start+1:loop_end+1]
        verified=encode(held_path,held,timing(len(held)))
        record=dict(base,**encoded,transitionRecipe=RECIPE,baseSha256=base['sha256'],referencePose=reference,
                    entryBridgeFrames=4,exitBridgeFrames=exit_count-1,endpointDifference=visible_difference(main[0],main[-1]),
                    bridgeCut=[physical,len(frames)-1],sourceStartFrame=physical,sourceEndFrame=len(frames),
                    dragStartFrame=3,dragLoopEnd=3+loop_end-physical,dragLoopFile=held_name,
                    dragLoopFrames=verified['frames'],dragLoopBytes=verified['bytes'],dragLoopSha256=verified['sha256'],
                    dragSourceStartFrame=physical,dragLoopSourceRange=[loop_start,loop_end],dragLoopRecipe=RECIPE)
        preview([main[3],main[record['dragLoopEnd']],held[0],held[-1]],output/'held-loop-preview.jpg')
        receipt.write_text(json.dumps(dict(recipe=RECIPE,baseSha256=base['sha256'],referencePose=reference,record=record,
            allFramesVerified=True,lastFrameMatchesDragEnd=held[-1].tobytes()==main[record['dragLoopEnd']].tobytes(),
            entryStepDifference=visible_difference(main[record['dragLoopEnd']],held[0])),ensure_ascii=False,indent=2),encoding='utf-8')
    item.update(record)
    descriptor.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (assets/'playback/drag.json').write_text(json.dumps(item,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Prepared native drag:',record['frames'],'frames; held loop:',record['dragLoopFrames'],'frames',flush=True)
    return item


if __name__=='__main__':prepare()
