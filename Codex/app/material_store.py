"""Immutable, content-addressed built-in materials, independent of app versions."""
import hashlib,json,sys
from pathlib import Path,PurePosixPath
from desktop_core import atomic_json
import embedded_assets

class MaterialError(ValueError):pass
class MaterialCancelled(MaterialError):pass

def checked(root,name):
    if not isinstance(name,str) or '\\' in name or ':' in name:raise MaterialError('素材路径无效')
    p=PurePosixPath(name)
    if p.is_absolute() or any(v in ('','.','..') for v in name.split('/')):raise MaterialError('素材路径无效')
    root=Path(root);target=root.joinpath(*p.parts)
    if root.is_symlink() or any(v.is_symlink() or getattr(v,'is_junction',lambda:False)() for v in [target,*target.parents] if v!=root.parent and (v==root or root in v.parents)):raise MaterialError('素材目录不能使用链接跳转')
    if not target.resolve().is_relative_to(root.resolve()):raise MaterialError('素材路径越界')
    return target

def cancelled(cancel):
    if cancel():raise MaterialCancelled('素材操作已取消，继续使用原画质')

def hash_file(path,cancel=lambda:False):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while data:=stream.read(1024*1024):cancelled(cancel);h.update(data)
    return h.hexdigest()

class MaterialStore:
    """Both tiers ship inside the one-file program and unpack locally on first use."""
    def __init__(self,app_root,state_dir,executable=None):
        self.app_root=Path(app_root);self.state=Path(state_dir);self.base=self.app_root/'assets/character'
        self.cache=self.state/'materials';self.preference=self.state/'material-preferences.json'
        catalog_path=self.app_root/'app/material_catalog.json'
        self.catalog=json.loads(catalog_path.read_text(encoding='utf-8')) if catalog_path.is_file() else None
        if self.catalog:
            if self.catalog.get('schema')!=1:raise MaterialError('素材目录版本不受支持')
            for tier in self.catalog['tiers'].values():
                if not tier['id'].isalnum() or len(tier['files'])>128:raise MaterialError('素材目录无效')
                for f in tier['files']:
                    checked(self.base,f['path'])
                    if not 0<f['bytes']<2**31 or len(f['sha256'])!=64:raise MaterialError('素材校验信息无效')
        if executable is None and getattr(sys,'frozen',False):executable=sys.executable
        self.executable=Path(executable) if executable else None
        self.embedded=embedded_assets.embedded_tiers(self.executable) if self.executable and self.catalog else set()
        try:self.preferred=json.loads(self.preference.read_text(encoding='utf-8'))['tier']
        except (OSError,ValueError,KeyError,TypeError):self.preferred='light'
        if self.preferred not in ('light','hd'):self.preferred='light'
        self.current='light' if self.catalog else 'hd'
        # Development assets are originals; frozen base is always the light tier.
        self.development=not getattr(sys,'frozen',False) and (self.app_root/'build/materials/light/素材清单.json').is_file()
        if self.catalog and self.preferred=='hd' and self.available('hd'):
            self.root=self.tier_root('hd');self.current='hd'
        else:
            if 'light' in self.embedded and not self.available('light'):self.unpack('light')
            self.root=self.tier_root('light')

    def tier_root(self,tier):
        if tier=='light':
            if 'light' in self.embedded:return checked(self.cache,'light/'+self.catalog['tiers']['light']['id'])
            return self.app_root/'build/materials/light' if self.development else self.base
        return checked(self.cache,'hd/'+self.catalog['tiers']['hd']['id'])

    def builtin(self,tier):
        return tier in self.embedded or (tier=='light' and bool(self.catalog))

    def available(self,tier):
        if not self.catalog:return tier=='hd'
        root=self.tier_root(tier)
        if tier=='light' and 'light' not in self.embedded:return (root/'素材清单.json').is_file()
        return embedded_assets.receipt_valid(root,self.catalog['tiers'][tier])

    def verify(self,root,tier,cancel=lambda:False,progress=lambda n,t,p:None):
        files=self.catalog['tiers'][tier]['files'];total=sum(f['bytes'] for f in files);done=0
        for f in files:
            cancelled(cancel);p=checked(root,f['path'])
            if p.stat().st_size!=f['bytes'] or hash_file(p,cancel)!=f['sha256']:raise MaterialError('素材校验失败：'+f['path'])
            done+=f['bytes'];progress(done,total,'verifying')
        return True

    def unpack(self,tier,cancel=lambda:False,progress=lambda n,t,p:None):
        try:root=embedded_assets.unpack(self.executable,self.cache/tier,tier,self.catalog['tiers'][tier],cancel,progress)
        except embedded_assets.Cancelled as exc:raise MaterialCancelled(str(exc)) from exc
        except (OSError,ValueError) as exc:raise MaterialError('内置素材损坏或无法解包：'+str(exc)) from exc
        if root is None:raise MaterialError('当前程序没有内置这套素材')
        return root

    def ensure(self,tier,cancel=lambda:False,progress=lambda n,t,p:None):
        if not self.catalog:raise MaterialError('当前版本没有可切换的素材目录')
        root=self.tier_root(tier)
        if self.available(tier):self.verify(root,tier,cancel,progress);return root
        if tier in self.embedded:return self.unpack(tier,cancel,progress)
        if tier=='light':raise MaterialError('内置轻量素材缺失，请修复安装')
        raise MaterialError('当前运行方式没有内置高清素材，请使用打包后的 DesktopPet.exe')

    def activate(self,tier,root):
        if Path(root)!=self.tier_root(tier) or not self.available(tier):raise MaterialError('素材尚未准备完成')
        atomic_json(self.preference,dict(schema=1,tier=tier))
        self.preferred=tier;self.current=tier;self.root=Path(root)
