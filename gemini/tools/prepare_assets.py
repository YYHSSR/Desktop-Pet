"""Prepare transparent, aligned Gemini animations without changing original WebPs."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from PIL import Image
from share.asset_tools.alpha_repair import repair
from share.asset_tools.animation_pack import align, digest, loop_cut, transform_for
from share.asset_tools.white_background import matte_white

CHOICES = [
    ('idle', '平常', '星光待机', '待机', True, False),
    ('stretch', '伸懒腰', '伸个懒腰', '日常', False, True),
    ('greeting', '打招呼', '向你招手', '互动', False, False),
    ('curious', '好奇', '好奇探头', '互动', False, True),
    ('pout', '生气又软下来', '哄哄猫猫', '互动', False, False),
    ('glance', '惊鸿一瞥', '回眸一笑', '日常', False, True),
    ('meow', '喵喵喵', '喵喵回应', '互动', False, True),
    ('hop', '跳一跳', '轻轻一跳', '日常', False, True),
    ('chase', '追尾巴', '追逐尾巴', '活泼', False, False),
    ('pounce', '扑过来', '扑向你', '活泼', False, False),
    ('catch', '接住星星', '接住星光', '星光', False, False),
    ('lift', '被拎起来', '被拎起来', '互动', False, False),
    ('drag', '拖拽', '被拖着走', '互动', False, False),
    ('walk-left', '向左', '向左追尾', '移动', False, False),
    ('walk-right', '向右', '向右扑去', '移动', False, False),
]
# Source frames in which she travels; the window moves with her then.
WALKS = {'walk-right': (1, 28, 136), 'walk-left': (-1, 22, 128)}
RECIPE = 'backdrop-colour-matte-temporal-repair-rgb94-alpha100'


def prepare(only=None):
    character = ROOT / 'assets/character'
    source_manifest = json.loads((character / 'manifest.json').read_text(encoding='utf-8-sig'))
    by_name = {Path(item['file']).stem: item for item in source_manifest['files']}
    playback = character / 'playback'
    playback.mkdir(exist_ok=True)
    base = ROOT / 'build/animation-base'
    base.mkdir(parents=True, exist_ok=True)
    preview = ROOT / 'build/asset-previews'
    preview.mkdir(parents=True, exist_ok=True)
    records = []
    for key, source_name, label, group, looping, random_action in CHOICES:
        item = by_name[source_name]
        path = character / item['file']
        if digest(path) != item['sha256']:
            raise ValueError(f'Source checksum mismatch: {path}')
        target = base / (key + '.webp')
        receipt = base / (key + '.json')
        recipe = RECIPE+('-body-fit' if key in ('catch', 'drag', 'lift', *WALKS) else '')
        if receipt.exists() and target.exists():
            record = json.loads(receipt.read_text(encoding='utf-8'))
            if record.get('recipe') == recipe and record['sourceSha256'] == item['sha256'] and record['sha256'] == digest(target):
                records.append(record)
                print('CACHED ' + key, flush=True)
                continue
        if only and key not in only:
            continue
        print('PREPARE ' + key, flush=True)
        frames, durations = [], []
        with Image.open(path) as source:
            transform = transform_for(source, effects_crop=key in ('catch', 'drag', 'lift', *WALKS), travel=key in WALKS)
            for index in range(source.n_frames):
                source.seek(index)
                source.load()
                durations.append(max(15, int(source.info.get('duration', 42))))
                frames.append(align(matte_white(source), transform))
        frames, report = repair(frames)
        loop = None
        if looping:
            frames, durations, loop = loop_cut(frames, durations)
        frames[0].save(target, save_all=True, append_images=frames[1:], duration=durations,
                       loop=0, lossless=False, quality=94, alpha_quality=100, method=4)
        record = dict(id=key, name=label, group=group, file='playback/' + target.name,
                      durationMs=sum(durations), frames=len(frames), loop=looping,
                      random=random_action, recipe=recipe, bytes=target.stat().st_size, sha256=digest(target),
                      source=item['file'], sourceSha256=item['sha256'], transform=transform, repair=report)
        if loop:
            record['loopPreparation'] = loop
        receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        records.append(record)
        sheet = Image.new('RGB', (1024, 1024), '#151b31')
        for tile, index in enumerate((0, len(frames)//3, len(frames)*2//3, len(frames)-1)):
            sheet.paste(frames[index], ((tile % 2)*512, (tile//2)*512), frames[index])
        sheet.save(preview / (key + '.jpg'), quality=95)
        frames[0].save(preview / (key + '.png'))
        print(f'OK {key}: {record["frames"]} frames, {record["bytes"] // 1024} KiB', flush=True)
    if not only:
        result = dict(character='gemini', name='Gemini 娘', idle='idle', drag='drag', actions=records,
                      selectionNotes=dict(excluded=[dict(source='特殊/星星魔法.webp',
                          reason='原片镜头放大并裁切人物；默认庆祝使用全身完整的接住星星。'),
                          dict(source='待机/日常.webp', reason='与主待机内容接近，色调偏淡；不加入默认播放包。')]))
        (character / 'character.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        from prepare_transitions import prepare as prepare_bridges
        records = prepare_bridges(records)
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', nargs='+')
    prepare(parser.parse_args().only)
