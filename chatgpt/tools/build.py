"""Build ChatGpt for Windows without an installer.

The default is a folder build: ChatGpt/ChatGpt.exe starts without unpacking
Python and Qt into a temporary folder on every launch (about one second
saved). The native 512px character pack is embedded in the executable either way and
unpack once into the user's data folder. --onefile keeps the single-file form.
"""
import argparse
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = 'ChatGpt'
sys.path[:0] = [str(ROOT), str(ROOT / 'app'), str(ROOT / 'tools'), str(ROOT.parent)]


def idle_path(folder):
    import json
    from material_manifest import manifest_path, playback_path
    data=json.loads(manifest_path(folder).read_text(encoding='utf-8-sig'))
    return playback_path(folder,data['idle'])


def prepare_materials():
    from material_store import MaterialStore
    if not (ROOT/'app/material_catalog.json').is_file():
        raise FileNotFoundError('缺少当前角色资源校验清单')
    with TemporaryDirectory(prefix='desktop-pet-build-state-') as state:
        store=MaterialStore(ROOT,Path(state))
        store.verify(ROOT/'assets/character','light')
    return ROOT/'assets/character'


def build(output=None,onefile=False):
    materials=prepare_materials()
    output=Path(output or ROOT/'dist').resolve();output.mkdir(parents=True,exist_ok=True)
    work=ROOT/'build/package';work.mkdir(parents=True,exist_ok=True)
    from PIL import Image
    icon=work/'desktop-pet.ico'
    with Image.open(idle_path(materials)) as image:
        image.convert('RGBA').save(icon,sizes=[(32,32),(48,48),(64,64),(128,128),(256,256)])
    command=[
        sys.executable,'-m','PyInstaller.utils.cliutils.makespec','--windowed',
        '--onefile' if onefile else '--onedir','--name',APP_NAME,'--specpath',str(work),
        '--paths',str(ROOT/'app'),'--paths',str(ROOT.parent),'--icon',str(icon),'--noupx',
        '--exclude-module','imageio_ffmpeg',
    ]
    # The character files are embedded outside PyInstaller's archive, so no
    # launch re-extracts hundreds of megabytes into a temporary folder.
    data=[*( (ROOT/'assets'/name,'assets/'+name) for name in ('sounds','licenses') ),
          (ROOT.parent/'share/assets/fonts','assets/fonts'),
          (ROOT/'app/material_catalog.json','app')]
    for source,destination in data:command.extend(['--add-data',str(source)+';'+destination])
    from share.pet_engine.packaging import native_build_environment
    env=native_build_environment(command)
    command.append(str(ROOT/'app/main.py'))
    subprocess.run(command,cwd=ROOT,env=env,check=True)
    spec=work/(APP_NAME+'.spec');trim_spec(spec)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(output),'--workpath',str(work),str(spec)],cwd=ROOT,env=env,check=True)
    executable=output/(APP_NAME+'.exe') if onefile else output/APP_NAME/(APP_NAME+'.exe')
    embed_materials(executable,materials)
    return executable


# Qt/PIL components the pet never loads; every launch would otherwise unpack them.
UNUSED=('pyside6/opengl32sw.dll','pyside6/qt6quick','pyside6/qt6qml','pyside6/qt6pdf','pyside6/qt6virtualkeyboard',
        'pyside6/plugins/platforminputcontexts/','pyside6/plugins/imageformats/qpdf','pyside6/plugins/platforms/qdirect2d',
        'pyside6/translations/','pil/_avif')


def trim_spec(spec):
    text=spec.read_text(encoding='utf-8');anchor='pyz = PYZ(a.pure)'
    if anchor not in text:raise ValueError('PyInstaller 规格文件格式未知，无法裁剪未用组件')
    rule=(f'UNUSED={UNUSED!r}\n'
          "a.binaries=[e for e in a.binaries if not e[0].replace('\\\\','/').lower().startswith(UNUSED)]\n"
          "a.datas=[e for e in a.datas if not e[0].replace('\\\\','/').lower().startswith(UNUSED)]\n")
    spec.write_text(text.replace(anchor,rule+anchor,1),encoding='utf-8')


def embed_materials(executable,materials):
    import json
    from embedded_assets import embed
    tiers=json.loads((ROOT/'app/material_catalog.json').read_text(encoding='utf-8'))['tiers']
    embed(executable,dict(light=(materials,tiers['light']['files'])))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='Directory for the completed executable')
    parser.add_argument('--onefile',action='store_true',help='Build one executable (slower start) instead of a folder')
    args=parser.parse_args()
    try:
        print(build(args.output,onefile=args.onefile))
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
