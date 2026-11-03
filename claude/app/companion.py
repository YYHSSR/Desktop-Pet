"""Claude's paper card, character actions and local usage readers."""
from share.desktop.companion_app import CompanionApp
from model import SCHEMA, CLICK_WEIGHTS, DOUBLE_WEIGHTS, WALK_WEIGHT, action_weight
from messages import MESSAGES
from PySide6.QtCore import QTimer
from share.desktop import desktop_integration as integration
from claude_windowing import native_windows, ordinary_workspace, capture_overlay


class Companion(CompanionApp):
    CHARACTER = 'claude'
    NAME = 'Claude'
    TITLE = 'Claude 娘 · 书页陪伴'
    APP_NAME = 'ClaudeDesktopPet'
    INSTANCE = 'claude-reading-local'
    WEB_URL = 'https://claude.ai/'
    WEB_TITLE = '打开 Claude 网页'
    SCHEMA = SCHEMA
    DEFAULT_SIDE = 'left'
    LINES = MESSAGES
    QUOTA_CELEBRATE = 'sparkles'
    QUOTA_WORRY = 'peek'
    CLICK_WEIGHTS = CLICK_WEIGHTS
    DOUBLE_WEIGHTS = DOUBLE_WEIGHTS
    WALK_WEIGHT = WALK_WEIGHT

    def __init__(self,*args,**kwargs):
        self._last_foreground=0
        self._capture_active=False
        super().__init__(*args,**kwargs)
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
        from claude_sprite import ClaudeSprite
        return ClaudeSprite(self.pack,self.settings['size'])

    def drag_finished(self):
        key=self.pack.data.get('drag')
        if self.director.current==key and self.pack.actions[key].get('dragHoldFrame') is not None:
            self.save_timer.start()
            self.sprite.release_drag(key)
            self.show_action(key,self.director.pending or self.director.queued)
            return
        return super().drag_finished()

    def make_token_source(self):
        from claude_tokens import ClaudeCodeTokens
        return ClaudeCodeTokens()

    def create_card(self):
        from card import CompanionCard
        return CompanionCard(self.pack.actions, self.settings)

    def make_quota_reader(self):
        from claude_link import ClaudeUsageReader
        return ClaudeUsageReader()

    def action_weight(self, key, hour):
        return action_weight(key, hour)


