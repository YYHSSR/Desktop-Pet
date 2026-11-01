"""Build and verify every pet; archive replaced programs without deleting files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[2]
NAMES={'chatgpt':'ChatGpt','claude':'ClaudePet','gemini':'GeminiPet'}


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def checked(path):
    path=Path(path).absolute()
    if not path.resolve().is_relative_to(ROOT) or path==ROOT:raise ValueError('Path outside project')
    for part in (path,*path.parents):
        if part==ROOT.parent:break
        if part.is_symlink() or part.is_junction():raise ValueError('Linked package path')
    return path


def fingerprint(role):
    files=list((ROOT/role/'app').rglob('*.py'))
    for folder in ('desktop','pet_engine'):files.extend((ROOT/'share'/folder).rglob('*.py'))
    for path in (ROOT/role/'app/material_catalog.json',ROOT/role/'assets/character/manifest.json',ROOT/role/'assets/character/character.json'):
        if path.is_file():files.append(path)
    h=hashlib.sha256()
    for path in sorted(files):h.update(path.relative_to(ROOT).as_posix().encode());h.update(bytes.fromhex(digest(path)))
    return h.hexdigest()


def build_and_verify(role):
    folder=ROOT/role;name=NAMES[role];checks=folder/'build/checks'
    checks.mkdir(parents=True,exist_ok=True)
    identity=fingerprint(role)
    stage=checked(folder/'build/package-output')
    print('BUILD '+role,flush=True)
    with (checks/'package-build.log').open('wb') as log:
        subprocess.run([sys.executable,str(folder/'tools/build.py'),'--output',str(stage)],cwd=folder,
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    package=stage/name;exe=package/(name+'.exe')
    with tempfile.TemporaryDirectory(prefix='desktop-pet-package-') as tmp:
        state=Path(tmp);env=os.environ.copy()
        env.update(LOCALAPPDATA=tmp,APPDATA=str(state/'roaming'),CODEX_HOME=str(state/'codex'),QT_QPA_PLATFORM='offscreen')
        with (checks/'package-smoke.log').open('wb') as log:
            if role=='chatgpt':
                for flag,target in (('--bundle-check','package-resources.json'),('--material-probe','package-ui.json')):
                    subprocess.run([str(exe),flag,str(checks/target)],env=env,cwd=state,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
                    assert read(checks/target)['passed'],target
                assert not read(checks/'package-resources.json')['hdBuiltin']
            else:
                assets=package/'_internal/assets/character';original=folder/'assets/character'
                assert digest(assets/'character.json')==digest(original/'character.json')
                descriptor=read(assets/'character.json')
                files={item['file']:item['sha256'] for item in descriptor['actions']}
                for item in descriptor['actions']:
                    if item.get('dragLoopFile'):files[item['dragLoopFile']]=item['dragLoopSha256']
                for path,sha in files.items():assert digest(assets/path)==sha,path
                assert {p.relative_to(assets).as_posix() for p in assets.rglob('*.webp')}==set(files)
                subprocess.run([str(exe),'--smoke-test','--no-tray','--show-panel','--state-dir',str(state),
                                '--capture-dir',str(checks/'package-ui')],env=env,cwd=state,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
                result=read(state/'smoke-result.json')
                assert result['card_ready'] and result['source_frame']>=0,result
                assert result['editor_tabs']==['常规','动作'] and result['editor_navigation']==['状态','设置'],result
                (checks/'package-ui.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert fingerprint(role)==identity,'Source changed during packaging'
    result=dict(passed=True,sourceFingerprint=identity,executable=str(exe),sha256=digest(exe),
                bytes=sum(p.stat().st_size for p in package.rglob('*') if p.is_file()))
    (checks/'package-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('READY '+role+' '+str(round(result['bytes']/2**20,1))+' MiB',flush=True)


def activate(roles):
    import psutil
    plans=[]
    running={os.path.normcase(p.info['exe']) for p in psutil.process_iter(['exe']) if p.info['exe']}
    for role in roles:
        name=NAMES[role];proof=read(ROOT/role/'build/checks/package-result.json')
        source=checked(ROOT/role/'build/package-output'/name)
        target=checked(ROOT/role/'dist'/name)
        archive=checked(ROOT/'build/archive'/role/'programs'/(name+'-'+uuid.uuid4().hex[:8]))
        assert proof['passed'] and proof['sourceFingerprint']==fingerprint(role)
        assert digest(source/(name+'.exe'))==proof['sha256']
        if os.path.normcase(str(target/(name+'.exe'))) in running:raise RuntimeError('Please exit '+name+' before activation')
        plans.append((role,source,target,archive,proof))
    for role,source,target,archive,proof in plans:
        archive.parent.mkdir(parents=True,exist_ok=True);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():target.rename(archive)
        try:source.rename(target)
        except OSError:
            if archive.exists() and not target.exists():archive.rename(target)
            raise
        proof.update(executable=str(target/(NAMES[role]+'.exe')),archivedProgram=str(archive))
        (ROOT/role/'build/checks/package-result.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        print('ACTIVATED '+proof['executable'],flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roles',nargs='+',choices=tuple(NAMES),default=list(NAMES))
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--activate',action='store_true',help='activate after all packages pass; archive previous programs')
    mode.add_argument('--activate-only',action='store_true',help='activate previously verified staged packages')
    args=parser.parse_args()
    if not args.activate_only:
        for role in args.roles:build_and_verify(role)
    if args.activate or args.activate_only:activate(args.roles)


if __name__=='__main__':main()
