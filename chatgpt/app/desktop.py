"""Full desktop controls on top of the existing Codex/quota integration."""
import copy
import json
import math
import random
import shutil
import sys
import time
from collections import deque
from action_picker import ActionPicker
from share.pet_engine.action_catalog import populate_action_menu, unique_actions
from share.desktop.context_menu import populate_menu as populate_shared_menu
from PySide6.QtCore import Qt,QTimer,QPoint,QPointF,QRect,QRectF,QUrl,QEvent,Signal
from PySide6.QtGui import QCursor,QDesktopServices,QTransform
from PySide6.QtWidgets import QApplication,QMenu,QSystemTrayIcon
from enhanced import EnhancedPet,STATE_DIR,CONFIG
from pet import ROOT,clamp_position
from enhanced_core import motion_step,clean_text
from performance_metrics import measured
from desktop_core import (normalized,atomic_json,ActionGate,physics_step,relative_position,
    restore_position)
from desktop_services import all_items,open_codex
from stream_player import PreparedSegment,StreamPlayer
from loop_cache import DecodedLoopCache
from status_reactions import StatusReactions
from continuous_work import ContinuousWork
from sustained_player import SustainedPlayback
from sustained_assets import profile_paths,seam_items
from material_manifest import manifest_path
from pose_handoff import PoseHandoff
from share.desktop.sprite_window import stride

# How often each built-in variant turns up on its own: everyday gestures are
# common, the dragon-lore pieces stay special. Imported characters fall back to 1.
VARIANT_WEIGHTS={'01':3.,'20':2.7,'08':2.5,'04':2.2,'05':1.8,'14':1.1,'09':.9,'17':1.3,
    '13':.3,'18':0.,'22':.25,'25':.15,'21':.1,'24':.65,'26':.2}

# Built-in pacing; these used to be advanced settings.
ACTIVITY_SECONDS=12.   # average pause between things she does on her own
ACTION_GAP=2.          # breather after every action
STATUS_REPEAT=12.      # a Codex state animates again at most this often
WALK_SPEED=.26         # sprite widths per second while she walks
PLAN_AHEAD=20          # idle frames before its seam at which the next move is picked and decoded
PRESS_HOLD_MS=220      # distinguish a deliberate hold from an ordinary quick click

def variant_weight(item,hour=None):
    hour=time.localtime().tm_hour if hour is None else hour
    key=item.get('id');weight=item.get('randomWeight',VARIANT_WEIGHTS.get(key,1.))
    if key=='14' and (13<=hour<15 or hour>=23 or hour<6):weight*=3  # sleepy after lunch and late
    elif key=='01' and 7<=hour<10:weight*=1.6                       # morning hello
    elif key=='17' and (11<=hour<13 or 17<=hour<19):weight*=2        # snack time
    return weight

class DesktopPet(EnhancedPet):
    LAZY=True
    settingsChanged=Signal(dict)
    connectionHealthChanged=Signal(dict)
    def __init__(self,monitor=True):
        self._video_yielded=False;self.video_yield=None
        self._desktop_hidden=False;self._card_anchor=None;self._visibility_ready=False
        self._card_revealed=False;self.picker=ActionPicker();self.stroll=None;self.planned=None;self.upcoming=None
        from codex_connection import data_home
        from connection_health import CapabilityHealth
        try:previous=json.loads((STATE_DIR/'runtime.json').read_text(encoding='utf-8')).get('connection_health')
        except (OSError,ValueError):previous=None
        self.connection_health=CapabilityHealth(data_home(),previous)
        from material_store import MaterialStore
        self.material_store=MaterialStore(ROOT,STATE_DIR)
        self.player=None;self.gate=ActionGate();self.handoff=PoseHandoff();self._drag_loop_phase=None;self._landing_due=False;self.release_tail=None;self.asset_root=self.material_store.root
        self.animation_wakeups=0;self.movement_wakeups=0
        self.sustained=SustainedPlayback();self.continuous=ContinuousWork();self._resume_idle=False
        self._interactive_action=False;self._manual_action=False;self._priority=0
        self._hit_image=None;self.throwing=False;self.velocity=(0.,0.)
        self._pointer_pressed=False;self._pointer_epoch=0
        self.drag_samples=deque(maxlen=12);self.press_feedback=0;self.buffer_until=0
        self.pending_completion=None;self.settings_dialog=None
        self.reactions=StatusReactions(time.monotonic());self.last_reaction=None
        self.character_dir=STATE_DIR/'characters';self.character_dir.mkdir(exist_ok=True)
        self.created_at=time.monotonic();self.decode_error=None
        super().__init__(monitor)
        self.card_timer=QTimer(self);self.card_timer.setSingleShot(True);self.card_timer.timeout.connect(self.conceal_card)
        # A hidden Qt/native owner can also suppress its tool windows. Keep a
        # logical owner for data/placement, with an independent native card.
        self.bubble.setParent(None,self.bubble.windowFlags())
        self.bubble._owner=self
        from codex_navigation import CodexNavigation
        self.codex_navigation=CodexNavigation(lambda session:open_codex(session),self)
        self.codex_navigation.error.connect(lambda text:self.say(text,6000))
        self.reactions.set_actions(item['id'] for item in all_items(self.manifest))
        self.bubble.settingsRequested.connect(self.open_settings)
        self.bubble.webRequested.connect(self.open_web)
        self.bubble.codexRequested.connect(self.open_assistant)
        self.bubble.conversationRequested.connect(self.open_conversation)
        self.bubble.optionRequested.connect(self.set_option)
        self.bubble.installEventFilter(self)
        if self.settings.get('schema')!=2 and CONFIG.exists():
            shutil.copy2(CONFIG,STATE_DIR/'settings-before-migration.json')
        self.settings=normalized(self.settings)
        self._visibility_ready=True
        self._card_anchor=self.settings.get('card_anchor')
        self.walk_direction=self.settings['facing']
        self.apply_settings({},save=False)
        chosen=self.settings.get('character','builtin')
        if chosen!='builtin':
            try:self.switch_character(chosen)
            except (OSError,ValueError,KeyError):
                self.settings['character']='builtin';self.say('角色包不可用，已恢复ChatGpt 默认素材。',6000)
        self.restore_saved_position()
        self.next_chain=time.monotonic()+self.picker.delay(ACTIVITY_SECONDS)
        self.motion_clock=time.monotonic()
        self.tray.setToolTip('ChatGpt')
        self.tray.activated.disconnect()
        self.tray.activated.connect(lambda reason:self.recover() if reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        self.tray_menu=QMenu();self.tray_menu.aboutToShow.connect(self.populate_tray);self.tray.setContextMenu(self.tray_menu)
        if monitor and sys.platform=='win32':
            from video_yield import VideoYield
            self.video_yield=VideoYield(self)
        self.save_settings()
        self.schedule_animation()

    def asset_path(self,item):
        name=item.get('playbackFile') or item['file'].replace('.webm','.webp')
        path=(self.asset_root/name).resolve()
        if not path.is_relative_to(self.asset_root.resolve()):raise ValueError('素材路径不在角色目录内')
        return path

    def play(self,item,mode):
        if self._visibility_ready and (self._desktop_hidden or not self.settings.get('character_visible',True)):return False
        if self._interactive_action and mode=='variant':mode='click'
        if not self.gate.request(mode,item,force=self._interactive_action or self._manual_action):return False
        if mode=='drag' and item is self.current and (self._landing_due or
                item.get('dragHoldFrame') is not None and self._drag_loop_phase in ('enter','held')):
            # Caught again before she was set down: the lift simply carries on.
            self._landing_due=False;self.mode=mode;return True
        previous_frame=self.frames[self.index] if getattr(self,'frames',None) else None
        previous_item=getattr(self,'current',None)
        # Every clip ends exactly on the shared pose and the next one starts
        # there, so a clip that ran to its end is followed by a plain cut.
        natural=self.player is not None and self.player.ended and mode not in ('drag','throw')
        upcoming,self.upcoming=self.upcoming,None
        if mode!='idle':self.planned=None
        self.sustained.cancel()
        self._drag_loop_phase=None;self._landing_due=False
        if mode not in ('drag','throw'):self.drop_release()
        if self.player is None:
            self.player=StreamPlayer()
            # Native detailed lace exceeds the engine's small generic entry cap.
            # Keep complete idle/held loops instead of decoding them every repeat.
            self.player.loop_cache=DecodedLoopCache(limit=160*1024*1024)
            self.player.loop_cache.entry_limit=128*1024*1024
        try:
            options={}
            if mode in ('drag','throw') and item.get('dragHoldFrame') is not None:
                # Skip the video's idle lead-in so the press visibly responds.
                options=dict(start_frame=item.get('dragStartFrame',0),end_frame=item['dragHoldFrame'])
                self._drag_loop_phase='enter'
                self.prepare_release(item)
            elif mode=='landing' and item.get('dragHoldFrame') is not None:
                options=dict(start_frame=item['releaseFrame'])
            elif mode in ('drag','throw') and item.get('dragLoopFile'):
                # Lift through the clip's short entrance; decode the way down meanwhile.
                options=dict(end_frame=item['dragLoopEnd'])
                self._drag_loop_phase='enter'
                self.prepare_release(item)
            path=self.asset_path(item)
            # A clip picked ahead of the idle seam is already decoding: cut straight in.
            ready=(upcoming is not None and upcoming[0]==path
                   and upcoming[1].start==options.get('start_frame',0)
                   and upcoming[1].end==options.get('end_frame',item['frames']-1)
                   and upcoming[1].ready.is_set()
                   and not upcoming[1].error and upcoming[1].size==self.frame_size)
            if upcoming is not None and not ready:upcoming[1].close()
            if ready:frame=self.player.adopt(upcoming[1])
            else:frame=self.player.start(path,self.frame_size,item.get('durationMs',4000)/1000,
                                        cache_loop=mode=='idle' or item.get('loop',False),**options)
        except (OSError,ValueError,KeyError) as error:
            self.decode_error=type(error).__name__;self.gate.state='idle'
            if self.current and self.current is not item:
                fallback=self.idles[0]
                if item is not fallback:self.play(fallback,'idle')
                return False
            raise
        self.frames=[frame];self._hit_image=frame.toImage();self.current=item;self.mode=mode;self.index=0
        self.started=time.monotonic();self.transition=None
        if previous_frame is not None and previous_item is not None and not natural:
            self.handoff.begin(previous_frame,previous_item,.12 if mode=='drag' else .22)
        self.update_frame()
        self.schedule_animation()
        return True

    def prepare_release(self,item):
        self.drop_release()
        if item.get('releaseFrame') is not None and item['releaseFrame']<item['frames']-1:
            self.release_tail=PreparedSegment(self.asset_path(item),self.frame_size,item['releaseFrame'],item['frames']-1)

    def drop_release(self):
        if self.release_tail is not None:self.release_tail.close();self.release_tail=None

    def prepare_next(self,item,start=0,end=None):
        self.drop_upcoming()
        try:path=self.asset_path(item);self.upcoming=(path,PreparedSegment(path,self.frame_size,start,item['frames']-1 if end is None else end))
        except (OSError,ValueError,KeyError):pass

    def drop_upcoming(self):
        if self.upcoming is not None:self.upcoming[1].close();self.upcoming=None

    def land(self):
        """Set her down: the drag clip's own return to the shared pose, then idle."""
        if self.mode=='landing' and self.current.get('dragHoldFrame') is not None:
            return True
        if self._drag_loop_phase=='enter' and self.mode in ('drag','throw') and self.player and not self.player.ended:
            # A quick release still plays the whole lift; she comes down from its end.
            self._landing_due=True;self.mode='drag';self.gate.state='landing';return True
        self._landing_due=False
        natural=self.player is not None and self.player.ended
        tail,self.release_tail=self.release_tail,None
        item=self.manifest.get('dragAnimation')
        if not item and not self.manifest.get('landingAnimation'):
            if tail is not None:tail.close()
            self.idle()
            return True
        if item and item.get('dragHoldFrame') is not None:
            self.gate.state='landing'
        ready=tail is not None and tail.ready.is_set() and not tail.error and tail.size==self.frame_size
        if ready and item and self.gate.request('landing',item):
            previous=self.frames[self.index] if self.frames else None
            self.sustained.cancel();self._drag_loop_phase=None
            frame=self.player.adopt(tail)
            self.frames=[frame];self._hit_image=frame.toImage();self.current=item;self.mode='landing';self.index=0
            self.started=time.monotonic();self.transition=None
            if previous is not None and not natural:self.handoff.begin(previous,item,.2)
            self.update_frame();self.schedule_animation()
            return True
        if tail is not None:tail.close()
        if item and item.get('dragHoldFrame') is not None:
            self.gate.state='idle'
            return self.play(item,'landing')
        return self.play(self.manifest.get('landingAnimation') or self.idles[0],'landing')

    def repeat_drag_loop(self):
        item=self.current;self._drag_loop_phase='held'
        frame=self.player.start(self.asset_root/item['dragLoopFile'],self.frame_size,
                                end_frame=item['dragLoopFrames']-1,cache_loop=True)
        self.frames=[frame];self.index=0;self._hit_image=frame.toImage();self.update_frame()

    def idle(self):
        self.gate.state='idle'
        self.play(self.idles[0],'idle')

    @measured('pet_animation_event')
    def animate(self):
        self.animation_wakeups+=1
        try:self._animate_frame()
        finally:self.schedule_animation()

    def schedule_movement(self):
        if not hasattr(self,'motion_timer') or not self.motion_timer.isActive():return
        active=self.walking or self.throwing
        interval=33 if active else 1000
        if self.motion_timer.interval()!=interval:
            if active:self.motion_clock=time.monotonic()
            self.motion_timer.setInterval(interval)

    def schedule_animation(self):
        self.schedule_movement()
        if not hasattr(self,'tick') or not self.tick.isActive() or not self.player:return
        interval=self.player.next_delay_ms(self.sustained.speed_factor(self.player))
        if getattr(self,'_drag_loop_phase',None)=='held' and self.current.get('dragHoldFrame') is not None:
            interval=250
        if getattr(self,'handoff',None) and self.handoff.active():interval=min(16,interval)
        if self.press_feedback and time.monotonic()-self.press_feedback<.5:interval=min(16,interval)
        self.tick.setInterval(interval)

    def _animate_frame(self):
        if self.player is None or not self.current:return
        if getattr(self,'_visibility_ready',False) and (self._desktop_hidden or not self.settings.get('character_visible',True)):return
        now=time.monotonic()
        desired=self.continuous.target(self.reactions,now,self.status_animation_allowed())
        was_sustained=self.sustained.active
        if was_sustained:
            owner=self.sustained.owner
            self.sustained.request(bool(desired and (desired.session,desired.turn,desired.action_id)==(owner.session,owner.turn,owner.action_id)))
        frame,ended=self.player.advance(self.frame_size,self.sustained.speed_factor(self.player))
        if frame is not None:
            self.frames=[frame];self.index=0;self._hit_image=frame.toImage();self.update_frame()
            if self.mode=='idle' and self.planned is None and self.player.frame_index>=self.current.get('frames',0)-PLAN_AHEAD:
                self.plan_ahead(now)
        if self.handoff.active() or self.press_feedback and time.monotonic()-self.press_feedback<.5:self.update()
        if ended:
            if was_sustained:
                frame,finished=self.sustained.boundary(self.player,self.frame_size)
                if not finished:
                    self.frames=[frame];self.index=0;self._hit_image=frame.toImage();self.update_frame();return
            if self.player.error:
                self.decode_error=self.player.error
                if self.enhanced_ready:self.say('这段素材读取失败，已回到待机。',5000)
            if self.mode in ('drag','throw') and self.current.get('dragHoldFrame') is not None:
                if self._landing_due or not self.dragging:self.land()
                else:self._drag_loop_phase='held'
                return
            if self.mode in ('drag','throw') and self.current.get('dragLoopFile'):
                if self._landing_due:self.land()
                else:self.repeat_drag_loop()
                return
            if self.mode in ('drag','throw') or (self.mode=='walk' and self.walking and not self.stroll):
                mode=self.mode;self.gate.state=mode;self.play(self.current,mode);return
            if self.stroll:
                # A walk clip plays once: she has arrived, and settles into idle.
                self.walking=False;self.stroll=None;self.save_settings()
            previous=self.mode;self.gate.finish();now=time.monotonic()
            plan,self.planned=self.planned,None
            if previous!='idle':
                dedicated=previous=='reaction' and str(self.current.get('id','')).startswith('work')
                self.reactions.finished(now,0 if was_sustained else max(2 if dedicated else 8,ACTION_GAP))
                self.buffer_until=now+max(.8,ACTION_GAP)
            if previous in ('click','landing','task','quota','reaction','walk'):self.next_chain=self.buffer_until+self.picker.delay(ACTIVITY_SECONDS)
            if self.play_status_reaction(now):return
            if previous=='idle' and self.autonomous_boundary(now,plan):return
            self.idle()

    def status_animation_allowed(self):
        return self.isVisible() and self.settings.get('status_actions',True) and not (self.dragging or self.throwing or self.walking)

    def play_status_reaction(self,now):
        if self.gate.state!='idle' or not self.status_animation_allowed() or not self.player or not self.player.ended:return False
        selected=self.reactions.take_completion(now) or self.reactions.take_opening(now)
        desired=self.continuous.target(self.reactions,now)
        retired={item.get('id') for item in self.manifest.get('additionalIdleAnimations',[])}
        items={item['id']:item for item in all_items(self.manifest) if item['id'] not in retired}
        if selected is None and desired and now>=self.reactions.earliest:
            item=items.get(desired.action_id)
            try:profile=profile_paths(self.asset_root,item) if item else None
            except (OSError,ValueError,KeyError):profile=None;self.decode_error='invalid_sustained_profile'
            if profile:
                if not self.gate.request('reaction',item):return False
                try:frame=self.sustained.begin(self.player,profile,desired,self.frame_size)
                except (OSError,ValueError):
                    self.sustained.cancel();self.gate.state='idle';self.decode_error='sustained_start_failed';return False
                self.current=item;self.mode='reaction';self.frames=[frame];self.index=0;self._hit_image=frame.toImage()
                self.started=now;self.transition=None;self.update_frame()
                self.continuous.commit(desired);self.last_reaction=desired;self.reactions.record(desired,now)
                return True
            selected=self.reactions.take_current(desired,now)
        # Paused feedback remains a one-shot, independent of active-state loops.
        if selected is None and self.reactions.latest and self.reactions.latest.get('state')=='interrupted':
            selected=self.reactions.poll(now,boundary=True)
        if selected is None:return False
        item=items.get(selected.action_id)
        # Imported characters need an actual corresponding action. Do not
        # substitute an unrelated random animation when a mapping is absent.
        if item is None:return False
        if selected.kind=='complete':self.pending_completion=None
        mode='task' if selected.kind=='complete' else 'reaction'
        if not self.play(item,mode):return False
        if selected.kind not in ('complete','received'):self.continuous.commit(selected)
        self.last_reaction=selected
        return True

    def roll_autonomous(self,now):
        """What she does on her own at an idle seam: (kind, clip) or None to stay idle."""
        if not self.isVisible() or self.dragging or self.throwing or self.walking:return None
        if now<max(self.next_chain,self.buffer_until,self.status_hold):return None
        if self.settings.get('status_actions',True) and self.reactions.busy(now):return None
        self.next_chain=now+self.picker.delay(ACTIVITY_SECONDS)+ACTION_GAP
        choices=['idle'];weights=[10]
        if self.random_actions:
            if self.manifest.get('additionalIdleAnimations') or self.manifest.get('turnAnimations'):
                choices.append('turn');weights.append(8)
            if self.variants:choices.append('variant');weights.append(62)
        if self.wandering and not self.settings['no_move']:choices+=['walk'];weights+=[20]
        selected=self.picker.rng.choices(choices,weights)[0]
        if selected=='walk':return 'walk',self.walk_plan() if self.directional() else None
        if selected=='turn':
            if self.settings.get('character','builtin')=='builtin' and self.manifest.get('additionalIdleAnimations'):
                return 'turn',self.picker.pick(self.manifest['additionalIdleAnimations'])
            return 'flip',self.picker.pick(self.manifest.get('turnAnimations') or self.idles)
        if selected=='variant' and self.variants:return 'variant',self.picker.pick(self.variants,weight=variant_weight)
        # A skipped turn retries sooner instead of waiting a whole interval.
        self.next_chain=now+self.picker.delay(ACTIVITY_SECONDS)*.5
        return None

    def plan_ahead(self,now):
        """Pick the coming seam's move a little early and start decoding its clip."""
        self.planned=self.roll_autonomous(now+PLAN_AHEAD/24) or False
        if self.planned and self.planned[1]:
            clip=self.planned[1]
            self.prepare_next(clip[0] if isinstance(clip,tuple) else clip)

    def autonomous_boundary(self,now,plan=None):
        if plan is None:plan=self.roll_autonomous(now)
        if not plan or not self.isVisible() or self.dragging or self.throwing or self.walking:return False
        kind,clip=plan
        if kind=='walk':self.start_walk(clip);return self.walking
        if kind=='flip':self.walk_direction*=-1;self.settings['facing']=self.walk_direction
        if kind in ('turn','flip'):return self.play(clip,'turn')
        self.choose(clip);return True

    def frame_transform(self,canvas):
        transform=QTransform()
        elapsed=time.monotonic()-self.press_feedback if self.press_feedback else 99
        if elapsed<.5:
            squash=math.sin(elapsed/.5*math.pi*2)*.075*math.exp(-elapsed*5)
            transform.translate(canvas.center().x(),canvas.bottom())
            transform.scale(1+squash,1-squash);transform.translate(-canvas.center().x(),-canvas.bottom())
        if getattr(self,'walk_direction',1)<0 and not self.directional():
            transform.translate(canvas.x()*2+canvas.width(),0);transform.scale(-1,1)
        return transform

    def directional(self):
        """Walk clips that already face their way are never mirrored."""
        return any(item.get('walk') for item in getattr(self,'manifest',{}).get('moveAnimations',[]))

    def draw_frame(self,painter,canvas):
        painter.save();painter.setTransform(self.frame_transform(canvas),True)
        # The base EnhancedPet mirrors only during walking; call Pet directly.
        from pet import Pet
        Pet.draw_frame(self,painter,canvas)
        self.handoff.paint(painter,canvas);painter.restore()

    def nativeEvent(self,event_type,message):
        if sys.platform=='win32' and self.enhanced_ready and not self.dragging:
            from ctypes import wintypes
            msg=wintypes.MSG.from_address(int(message))
            if msg.message==0x84: # WM_NCHITTEST. Preserve soft alpha in the layered window.
                from native_coordinates import client_position,message_position
                pos=client_position(msg.hWnd,*message_position(msg.lParam),self.width(),self.height())
                # Conversion failure delegates to Qt instead of making the pet unclickable.
                if pos is not None and not self.alpha_hit(*pos):return True,-1
        return super().nativeEvent(event_type,message)

    def alpha_hit(self,x,y):
        if not self.frames or not self.current:return False
        if not (0<=x<self.width() and 0<=y<self.height()):return False
        canvas=QRectF(self.rect());inverse,valid=self.frame_transform(canvas).inverted()
        if not valid:return False
        point=inverse.map(QPointF(x,y));target=self.frame_target(canvas)
        if self.handoff.hit(point,canvas):return True
        if target.isEmpty() or not target.contains(point):return False
        image=self._hit_image or self.frames[self.index].toImage()
        fx=math.floor((point.x()-target.x())/target.width()*image.width())
        fy=math.floor((point.y()-target.y())/target.height()*image.height())
        return 0<=fx<image.width() and 0<=fy<image.height() and image.pixelColor(fx,fy).alpha()>=12

    def choose(self,item,interactive=False,manual=False):
        if self._visibility_ready and (self._desktop_hidden or not self.settings.get('character_visible',True)):return
        if not interactive and not manual and self.gate.state not in ('idle','turn','walk','variant'):return
        if interactive and self.gate.state=='task':return
        if item.get('walk') and self.manifest.get('manualMovementActions') and (interactive or manual):
            if self.dragging:return
            self.stop_walk();self.throwing=False
            self.gate.state='idle'
            plan=self.walk_plan(item) if not self.settings.get('no_move') else None
            if plan is not None:self.start_walk(plan)
            else:
                # At a screen boundary or while locked, preview the chosen walk in place.
                self.gate.state='idle';self.play(item,'variant')
            return
        self.stop_walk();self.throwing=False
        self._interactive_action=interactive;self._manual_action=manual
        old=self._priority;self._priority=5 if interactive or manual else 1
        try:super().choose(item,interactive)
        finally:self._interactive_action=False;self._manual_action=False;self._priority=old

    def single_click(self):
        self.last_click=None;self.press_feedback=time.monotonic()
        pool=self.manifest.get('clickAnimations') or [v for v in self.variants if v['id'] in ('01','08','09','10','11','17','20','26') ] or self.variants or self.idles
        self.choose(self.picker.pick(pool),interactive=True)

    def say(self,text,ms=4000):
        if self.enhanced_ready:
            now=time.monotonic();priority=self._priority or 3
            if now<self.status_hold and priority<getattr(self,'message_priority',0):return
            # Automatic action lines never obscure an active Codex task.
            if priority<=1 and (self.last_activity.get('active',0)>0 or self.last_activity.get('state') in ('working','thinking','responding')):return
            self.message_priority=priority
            if priority>=10:self.reveal_card()
        super().say(text,ms)

    def stop_walk(self):
        self.walking=False;self.walk_target=None;self.stroll=None
        if self.mode=='walk':self.gate.state='idle';self.idle()

    def walk_plan(self,preferred=None):
        """(walk clip, signed distance) towards a side with room, or None."""
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen();area=screen.availableGeometry()
        room={-1:self.x()-area.left()-8,1:area.right()-self.geometry().right()-8};options=[]
        for item in self.manifest.get('moveAnimations',[]):
            if preferred is not None and item['id']!=preferred['id']:continue
            walk=item.get('walk')
            if not walk:continue
            distance=WALK_SPEED*self.width()*(walk['end']-walk['start'])/24;space=room[walk['direction']]
            if space>=distance*.4:options.append((item,walk['direction']*min(distance,space),space))
        if not options:return None
        item,distance,_=self.picker.rng.choices(options,[space for *_,space in options])[0]
        return item,round(distance)

    def start_walk(self,plan=None):
        if (self.bubble.report and self.bubble.report.requested) or self.bubble.panel_page!='status' or self.settings.get('no_move') or self.dragging or self.throwing or self.gate.state not in ('idle','walk'):return
        if self.directional():
            # The clip shows her stepping; the window carries her across the desktop.
            plan=plan or self.walk_plan()
            if plan is None:return
            item,distance=plan;walk=item['walk']
            self.stroll=dict(origin=(self.x(),self.y()),distance=distance,frames=(walk['start'],walk['end']))
            self.walking=True;self.gate.state='idle'
            if not self.play(item,'walk'):self.walking=False;self.stroll=None
            return
        # Imported characters without directional clips roam to a random spot.
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen();area=screen.availableGeometry()
        spanx=max(0,area.width()-self.width()-16);spany=max(0,area.height()-self.height()-16)
        left=area.left()+8+spanx*.125;right=left+spanx*.75
        top=area.top()+8+spany*.125;bottom=top+spany*.75
        tx=random.uniform(left,right);ty=random.uniform(top,bottom)
        self.walk_direction=1 if tx>=self.x() else -1;self.settings['facing']=self.walk_direction
        self._fx,self._fy=float(self.x()),float(self.y());self.walk_target=(tx,ty,(area.left(),area.top(),area.right()-self.width()+1,area.bottom()-self.height()+1))
        pool=self.manifest.get('moveAnimations') or self.manifest.get('additionalIdleAnimations') or self.idles
        self.walking=True;self.gate.state='idle';self.play(self.picker.pick(pool),'walk');self.gesture_until=time.monotonic()+15

    def motion_tick(self):
        self.movement_wakeups+=1
        try:self._move_frame()
        finally:self.schedule_movement()

    def _move_frame(self):
        if not self.enhanced_ready:return
        now=time.monotonic();dt=now-self.motion_clock;self.motion_clock=now
        if not self.isVisible():return
        if self.throwing:
            a=(QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()).availableGeometry()
            bounds=(a.left(),a.top(),max(a.left(),a.right()-self.width()+1),max(a.top(),a.bottom()-self.height()+1))
            self._fx,self._fy,vx,vy,done=physics_step(self._fx,self._fy,*self.velocity,dt,bounds);self.velocity=(vx,vy)
            self.move(round(self._fx),round(self._fy));self.position_bubble()
            if done:
                self.throwing=False
                if self.mode in ('drag','throw'):
                    self.gate.state='idle';self.land()
                self.save_settings()
            return
        if self.walking and self.stroll and not self.dragging and self.player:
            first,last=self.stroll['frames'];x,y=self.stroll['origin']
            target=self.constrained_position(QPoint(x+round(self.stroll['distance']*stride((self.player.frame_index-first)/max(1,last-first))),y))
            if target!=self.pos():self.move(target);self.position_bubble()
            return
        if self.walking and self.walk_target and not self.dragging:
            tx,ty,bounds=self.walk_target
            self._fx,self._fy,done=motion_step(self._fx,self._fy,tx,ty,55,dt,bounds)
            self.move(round(self._fx),round(self._fy));self.position_bubble()
            if done or now>self.gesture_until:
                self.stop_walk();self.buffer_until=now+ACTION_GAP;self.next_chain=now+ACTIVITY_SECONDS;self.save_settings()
        # Automatic gestures are dispatched in animate(), only after the
        # current clip has ended. This timer only moves the desktop window.

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self._pointer_epoch+=1;self._pointer_pressed=True
        self.throwing=False
        if self.mode=='throw':self.gate.state='idle';self.idle()
        self.press_feedback=time.monotonic();self.drag_samples.clear();self.drag_samples.append((time.monotonic(),self.x(),self.y()))
        super().mousePressEvent(event)
        if event.button()==Qt.MouseButton.LeftButton:
            item=self.manifest.get('dragAnimation')
            if item and item.get('dragStartFrame') is not None and not (
                    self.mode in ('drag','throw') and self._drag_loop_phase in ('enter','held')):
                self.prepare_next(item,item['dragStartFrame'],item['dragHoldFrame'])
            epoch=self._pointer_epoch
            QTimer.singleShot(PRESS_HOLD_MS,self,lambda:self.begin_press_hold(epoch))
        self.schedule_animation()

    def begin_press_hold(self,epoch):
        """A sustained press can lift her without requiring pointer movement."""
        if (epoch!=self._pointer_epoch or not self._pointer_pressed or self.dragging or self.closing
                or not self.isVisible() or self._desktop_hidden):return
        item=self.manifest.get('dragAnimation')
        if not item or item.get('dragHoldFrame') is None:return
        self.stop_walk();self.throwing=False;self.gate.state='idle'
        self.dragging=True;self.click_timer.stop();self.last_click=None;self.generation+=1
        self.bubble_timer.stop();self.bubble.hide()
        self.play(item,'drag');self.gate.state='drag'

    def mouseMoveEvent(self,event):
        if self.settings.get('no_move'):return
        if not self._pointer_pressed and not self.dragging:return
        # User dragging is the highest priority; it can interrupt a task gesture.
        if event.buttons()&Qt.MouseButton.LeftButton and not self.dragging and hasattr(self,'press_pos'):
            if (event.globalPosition().toPoint()-self.press_pos).manhattanLength()>8:self.gate.state='idle'
        super().mouseMoveEvent(event)
        if self.dragging:self.gate.state='drag';self.drag_samples.append((time.monotonic(),self.x(),self.y()))
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        had_press=self._pointer_pressed or self.dragging
        self._pointer_pressed=False;self._pointer_epoch+=1
        if not had_press:return
        if self.dragging:
            self.dragging=False;self.last_click=None;self.click_timer.stop();self.gate.state='idle'
            samples=[s for s in self.drag_samples if time.monotonic()-s[0]<.15]
            vx=vy=0
            if len(samples)>1:
                a,b=samples[0],samples[-1];dt=max(.01,b[0]-a[0]);vx=(b[1]-a[1])/dt;vy=(b[2]-a[2])/dt
            length=math.hypot(vx,vy)
            if self.settings['drag_physics'] and length>120 and not self.settings['no_move']:
                factor=min(1,1800/max(1,length));self.velocity=(vx*factor,vy*factor)
                self._fx,self._fy=float(self.x()),float(self.y());self.throwing=True
                # Carry the already-running drag pose into inertia, without replaying its entrance.
                self.mode='throw';self.gate.state='throw'
                if self.current.get('dragHoldFrame') is not None:self.land()
            else:self.land()
            self.bubble.redraw();self.position_bubble();self.save_settings();return
        item=self.manifest.get('dragAnimation')
        if item and self.upcoming is not None and self.upcoming[0]==self.asset_path(item):self.drop_upcoming()
        self.reveal_card()
        super().mouseReleaseEvent(event)

    def cancel_pointer(self):
        """A lost grab has no release event; finish safely without a click or throw."""
        if not (self._pointer_pressed or self.dragging):return
        self._pointer_pressed=False;self._pointer_epoch+=1;self.dragging=False
        self.drop_upcoming()
        self.drag_samples.clear();self.last_click=None;self.click_timer.stop()
        if self.mode=='drag':
            self.gate.state='idle';self.idle()
        if self.enhanced_ready:self.bubble.redraw();self.position_bubble()

    def cancel_lost_grab(self,epoch):
        if epoch==self._pointer_epoch:self.cancel_pointer()

    @measured('ui_activity')
    def on_activity(self,event):
        if event.get('kind')=='animation_lifecycle':
            self.reactions.confirm(event.get('session',''),event.get('turn',''),event.get('active',False),time.monotonic());return
        if event.get('kind')=='connection_health':
            self.update_connection_health(event.get('capabilities',{}));return
        if event.get('kind')=='conversation_names':
            if self.bubble.roster.update_names(event.get('names',{})):self.bubble.refresh_status()
            return
        if event.get('kind')=='read_receipts':
            if self.bubble.status_indicator.acknowledge_seen(event.get('seen',[])):self.bubble.refresh_status()
            return
        if event.get('kind')=='complete' and not self.bubble.status_indicator.notify_complete(event):return
        if event.get('kind') in ('status','complete'):
            self.bubble.roster.observe(event)
        if event.get('kind')=='codex_presence':
            self.reactions.present=event.get('open');return
        if event.get('kind')=='complete':
            self.reveal_card()
            title=clean_text(event.get('title','Codex 任务'),70)
            self._priority=10
            try:self.say('Codex 任务完成啦！\n'+title,14000)
            finally:self._priority=0
            self.notify('Codex 任务已完成',title);self.refresh_quota()
            self.complete_animation(event)
        else:
            if event.get('kind')=='status':
                self.reactions.observe(event,time.monotonic())
                if self.reactions.completion is None:self.pending_completion=None
            elif event.get('kind')=='monitor_error':
                self.reactions.observe(dict(state='offline',text='监听异常',active=0),time.monotonic())
            super().on_activity(event)
    def complete_animation(self,event):
        if self.reactions.queue_completion(event,time.monotonic()):self.pending_completion=event
    def update_connection_health(self,values):
        self.connection_health.update(values);self.connectionHealthChanged.emit(self.connection_health.snapshot())
    def quota_ready(self,windows):
        super().quota_ready(windows)
        known=any(isinstance(w.get('remaining'),(int,float)) for w in windows)
        self.update_connection_health({'quota':dict(state='available' if known else 'degraded',code='ok' if known else 'quota_unknown' if windows else 'no_windows',success_at=time.time())})
    def quota_failed(self,error):
        super().quota_failed(error)
        from quota import classify_error
        code=getattr(error,'code',None) or classify_error(str(error)).code
        if str(error) in ('服务器暂未提供额度窗口。','当前账户没有可读取的 Codex 额度。'):code='no_windows'
        self.update_connection_health({'quota':dict(state='degraded' if code=='no_windows' else 'unavailable',code=code)})
    def on_reset_feed(self,snapshot,alerts,fresh):
        self._priority=10
        try:super().on_reset_feed(snapshot,alerts,fresh)
        finally:self._priority=0

    def apply_settings(self,values,save=True):
        from quick_actions import website_url
        if values.get('web_button',self.settings.get('web_button'))=='website':
            website_url(values.get('web_url',self.settings.get('web_url','')))
        previous=copy.deepcopy(self.settings)
        if previous.get('character_visible',True) and values.get('character_visible') is False:
            self.remember_card_anchor(self.bubble.content_geometry())
        old_size=self.height();foot=self.geometry().bottom()+1;center=self.geometry().center().x()
        self.settings.update(values);self.settings=normalized(self.settings)
        if (self.settings['no_move'] or
            self.settings['scale']!=previous.get('scale') or self.settings['on_top']!=previous.get('on_top')):
            self.cancel_pointer()
        self.reactions.configure(STATUS_REPEAT,time.monotonic())
        for attr in ('wandering','random_actions','commentary'):setattr(self,attr,self.settings[attr])
        self.bubble.enabled=self.settings['bubble'];self.bubble.show_quota=self.settings['quota_visible']
        self.card_timer.setInterval(round(self.settings['card_hide_delay']*1000))
        self.bubble.token_range=self.settings['token_chart_range']
        self.bubble.pinned=self.settings['on_top'];self.bubble.wandering=self.settings['wandering'];self.bubble.movement_locked=self.settings['no_move']
        size=round(256*self.settings['scale']);self.setFixedSize(size,size)
        if size!=old_size:self.move(self.constrained_position(QPoint(center-size//2,foot-size)))
        # All states use one physical-pixel decode policy. Refresh the current
        # frame immediately rather than changing clarity on the next action.
        self.sync_decode_size()
        if self.settings['no_move'] or not self.wandering:self.stop_walk()
        if self.settings['no_move']:self.throwing=False
        for widget in (self,self.bubble):
            visible=widget.isVisible()
            widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,self.settings['on_top'])
            if visible:widget.show()
        self.sync_panel_flags()
        self.bubble.redraw();self.position_bubble()
        if self._visibility_ready:self.apply_surface_visibility()
        if self.video_yield:self.video_yield.reconcile()
        self.next_chain=time.monotonic()+self.picker.delay(ACTIVITY_SECONDS)
        self.schedule_animation()
        if save:
            try:self.save_settings()
            except (OSError,ValueError):
                self.settings=previous;self.apply_settings({},save=False);raise
        changed={key:copy.deepcopy(value) for key,value in self.settings.items() if previous.get(key)!=value}
        if changed:
            self.settingsChanged.emit(changed)

    def sync_decode_size(self):
        # The current pack is native 512px; Qt scales the final pixmap for HiDPI.
        self.frame_size=min(512,max(128,round(self.height()*(self.screen().devicePixelRatio() if self.screen() else 1))))
        if self.player is not None:
            frame=self.player.resize(self.frame_size)
            if frame is not None:
                self.frames=[frame];self.index=0;self._hit_image=frame.toImage();self.update_frame()
                if self.sustained.active:self.sustained.prewarm(self.player,self.frame_size)

    def pause_hidden_animation(self):
        if not self.isVisible() and self.player:
            self.drop_upcoming();self.planned=None
            self.sustained.cancel();self.player.close();self.continuous.clear();self.gate.state='idle';self._resume_idle=True

    def event(self,event):
        if getattr(self,'enhanced_ready',False):
            if event.type()==QEvent.Type.UngrabMouse:
                # Qt can release its implicit grab just before delivering mouseRelease.
                epoch=self._pointer_epoch
                QTimer.singleShot(0,self,lambda:self.cancel_lost_grab(epoch))
            elif event.type()==QEvent.Type.Hide:
                self.cancel_pointer();QTimer.singleShot(0,self,self.pause_hidden_animation)
            elif event.type()==QEvent.Type.Show and self._resume_idle:
                self._resume_idle=False;self.idle()
        result=super().event(event)
        if event.type()==QEvent.Type.DevicePixelRatioChange and getattr(self,'enhanced_ready',False):
            QTimer.singleShot(0,self.sync_decode_size)
        return result

    def save_settings(self):
        if not self.enhanced_ready:return
        super().save_settings()
        self.settings['facing']=self.walk_direction
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen();a=screen.availableGeometry()
        self.settings['screen_position']=relative_position(self.x(),self.y(),self.width(),self.height(),(a.x(),a.y(),a.width(),a.height()),screen.name())
        atomic_json(CONFIG,self.settings)
    def restore_saved_position(self):
        saved=self.settings.get('screen_position')
        if isinstance(saved,dict):
            screen=next((s for s in QApplication.screens() if s.name()==saved.get('screen')),QApplication.primaryScreen());a=screen.availableGeometry()
            try:x,y=restore_position(saved,self.width(),self.height(),(a.x(),a.y(),a.width(),a.height()));self.move(x,y)
            except (ValueError,TypeError):self.ensure_on_screen()
        self.position_bubble()
    def reset_position(self):
        self.stop_walk();self.throwing=False
        screen=QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen();a=screen.availableGeometry()
        self.move(clamp_position(QPoint(a.right()-self.width()-20,a.bottom()-self.height()-20),self.size(),a));self.position_bubble();self.save_settings()
    def recover(self):
        if self.closing:return
        self._desktop_hidden=False;values={}
        if not self.settings.get('character_visible',True):values['bubble']=True
        self._card_revealed=True;self.card_timer.start()
        self.apply_settings(values);self.apply_surface_visibility();self.bubble.redraw();self.position_bubble()
    def toggle_pet(self):
        self._desktop_hidden=not self._desktop_hidden;self.apply_surface_visibility()
    def card_surface_visible(self):
        if self._desktop_hidden:return False
        if not self.settings.get('character_visible',True):return True
        return self.isVisible() and (self._card_revealed or self.bubble.panel_page!='status')
    def reveal_card(self):
        """Show the status card after a click or an alert; conceal_card retires it."""
        if not self._visibility_ready:return
        self._card_revealed=True;self.card_timer.start()
        if not self.bubble.isVisible():self.apply_surface_visibility()
    def conceal_card(self):
        b=self.bubble
        if not self._card_revealed or not self.settings.get('character_visible',True):return
        busy=(b.panel_page!='status' or b.expanded or (b.report and b.report.requested) or b.size_transition.running
              or b.underMouse() or QApplication.activePopupWidget() is not None)
        if busy:self.card_timer.start();return
        self._card_revealed=False
        if b.isVisible():b.size_transition.dismiss()
    def eventFilter(self,obj,event):
        if obj is self.bubble and self._card_revealed and event.type() in (QEvent.Type.Enter,QEvent.Type.Leave,QEvent.Type.MouseButtonPress):
            self.card_timer.start()
        return super().eventFilter(obj,event)
    def apply_surface_visibility(self):
        if not self._visibility_ready:return
        if self.closing:
            self.hide();self.bubble.hide();return
        character=self.settings.get('character_visible',True) and not self._desktop_hidden
        if character:
            if not self.isVisible():self.show();self.tick.start()
        else:
            self.stop_walk();self.throwing=False;self.cancel_pointer();self.hide();self.tick.stop();self.pause_hidden_animation()
        if not self.card_surface_visible():self.bubble.hide()
        elif self.bubble.enabled or self.bubble.panel_page!='status':
            self.bubble.show();self.position_bubble()
    def remember_card_anchor(self,rect):
        screen=QApplication.screenAt(rect.center()) or QApplication.primaryScreen();a=screen.availableGeometry()
        self._card_anchor=dict(screen=screen.name(),rx=(rect.center().x()-a.left())/max(1,a.width()),bottom=(rect.bottom()+1-a.top())/max(1,a.height()))
        self.settings['card_anchor']=dict(self._card_anchor)
    def card_geometry(self,size):
        anchor=self._card_anchor
        if not isinstance(anchor,dict):
            rect=QRect(self.bubble.pos(),size);self.remember_card_anchor(rect);anchor=self._card_anchor
        screen=next((s for s in QApplication.screens() if s.name()==anchor.get('screen')),QApplication.primaryScreen());a=screen.availableGeometry()
        try:cx=a.left()+a.width()*max(0,min(1,float(anchor.get('rx',.8))));bottom=a.top()+a.height()*max(0,min(1,float(anchor.get('bottom',.8))))
        except (TypeError,ValueError):cx=a.right()-80;bottom=a.bottom()-40
        x=round(cx-size.width()/2);y=round(bottom-size.height())
        reserve=self.bubble.report.reserved_height()+6 if self.bubble.report and self.bubble.report.requested else 0
        x=max(a.left(),min(x,a.right()-size.width()+1));y=max(a.top()+min(reserve,max(0,a.height()-size.height())),min(y,a.bottom()-size.height()+1))
        return QRect(x,y,size.width(),size.height())
    def move_card(self,point):
        rect=QRect(point,self.bubble.size());self.remember_card_anchor(rect);self.bubble.move(self.card_geometry(rect.size()).topLeft());self.remember_card_anchor(self.bubble.geometry())
    def position_bubble(self):
        if self.enhanced_ready and (self.bubble.size_transition.running or self.bubble.size_transition.preparing or self.bubble.size_transition.landing.image is not None):return
        if self.enhanced_ready and not self.settings.get('character_visible',True):
            self.bubble.move(self.card_geometry(self.bubble.content.size()).topLeft())
            if self._desktop_hidden:self.bubble.hide()
            return
        if self.enhanced_ready and self.bubble.panel_page!='status' and self.bubble._editor_positioned:
            if not self.card_surface_visible():self.bubble.hide()
            return
        super().position_bubble()
        if self.enhanced_ready and self.bubble.panel_page!='status':self.bubble._editor_positioned=True
        if self.enhanced_ready and not self.card_surface_visible():self.bubble.hide()
    def can_raise_bubble(self):
        if self._video_yielded:return False
        # Owned panels stay above the pet. Periodic bubble updates must not
        # reorder its sibling windows over an open settings panel.
        if QApplication.activePopupWidget() is not None or self.bubble.panel_page!='status':return False
        panel=self.settings_dialog
        return not (panel and panel.isVisible() and not panel.isMinimized())
    def sync_panel_flags(self):
        self.bubble._editing_flags(self.bubble.panel_page!='status')
        panel=self.settings_dialog
        if panel is not None and panel.isWindow():
            target=self.settings['on_top']
            if bool(panel.windowFlags()&Qt.WindowType.WindowStaysOnTopHint)!=target:
                visible=panel.isVisible();state=panel.windowState();active=panel.isActiveWindow()
                panel.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,target)
                if visible:
                    panel.setWindowState(state);panel.show()
                    if active:panel.raise_();panel.activateWindow()
    def show_panel(self,panel):
        if not panel.isWindow():
            self.stop_walk();self.throwing=False;self._desktop_hidden=False;self._card_revealed=True;self.card_timer.start();self.apply_surface_visibility()
            # First activation can synchronously polish the native editor and
            # take a full frame. Do it before the snapshot animation starts so
            # the visible morph has an uninterrupted clock.
            self.bubble.raise_();self.bubble.activateWindow()
            if self.bubble.windowHandle():self.bubble.windowHandle().requestActivate()
            QApplication.setActiveWindow(self.bubble)
            self.bubble.show_page('settings',panel);panel.tabs.tabBar().setFocus()
            return
        self.sync_panel_flags();panel.showNormal();panel.raise_();panel.activateWindow()
    def set_option(self,attr,value):
        try:self.apply_settings({attr:value})
        except (OSError,ValueError) as error:
            message='设置保存失败，已恢复原值：'+str(error)
            if self.settings_dialog:self.settings_dialog.status.setText(message)
            previous=self._priority;self._priority=10
            try:self.say(message,6500)
            finally:self._priority=previous
    def toggle_bubble(self):self.set_option('bubble',not self.bubble.enabled)
    def toggle_quota(self,value):self.set_option('quota_visible',value)
    def quota(self):
        self.refresh_quota()

    def action_groups(self):
        # Walks only happen while she wanders, so they are not manual actions.
        groups={'待机':self.idles+self.manifest.get('additionalIdleAnimations',[]),'转向':self.manifest.get('turnAnimations',[]),
            '点击回应':self.manifest.get('clickAnimations') or [v for v in self.variants if v['id'] in ('01','08','09','10','11')],
            '互动动作':self.variants,'工作动作':[v for v in self.manifest.get('workAnimations',[]) if v], '额度回应（不刷新数据）':[self.manifest['quotaAnimation']] if self.manifest.get('quotaAnimation') else [],
            '拖拽':[self.manifest['dragAnimation']] if self.manifest.get('dragAnimation') else [],
            '落地':[self.manifest['landingAnimation']] if self.manifest.get('landingAnimation') else []}
        if self.manifest.get('manualMovementActions'):groups['Movement']=self.manifest.get('moveAnimations',[])
        return {group:items for group,items in groups.items() if items}
    def role_actions(self):
        # Shared interactions can occur in several semantic groups; the menu
        # exposes each physical animation once, in a single vertical list.
        return unique_actions([item for group in self.action_groups().values() for item in group])
    def populate_tray(self):self.build_menu(self.tray_menu,tray=True)
    def execute_command(self,command,checked=False):
        toggles={'character':'character_visible','pin':'on_top','lock':'no_move','bubble':'bubble'}
        if command in toggles:self.set_option(toggles[command],checked);return
        commands={'status':self.open_status,'settings':self.open_settings,
            'visible':self.toggle_pet,'recover':self.recover,'position':self.reset_position,
            'walk':lambda:self.set_option('wandering',not self.settings['wandering']),'quit':self.close}
        commands[command]()
    def menu_command(self,menu,command):
        labels={'status':'查看状态','settings':'桌宠设置…',
            'visible':'显示桌面组件' if self._desktop_hidden else '隐藏全部组件','recover':'找回全部组件','character':'显示人物',
            'position':'回到当前屏幕右下角','pin':'始终置顶','lock':'锁定人物位置（含拖动）',
            'bubble':'显示气泡','quit':'退出ChatGpt',
            'walk':('自主走动（位置已锁定）' if self.settings['no_move'] else '暂停自主走动' if self.settings['wandering'] else '恢复自主走动')}
        action=menu.addAction(labels[command]);action.setObjectName('command_'+command)
        key={'character':'character_visible','pin':'on_top','lock':'no_move','bubble':'bubble'}.get(command)
        if key:action.setCheckable(True);action.setChecked(self.settings[key])
        if command=='walk':action.setEnabled(not self.settings['no_move'])
        action.triggered.connect(lambda value=False,c=command:QTimer.singleShot(0,self,lambda:self.execute_command(c,value)))
        return action
    def build_menu(self,menu,tray=False):
        populate_shared_menu(menu,self.menu_command,
            lambda actions:populate_action_menu(actions,self.role_actions(),lambda item:self.choose(item,interactive=True,manual=True)),
            tray=tray)
    def context_menu(self,point):
        self.stop_walk();menu=QMenu(self);self.build_menu(menu);menu.exec(point)

    def open_settings(self):
        if not self.settings_dialog:
            from desktop_settings import SettingsDialog
            self.settings_dialog=SettingsDialog(self,embedded=True)
        self.settings_dialog.sync_from_pet(read_startup=True)
        self.show_panel(self.settings_dialog)
    def open_status(self):
        self._desktop_hidden=False
        if not self.bubble.enabled:self.set_option('bubble',True)
        self._card_revealed=True;self.card_timer.start()
        self.apply_surface_visibility()
        self.bubble.collapse_to_normal()
    def open_web(self):
        from quick_actions import target_url
        try:
            if not QDesktopServices.openUrl(QUrl(target_url(self.settings))):raise OSError('未能打开默认浏览器，请检查系统的浏览器设置。')
        except (ValueError,OSError) as error:self.say(str(error),6000)
    def open_assistant(self):
        try:self.codex_navigation.open()
        except OSError as error:self.say(str(error),6000)
    def open_conversation(self,session):
        self.recently_visited=getattr(self,'recently_visited',{});self.recently_visited[session]=time.monotonic()
        try:self.codex_navigation.open(session)
        except OSError as error:self.say(str(error),6000)
    def character_choices(self):
        choices=[('builtin','ChatGpt · 内置')]
        for folder in sorted(self.character_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith('import-'):continue
            try:
                m=json.loads(manifest_path(folder).read_text(encoding='utf-8-sig'));choices.append((folder.name,m.get('character',folder.name)))
            except (ValueError,OSError):pass
        return choices
    def switch_character(self,key):
        if not key:return
        if key=='builtin':root=self.material_store.root
        else:
            root=(self.character_dir/key).resolve()
            if root.parent!=self.character_dir.resolve():raise ValueError('角色目录无效')
        # Import performs full decoding. Switching checks structure and first frame only.
        m=json.loads(manifest_path(root).read_text(encoding='utf-8-sig'))
        if not isinstance(m,dict) or not isinstance(m.get('idle'),dict) or not isinstance(m.get('variants',[]),list):raise ValueError('角色清单结构无效')
        for item in all_items(m)+seam_items(m):
            path=(root/(item.get('playbackFile') or item['file'])).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():raise ValueError('角色包缺少素材或路径无效')
        old=(self.asset_root,self.manifest,self.idles,self.variants,self.settings.get('character','builtin'))
        preference_keys=('scale',)
        self.settings['character_preferences'][old[4]]={k:copy.deepcopy(self.settings[k]) for k in preference_keys}
        self.stop_walk();self.throwing=False;self.gate.state='idle'
        self.sustained.cancel();self.continuous.clear()
        try:
            self.asset_root=root;self.manifest=m;self.idles=[m['idle']];self.variants=m.get('variants',[])
            self.reactions.set_actions(item['id'] for item in all_items(m))
            self.idle()
        except Exception:
            self.asset_root,self.manifest,self.idles,self.variants,_=old
            self.reactions.set_actions(item['id'] for item in all_items(self.manifest))
            self.gate.state='idle';self.idle();raise
        self.settings['character']=key
        self.apply_settings(self.settings['character_preferences'].get(key,{}))
        if self.bubble.report:self.bubble.report.animation.stop();self.bubble.report.hide()

    def record_state(self):
        path=STATE_DIR/'runtime.json';value=super().runtime_state()
        from decode_runtime import STATS
        value.update(shared_body_tail_decode=True,nonblocking_decoder_cancel=True,adaptive_animation_clock=True,high_resolution_frame_clock=True,frame_clock_resolution=time.get_clock_info('perf_counter').resolution,idle_movement_timer_ms=1000,
            decode_runtime=STATS.snapshot(),animation_wakeups=self.animation_wakeups,movement_wakeups=self.movement_wakeups,decode_error=self.decode_error)
        value.update(material_tiers=False,material_default='light',material_current=self.material_store.current,
            material_resolution=720 if self.material_store.current=='hd' else 512,material_hd_cached=self.material_store.available('hd'),
            material_content_id=self.material_store.catalog['tiers'][self.material_store.current]['id'] if self.material_store.catalog else None,
            material_switch_pending=False)
        value.update(native_client_hit_testing=True,shared_paint_hit_transform=True,lost_mouse_grab_recovery=True,character_switch_keeps_navigation=True,
            independent_card_surface=True,character_visible=self.settings['character_visible'],card_click_reveal=True,hidden_character_decoder_paused=not self.settings['character_visible'] and not self.tick.isActive(),
            isolated_transition_preparation=True,cleared_native_landing=True,linked_report_motion=True,
            continuous_state_playback=True,sustained_animation_phase=self.sustained.phase,sustained_animation_cycles=self.sustained.cycles,
            natural_sustained_variants=True,isolated_report_presentation=True,sustained_animation_variant=self.sustained.variant_index,
            sustained_supported_actions=[i['id'] for i in self.manifest.get('workAnimations',[]) if i.get('sustained')],status_stability_seconds=self.continuous.stable_seconds,
            asset_count=len(all_items(self.manifest)),work_animation_count=len([v for v in self.manifest.get('workAnimations',[]) if v]),
            semantic_work_actions=True,explicit_task_arrival_animation=True,current_animation=self.current.get('id') if self.current else None,
            sustained_work_response=True,status_action_interval=self.reactions.interval,animation_lifecycle_leases=len(self.reactions.leases),
            smoothed_token_curves=True,conversation_hover_contrast=True,asynchronous_codex_navigation=True,
            last_reaction_kind=self.last_reaction.kind if self.last_reaction else None,
            pending_task_greetings=len(self.reactions.openings),animation_decoder_queue=self.player.frames.qsize() if self.player else 0)
        import psutil
        process=psutil.Process();mem=process.memory_info()
        snapshot=self.bubble.token_snapshot or {}
        idle_cache=self.player.loop_cache.stats() if self.player else dict(bytes=0,hits=0,limit=24*1048576)
        from typography import LATIN_FAMILY,register_font
        report=self.bubble.report
        report_data=snapshot.get('report') or {}
        value.update(reset_countdown_format='hours_minutes',read_terminal_turn_acknowledgement=True,reset_countdown_priority=True,codex_startup_supported=True,hourly_token_entry='today_tokens',unified_refresh=True,icon_only_header_actions=True,refresh_icon_style='single_arc',icon_motion_speed=1.2,busy_icon_style='orbit_rings',status_icon_morph=True,status_waiting_live_flags=True,native_shrink_landing=True,shrink_preserves_chart_progress=True,native_landing_hold_ms=34,cached_chart_layers=True,stable_report_scrollbar=True,animated_deck_tabs=True,incremental_deck_switch=True,prewarmed_transition_landing=True,monotone_container_motion=True,status_updates_preserve_surface=True,atomic_transition_handoff=True,clean_report_dismiss=True,unified_card_motion=True,report_continuous_shape=True,week_quota_palette=True,continuous_surface_morph=True,shared_status_glyph=True,panel_shrink_spring=True,panel_dismiss_spring=True,panel_shrink_ms=440,panel_dismiss_ms=360,lossless_asset_pack=True,lossless_asset_encoding=True,lightweight_resampling=self.material_store.current=='light',optional_webm_converter=True,fair_activity_targets=True,persistent_completion_ledger=True,cached_log_discovery=True,semantic_controls=True,labeled_header_actions=False,editor_keyboard_save=True,capability_health=True,connection_path_picker=True,report_scope_groups=True,report_model_filter_explicit=True,settings_draft_merge=True,settings_dirty_fields_only=True,context_menu_root_items=7,tray_recovery_menu=True,editor_returns_to_origin=True,quota_query_silent=True,subagent_completion_filter=True,ring_persistent_legend=False,quota_display_layout='labeled_bars',quota_reset_per_window=True,today_tokens_direct_value=True,conversation_name_pointer_feedback=True,context_compaction_tracking=True,conversation_name_navigation=True,codex_live_status_connected=bool(self.activity and self.activity.live_reader and self.activity.live_reader.connected),daily_report_incremental_updates=True,daily_report_chart_start_after_show=True,quota_source_header_visible=False,incremental_status_refresh=True,skip_unchanged_log_reads=True,single_runtime_write=True,read_acknowledgement_history=True,read_acknowledgement_settle_seconds=4,conversation_names_visible=True,completed_conversation_background=True,independent_conversation_scroll=True,operation_status_summary=True,session_read_tracking=True,conversation_status_limit=2,codex_connection_diagnostics=True,portable_codex_discovery=True,panel_transition_stable_canvas=True,panel_transition_content_blend=True,chart_entry_animation=True,daily_report=False,daily_report_stable_surface=True,token_scan_background=True,token_models=len({r['model'] for r in report_data.get('daily_models',[])}),token_report_hours=len(report_data.get('hours',[])),daily_report_visible=bool(report and report.isVisible()),daily_report_aligned=not report or not report.isVisible() or (report.content_geometry().width()==self.bubble.width() and report.content_geometry().x()==self.bubble.x() and report.content_geometry().bottom()+1==self.bubble.y()-6),ring_center_y=None,daily_report_open=bool(self.bubble.report and self.bubble.report.requested),inline_explanations_only=True,status_icon_animated=True,status_icon_unread=len(self.bubble.status_indicator.unread),status_icon_acknowledgement=True,status_icon_state=self.bubble.status_indicator.visual(),status_icon_timer=self.bubble.status_indicator.timer.isActive(),panel_transition_no_fade=True,panel_transition_staged_layout=True,panel_transition_ms=480,idle_cache_mb=round(idle_cache['bytes']/1048576,2),idle_cache_limit_mb=idle_cache['limit']/1048576,idle_cache_hits=idle_cache['hits'],integrated_panels=True,panel_page=self.bubble.panel_page,separate_panel_windows=sum(bool(p and p.isWindow()) for p in (self.settings_dialog,)),expanded_details_grouped=True,latin_font=LATIN_FAMILY,latin_font_loaded=register_font(),status_height_transition_ms=300,status_transition_synchronized=True,token_chart_range=self.bubble.token_range,
            token_history_days=len(snapshot.get('history_days',{})),token_hour_slots=len(snapshot.get('hours',[])),
            mode=self.mode,action_state=self.gate.state,scale=self.settings['scale'],
            facing=self.walk_direction,decoder_queue=self.player.frames.qsize() if self.player else 0,first_frame_cache=len(self.player.first) if self.player else 0,
            decode_size=self.frame_size,source_frame=self.player.frame_index if self.player else 0,quality_revision=self.manifest.get('qualityRevision',0),
            status_reactions=self.settings['status_actions'],reaction_samples=self.reactions.sample_count,
            reaction_kind=self.last_reaction.kind if self.last_reaction else None,reaction_action=self.last_reaction.action_id if self.last_reaction else None,
            completion_animation_pending=self.reactions.completion is not None,
            rss_mb=round(mem.rss/1048576,1),uptime=round(time.monotonic()-self.created_at,1),throwing=self.throwing)
        if self.connection_health.records['quota']['state']=='available' and any(w.get('resetsAt') and w['resetsAt']<=time.time() for w in self.quota_windows):
            self.connection_health.record('quota',dict(state='degraded',code='quota_expired'))
        value['video_fullscreen_yield_enabled']=self.settings['video_fullscreen_yield']
        value['video_fullscreen_yielding']=self._video_yielded
        value['video_detector_running']=bool(self.video_yield and self.video_yield.worker and self.video_yield.worker.is_alive())
        value['video_detection_reason']=self.video_yield.reason if self.video_yield else 'disabled'
        value['video_detection_sample']=self.video_yield.last_sample if self.video_yield else {}
        value['video_native_yield_applied']=bool(self.video_yield and self.video_yield.native_applied)
        value['video_completion_priority']=True
        value['video_firefox_backend']='ia2_video_tag'
        value['video_completion_override']=bool(self.video_yield and self.video_yield.attention_override)
        value['connection_health']=self.connection_health.snapshot()
        from performance_metrics import METRICS
        if METRICS.enabled:value['performance']=METRICS.snapshot()
        if self.activity:
            self.recently_visited={sid:t for sid,t in getattr(self,'recently_visited',{}).items() if time.monotonic()-t<120}
            self.activity.set_context(self.bubble.roster.pinned,self.recently_visited)
        if self.settings_dialog and self.settings_dialog.isVisible():self.connectionHealthChanged.emit(value['connection_health'])
        atomic_json(path,value)
    def closeEvent(self,event):
        # Withdraw every surface immediately, even while workers finish.
        # Settings no longer owns the removed connection/path jobs.
        self.begin_shutdown()
        self.card_timer.stop();self.click_timer.stop();self.bubble_timer.stop();self.drop_release();self.drop_upcoming()
        self.hide();self.bubble.hide()
        if self.settings_dialog:
            dialog=self.settings_dialog
            dialog.hide()
            from worker_lifecycle import workers_finished
            jobs=tuple(getattr(dialog,key,None) for key in ('connection_job','job'))
            for job in jobs:
                cancel=getattr(job,'cancel',None)
                if cancel is not None:cancel.set()
            if not workers_finished(self,jobs):
                event.ignore();return
        self.cancel_pointer();self.sustained.cancel();self.codex_navigation.close()
        if self.bubble.report:self.bubble.report.animation.stop();self.bubble.report.hide()
        if self.settings_dialog:self.settings_dialog.hide()
        if self.player:self.player.close()
        if self.video_yield:self.video_yield.shutdown()
        super().closeEvent(event)
