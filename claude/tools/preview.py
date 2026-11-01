"""Render a lightweight animation preview of Claude's prepared actions."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def preview(output):
    assets = ROOT/'assets/character'
    data = json.loads((assets/'character.json').read_text(encoding='utf-8'))
    actions = {item['id']: item for item in data['actions']}
    frames = []
    # A short sample of actual source movement and the complete prepared tail.
    for key in ('idle', 'wave', 'peek', 'flower', 'sparkles'):
        with Image.open(assets/actions[key]['file']) as source:
            indexes = list(range(0, source.n_frames, 3))
            if source.n_frames-1 not in indexes:
                indexes.append(source.n_frames-1)
            for index in indexes:
                source.seek(index); source.load()
                frame = Image.new('RGB', (320, 344), '#eee6dc')
                pet = source.convert('RGBA').resize((320, 320), Image.Resampling.LANCZOS)
                frame.paste(pet, (0, 20), pet)
                ImageDraw.Draw(frame).text((12, 8), 'CLAUDE / '+key.upper(), fill='#996747')
                frames.append(frame)
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=125, loop=0, optimize=False)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'build/claude-preview.gif')
    print(preview(parser.parse_args().output))
