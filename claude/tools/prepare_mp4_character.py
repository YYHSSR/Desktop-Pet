"""Rebuild Claude exclusively from her MP4s and the idle clip's reference pose."""
from pathlib import Path
import hashlib
import json
import sys
import cv2
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT.parent),str(ROOT/'app')]
from mp4_matte import matte_frame, outlined_foreground
from share.asset_tools.exact_webp import encode
from model import ACTION_WEIGHTS, MENU_ORDER

ASSETS=ROOT/'assets/character'
BUILD=ROOT/'build/mp4-rebuild'
RECIPE='claude-mp4-contour-native-rgb-shared-idle'
NAMES=dict(idle='\u5f85\u673a',rest='\u62b1\u4e66\u9759\u5019',wave='\u5411\u4f60\u6325\u624b',
           peek='\u4e66\u540e\u5077\u770b',idea='\u7075\u611f\u6765\u4e86',sparkles='\u4e66\u9875\u82b1\u5149',
           wind='\u98ce\u4e2d\u6574\u7406',bow='\u8f6c\u5708\u884c\u793c',flower='\u4e66\u4e2d\u8d60\u82b1',
           drag='\u62d6\u62fd',**{'walk-left':'\u5411\u5de6\u8d70\u8d70','walk-right':'\u5411\u53f3\u8d70\u8d70'})
cv2.setNumThreads(1)

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')

def dissolve(a,b,count):
    a,b=np.asarray(a,np.float32)/255,np.asarray(b,np.float32)/255
    a[...,:3]*=a[...,3:];b[...,:3]*=b[...,3:]
    result=[]
    for index in range(count):
        t=index/(count-1);t=t*t*(3-2*t)
        value=a*(1-t)+b*t;alpha=value[...,3:]
        rgb=np.divide(value[...,:3],alpha,out=np.zeros_like(value[...,:3]),where=alpha>.001)
        result.append(Image.fromarray(np.rint(np.clip(np.dstack((rgb,alpha)),0,1)*255).astype(np.uint8)))
    return result

def decode(path,soft=False):
    cap=cv2.VideoCapture(str(path))
    if not cap.isOpened():raise ValueError('Cannot open source MP4: '+path.name)
    if (int(cap.get(3)),int(cap.get(4)))!=(480,480) or abs(cap.get(cv2.CAP_PROP_FPS)-24)>.001:
        raise ValueError('Expected native 480px, 24fps source clips')
    frames=[];tinted_total=tinted_lost=opaque_total=0
    try:
        while True:
            ok,bgr=cap.read()
            if not ok:break
            rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
            image=matte_frame(Image.fromarray(rgb),soft_effects=soft)
            rgba=np.asarray(image);opaque=rgba[...,3]==255
            if not np.array_equal(rgba[...,:3][opaque],rgb[opaque]):raise ValueError('Opaque source RGB changed')
            tinted=(np.ptp(rgb,axis=2)>=20)&(rgb.min(axis=2)<235)
            if soft:tinted &= outlined_foreground(rgb)
            tinted_total+=int(tinted.sum());tinted_lost+=int((tinted&(rgba[...,3]<128)).sum())
            opaque_total+=int(opaque.sum())
            canvas=Image.new('RGBA',(512,512));canvas.paste(image,(16,16));frames.append(canvas)
    finally:cap.release()
    if len(frames)<24 or tinted_lost/max(1,tinted_total)>.002:raise ValueError('Character retention check failed: '+path.name)
    return frames,dict(sourceFrames=len(frames),sourceFramesKept=len(frames),fps=24,sourceResolution=[480,480],
                       opaqueRGBMaximumError=0,opaqueSourcePixelsPreserved=opaque_total,
                       tintedPixels=tinted_total,lostTintedPixels=tinted_lost,
                       tintedPixelCheckScope='outlined-character' if soft else 'all-artwork')

def prepare():
    BUILD.mkdir(parents=True,exist_ok=True)
    paths={key:ASSETS/'MP4'/(name+'.mp4') for key,name in NAMES.items()}
    if not all(path.is_file() for path in paths.values()):raise ValueError('Required Claude MP4 source is missing')
    hashes={key:digest(path) for key,path in paths.items()}
    records=[];reports={};anchor=None
    for key,path in paths.items():
        print('PREPARE '+key,flush=True)
        soft=key in ('sparkles','idea')
        frames,report=decode(path,soft)
        if anchor is None:anchor=frames[0].copy()
        differences=[float(np.abs(np.asarray(frame,np.float32)-np.asarray(anchor,np.float32)).mean()/255)
                     for frame in (frames[0],frames[-1])]
        if max(differences)>.035:raise ValueError('Source endpoints differ from idle: '+key)
        entry=[] if frames[0].tobytes()==anchor.tobytes() else dissolve(anchor,frames[0],7)[:-1]
        tail=dissolve(frames[-1],anchor,10)[1:]
        frames=entry+frames+tail
        delays=[round((i+1)*1000/24)-round(i*1000/24) for i in range(len(frames))]
        relative='playback-mp4/'+key+'.webp'
        encoded=encode(ASSETS/relative,frames,delays)
        weight=ACTION_WEIGHTS.get(key,0.)
        record=dict(id=key,name=path.stem,group='Actions',file=relative,loop=key=='idle',
                    durationMs=sum(delays),frames=len(frames),bytes=encoded['bytes'],sha256=encoded['sha256'],
                    recipe=RECIPE,source=path.relative_to(ASSETS).as_posix(),sourceSha256=hashes[key],
                    sourceFrames=report['sourceFrames'],sourceFrameOffset=len(entry),
                    entryBridgeFrames=len(entry),exitBridgeFrames=len(tail),randomWeight=weight,random=weight>0)
        if key in ('walk-left','walk-right'):
            record['walk']=dict(direction=-1 if key=='walk-left' else 1,start=len(entry)+24,end=len(entry)+230)
        if key=='drag':
            record.update(dragStartFrame=len(entry)+36,dragHoldFrame=len(entry)+176,
                          releaseFrame=len(entry)+177,liftCompletes=True,
                          dragHoldPolicy='complete-action-static-pose-until-release')
        records.append(record)
        report.update(originalEndpointDifference=differences,entryFramesAdded=len(entry),returnFramesAdded=len(tail),
                      encoded=encoded,allFramesVerified=True,softExteriorEffects=soft)
        reports[key]=report
        sheet=Image.new('RGB',(1536,280),'#253447')
        for column,index in enumerate((0,len(entry)+58,len(entry)+115,len(entry)+173,len(entry)+230,len(frames)-1)):
            tile=frames[index].resize((256,256));sheet.paste(tile,(column*256,12),tile)
        sheet.save(BUILD/(key+'-preview.png'))
        print('VERIFIED '+key+': '+str(len(frames))+' exact frames',flush=True)
    reference=hashlib.sha256(anchor.tobytes()).hexdigest()
    for record in records:record['referencePose']=reference
    ordered={record['id']:record for record in records}
    descriptor=dict(character='claude',name='Claude',sourceFormat='mp4',idle='idle',drag='drag',
                    referencePose=reference,actions=[ordered[key] for key in MENU_ORDER])
    write_json(ASSETS/'character.json',descriptor)
    inventory=[dict(file=path.relative_to(ASSETS).as_posix(),name=path.stem,bytes=path.stat().st_size,
                    sha256=hashes[key],frames=reports[key]['sourceFrames'],fps=24) for key,path in paths.items()]
    write_json(ASSETS/'manifest.json',dict(character='claude',kind='mp4-originals',background='white',files=inventory))
    if any(digest(path)!=hashes[key] for key,path in paths.items()):raise ValueError('An original MP4 changed during preparation')
    write_json(BUILD/'verification.json',dict(passed=True,actions=len(records),referencePose=reference,
               originalMP4sPreserved=True,allFramesVerified=True,noTextureReconstruction=True,reports=reports))
    print('COMPLETE: Claude rebuilt from her 12 MP4 sources.',flush=True)

if __name__=='__main__':prepare()
