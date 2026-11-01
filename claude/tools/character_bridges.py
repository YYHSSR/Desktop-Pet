"""Claude-only common-pose preparation and a safe loop for held dragging."""
import hashlib
import io
import json
from pathlib import Path
import struct
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from share.asset_tools.animation_pack import digest, best_cut, timing, preview
from share.asset_tools.pose_bridge import pose_bridge, visible_difference

RECIPE = 'claude-fixed-reference-exact-short-drag-body-loop-v1'


def encode(path, frames, durations):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.preparing.webp')
    def chunk(tag, value):
        return tag+struct.pack('<I',len(value))+value+(b'\0' if len(value)%2 else b'')
    u24 = lambda value: int(value).to_bytes(3,'little')
    with temp.open('wb') as stream:
        stream.write(b'RIFF\0\0\0\0WEBP')
        stream.write(chunk(b'VP8X',b'\x12\0\0\0'+u24(511)+u24(511)))
        stream.write(chunk(b'ANIM',struct.pack('<IH',0,0)))
        for frame, delay in zip(frames,durations):
            buffer=io.BytesIO();frame.save(buffer,format='WEBP',lossless=True,exact=True,method=1,quality=80)
            data, at, payload = buffer.getvalue(),12,b''
            while at < len(data):
                length=int.from_bytes(data[at+4:at+8],'little'); end=at+8+length+(length%2)
                if data[at:at+4] == b'VP8L': payload+=data[at:end]
                at=end
            if not payload: raise ValueError('Expected lossless frame')
            stream.write(chunk(b'ANMF',u24(0)+u24(0)+u24(511)+u24(511)+u24(delay)+b'\x02'+payload))
        length=stream.tell()-8;stream.seek(4);stream.write(struct.pack('<I',length))
    with Image.open(temp) as check:
        if check.n_frames != len(frames): raise ValueError('Frame count changed')
        for i,(frame,delay) in enumerate(zip(frames,durations)):
            check.seek(i);check.load()
            if check.convert('RGBA').tobytes()!=frame.tobytes() or check.info['duration']!=delay:
                raise ValueError('Frame verification failed: '+path.name)
    temp.replace(path)


def prepare_bridges(root, records):
    root=Path(root);assets=root/'assets/character';base=root/'build/animation-base'
    output=root/'build/character-preparation';output.mkdir(parents=True,exist_ok=True)
    with Image.open(base/'idle.webp') as source: anchor=source.convert('RGBA')
    reference=hashlib.sha256(anchor.tobytes()).hexdigest()
    def one(item):
        key=item['id'];target=assets/'playback'/(key+'.webp');receipt=output/(key+'.json')
        source_path=base/(key+'.webp');source_hash=digest(source_path)
        if target.is_file() and receipt.is_file():
            previous=json.loads(receipt.read_text(encoding='utf-8'))
            if (previous.get('transitionRecipe')==RECIPE and previous.get('baseSha256')==source_hash
                    and previous.get('referencePose')==reference and previous['sha256']==digest(target)):
                held=previous.get('dragLoopFile')
                if not held or (assets/held).is_file() and digest(assets/held)==previous['dragLoopSha256']:
                    print('CACHED transition '+key,flush=True);return previous
        print('BRIDGE '+key,flush=True)
        frames,delays=[],[]
        with Image.open(source_path) as source:
            for i in range(source.n_frames):
                source.seek(i);source.load();frames.append(source.convert('RGBA'));delays.append(int(source.info.get('duration',42)))
        entry=0 if key=='idle' else 4 if key=='drag' else 12
        exit_count=16 if key in ('flower','sparkles') else 12
        if key=='idle':
            result=frames+pose_bridge(frames[-1],anchor,12)[1:];durations=delays+timing(11);cut=[0,len(frames)-1]
        else:
            start,end=(0,len(frames)-1) if key=='drag' else best_cut(frames,anchor)
            frames,delays=frames[start:end+1],delays[start:end+1];cut=[start,end]
            entrance=pose_bridge(anchor,frames[0],entry);tail=pose_bridge(frames[-1],anchor,exit_count)
            result=entrance[:-1]+frames+tail[1:];durations=timing(entry-1)+delays+timing(exit_count-1)
        encode(target,result,durations)
        record=dict(item,sha256=digest(target),bytes=target.stat().st_size,frames=len(result),durationMs=sum(durations),
                    transitionRecipe=RECIPE,baseSha256=source_hash,referencePose=reference,entryBridgeFrames=entry,
                    exitBridgeFrames=11 if key=='idle' else exit_count-1,endpointDifference=visible_difference(result[0],result[-1]),bridgeCut=cut)
        if key=='drag':
            start=entry-1;end=start+len(frames)-1
            held=pose_bridge(result[end],result[start],9)[1:]+result[start+1:end+1]
            held_name='playback/drag-held.webp';encode(assets/held_name,held,timing(len(held)))
            record.update(dragStartFrame=start,dragLoopEnd=end,dragLoopFile=held_name,dragLoopFrames=len(held),
                          dragLoopSha256=digest(assets/held_name),dragLoopBytes=(assets/held_name).stat().st_size)
        preview(result,output/(key+'-preview.jpg'))
        receipt.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (assets/'playback'/(key+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(f'OK {key}: {len(result)} frames, endpoint gap {record["endpointDifference"]:.6f}',flush=True)
        return record
    with ThreadPoolExecutor(max_workers=2) as pool: result=list(pool.map(one,records))
    descriptor=json.loads((assets/'character.json').read_text(encoding='utf-8'))
    descriptor.update(actions=result,referencePose=reference)
    (assets/'character.json').write_text(json.dumps(descriptor,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'verification.json').write_text(json.dumps(dict(passed=True,actions=len(result),allFramesVerified=True,
        maximumEndpointDifference=max(r['endpointDifference'] for r in result)),indent=2)+'\n',encoding='utf-8')
    return result
