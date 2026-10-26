"""Incremental local token accounting. Persist counters, never conversation content."""
import calendar
import copy
import math
import sqlite3
import time
from contextlib import closing
from datetime import datetime,timedelta
from pathlib import Path

def counter(value):
    if isinstance(value,int) and not isinstance(value,bool) and 0<=value<2**62:return value
    return None

def compact_tokens(value):
    if value>=1_000_000_000:return f'{value/1_000_000_000:.2f}B'
    if value>=1_000_000:return f'{value/1_000_000:.2f}M'
    if value>=1000:return f'{value/1000:.1f}K'
    return str(value)

def month_bounds(now=None):
    current=datetime.fromtimestamp(time.time() if now is None else now)
    start=current.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    end=start.replace(year=start.year+1,month=1) if start.month==12 else start.replace(month=start.month+1)
    return start,end

class TokenUsageIndex:
    def __init__(self,path,home=None):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.home=__import__('codex_connection').data_home(home)
        self.format_known={}
        self.file_states={};self.cached_snapshot=None;self.cached_day=None
        self.cached_at=0;self.next_usage=float('inf');self.database_state=None
        from log_catalog import LogCatalog
        self.catalog=LogCatalog(self.home)

    def connect(self):
        db=sqlite3.connect(self.path,timeout=5)
        db.execute('CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, offset INTEGER, highwater INTEGER)')
        db.execute('CREATE TABLE IF NOT EXISTS usage (fingerprint TEXT PRIMARY KEY, stamp REAL, tokens INTEGER)')
        db.execute('CREATE INDEX IF NOT EXISTS usage_stamp ON usage(stamp)')
        from token_analytics import migrate
        migrate(db)
        return db

    def scan_file(self,db,path,stop):
        from token_analytics import scan_file
        return scan_file(self,db,path,stop)

    def poll(self,now=None,stop=lambda:False):
        from performance_metrics import METRICS
        now=time.time() if now is None else now
        files=self.catalog.discover(check=True);errors=self.catalog.errors;readable=0;schema_errors=0
        database_state=self.database_signature()
        with closing(self.connect()) as db, db:
            changes=db.total_changes
            for path in sorted(files):
                if stop():break
                try:
                    stat=path.stat();signature=(stat.st_size,stat.st_mtime_ns,stat.st_ino,stat.st_ctime_ns)
                    previous=self.file_states.get(path)
                    if previous is not None and previous[0]==signature:known=previous[1]
                    else:
                        with METRICS.span('token_scan_file'):known=self.scan_file(db,path,stop)
                        if not stop():self.file_states[path]=(signature,known)
                    if known is False:errors+=1;schema_errors+=1
                    else:readable+=1
                except OSError:errors+=1
            self.file_states={path:value for path,value in self.file_states.items() if path in files}
            day=datetime.fromtimestamp(now).date()
            if self.cached_snapshot is None or db.total_changes!=changes or database_state!=self.database_state or day!=self.cached_day or now<self.cached_at or now>=self.next_usage:
                self.cached_snapshot=self.snapshot(db,now,0);self.cached_day=day;self.cached_at=now
                future=db.execute('SELECT MIN(stamp) FROM usage WHERE stamp>?',(now,)).fetchone()[0]
                self.next_usage=float('inf') if future is None else future
            result=copy.deepcopy(self.cached_snapshot)
            result.update(checked=now,partial=bool(errors),log_files=len(files),readable_files=readable,format_unknown=bool(schema_errors))
            if not readable:
                result['partial']=True
                if not result.get('history_days'):result['unavailable']=True;result['report']={}
        self.database_state=self.database_signature()
        return result

    def database_signature(self):
        values=[]
        for path in (self.path,self.path.with_name(self.path.name+'-wal')):
            try:
                stat=path.stat();values.append((stat.st_size,stat.st_mtime_ns))
            except OSError:values.append(None)
        return tuple(values)

    def snapshot(self,db,now=None,errors=0):
        now=time.time() if now is None else now;start,end=month_bounds(now)
        days={f'{start:%Y-%m}-{day:02}':0 for day in range(1,calendar.monthrange(start.year,start.month)[1]+1)}
        history=dict(db.execute("SELECT date(stamp,'unixepoch','localtime'),SUM(tokens) FROM usage WHERE stamp<=? GROUP BY date(stamp,'unixepoch','localtime')",(now,)))
        for day,value in history.items():
            if day in days:days[day]=value
        current=datetime.fromtimestamp(now);midnight=current.replace(hour=0,minute=0,second=0,microsecond=0)
        hours=[0]*24
        for hour,value in db.execute("SELECT strftime('%H',stamp,'unixepoch','localtime'),SUM(tokens) FROM usage WHERE stamp>=? AND stamp<=? GROUP BY strftime('%H',stamp,'unixepoch','localtime')",(midnight.timestamp(),now)):
            hours[int(hour)]=value
        from token_analytics import report_snapshot
        return {'report':report_snapshot(db,now),'month':start.strftime('%Y-%m'),'days':days,'total':sum(days.values()),
                'history_days':history,'history_start':min(history,default=None),'all_total':sum(history.values()),
                'today':current.strftime('%Y-%m-%d'),'hours':hours,
                'checked':now,'partial':bool(errors),'source':'本机 Codex 日志'}


TOKEN_RANGES=('all','30d','7d','day')

def usage_series(snapshot,period='30d',now=None):
    """Bounded daily bars or hourly consumption, with honest future/empty slots."""
    snapshot=snapshot or {};now=time.time() if now is None else now
    current=datetime.fromtimestamp(now);today=current.date();period=period if period in TOKEN_RANGES else '30d'
    bins=[];available=bool(snapshot) and not snapshot.get('unavailable')
    if period=='day':
        values=snapshot.get('hours') or [];available=available and snapshot.get('today')==today.isoformat() and len(values)==24
        for hour in range(24):
            value=counter(values[hour]) if available else 0
            bins.append(dict(label=f'{hour:02}:00–{hour+1:02}:00',value=value or 0,
                             future=hour>current.hour,current=hour==current.hour,start=hour,end=hour))
        return dict(mode='line',period=period,title='今日',bins=bins,total=sum(b['value'] for b in bins if not b['future']),
                    available=available,start=today.isoformat(),end=today.isoformat())
    history=snapshot.get('history_days',snapshot.get('days',{})) or {};clean={}
    for key,value in history.items():
        try:day=datetime.strptime(key,'%Y-%m-%d').date()
        except (ValueError,TypeError):continue
        if day<=today and counter(value) is not None:clean[day]=value
    start=min(clean,default=today) if period=='all' else today-timedelta(days=29 if period=='30d' else 6)
    span=(today-start).days+1;step=max(1,math.ceil(span/24)) if period=='all' else 1
    cursor=start
    while cursor<=today:
        last=min(today,cursor+timedelta(days=step-1))
        value=sum(clean.get(cursor+timedelta(days=i),0) for i in range((last-cursor).days+1))
        label=str(cursor) if cursor==last else f'{cursor} 至 {last}'
        bins.append(dict(start=cursor.isoformat(),end=last.isoformat(),label=label,value=value,current=last==today,future=False))
        cursor=last+timedelta(days=1)
    return dict(mode='bars',period=period,title={'all':'全部','30d':'30天','7d':'7天'}[period],bins=bins,
                total=sum(b['value'] for b in bins),available=available,start=start.isoformat(),end=today.isoformat(),bucket_days=step)
