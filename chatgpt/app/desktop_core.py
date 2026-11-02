"""Desktop configuration, action arbitration and bounded physics (no Qt)."""
import copy
import json
import math
import os
from pathlib import Path

DEFAULTS=dict(schema=3,scale=1.0,drag_physics=True,
    on_top=True,video_fullscreen_yield=True,no_move=False,wandering=True,random_actions=True,
    commentary=True,bubble=True,quota_visible=True,character_visible=True,card_anchor=None,
    status_actions=True,token_chart_range='all',
    card_hide_delay=10.,web_button='chatgpt',web_url='',
    facing=1,character='builtin',character_preferences={})

REMOVED=('update_checks','chat_follow','self_talk','talk_min','talk_max','talk_quiet','talk_lines','mouse_through',
         'bubble_mode','capsule_action','capsule_website',
         # Action pacing is built in now.
         'playback_speed','action_gap','random_interval','move_speed','move_range',
         'status_action_interval','status_response_revision',
         # The character makes no sound.
         'sound')

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temp,path)

def normalized(raw):
    out=copy.deepcopy(DEFAULTS);out.update(raw if isinstance(raw,dict) else {})
    for k,lo,hi in [('scale',.4,2.5),('card_hide_delay',3,120)]:
        try:v=float(out[k]);out[k]=min(hi,max(lo,v)) if math.isfinite(v) else DEFAULTS[k]
        except (TypeError,ValueError):out[k]=DEFAULTS[k]
    for k,v in DEFAULTS.items():
        if isinstance(v,bool):out[k]=out[k] if isinstance(out[k],bool) else v
    out['facing']=-1 if out['facing']==-1 else 1
    if out['token_chart_range'] not in ('all','30d','7d','day'):out['token_chart_range']='all'
    if isinstance(raw,dict) and 'web_button' not in raw and raw.get('capsule_action')=='website':
        out['web_button']='website';out['web_url']=raw.get('capsule_website','')
    if out['web_button'] not in ('chatgpt','website'):out['web_button']='chatgpt'
    out['web_url']=str(out['web_url'] or '')[:2048]
    if out['web_button']=='website':
        from quick_actions import website_url
        try:out['web_url']=website_url(out['web_url'])
        except ValueError:out['web_button']='chatgpt'
    if not isinstance(out['character_preferences'],dict):out['character_preferences']={}
    for preferences in out['character_preferences'].values():
        if isinstance(preferences,dict):preferences.pop('talk_lines',None)
    if not isinstance(out['character'],str) or not out['character'] or len(out['character'])>128:out['character']='builtin'
    for key in REMOVED:out.pop(key,None)
    out['schema']=3
    return out

PRIORITY={'idle':0,'turn':1,'walk':1,'variant':2,'reaction':2,'click':5,'quota':5,'task':7,'landing':8,'throw':9,'drag':10}
class ActionGate:
    def __init__(self):self.state='idle';self.pending=None
    def request(self,state,item=None,force=False):
        if force or PRIORITY.get(state,2)>=PRIORITY.get(self.state,2):
            self.state=state;return True
        if state=='task':self.pending=(state,item)
        return False
    def finish(self):
        pending=self.pending;self.pending=None;self.state='idle';return pending

def physics_step(x,y,vx,vy,dt,bounds):
    dt=min(.05,max(0,dt));left,top,right,bottom=bounds
    x+=vx*dt;y+=vy*dt
    if x<left:x=left;vx=abs(vx)*.45
    if x>right:x=right;vx=-abs(vx)*.45
    if y<top:y=top;vy=abs(vy)*.45
    if y>bottom:y=bottom;vy=-abs(vy)*.45
    drag=math.exp(-3.8*dt);vx*=drag;vy*=drag
    return x,y,vx,vy,math.hypot(vx,vy)<15

def relative_position(x,y,w,h,area,name):
    left,top,aw,ah=area
    return dict(screen=name,rx=max(0,min(1,(x-left)/max(1,aw-w))),ry=max(0,min(1,(y-top)/max(1,ah-h))))

def restore_position(saved,w,h,area):
    left,top,aw,ah=area
    return round(left+max(0,aw-w)*max(0,min(1,float(saved.get('rx',.85))))),round(top+max(0,ah-h)*max(0,min(1,float(saved.get('ry',.85)))))
