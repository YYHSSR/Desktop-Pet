"""Lossless independent RGBA frames with verified frame indices and timing."""
import hashlib
import io
from pathlib import Path
import struct
from PIL import Image


def encode(path, frames, durations):
    if not frames or len(frames)!=len(durations):raise ValueError('Invalid animation sequence')
    width,height=frames[0].size
    if any(frame.mode!='RGBA' or frame.size!=(width,height) for frame in frames):raise ValueError('Inconsistent RGBA canvas')
    if any(type(delay) is not int or not 1<=delay<2**24 for delay in durations):raise ValueError('Invalid frame timing')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.preparing.webp')
    def chunk(tag,value):return tag+struct.pack('<I',len(value))+value+(b'\0' if len(value)%2 else b'')
    u24=lambda value:int(value).to_bytes(3,'little')
    with temporary.open('wb') as stream:
        stream.write(b'RIFF\0\0\0\0WEBP')
        stream.write(chunk(b'VP8X',b'\x12\0\0\0'+u24(width-1)+u24(height-1)))
        stream.write(chunk(b'ANIM',struct.pack('<IH',0,0)))
        for frame,delay in zip(frames,durations):
            buffer=io.BytesIO();frame.save(buffer,format='WEBP',lossless=True,exact=True,method=1,quality=80)
            data=buffer.getvalue();offset=12;payload=b''
            while offset<len(data):
                length=int.from_bytes(data[offset+4:offset+8],'little');end=offset+8+length+(length%2)
                if data[offset:offset+4]==b'VP8L':payload+=data[offset:end]
                offset=end
            if not payload:raise ValueError('Missing lossless WebP payload')
            stream.write(chunk(b'ANMF',u24(0)+u24(0)+u24(width-1)+u24(height-1)+u24(delay)+b'\x02'+payload))
        length=stream.tell()-8;stream.seek(4);stream.write(struct.pack('<I',length))
    with Image.open(temporary) as check:
        if check.size!=(width,height) or check.n_frames!=len(frames):raise ValueError('Animation structure changed')
        for index,(frame,delay) in enumerate(zip(frames,durations)):
            check.seek(index);check.load()
            if check.convert('RGBA').tobytes()!=frame.tobytes() or check.info['duration']!=delay:
                raise ValueError('Frame verification failed: '+str(index))
    temporary.replace(path)
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(frames=len(frames),durationMs=sum(durations),bytes=path.stat().st_size,sha256=sha)
