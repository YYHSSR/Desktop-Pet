"""Gemini's own touches on the shared companion: the starlit card with cat ears,
ear petting and a little hop after being carried."""
import time
from share.desktop.companion_app import CompanionApp
from model import SCHEMA, action_weight
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

    def make_token_source(self):
        from antigravity_tokens import AntigravityTokens
        return AntigravityTokens()

    def __init__(self, *args, **kwargs):
        self._last_ear = 0.
        super().__init__(*args, **kwargs)


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
        if (self.director.current==drag and self.pack.actions.get(drag,{}).get('dragLoopFile')
                and self.settings['hop_after_drag'] and not self.director.pending and not self.director.queued):
            self.director.queued='hop'
        super().drag_finished()

    def drag_release_action(self):
        return 'hop' if self.settings['hop_after_drag'] else None


