"""Gemini's own touches on the shared companion: the starlit card with cat ears,
ear petting and a little hop after being carried."""
import time
from PySide6.QtCore import QTimer
from share.desktop import desktop_integration as integration
from gemini_windowing import native_windows, ordinary_workspace, capture_overlay
from share.desktop.companion_app import CompanionApp
from model import SCHEMA, CLICK_WEIGHTS, DOUBLE_WEIGHTS, WALK_WEIGHT, action_weight
from sprite import GeminiSprite

LINES = {
    'idle': '星星到位，今天也陪着你。',
    'greeting': '嗨，今天想先做哪件小事？',
    'curious': '欸？让我也看看嘛。',
    'meow': '喵，收到你的呼唤啦。',
    'stretch': '伸个懒腰，再慢慢出发。',
    'pout': '哼……好啦，再陪你一会儿。',
    'glance': '刚好看见你，也刚好有一点开心。',
    'hop': '把一点轻快，跳进今天。',
    'chase': '尾巴怎么总是快我一步？',
    'pounce': '接住这一只小猫！',
    'catch': '接住了！这一颗星送给你。',
    'lift': '被你拎起来啦，耳朵也跟着晃一晃喵。',
    'drag': '晃来晃去的，尾巴都甩乱了喵。',
    'walk-left': '尾巴，等等我喵！',
    'walk-right': '扑——到这边来啦喵。',
    'back_to_idle': '当前动作收尾后，回到星光待机。',
    'already': '正在做这个动作喵。',
    'ear': '收到你的呼唤啦，喵～',
    'quota_refreshed': 'Antigravity 的额度刷新啦，星星又满格了喵！',
    'quota_high': '{label}只剩 {left}% 了喵，省着点用～',
}


class Companion(CompanionApp):
    CHARACTER = 'gemini'
    NAME = 'Gemini'
    TITLE = 'Gemini 娘 · 星光陪伴'
    APP_NAME = 'GeminiDesktopPet'
    INSTANCE = 'gemini-constellation-local'
    WEB_URL = 'https://gemini.google.com/'
    WEB_TITLE = '打开 Gemini 网页'
    SCHEMA = SCHEMA
    DEFAULT_SIDE = 'right'
    LINES = LINES
    QUOTA_CELEBRATE = 'hop'
    QUOTA_WORRY = 'pout'
    CLICK_WEIGHTS = CLICK_WEIGHTS
    DOUBLE_WEIGHTS = DOUBLE_WEIGHTS
    WALK_WEIGHT = WALK_WEIGHT

    def make_token_source(self):
        from antigravity_tokens import AntigravityTokens
        return AntigravityTokens()

    def __init__(self, *args, **kwargs):
        self._last_ear = 0.
        self._last_foreground=0
        self._capture_active=False
        super().__init__(*args, **kwargs)
        QTimer.singleShot(0,self.ensure_native_front)
        QTimer.singleShot(180,self.ensure_native_front)

    def ensure_native_front(self,force=True):
        if self.closing or self.yielded:return
        api=native_windows()
        if api is None:return
        foreground=api.foreground()
        if capture_overlay(api.info(foreground)):
            capture=integration.fullscreen_foreground()
            if capture and capture[0]==foreground:return
        windows=[w for w in [self.sprite]+([self._card] if self._card is not None else []) if w.isVisible()]
        owned={int(w.winId()) for w in windows}
        for window in windows:
            hwnd=int(window.winId())
            repair=self.settings['on_top'] and foreground not in owned and not api.above(hwnd,foreground)
            api.set_topmost(hwnd,self.settings['on_top'],force or repair)

    def apply_options(self):
        super().apply_options()
        self.ensure_native_front()

    def show_panel(self,page=None):
        result=super().show_panel(page)
        self.ensure_native_front()
        return result

    def recover(self):
        super().recover()
        self.ensure_native_front()
        QTimer.singleShot(100,self.ensure_native_front)

    def check_fullscreen(self):
        if self.closing:return
        api=native_windows()
        foreground=api.foreground() if api is not None else 0
        changed=foreground!=self._last_foreground
        self._last_foreground=foreground
        is_capture=api is not None and capture_overlay(api.info(foreground))
        candidate=integration.fullscreen_foreground() if self.settings['fullscreen_yield'] or is_capture else None
        if is_capture and candidate and candidate[0]==foreground:
            self._capture_active=True
            return
        capture_ended=self._capture_active
        self._capture_active=False
        found=candidate if self.settings['fullscreen_yield'] else None
        if found and api is not None and ordinary_workspace(api.info(found[0])):found=None
        if found is None:
            self.yield_override=None
            if self.yielded:self.end_yield()
            if self.settings['on_top']:self.ensure_native_front(force=changed or capture_ended)
            return
        hwnd,monitor=found
        covering=monitor==integration.monitor_of(int(self.sprite.winId()))
        if covering and hwnd!=self.yield_override and not self.yielded:
            self.yielded=True;self.sprite.hide()
            if self._card is not None:self._card.hide()
            self.on_yield()
        elif self.yielded and (not covering or hwnd==self.yield_override):
            self.end_yield();self.ensure_native_front()

    def make_sprite(self):
        sprite = GeminiSprite(self.pack, self.settings['size'])
        sprite.sparkles = self.settings['sparkles']
        return sprite

    def create_card(self):
        from card import CompanionCard
        return CompanionCard(self.pack.actions, self.settings)

    def make_quota_reader(self):
        from antigravity_link import AntigravityQuotaReader
        return AntigravityQuotaReader()

    def action_weight(self, key, hour):
        return action_weight(key, hour)

    def connect_card(self, card):
        card.earPetted.connect(self.ear_petted)

    def on_option(self, key, value):
        if key == 'sparkles':
            self.sprite.sparkles = value
            self.sprite.update()

    def ear_petted(self):
        if not self.settings['ear_meow']:
            return
        now = time.monotonic()
        if now-self._last_ear < 1.2:
            return
        self._last_ear = now
        if self.play('meow'):
            self.say(self.lines['ear'])

    def after_drag(self):
        if self.settings['hop_after_drag']:
            self.play('hop', automatic=True)

    def drag_finished(self):
        drag=self.pack.data.get('drag')
        if self.director.current==drag and self.pack.actions.get(drag,{}).get('dragHoldFrame') is not None:
            release=self.drag_release_action()
            if release in self.pack.actions and not self.director.pending and not self.director.queued:
                self.director.queued=release
            self.save_timer.start()
            self.sprite.release_drag(drag)
            self.show_action(drag,self.director.pending or self.director.queued)
            return
        if (self.director.current==drag and self.pack.actions.get(drag,{}).get('dragLoopFile')
                and self.settings['hop_after_drag'] and not self.director.pending and not self.director.queued):
            self.director.queued='hop'
        super().drag_finished()

    def drag_release_action(self):
        return 'hop' if self.settings['hop_after_drag'] else None


