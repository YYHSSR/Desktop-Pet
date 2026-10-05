"""Click the unchanged shipped executable; restore only its Run value afterwards."""
import os, time, ctypes, subprocess, winreg, shutil, argparse
from pathlib import Path
from ctypes import wintypes
from PIL import ImageGrab
u=ctypes.windll.user32
u.SetProcessDPIAware()
u.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
u.GetWindowRect.argtypes=[ctypes.c_void_p,ctypes.POINTER(wintypes.RECT)]
u.IsWindowVisible.argtypes=[ctypes.c_void_p]
CB=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
class Mouse(ctypes.Structure):
    _fields_=[('dx',wintypes.LONG),('dy',wintypes.LONG),('data',wintypes.DWORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
class Union(ctypes.Union):
    _fields_=[('mouse',Mouse)]
class Input(ctypes.Structure):
    _fields_=[('type',wintypes.DWORD),('data',Union)]
key=r'Software\Microsoft\Windows\CurrentVersion\Run'
name='dsh-pet-standalone-webm-chat'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--exe',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--config',type=Path)
parser.add_argument('--run-key',action='store_true',help='Allow testing and restoring this app Run value')
args=parser.parse_args()
if not args.run_key: parser.error('This unchanged-executable check requires --run-key')
exe=args.exe.resolve()
name=exe.stem
output=args.output.resolve()
output.mkdir(exist_ok=True)
env=os.environ.copy()
env['APPDATA']=str(output/'AppData')
env.pop('QT_QPA_PLATFORM',None)
config=Path(env['APPDATA'])/name/'config.json'
config.parent.mkdir(parents=True,exist_ok=True)
if args.config: shutil.copyfile(args.config,config)
def read():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key) as k:
            return winreg.QueryValueEx(k,name)
    except FileNotFoundError: return None
prev=read()
cursor=wintypes.POINT()
u.GetCursorPos(ctypes.byref(cursor))
p=subprocess.Popen([str(exe)],env=env,cwd=exe.parent,creationflags=subprocess.CREATE_NO_WINDOW)
def windows():
    found=[]
    @CB
    def cb(hwnd,_):
        pid=wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==p.pid:
            title=ctypes.create_unicode_buffer(256); cls=ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(hwnd,title,256);u.GetClassNameW(hwnd,cls,256)
            b=wintypes.RECT();u.GetWindowRect(hwnd,ctypes.byref(b))
            found.append((hwnd,title.value,cls.value,bool(u.IsWindowVisible(hwnd)),(b.left,b.top,b.right,b.bottom)))
        return True
    u.EnumWindows(cb,0)
    return found
try:
    time.sleep(5)
    print('PID',p.pid,flush=True)
    tray=next(w[0] for w in windows() if w[1]=='QTrayIconMessageWindow')
    for i in range(4):
        u.SetCursorPos(100,500)
        u.PostMessageW(tray,0x8000+101,100|(500<<16),0x7b)
        time.sleep(.4)
        ws=windows();print('POPUP OPEN',i,flush=True)
        menu=next(w for w in ws if w[3] and 'Popup' in w[2])
        l,t,r,b=menu[4]
        u.SetCursorPos((l+r)//2,t+round((b-t)*.59))
        clicks=(Input*2)();clicks[0].data.mouse.flags=2;clicks[1].data.mouse.flags=4
        assert u.SendInput(2,clicks,ctypes.sizeof(Input))==2
        began=time.perf_counter();old='unset'
        while time.perf_counter()-began<10:
            value=read()
            if value!=old:
                print('REG',i,round((time.perf_counter()-began)*1000,2),value,flush=True);old=value
            time.sleep(.001)
        expected = (not bool(prev)) if i % 2 == 0 else bool(prev)
        assert bool(read()) == expected, f'Registry state incorrect after click {i}'
        u.SetCursorPos(100,500)
        u.PostMessageW(tray,0x8000+101,100|(500<<16),0x7b)
        time.sleep(.25)
        menu=next(w for w in windows() if w[3] and 'Popup' in w[2])
        l,t,r,b=menu[4]
        image=ImageGrab.grab(bbox=(l,t,r,b))
        image.save(output/f'menu-{i}.png')
        y=round((b-t)*.59)
        region=image.crop((r-l-38,y-10,r-l-12,y+10))
        blue=sum(1 for y in range(region.height) for x in range(region.width)
                 if (px:=region.getpixel((x,y)))[2]>150 and px[0]<60)
        print('VISIBLE CHECK',i,expected,blue,flush=True)
        assert (blue>10)==expected, f'Visible check incorrect after click {i}'
        logfile=config.parent/f'pet-{p.pid}.log'
        print('AUTOSTART LOG', '\n'.join(line for line in logfile.read_text(encoding='utf-8').splitlines() if 'utostart' in line),flush=True)
    print('SHIPPED_TRAY_OK',flush=True)
finally:
    for w in windows():
        if w[1]=='QTrayIconMessageWindow':u.PostMessageW(w[0],0x10,0,0)
    try:p.wait(timeout=15)
    except subprocess.TimeoutExpired:p.terminate();p.wait()
    u.SetCursorPos(cursor.x,cursor.y)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,key,0,winreg.KEY_SET_VALUE) as k:
        if prev is not None:winreg.SetValueEx(k,name,0,prev[1],prev[0])
        else:
            try:winreg.DeleteValue(k,name)
            except FileNotFoundError:pass
