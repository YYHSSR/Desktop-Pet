"""Compile Claude's original WebPs into a transparent, pose-matched character pack."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
if (ROOT/'build/asset-tools').is_dir():
    sys.path.insert(0, str(ROOT/'build/asset-tools'))
from PIL import Image
from share.asset_tools.animation_pack import digest, transform_for, align, loop_cut
from share.asset_tools.white_background import matte_white
from claude.tools.character_bridges import prepare_bridges

# Last field limits source frames before the flower clip's camera zoom crops feet
# (the v2 clip starts a slow push-in after frame 101).
CHOICES = [
    ('idle', '抱书静候', '抱书静候', '陪伴', True, False, None),
    ('wave', '挥手', '向你挥手', '互动', False, True, None),
    ('peek', '书挡脸', '书后偷看', '互动', False, True, None),
    ('wind', '被风吹乱', '风中整理', '日常', False, False, None),
    ('bow', '转圈行礼', '转圈行礼', '互动', False, False, None),
    ('sparkles', '书页光点', '书页花光', '特别', False, False, None),
    ('flower', '送出花朵', '书中赠花', '特别', False, False, None),
    ('idea', '灵光一闪', '灵感来了', '日常', False, True, None),
    ('drag', '拖拽', '被拖着走', '互动', False, False, 65),
]
RECIPE = 'claude-paper-white-bodyfit-flower-trim-rgb94'


def prepare():
    assets = ROOT/'assets/character'
    originals = json.loads((assets/'manifest.json').read_text(encoding='utf-8-sig'))
    lookup = {Path(item['file']).stem: item for item in originals['files']}
    for item in originals['files']:
        path = assets/item['file']
        if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError('Original asset changed: '+item['file'])
    base, previews = ROOT/'build/animation-base', ROOT/'build/asset-previews'
    base.mkdir(parents=True, exist_ok=True)
    previews.mkdir(parents=True, exist_ok=True)
    (assets/'playback').mkdir(exist_ok=True)
    records = []
    for key, stem, name, group, loop, random_action, limit in CHOICES:
        item = lookup[stem]
        target, receipt = base/(key+'.webp'), base/(key+'.json')
        hold = 0
        start_frame = 40 if key == 'drag' else 0
        recipe = RECIPE + ('-safe-drag-40-65' if key == 'drag' else '')
        if target.exists() and receipt.exists():
            record = json.loads(receipt.read_text(encoding='utf-8'))
            if (record.get('recipe') == recipe and record['sourceSha256'] == item['sha256']
                    and record.get('sourceEndFrame') == limit
                    and record.get('holdTailMs', 0) == hold
                    and record['sha256'] == digest(target)):
                records.append(record)
                print('CACHED '+key, flush=True)
                continue
        print('PREPARE '+key, flush=True)
        frames, durations = [], []
        with Image.open(assets/item['file']) as source:
            # Restrict the transform scan as well as the output to the safe clip.
            count = min(source.n_frames, limit or source.n_frames)
            if limit:
                class Window:
                    n_frames = count-start_frame
                    def seek(self, index): source.seek(start_frame+index)
                    def __getattr__(self, name): return getattr(source,name)
                transform = transform_for(Window(), effects_crop=True)
            else:
                transform = transform_for(source, effects_crop=True)
            for index in range(start_frame,count):
                source.seek(index); source.load()
                frames.append(align(matte_white(source), transform))
                durations.append(max(15, int(source.info.get('duration', 42))))
        cut = None
        # Idle keeps its standing first frame as the shared pose. The bridge
        # closes the loop; cutting a similar sub-range would drop that pose.
        if loop and key != 'idle':
            frames, durations, cut = loop_cut(frames, durations)
        durations[-1] += hold
        frames[0].save(target, save_all=True, append_images=frames[1:], duration=durations,
                       loop=0, quality=94, alpha_quality=100, method=4)
        with Image.open(target) as encoded:
            count = encoded.n_frames
        record = dict(id=key, name=name, group=group, file='playback/'+key+'.webp',
                      loop=loop, random=random_action, durationMs=sum(durations), frames=count,
                      bytes=target.stat().st_size, sha256=digest(target), recipe=recipe,
                      source=item['file'], sourceSha256=item['sha256'], transform=transform,
                      sourceStartFrame=start_frame, sourceEndFrame=limit, holdTailMs=hold, loopPreparation=cut)
        receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        records.append(record)
        sheet = Image.new('RGB', (1024, 256), '#e4ded8')
        for col, index in enumerate((0, len(frames)//3, len(frames)*2//3, len(frames)-1)):
            frame = frames[index].resize((256, 256), Image.Resampling.LANCZOS)
            sheet.paste(frame, (col*256, 0), frame)
        sheet.save(previews/(key+'.jpg'), quality=95)
        print(f'OK {key}: {count} frames', flush=True)
    data = dict(character='claude', name='Claude 娘', idle='idle', drag='drag', actions=records,
                selectionNotes=dict(excluded=[dict(source='特殊/萤火虫.webp',
                    reason='新版仍是深色夜景，白底抠图会留下整块暗底，只保留分类原片。')],
                    removed=originals.get('removed', []),
                    trimmed=[dict(id='drag',startFrame=40,endFrame=65,
                        reason='后半段脚部和头发出画，只使用完整人物的侧移段，原片不改写。')]))
    (assets/'character.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    prepare_bridges(ROOT, records)
    from share.pet_engine.action_catalog import update_pack_policy
    from claude.app.model import ACTION_WEIGHTS, MENU_ORDER
    return update_pack_policy(ROOT, ACTION_WEIGHTS, MENU_ORDER)


if __name__ == '__main__':
    prepare()
