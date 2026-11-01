"""Claude: Gpt-style dashboard and editor, with character-specific pages."""
from share.desktop.card_surface import CompanionCardSurface, Dashboard, Theme

from datetime import datetime
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QScrollArea
from share.desktop.card_kit import CurrentPageStack, Palette, QuotaPanel, SettingsPanel, button, label
from share.desktop.token_widgets import TodayTokens
from model import SCHEMA, normalized, greeting
from ornaments import ACCENT, SERIF_CSS, Ribbon, spark_path

BODY_W = 268  # compact status width; the shared editor expands independently


# Warm terracotta ink on cream paper, serif type for her voice and numbers.
INK_STROKE = 'qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #b9583a, stop:1 #e09a74)'
THEME = Theme(surface='#fffaf3', border='#e8d3bd', ink='#4a3a2f', muted='#9a8270', stat='#7a4a33',
              primary='#c3694a', primary_hover='#a9573a', primary_fill='#c3694a', hover='#f8eadb',
              soft='#f5e0cf', focus='#d58a68', tile='#f8eee2', card='#fffaf3', card_border='#efdcc8',
              footer='#f4e7d8', nav='#f6ebde', track='#efe0cf', chunk=INK_STROKE, scroll='#e0c6ad',
              selection='#f1d2bd', disabled='#f4ece3', mark='#d97757', display=SERIF_CSS)
MODEL_COLORS = ('#c3694a', '#e3a37f', '#8f4a30', '#c9a27e', '#7f9a7a', '#b98aa0')
PALETTE = Palette(accent='#c3694a', accent_soft='#e6b79c', text='#4a3a2f', muted='#9a8270',
                  track='#efe2d3', surface='#fffbf5', hover='#f6e6d6', tile='#f8eee2')
QUICK = (('wave', '招手'), ('peek', '偷看'), ('idea', '灵光'))


class CompanionCard(CompanionCardSurface):
    ROLE = 'claude'
    actionRequested = Signal(str)
    optionChanged = Signal(str, object)
    resetRequested = Signal(list)
    webRequested = Signal()
    refreshRequested = Signal()
    layoutChanged = Signal()
    PAGE_NAMES = ('card', 'settings', 'actions', 'quota')
    PAGE_SETTINGS, PAGE_ACTIONS, PAGE_QUOTA = 1, 2, 3
    BODY_W = BODY_W
    THEME = THEME
    PALETTE = PALETTE
    STAY_OPEN = (1,)  # settings stay open

    def __init__(self, actions, settings):
        super().__init__()
        self.setWindowTitle('Claude · 陪伴卡片')
        self.actions = actions
        self.quick_buttons, self.action_buttons = {}, {}
        self.nickname = settings.get('nickname', '')
        self.motion = False
        self._said = ''
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(10, 6, 10, 5)
        outer.setSpacing(3)
        self.setup_header(outer, 'Claude')
        self.dot.mark = self.paint_spark
        self.dot.setToolTip('Claude')
        self.ribbon = Ribbon(0, 1)
        self.ribbon.LENGTH, self.ribbon.WIDTH = 22., 9.
        self.sync_navigation('on_top', settings['on_top'])
        self.sync_navigation('lock_position', settings['lock_position'])
        self.pages = CurrentPageStack()
        self.pages.addWidget(self.overview_page())
        self.pages.addWidget(self.settings_page(settings))
        self.pages.addWidget(self.actions_page())
        self.pages.addWidget(self.quota_page())
        self.scroller = QScrollArea()
        self.scroller.setWidgetResizable(True)
        self.scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroller.setWidget(self.pages)
        outer.addWidget(self.scroller, 1)
        self.footer_widget = TodayTokens(self.THEME)
        self.footer_widget.activated.connect(self.dashboard.toggle_tokens)
        outer.addWidget(self.footer_widget)
        self.ambient = QTimer(self)
        self.say(self.idle_message())
        self.set_page(0)

    # ---- small public surface used by the companion ----


    def update_tokens(self, report):
        self.footer_widget.set_report(report)
        self.dashboard.update_tokens(self.footer_widget.report)

    def idle_message(self):
        return greeting(datetime.now().hour, self.nickname)

    def say(self, text):
        """One serif line; long lines are elided and kept whole in the tooltip."""
        self._said = text
        shown = self.message.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, BODY_W-26)
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

    def set_action(self, key, queued=None):
        self.current_action.setText(self.actions.get(key, {}).get('name', key))
        text = '接着：'+self.actions[queued]['name'] if queued in self.actions else '点一下，马上换动作'
        self.action_hint.setToolTip(text)
        self.action_hint.setText(self.action_hint.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, 112))
        for name, widget in self.action_buttons.items():
            playing = name == key
            if widget.property('playing') != playing:
                widget.setProperty('playing', playing)
                widget.style().unpolish(widget)
                widget.style().polish(widget)


    def update_quota(self, snapshot):
        """Keep the real allowance in the dashboard and the full details page."""
        self.quota_panel.set_snapshot(snapshot)
        self.dashboard.update_quota(snapshot)


    # ---- pages ----

    def page(self, margins=(2, 0, 2, 0), spacing=7):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        return widget, layout

    def overview_page(self):
        self.dashboard = Dashboard(self, QUICK)
        self.current_action = self.dashboard.current
        self.action_hint = self.dashboard.hint
        
        return self.dashboard


    def settings_page(self, settings):
        from share.desktop.settings_panel import companion_sections
        values = dict(settings, autostart=False)
        sections = companion_sections(self.ROLE, self.actions)
        self.settings_panel = SettingsPanel(sections, values, PALETTE, defaults=normalized({}, SCHEMA))
        self.settings_panel.optionChanged.connect(self.optionChanged)
        self.settings_panel.resetRequested.connect(self.resetRequested)
        self.settings_panel.returnRequested.connect(self.return_to_status)
        return self.settings_panel

    def actions_page(self):
        page, layout = self.page((0, 0, 0, 0))
        layout.addWidget(label('点一下立即换上，前一个动作会柔和地淡出', 'muted'))
        grid = QGridLayout()
        grid.setSpacing(5)
        for index, item in enumerate(v for v in self.actions.values() if v['id'] != 'idle'):
            widget = button(item['name'], lambda checked=False, key=item['id']: self.actionRequested.emit(key),
                            'action', item.get('group'))
            self.action_buttons[item['id']] = widget
            grid.addWidget(widget, index//2, index % 2)
        layout.addLayout(grid)
        layout.addStretch()
        return page

    def quota_page(self):
        page, layout = self.page((0, 0, 0, 0), 4)
        self.quota_panel = QuotaPanel(PALETTE, 'used', 'Claude 桌面端 · 尚未连接')
        layout.addWidget(self.quota_panel, 1)
        row = QHBoxLayout()
        row.addWidget(label('只读本机记录，不登录、不联网', 'muted'), 1)
        row.addWidget(button('打开 Claude 网页 ›', self.webRequested.emit, 'link'))
        layout.addLayout(row)
        return page





    # ---- the paper sheet ----
    def paint_spark(self, p, rect):
        p.setBrush(ACCENT)
        p.drawPath(spark_path(rect.center().x(), rect.center().y(), 6.))

    def place_ribbon(self, rect):
        # A bookmark hanging in the quiet gap between the name and the header buttons.
        self.ribbon.anchor.setX(rect.width()-142-(60 if self.pages.currentIndex()==self.PAGE_SETTINGS else 0))

    def paint_surface(self, p, rect):
        from PySide6.QtGui import QLinearGradient
        sheet = rect.adjusted(.5, .5, -.5, -.5)
        paper = QLinearGradient(0, 0, 0, rect.height())
        paper.setColorAt(0, QColor('#fffcf7'))
        paper.setColorAt(1, QColor('#fdf4e8'))
        p.setPen(QPen(QColor(THEME.border), 1))
        p.setBrush(paper)
        p.drawRoundedRect(sheet, 18, 18)
        p.setPen(QPen(QColor('#f3e5d4'), 1))  # the page's inner margin line
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(sheet.adjusted(3, 3, -3, -3), 15, 15)
        self.place_ribbon(rect)
        self.ribbon.paint(p)

    # ---- behaviour ----

    # ---- ambient motion: runs only while the card is on screen ----


