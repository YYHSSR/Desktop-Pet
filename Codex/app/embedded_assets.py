"""Character tiers stored inside the one-file executable, unpacked once per tier."""
import hashlib,json,os,shutil,struct,uuid
from pathlib import Path,PurePosixPath

MARKER=b'BAILONG-ASSETS\x00\x00'
FOOTER=struct.Struct('<16sQQ')
COOKIE=struct.Struct('!8sIIii64s')
COOKIE_MARKER=b'MEI\014\013\012\013\016'
CHUNK=1024*1024

class Cancelled(ValueError):pass

def archive_start(stream):
    stream.seek(0,os.SEEK_END);size=stream.tell()
    if size<COOKIE.size:return None
    stream.seek(size-COOKIE.size);cookie=COOKIE.unpack(stream.read(COOKIE.size))
    if cookie[0]!=COOKIE_MARKER or not 0<cookie[1]<=size:return None
    return size-cookie[1]

def embed(executable,tiers):
    """Insert tiers between the bootloader and its archive; the bootloader ignores this span.

    tiers maps a tier name to (source folder, catalog file entries)."""
    executable=Path(executable);temp=executable.with_name(executable.name+'.embed')
    with executable.open('rb') as source,temp.open('wb') as output:
        start=archive_start(source)
        if start is None:raise ValueError('不是单文件程序，无法内嵌素材')
        source.seek(0);left=start
        while left:data=source.read(min(CHUNK,left));output.write(data);left-=len(data)
        index={}
        for name,(root,files) in tiers.items():
            entries=index[name]=[]
            for f in files:
                offset=output.tell()
                with (Path(root)/PurePosixPath(f['path'])).open('rb') as data:shutil.copyfileobj(data,output,CHUNK)
                if output.tell()-offset!=f['bytes']:raise ValueError('素材大小不符：'+f['path'])
                entries.append(dict(path=f['path'],offset=offset,bytes=f['bytes']))
        body=json.dumps(index,ensure_ascii=False).encode('utf-8');offset=output.tell()
        output.write(body);output.write(FOOTER.pack(MARKER,offset,len(body)))
        shutil.copyfileobj(source,output,CHUNK)
    os.replace(temp,executable)

def read_index(stream):
    start=archive_start(stream)
    if start is None or start<FOOTER.size:return None
    stream.seek(start-FOOTER.size);marker,offset,length=FOOTER.unpack(stream.read(FOOTER.size))
    if marker!=MARKER or offset+length>start-FOOTER.size or length>4*CHUNK:return None
    stream.seek(offset);index=json.loads(stream.read(length).decode('utf-8'))
    return index if isinstance(index,dict) else None

def embedded_tiers(executable):
    try:
        with Path(executable).open('rb') as stream:index=read_index(stream)
    except (OSError,ValueError):return set()
    return set(index or ())

def receipt_valid(root,spec):
    try:
        receipt=json.loads((root/'.verified.json').read_text(encoding='utf-8'))
        if receipt['id']!=spec['id']:return False
        for f in spec['files']:
            s=(root/PurePosixPath(f['path'])).stat()
            if s.st_size!=f['bytes'] or receipt['files'][f['path']]!=[s.st_size,s.st_mtime_ns]:return False
        return True
    except (OSError,ValueError,KeyError,TypeError):return False

def unpack(executable,cache,name,spec,cancel=lambda:False,progress=lambda n,t,p:None):
    """Return a verified copy of an embedded tier in cache/<id>, or None when it is not embedded."""
    cache=Path(cache);target=cache/spec['id'];files=spec['files']
    if receipt_valid(target,spec):return target
    with Path(executable).open('rb') as stream:
        index=read_index(stream)
        if not index or name not in index:return None
        entries={e['path']:e for e in index[name]}
        if set(entries)!={f['path'] for f in files}:raise ValueError('内嵌素材与校验清单不一致')
        cache.mkdir(parents=True,exist_ok=True);stage=cache/('staging-'+uuid.uuid4().hex)
        total=sum(f['bytes'] for f in files);done=0
        try:
            receipt={}
            for f in files:
                entry=entries[f['path']]
                if entry['bytes']!=f['bytes']:raise ValueError('内嵌素材大小不符：'+f['path'])
                path=stage/PurePosixPath(f['path']);path.parent.mkdir(parents=True,exist_ok=True)
                digest=hashlib.sha256();stream.seek(entry['offset']);left=entry['bytes']
                with path.open('wb') as output:
                    while left:
                        if cancel():raise Cancelled('素材操作已取消，继续使用原画质')
                        data=stream.read(min(CHUNK,left))
                        if not data:raise ValueError('内嵌素材不完整：'+f['path'])
                        digest.update(data);output.write(data);left-=len(data);done+=len(data)
                        progress(done,total,'unpacking')
                if digest.hexdigest()!=f['sha256']:raise ValueError('内嵌素材校验失败：'+f['path'])
                s=path.stat();receipt[f['path']]=[s.st_size,s.st_mtime_ns]
            (stage/'.verified.json').write_text(json.dumps(dict(id=spec['id'],files=receipt)),encoding='utf-8')
            if target.exists():shutil.rmtree(target)
            stage.replace(target)
        finally:
            if stage.exists():shutil.rmtree(stage,ignore_errors=True)
    for old in cache.iterdir():
        if old!=target and old.is_dir() and not old.name.startswith(('staging-','download-')):shutil.rmtree(old,ignore_errors=True)
    return target
