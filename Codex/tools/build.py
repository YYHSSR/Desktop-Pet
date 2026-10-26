"""Build a self-contained Windows executable without an installer."""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'app'), str(ROOT / 'tools'), str(ROOT.parent)]


def prepare_materials():
    from material_store import MaterialStore
    if not (ROOT/'app/material_catalog.json').is_file():raise FileNotFoundError('缺少角色资源校验清单')
    cached=ROOT/'build/materials/light'
    with TemporaryDirectory(prefix='desktop-pet-build-state-') as state:
        store=MaterialStore(ROOT,Path(state))
        try:
            store.verify(cached,'light')
            return cached
        except (OSError,ValueError):pass
        try:
            store.verify(ROOT/'assets/character','light')
        except (OSError,ValueError):pass
        else:
            cached.mkdir(parents=True,exist_ok=True)
            for item in store.catalog['tiers']['light']['files']:
                target=cached/item['path'];target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/'assets/character'/item['path'],target)
            return cached
    from import_assets import missing_assets
    missing = missing_assets(ROOT)
    if missing:
        raise FileNotFoundError(f'缺少 {len(missing)} 个角色素材文件，请先运行 tools/import_assets.py')
    from PIL import Image
    with Image.open(ROOT/'assets/character/quality-v1/idle.webp') as image:
        if image.size!=(720,720):raise ValueError('素材既不匹配轻量校验清单，也不是完整高清构建源')
    from build_materials import build as build_materials
    build_materials()
    return cached


def prepare_hd(source=None):
    """Find a folder whose files match the HD checksums; the program embeds it unchanged."""
    from material_store import MaterialStore
    with TemporaryDirectory(prefix='desktop-pet-build-state-') as state:
        store=MaterialStore(ROOT,Path(state))
    hd=store.catalog['tiers']['hd']['id']
    local=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'BailongEnhanced/materials/hd'/hd
    candidates=[Path(source)] if source else [ROOT/'build/materials/hd',ROOT/'assets/character',local]
    for folder in candidates:
        try:
            store.verify(folder,'hd')
            return folder
        except (OSError,ValueError):continue
    raise FileNotFoundError('找不到通过校验的高清素材，请用 --hd-source 指定高清素材文件夹')


def build(output=None,onefile=True,hd_source=None):
    materials=prepare_materials()
    hd=prepare_hd(hd_source) if onefile else None
    output=Path(output or ROOT/'dist').resolve();output.mkdir(parents=True,exist_ok=True)
    work=ROOT/'build/package';work.mkdir(parents=True,exist_ok=True)
    from PIL import Image
    icon=work/'desktop-pet.ico'
    with Image.open(materials/'quality-v1/idle.webp') as image:
        image.convert('RGBA').save(icon,sizes=[(32,32),(48,48),(64,64),(128,128),(256,256)])
    command=[
        sys.executable,'-m','PyInstaller.utils.cliutils.makespec','--windowed',
        '--onefile' if onefile else '--onedir','--name','DesktopPet','--specpath',str(work),
        '--paths',str(ROOT/'app'),'--paths',str(ROOT.parent),'--icon',str(icon),'--noupx',
        '--exclude-module','imageio_ffmpeg',
    ]
    # One-file builds embed the character files outside PyInstaller's archive so
    # launches do not re-extract hundreds of megabytes into a temporary folder.
    data=[*( (ROOT/'app'/name,'app/'+name) for name in ('sounds','fonts','licenses') ),
          (ROOT/'app/material_catalog.json','app')]
    if not onefile:data.insert(0,(materials,'assets/character'))
    for source,destination in data:command.extend(['--add-data',str(source)+';'+destination])
    from shared.pet_engine.packaging import native_build_environment
    env=native_build_environment(command)
    command.append(str(ROOT/'app/enhanced.py'))
    subprocess.run(command,cwd=ROOT,env=env,check=True)
    spec=work/'DesktopPet.spec';trim_spec(spec)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(output),'--workpath',str(work),str(spec)],cwd=ROOT,env=env,check=True)
    if not onefile:return output/'DesktopPet/DesktopPet.exe'
    embed_materials(output/'DesktopPet.exe',materials,hd)
    return output/'DesktopPet.exe'


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


def embed_materials(executable,materials,hd):
    import json
    from embedded_assets import embed
    tiers=json.loads((ROOT/'app/material_catalog.json').read_text(encoding='utf-8'))['tiers']
    embed(executable,dict(light=(materials,tiers['light']['files']),hd=(hd,tiers['hd']['files'])))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='Directory for the completed executable')
    parser.add_argument('--onedir',action='store_true',help='Build a development directory instead of one executable')
    parser.add_argument('--hd-source',type=Path,help='Folder with verified HD character files to embed')
    args=parser.parse_args()
    try:
        print(build(args.output,onefile=not args.onedir,hd_source=args.hd_source))
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
