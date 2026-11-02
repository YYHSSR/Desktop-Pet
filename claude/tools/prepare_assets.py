"""Compile Claude's original WebPs into a transparent, pose-matched character pack."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from PIL import Image
from share.asset_tools.alpha_repair import repair
from share.asset_tools.animation_pack import digest, transform_for, align, prepare_bridges
from share.asset_tools.exact_webp import encode
from share.asset_tools.white_background import matte_white_sequence

# key, source stem, name, group, loops, source frame window (None = whole clip)
CHOICES = [
    ('idle', '抱书静候', '抱书静候', '陪伴', True, None),
    ('wave', '挥手', '向你挥手', '互动', False, None),
    ('peek', '书挡脸', '书后偷看', '互动', False, None),
    ('wind', '被风吹乱', '风中整理', '日常', False, None),
    ('bow', '转圈行礼', '转圈行礼', '互动', False, None),
    ('sparkles', '书页光点', '书页花光', '特别', False, None),
    ('flower', '送出花朵', '书中赠花', '特别', False, None),
    ('idea', '灵光一闪', '灵感来了', '日常', False, None),
    # The drag stands still for its first 24 frames, is lifted and swung
    # (calming from ~132, a blink at 142-145), set down by ~175 and stands from ~190.
    ('drag', '拖拽', '被拖着走', '互动', False, (24, 191)),
    ('walk-left', '向左', '向左走走', '移动', False, None),
    ('walk-right', '向右', '向右跳步', '移动', False, None),
]
# Source frames in which she travels; the window moves with her then.
WALKS = {'walk-right': (1, 18, 186), 'walk-left': (-1, 26, 218)}
# key, release frame, sway: a pickup plays the whole lift and swing up to the
# release frame (source 140, swing calmed, eyes open), however short the
# drag; held longer, she sways through the frames just before it instead of
# swinging again. Letting go plays the clip's own descent from there.
HOLD = ('drag', 116, 8)
RECIPE = 'claude-lace-matte-temporal-repair-exact'


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
    for key, stem, name, group, loop, window in CHOICES:
        item = lookup[stem]
        target, receipt = base/(key+'.webp'), base/(key+'.json')
        if target.exists() and receipt.exists():
            record = json.loads(receipt.read_text(encoding='utf-8'))
            if (record.get('recipe') == RECIPE and record['sourceSha256'] == item['sha256']
                    and record.get('sourceWindow') == (list(window) if window else None)
                    and record['sha256'] == digest(target)):
                records.append(record)
                print('CACHED '+key, flush=True)
                continue
        print('PREPARE '+key, flush=True)
        frames, durations = [], []
        with Image.open(assets/item['file']) as source:
            first, end = window or (0, source.n_frames)

            class Window:
                """The transform is measured on the frames actually used."""
                n_frames = end-first
                def seek(self, index): source.seek(first+index)
                def __getattr__(self, name): return getattr(source, name)
            transform = transform_for(Window(), effects_crop=True, travel=key in WALKS)
            def window_frames():
                for index in range(first, end):
                    source.seek(index)
                    source.load()
                    durations.append(max(15, int(source.info.get('duration', 42))))
                    yield source.convert('RGB')
            # The pale petticoat hem sits within a few levels of the white
            # backdrop; this matte keeps it solid and steady across frames.
            for frame in matte_white_sequence(window_frames()):
                frames.append(align(frame, transform))
        frames, report = repair(frames)
        written = encode(target, frames, durations)
        record = dict(id=key, name=name, group=group, file='playback/'+key+'.webp', loop=loop,
                      durationMs=written['durationMs'], frames=written['frames'], bytes=written['bytes'],
                      sha256=written['sha256'], recipe=RECIPE, source=item['file'], sourceSha256=item['sha256'],
                      transform=transform, sourceWindow=list(window) if window else None, repair=report)
        receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        records.append(record)
        sheet = Image.new('RGB', (1024, 256), '#e4ded8')
        for col, index in enumerate((0, len(frames)//3, len(frames)*2//3, len(frames)-1)):
            frame = frames[index].resize((256, 256), Image.Resampling.LANCZOS)
            sheet.paste(frame, (col*256, 0), frame)
        sheet.save(previews/(key+'.jpg'), quality=95)
        print(f'OK {key}: {len(frames)} frames, repaired {len(report["refilledFrames"])} frames', flush=True)
    data = dict(character='claude', name='Claude 娘', idle='idle', drag='drag', actions=records,
                selectionNotes=dict(excluded=[dict(source='特殊/萤火虫.webp',
                    reason='新版仍是深色夜景，白底抠图会留下整块暗底，只保留分类原片。')],
                    removed=originals.get('removed', []),
                    trimmed=[dict(id='drag', startFrame=24, endFrame=191,
                        reason='前 24 帧只是站着，第 190 帧后已站定不动；拎起从被抬起的那一刻开始，放下用原片自己的落地。')]))
    (assets/'character.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    prepare_bridges(ROOT, records, lossless=True, walks=WALKS, hold=HOLD)
    from share.pet_engine.action_catalog import update_pack_policy
    from claude.app.model import ACTION_WEIGHTS, MENU_ORDER
    return update_pack_policy(ROOT, ACTION_WEIGHTS, MENU_ORDER)


if __name__ == '__main__':
    prepare()
