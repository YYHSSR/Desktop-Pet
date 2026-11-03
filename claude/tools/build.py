"""Build Claude's own executable, bundling only prepared playback resources.

The default is a folder build (dist/ClaudePet/ClaudePet.exe): it starts in a
fraction of a second because nothing is unpacked at launch. --onefile still
produces a single ClaudePet.exe, but that one must unpack ~250 MB to a temp
folder on every start.
"""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NAME = 'ClaudePet'
sys.path.insert(0, str(ROOT.parent))


def build(onefile=False, output=None):
    from PIL import Image
    from share.pet_engine.character_pack import CharacterPack
    from share.pet_engine.packaging import COMPANION_EXCLUDES, native_build_environment, prune_qt
    pack = CharacterPack(ROOT/'assets/character')
    dist = Path(output or ROOT/'dist').resolve()
    dist.mkdir(parents=True, exist_ok=True)
    work = ROOT/'build/package'
    work.mkdir(parents=True, exist_ok=True)
    icon = work/'claude.ico'
    with Image.open(pack.path(pack.actions[pack.idle])) as image:
        image.convert('RGBA').save(icon, sizes=[(32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
               '--onefile' if onefile else '--onedir', '--name', NAME, '--noupx',
               '--distpath', str(dist), '--workpath', str(work/'work'),
               '--specpath', str(work), '--paths', str(ROOT.parent), '--icon', str(icon),
               '--add-data', str(pack.root/'character.json')+';assets/character',
               '--add-data', str(ROOT.parent/'LICENSE')+';assets/licenses',
               '--add-data', str(ROOT.parent/'share/assets/fonts')+';assets/fonts']
    for module in COMPANION_EXCLUDES:
        command.extend(['--exclude-module', module])
    for item in pack.actions.values():
        destination='assets/character/'+Path(item['file']).parent.as_posix()
        command.extend(['--add-data', str(pack.path(item))+';'+destination])
        if item.get('dragLoopFile'):
            command.extend(['--add-data', str(pack.path({'file':item['dragLoopFile']}))+';assets/character/playback'])
    env = native_build_environment(command)
    command.append(str(ROOT/'app/main.py'))
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    if onefile:
        return dist/f'{NAME}.exe'
    removed = prune_qt(dist/NAME/'_internal')
    print(f'pruned {removed/2**20:.1f} MiB of unused Qt files')
    return dist/NAME/f'{NAME}.exe'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--onefile', action='store_true', help='single exe; slower to start')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(build(args.onefile, args.output))
