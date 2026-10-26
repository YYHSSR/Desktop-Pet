"""WebM import may use an explicitly selected or existing local converter."""
import json,os,shutil,subprocess,sys
from pathlib import Path

def settings_file():return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'BailongEnhanced/optional-tools.json'
def find_ffmpeg():
    candidates=[os.environ.get('BAILONG_FFMPEG','')]
    try:candidates.append(json.loads(settings_file().read_text(encoding='utf-8')).get('ffmpeg',''))
    except (OSError,ValueError,AttributeError):pass
    candidates.append(shutil.which('ffmpeg.exe') or shutil.which('ffmpeg') or '')
    if not getattr(sys,'frozen',False):
        # Development only. Standalone builds use an explicitly selected tool.
        try:
            import importlib
            candidates.append(importlib.import_module('imageio_ffmpeg').get_ffmpeg_exe())
        except (ImportError,RuntimeError):pass
    return next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()),None)

def save_ffmpeg(path):
    path=Path(path).resolve()
    if not path.is_file():raise ValueError('所选转换工具不存在。')
    try:result=subprocess.run([str(path),'-version'],capture_output=True,timeout=5,creationflags=0x08000000 if os.name=='nt' else 0)
    except (OSError,subprocess.TimeoutExpired) as error:raise ValueError('转换工具版本检测失败。') from error
    if result.returncode or not result.stdout.lower().startswith(b'ffmpeg version'):raise ValueError('所选文件不是可识别的 FFmpeg。')
    from desktop_core import atomic_json
    settings_file().parent.mkdir(parents=True,exist_ok=True);atomic_json(settings_file(),dict(ffmpeg=str(path)))
