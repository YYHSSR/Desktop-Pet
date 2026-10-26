"""Portable Codex discovery; inspect paths and capabilities, never credentials."""
import os,shutil,subprocess,sys,time
from pathlib import Path

def user_environment(name):
    if sys.platform!='win32':return ''
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:return str(winreg.QueryValueEx(key,name)[0])
    except OSError:return ''

def data_home(home=None):
    value=home or os.environ.get('BAILONG_CODEX_HOME') or os.environ.get('CODEX_HOME') or user_environment('CODEX_HOME') or Path.home()/'.codex'
    return Path(os.path.expandvars(str(value).strip().strip('"'))).expanduser().resolve()

def child_environment():
    env=dict(os.environ);env['CODEX_HOME']=str(data_home());return env

def packaged_roots():
    roots=set()
    try:
        import psutil
        for p in psutil.process_iter(['name']):
            try:
                if (p.info['name'] or '').lower() in ('chatgpt.exe','codex.exe'):
                    path=Path(p.exe())
                    if 'openai.codex_' in str(path).lower():roots.add(path.parent)
            except (psutil.NoSuchProcess,psutil.AccessDenied,OSError):pass
    except ImportError:pass
    if not roots and sys.platform=='win32':
        try:
            result=subprocess.run(['powershell.exe','-NoProfile','-Command',"Get-AppxPackage -Name OpenAI.Codex | Select-Object -ExpandProperty InstallLocation"],capture_output=True,text=True,timeout=5,creationflags=0x08000000)
            roots.update(Path(line.strip())/'app' for line in result.stdout.splitlines() if line.strip())
        except (OSError,subprocess.TimeoutExpired):pass
    return roots

def find_executable():
    override=os.environ.get('BAILONG_CODEX','').strip().strip('"')
    if override:
        path=Path(os.path.expandvars(override)).expanduser()
        located=str(path) if path.is_file() else shutil.which(override)
        if located:return located
        raise RuntimeError('BAILONG_CODEX 指向的程序不存在，请修正该机器的 Codex CLI 路径。')
    local=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData/Local')
    cache=local/'OpenAI/Codex/bin';candidates=list(cache.glob('*/codex.exe')) if cache.is_dir() else []
    if (cache/'codex.exe').is_file():candidates.append(cache/'codex.exe')
    if candidates:
        try:return str(max(candidates,key=lambda p:p.stat().st_mtime))
        except OSError:pass
    for name in ('codex.exe','codex'):
        candidate=shutil.which(name)
        if candidate and (sys.platform!='win32' or Path(candidate).suffix.lower()=='.exe'):return candidate
    for root in packaged_roots():
        # The app/Codex.exe GUI is intentionally excluded; use its real CLI.
        candidate=root/'resources/codex.exe'
        if candidate.is_file():return str(candidate)
    npm=Path(os.environ.get('APPDATA') or Path.home()/'AppData/Roaming')/'npm/node_modules/@openai'
    for pattern in ('codex/vendor/*/codex/codex.exe','codex-win32-*/vendor/*/codex/codex.exe'):
        for path in npm.glob(pattern):
            if path.is_file():return str(path)
    raise RuntimeError('未找到 Codex CLI。请先安装并打开 Codex；特殊安装可设置 BAILONG_CODEX。')

def check_connection(query_quota=True,cancel=None):
    from desktop_services import codex_desktop_open
    from session_read_state import read_tracking_probe
    from quota import read_quota,quota_windows
    from connection_health import sample
    home=data_home();read=read_tracking_probe(home)
    report=dict(checked=time.time(),desktop_open=codex_desktop_open(),codex_home=str(home),home_exists=home.is_dir(),sessions_exists=(home/'sessions').is_dir(),read_tracking_available=read['state']=='available',cli_found=False,quota_read=False,capabilities={'read':read})
    if report['desktop_open'] is False and read['state']=='available':read.update(state='degraded',code='codex_closed')
    try:report['cli']=find_executable();report['cli_found']=True
    except RuntimeError as error:report['cli_error']=str(error)
    try:
        from enhanced_core import RolloutTail
        tail=RolloutTail(home);tail.poll();status=dict(tail.health)
        if status['state']=='available':status['success_at']=time.time()
        report['session_log_found']=bool(tail.files)
        report['capabilities'].update(tasks=status,completion=dict(status))
    except Exception:
        report['session_log_found']=False;report['capabilities'].update(tasks=sample('unavailable','logs_unreadable'),completion=sample('unavailable','logs_unreadable'))
    if query_quota and report['cli_found']:
        try:
            report['quota_windows']=quota_windows(read_quota(timeout=10,cancel=cancel,attempts=1,log_path=False),allow_empty=True);report['quota_read']=True
            known=any(isinstance(w.get('remaining'),(int,float)) for w in report['quota_windows'])
            report['capabilities']['quota']=sample('available' if known else 'degraded','ok' if known else 'quota_unknown' if report['quota_windows'] else 'no_windows',time.time())
        except Exception as error:
            code=getattr(error,'code','unavailable');code=code if code in ('authentication','network','timeout','cli_missing') else 'unavailable'
            report['quota_error_code']=code;report['capabilities']['quota']=sample('unavailable',code)
    elif not report['cli_found']:report['capabilities']['quota']=sample('unavailable','cli_missing')
    report['summary']=connection_summary(report);return report

def connection_summary(r):
    lines=['Codex 连接检查',
           '桌面应用：'+('已运行' if r.get('desktop_open') is True else '未运行或权限暂不可确认'),
           'CLI：'+('已找到' if r.get('cli_found') else '未找到，请先打开 Codex'),
           '本机状态 / Token：'+('已找到会话日志' if r.get('session_log_found') else '尚无会话，请在 Codex 中发送一次消息'),
           '账户额度：'+('查询成功' if r.get('quota_read') else '暂不可用，请检查 Codex 登录、网络及 CLI'),
           '自动已读：'+('支持当前 Codex 本地标记' if r.get('read_tracking_available') else '当前版本无可读标记，可点桌宠图标确认'),
           '数据目录：'+r.get('codex_home','')]
    return '\n'.join(lines)
