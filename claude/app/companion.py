"""Claude's paper card, character actions and local usage readers."""
from share.desktop.companion_app import CompanionApp
from model import SCHEMA, CLICK_WEIGHTS, DOUBLE_WEIGHTS, WALK_WEIGHT, action_weight
from messages import MESSAGES


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


