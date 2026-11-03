"""Gemini-only complete-action drag playback, using her own prepared MP4 pack."""
import time
from PySide6.QtCore import QEvent, QTimer, Qt
from share.desktop.sprite_window import SpriteWindow
from share.pet_engine.stream_player import PreparedSegment


class GeminiMotionSprite(SpriteWindow):
    def __init__(self,pack,size=300):
        super().__init__(pack,size)
        self.player.loop_cache.limit=160*2**20
        self.player.loop_cache.entry_limit=128*2**20
        self._pickup=None
        self._pointer_epoch=0

    def drop_pickup(self):
        if self._pickup is not None:self._pickup.close();self._pickup=None

    def mousePressEvent(self,event):
        super().mousePressEvent(event)
        if event.button()!=Qt.MouseButton.LeftButton:return
        self._pointer_epoch+=1
        key=self.pack.data.get('drag')
        item=self.pack.actions.get(key,{})
        if (not self.locked and item.get('dragHoldFrame') is not None
                and not (self.action==key and self.lift in ('lift','held'))):
            self.drop_pickup()
            self._pickup=PreparedSegment(self.pack.path(item),self.decode_size,
                                         item['dragStartFrame'],item['dragHoldFrame'])

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        if event.button()==Qt.MouseButton.LeftButton:
            self._pointer_epoch+=1
            self.drop_pickup()

    def play_range(self,key,start,end,prepared=None,blend=True):
        """Start an exact source range without changing shared sprite behaviour."""
        if prepared is not None:
            self.lift=None;self.landing_due=False
            return super().play(key,blend=blend,prepared=prepared,seconds=self.PICKUP_SECONDS)
        item=self.pack.actions[key]
        if self.upcoming is not None:self.upcoming[1].close();self.upcoming=None
        self.end_takeover()
        fade=blend and self.frame is not None and self.isVisible()
        old=self.player
        if fade:self.player=self.spare_player();self._spare=None
        try:
            frame=self.player.start(self.pack.path(item),self.decode_size,item['durationMs']/1000,
                                    start_frame=start,end_frame=end)
        except (OSError,ValueError) as error:
            if fade:self._spare,self.player=self.player,old
            self.playbackFailed.emit(str(error));return False
        self.serial+=1;self.lift=None;self.landing_due=False
        if fade:
            self.outgoing,self.outgoing_frame=old,self.frame
            self.takeover_started=time.perf_counter();self.takeover_seconds=self.PICKUP_SECONDS
        self.action=key;self.frame=frame;self.update();self.schedule()
        return True

    def start_drag(self,key):
        item=self.pack.actions[key]
        if item.get('dragHoldFrame') is None:return super().start_drag(key)
        if self.action==key and self.lift in ('lift','held'):
            self.landing_due=False;self.schedule();return True
        self.drop_release()
        self.release_tail=PreparedSegment(self.pack.path(item),self.decode_size,item['releaseFrame'],item['frames']-1)
        pickup,self._pickup=self._pickup,None
        ready=(pickup is not None and pickup.ready.is_set() and not pickup.error
               and pickup.size==self.decode_size and pickup.start==item['dragStartFrame']
               and pickup.end==item['dragHoldFrame'])
        if pickup is not None and not ready:pickup.close()
        started=self.play_range(key,item['dragStartFrame'],item['dragHoldFrame'],pickup if ready else None)
        if started:self.lift='lift'
        return started

    def release_drag(self,key,blend=True):
        item=self.pack.actions[key]
        if item.get('dragHoldFrame') is None:return super().release_drag(key,blend)
        if self.lift=='lift' and self.action==key and not self.player.ended:
            self.landing_due=True;return True
        if self.lift is None and self.action==key and self.player.range_start==item['releaseFrame']:
            return True
        tail,self.release_tail=self.release_tail,None
        ready=tail is not None and tail.ready.is_set() and not tail.error and tail.size==self.decode_size
        if tail is not None and not ready:tail.close()
        return self.play_range(key,item['releaseFrame'],item['frames']-1,tail if ready else None,blend)

    def schedule(self):
        if self.lift=='held' and self.dragging and self.pack.actions.get(self.action,{}).get('dragHoldFrame') is not None:return
        super().schedule()

    def animate(self):
        item=self.pack.actions.get(self.action,{})
        if item.get('dragHoldFrame') is None or self.lift not in ('lift','held'):
            return super().animate()
        if self._closing or not self.isVisible():return
        if self.lift=='held':
            if not self.dragging:self.release_drag(self.action,False)
            return
        if self.outgoing is not None:
            if time.perf_counter()-self.takeover_started>=self.takeover_seconds:self.end_takeover()
            else:
                frame,_=self.outgoing.advance(self.decode_size,self.speed)
                if frame is not None:self.outgoing_frame=frame
        frame,ended=self.player.advance(self.decode_size,self.speed)
        if frame is not None:self.frame=frame
        self.update()
        if ended:
            self.end_takeover()
            if self.player.error:
                self.playbackFailed.emit(self.player.error);self.lift=None
                self.playbackFinished.emit(self.action)
            elif self.landing_due or not self.dragging:
                self.landing_due=False;self.release_drag(self.action,False)
            else:self.lift='held'
            return
        self.schedule()

    def cancel_lost_pointer(self,epoch):
        if epoch!=self._pointer_epoch or self.press_global is None:return
        was_dragging=self.dragging
        self.press_global=None;self.dragging=False;self._pointer_epoch+=1
        self.click_timer.stop();self.drop_pickup()
        if was_dragging:self.dragFinished.emit();self.schedule()

    def event(self,event):
        if event.type()==QEvent.Type.UngrabMouse and hasattr(self,'_pointer_epoch'):
            epoch=self._pointer_epoch
            QTimer.singleShot(0,self,lambda:self.cancel_lost_pointer(epoch))
        return super().event(event)

    def hideEvent(self,event):
        self._pointer_epoch+=1;self.press_global=None;self.dragging=False
        self.drop_pickup();self.lift=None;self.landing_due=False
        super().hideEvent(event)

    def closeEvent(self,event):
        self.drop_pickup()
        super().closeEvent(event)
