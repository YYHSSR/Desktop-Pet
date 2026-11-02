"""Gemini: Gpt-style dashboard and editor, with character-specific pages."""
from share.desktop.card_surface import CompanionCardSurface, Dashboard, Theme

from datetime import datetime
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QColor, QPen, QPainterPath, QLinearGradient
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QGridLayout, QWidget, QScrollArea
from share.desktop.card_kit import CurrentPageStack, Palette, QuotaPanel, SettingsPanel, button, label
from share.desktop.token_widgets import TodayTokens
from model import SCHEMA, normalized, time_greeting

# Blue-violet starlight palette (Gpt keeps its plum porcelain).
SURFACE = '#fbfaff'
BORDER = '#cfc8f3'
INNER_EAR = '#e6defc'
STAR_BLUE = QColor('#6f86e8')
STAR_VIOLET = QColor('#a173d8')
STAR_IDLE = QColor('#cdc6ea')


STARLIGHT = 'qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6f86e8, stop:1 #a173d8)'
THEME = Theme(surface=SURFACE, border='#d6d0f5', ink='#33385a', muted='#737597', stat='#4f5596',
              primary='#6d6fd8', primary_fill=STARLIGHT,
              primary_hover='qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #5d74d8, stop:1 #8f60c9)',
              hover='#eeecfc', soft='#e6e3fb', focus='#9a90e6', tile='#f1f0fd', card=SURFACE,
              card_border='#e3dffa', footer='#eceafb', nav='#efedfc', track='#e4e2f5', chunk=STARLIGHT,
              scroll='#c9c3ee', selection='#d9d4fa', disabled='#f0eff8', mark='#8b7ce0')
MODEL_COLORS = ('#6f86e8', '#a173d8', '#4fb3c8', '#e28bb6', '#f0b45a', '#8d92b5')
PALETTE = Palette(accent='#7d6fd6', accent_soft='#c3bbef', text='#33385a', muted='#737597',
                  track='#e8e5f6', surface='#fbfaff', hover='#ebe8fa', tile='#f1f0fd')
# Three faint sparkles in the header gap: (offset from the right edge, y, radius, colour mix).
HEADER_STARS = ((142, 14, 4.6, 0.), (130, 7, 2.6, .5), (126, 20, 2., 1.))


def star_path(cx, cy, outer, inner=None):
    """Four-point sparkle, the Gemini signature shape."""
    inner = outer*.3 if inner is None else inner
    path = QPainterPath(QPointF(cx, cy-outer))
    for x, y in ((cx+inner, cy-inner), (cx+outer, cy), (cx+inner, cy+inner), (cx, cy+outer),
                 (cx-inner, cy+inner), (cx-outer, cy), (cx-inner, cy-inner)):
        path.lineTo(x, y)
    path.closeSubpath()
    return path


def blend(a, b, t):
    return QColor(round(a.red()+(b.red()-a.red())*t), round(a.green()+(b.green()-a.green())*t),
                  round(a.blue()+(b.blue()-a.blue())*t))


class CompanionCard(CompanionCardSurface):
    ROLE = 'gemini'
    actionRequested = Signal(str)
    optionChanged = Signal(str, object)
    webRequested = Signal()
    refreshRequested = Signal()
    layoutChanged = Signal()
    resetRequested = Signal(list)
    earPetted = Signal()
    PAGE_NAMES = ('card', 'settings', 'actions', 'quota')
    PAGE_SETTINGS, PAGE_ACTIONS, PAGE_QUOTA = 1, 2, 3
    STAY_OPEN = (1,)
    BODY_W = 268
    THEME = THEME
    PALETTE = PALETTE

    def __init__(self, actions, settings):
        super().__init__()
        self.setWindowTitle('Gemini · 陪伴卡片')
        self.actions = actions
        self.quick_buttons, self.action_buttons = {}, {}
        self.nickname = settings.get('nickname', '')
        self.motion = False
        self._said = ''
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(10, 6, 10, 5)
        outer.setSpacing(3)
        self.setup_header(outer, 'Gemini')
        self.dot.clicked.connect(self.earPetted)
        self.dot.mark = self.paint_star
        self.dot.setToolTip('Gemini')
        self.sync_navigation('on_top', settings['on_top'])
        self.sync_navigation('lock_position', settings['lock_position'])
        self.pages = CurrentPageStack()
        self.pages.addWidget(self.overview_page(settings))
        self.pages.addWidget(self.settings_page(settings))
        self.pages.addWidget(self.action_page(actions))
        self.pages.addWidget(self.quota_page())
        
        self.scroller = QScrollArea()
        self.scroller.setWidgetResizable(True)
        self.scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroller.setWidget(self.pages)
        outer.addWidget(self.scroller, 1)
        self.footer_widget = TodayTokens(self.THEME)
        self.footer_widget.activated.connect(self.dashboard.toggle_tokens)
        outer.addWidget(self.footer_widget)
        self.say(self.idle_message())
        self.set_page(0)


    # ---- the starlit sheet ----
    def paint_star(self, p, rect):
        gradient = QLinearGradient(rect.left(), rect.top()+6, rect.right(), rect.bottom()-6)
        gradient.setColorAt(0, STAR_BLUE)
        gradient.setColorAt(1, STAR_VIOLET)
        p.setBrush(gradient)
        p.drawPath(star_path(rect.center().x(), rect.center().y(), 6.))

    def paint_surface(self, p, rect):
        sheet = rect.adjusted(.5, .5, -.5, -.5)
        glow = QLinearGradient(0, 0, 0, rect.height())
        glow.setColorAt(0, QColor('#fdfcff'))
        glow.setColorAt(1, QColor('#f6f4ff'))
        edge = QLinearGradient(0, 0, rect.width(), rect.height())
        edge.setColorAt(0, QColor('#bccaf5'))
        edge.setColorAt(1, QColor('#d8c6f2'))
        p.setPen(QPen(edge, 1))
        p.setBrush(glow)
        p.drawRoundedRect(sheet, 18, 18)
        p.setPen(Qt.PenStyle.NoPen)
        for offset, y, radius, mix in HEADER_STARS:
            colour = blend(STAR_BLUE, STAR_VIOLET, mix)
            colour.setAlphaF(.5)
            p.setBrush(colour)
            p.drawPath(star_path(rect.width()-offset-(60 if self.pages.currentIndex()==self.PAGE_SETTINGS else 0), y, radius))


    def update_tokens(self, report):
        self.footer_widget.set_report(report)
        self.dashboard.update_tokens(self.footer_widget.report)

    def idle_message(self):
        return time_greeting(datetime.now().hour, self.nickname)

    def say(self, text):
        self._said = text
        shown = self.message.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, self.width()-24)
        self.message.setText(shown)
        self.message.setToolTip(text if shown != text else '')

    def said(self):
        return self._said

    def sync_option(self, key, value):
        self.settings_panel.sync(key, value)
        self.sync_navigation(key, value)
        if key == 'nickname':
            self.nickname = value
            self.say(self.idle_message())


    def overview_page(self, settings):
        self.dashboard = Dashboard(self, (('meow', '喵喵'), ('greeting', '招手'), ('catch', '星光')))
        self.current_action = self.dashboard.current
        self.action_hint = self.dashboard.hint
        return self.dashboard


    def settings_page(self, settings):
        from share.desktop.settings_panel import companion_sections
        values = dict(settings, autostart=False)
        sections = companion_sections(self.ROLE)
        self.settings_panel = SettingsPanel(sections, values, PALETTE, defaults=normalized({}, SCHEMA))
        self.settings_panel.optionChanged.connect(self.optionChanged)
        self.settings_panel.resetRequested.connect(self.resetRequested)
        self.settings_panel.returnRequested.connect(self.return_to_status)
        return self.settings_panel


    def action_page(self, actions):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        layout.addWidget(label('点一下立即换上，前一个动作会柔和地淡出', 'muted'))
        grid = QGridLayout()
        grid.setSpacing(5)
        for index, item in enumerate(v for v in actions.values() if v['id'] != 'idle' and not v.get('walk')):
            button = QPushButton(item['name'])
            button.setObjectName('action')
            button.setToolTip(item['group'])
            button.clicked.connect(lambda checked=False, key=item['id']: self.actionRequested.emit(key))
            self.action_buttons[item['id']] = button
            grid.addWidget(button, index//2, index%2)
        layout.addLayout(grid)
        layout.addStretch()
        return page

    def quota_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.quota_panel = QuotaPanel(PALETTE, 'remaining', 'Antigravity · 尚未连接')
        layout.addWidget(self.quota_panel, 1)
        layout.addWidget(label('只读 Antigravity 的本机缓存，不登录、不联网', 'muted'))
        return page


    def set_action(self, key, queued=None):
        item = self.actions.get(key, {})
        self.current_action.setText(item.get('name', key))
        self.action_hint.setText('接着：'+self.actions[queued]['name'] if queued in self.actions else '点一下，马上换动作')
        for name, widget in self.action_buttons.items():
            playing = name == key
            if widget.property('playing') != playing:
                widget.setProperty('playing', playing)
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def update_quota(self, snapshot):
        """Antigravity's model quota on the dashboard and its details page."""
        self.quota_panel.set_snapshot(snapshot)
        self.dashboard.update_quota(snapshot)
        self.dot.setToolTip(snapshot.message if snapshot else '')


