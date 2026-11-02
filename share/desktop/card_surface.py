"""Gpt-style companion cards: compact dashboard and snapshot-only navigation.

Native geometry changes at the ends of a transition. Every animated frame only
paints two prepared pixmaps on one fixed transparent canvas.
"""
import math
from dataclasses import dataclass
from PySide6.QtCore import Qt, QRect, QRectF, QSize, QPoint, Signal, QVariantAnimation, QTimer, QEvent
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PySide6.QtWidgets import (QApplication, QFrame, QWidget, QHBoxLayout, QPushButton, QLabel,
    QProgressBar, QScrollArea)
from .typography import FONT_CSS
from .spring_motion import container_progress, dismiss_progress, EXPAND_MS, SHRINK_MS, DISMISS_MS
from .card_kit import label, button

@dataclass(frozen=True)
class Theme:
    """Colours and type for one character; the card layout itself is shared."""
    surface: str = '#fcfafc'
    border: str = '#ded2e7'
    ink: str = '#393343'
    muted: str = '#706879'
    stat: str = '#514360'
    primary: str = '#75618d'
    primary_hover: str = '#5f4c77'
    primary_fill: str = '#75618d'      # any QSS brush, e.g. a gradient
    hover: str = '#eee7f5'
    soft: str = '#e8dff0'
    focus: str = '#8b78a6'
    tile: str = '#f5f2f7'
    card: str = '#faf7fc'
    card_border: str = '#e8dff0'
    footer: str = '#eee8f3'
    nav: str = '#f2edf7'
    track: str = '#e4dfea'
    chunk: str = '#8b78a6'             # any QSS brush
    scroll: str = '#c7bbd5'
    selection: str = '#dacbe8'
    disabled: str = '#efebf2'
    mark: str = '#9a81b4'
    display: str = ''                  # font CSS for the greeting, clock and big numbers


TEMPLATE = '''
QWidget { FONT color:%ink%; font-size:12px; background:transparent; }
QLabel { border:none; }
QLabel[role="muted"], QLabel[role="section"] { color:%muted%; font-size:10px; }
QLabel[role="say"] { %display% color:%ink%; }
QLabel[role="value"] { %display% color:%ink%; font-size:28px; }
QLabel[role="stat"] { %display% color:%stat%; font-size:18px; }
QFrame#tile { background:%tile%; border:none; border-radius:12px; }
QFrame#footer { background:%footer%; border:none; border-radius:9px; }
QPushButton { color:%stat%; background:%surface%; border:1px solid %border%; border-radius:7px; padding:5px 8px; }
QPushButton:hover { background:%hover%; border-color:%focus%; }
QPushButton:pressed { background:%soft%; }
QPushButton[role="primary"], QPushButton#primary { background:%primary_fill%; color:white; border-color:%primary%; }
QPushButton[role="primary"]:hover, QPushButton#primary:hover { background:%primary_hover%; }
QPushButton#link { border:none; background:transparent; padding:0; font-size:10px; color:%primary%; }
QPushButton#quick { font-size:10px; padding:2px 4px; }
QPushButton#action { text-align:left; padding:6px 9px; }
QPushButton#action[playing="true"] { background:%soft%; border-color:%focus%; }
QPushButton:disabled { color:%muted%; background:%disabled%; border-color:%track%; }
QPushButton:focus,QLineEdit:focus,QPlainTextEdit:focus,QComboBox:focus,QAbstractSpinBox:focus { border:2px solid %focus%; }
QCheckBox { spacing:7px; padding:3px 1px; }
QLineEdit,QPlainTextEdit,QComboBox,QAbstractSpinBox { background:%surface%; color:%ink%;
    border:2px solid %border%; border-radius:6px; padding:5px; selection-background-color:%selection%; }
QComboBox QAbstractItemView { background:%surface%; color:%ink%; selection-background-color:%selection%; }
QTabWidget::pane { border:0; }
QTabBar::tab { color:%muted%; padding:7px 10px; border-bottom:2px solid transparent; }
QTabBar::tab:selected { background:%soft%; color:%primary_hover%; border-bottom:2px solid %primary%; border-radius:5px; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { background:transparent; width:6px; margin:0; }
QScrollBar::handle:vertical { background:%scroll%; min-height:22px; border-radius:3px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QProgressBar { background:%track%; border:0; border-radius:2px; }
QProgressBar::chunk { background:%chunk%; border-radius:2px; }
QMenu { background:%surface%; color:%ink%; border:1px solid %border%; border-radius:8px; padding:5px; }
QMenu::item { padding:6px 15px; border-radius:5px; }
QMenu::item:selected { background:%soft%; }
'''.replace('FONT', FONT_CSS)


def style_sheet(theme):
    text = TEMPLATE
    for name, value in vars(theme).items():
        text = text.replace(f'%{name}%', value)
    return text


THEME = Theme()


class HeaderButton(QPushButton):
    def __init__(self, icon, tip, callback, theme=THEME):
        super().__init__()
        self.icon_name, self.theme = icon, theme
        self.header_label=''
        self.setFixedSize(28, 28)
        self.setToolTip(tip); self.setAccessibleName(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(callback)

    def set_label(self,text):
        self.header_label=text
        self.setFixedWidth(28+self.fontMetrics().horizontalAdvance(text)+4 if text else 28)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse() or self.hasFocus():
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(self.theme.hover)); p.drawRoundedRect(self.rect(), 6, 6)
        pen = QPen(QColor(self.theme.primary), 1.7); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin); p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        if self.icon_name == 'refresh':
            p.drawArc(QRectF(6, 6, 14, 14), 40*16, 280*16)
            p.drawLine(20, 5, 20, 10); p.drawLine(20, 10, 15, 10)
        elif self.icon_name == 'web':
            p.drawEllipse(QRectF(6, 6, 15, 15)); p.drawEllipse(QRectF(10, 6, 7, 15)); p.drawLine(6, 13.5, 21, 13.5)
        elif self.icon_name == 'back':
            p.drawLine(17, 7, 10, 13); p.drawLine(10, 13, 17, 19)
        elif self.icon_name == 'collapse':
            p.drawLine(7, 13, 21, 13)
        else:
            for y, x in ((8, 16), (13, 13), (18, 16)): p.drawLine(6, y, x, y)
            p.drawLine(18, 11, 22, 15); p.drawLine(22, 15, 18, 19)
        if self.header_label:p.drawText(QRectF(28,0,self.width()-28,self.height()),Qt.AlignmentFlag.AlignVCenter,self.header_label)


class StatusDot(QPushButton):
    def __init__(self, theme=THEME):
        super().__init__(); self.setFixedSize(15, 24)
        self.theme = theme; self.mark = None  # optional painter(p, rect) for a character emblem
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setPen(Qt.PenStyle.NoPen)
        if self.mark is not None: self.mark(p, QRectF(self.rect())); return
        p.setBrush(QColor(self.theme.mark)); p.drawEllipse(QRectF(6, 10, 3, 3))


from .quota_dashboard import QuotaDashboard as Dashboard


class SurfaceBody(QWidget):
    """The card sheet; the owning card paints it so each character can decorate it."""
    def __init__(self, owner):
        super().__init__(owner); self.setMouseTracking(True)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.parentWidget().paint_surface(p, QRectF(self.rect()))

    def mousePressEvent(self, event):
        if not self.parentWidget().surface_pressed(event.position()): super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        hot = self.parentWidget().surface_hot(event.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if hot else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)


class MotionCover(QWidget):
    def paintEvent(self, event):
        self.parentWidget().paint_transition(QPainter(self))


class NativeLanding(QWidget):
    """Keep the final raster visible across Windows' native backing-store resize."""
    def __init__(self, owner):
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                 Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(owner, flags); self.image = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def present(self, image, rect):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,
                           bool(self.parentWidget().windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
        self.image = image; self.setGeometry(rect); self.show(); self.raise_(); self.repaint()

    def release(self):
        self.image = None
        if self.isVisible(): self.repaint()
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self); p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        if self.image is not None: p.drawPixmap(0, 0, self.image)


class CompanionCardSurface(QFrame):
    """Shared surface; character classes provide page bodies and their own data."""
    contextRequested = Signal(QPoint)
    BODY_W = 268
    THEME = THEME
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.content = SurfaceBody(self)
        self.setStyleSheet(style_sheet(self.THEME))
        self.geometry_provider = None
        self.transition_active = False; self.closing_surface = False; self.pending_page = None
        self.expanded_status = False; self._editor_origin_expanded = False
        self.transition_progress = 0.; self.before = self.after = None
        self.cover = MotionCover(self); self.cover.hide()
        self.landing = NativeLanding(self)
        self.landing_timer = QTimer(self); self.landing_timer.setSingleShot(True)
        self.landing_timer.setInterval(34); self.landing_timer.timeout.connect(self.landing.release)
        self.animation = QVariantAnimation(self)
        self.animation.setStartValue(0.); self.animation.setEndValue(1.)
        self.animation.valueChanged.connect(self.advance_transition)
        self.animation.finished.connect(self.finish_transition)
        self.reset_ticker = QTimer(self); self.reset_ticker.setInterval(30000)
        self.reset_ticker.timeout.connect(self.tick_countdown)

    def tick_countdown(self):
        self.footer_widget.refresh()
        self.dashboard.update_tokens(self.footer_widget.report)
        snapshot = getattr(self.dashboard, 'snapshot', None)
        if snapshot is not None:
            self.dashboard.update_quota(snapshot)
            self.quota_panel.set_snapshot(snapshot)

    def showEvent(self, event):
        super().showEvent(event)
        self.reset_ticker.start()

    def setup_header(self, outer, name):
        header = QHBoxLayout(); header.setContentsMargins(0, 0, 0, 0); header.setSpacing(1)
        theme = self.THEME
        self.back = HeaderButton('back', '返回状态卡片', lambda: self.set_page(0), theme)
        self.dot = StatusDot(theme); self.spark = self.dot
        self.heading = label(name); self.heading.setStyleSheet(f'{theme.display}font-size:12px;color:{theme.ink};')
        self.back.hide()
        header.addWidget(self.dot); header.addWidget(self.heading); header.addStretch()
        for icon, tip, slot in [('refresh', '刷新额度与当前状态', self.refreshRequested.emit),
                                 ('web', '打开网页', self.webRequested.emit),
                                 ('menu', '设置', self.toggle_editor)]:
            item = HeaderButton(icon, tip, slot, theme); setattr(self, icon+'_button', item); header.addWidget(item)
        outer.addLayout(header)
        self.message = label('', 'say'); self.message.setFixedHeight(18); outer.addWidget(self.message)
        self.navigation = QFrame(); self.navigation.setObjectName('editor_navigation')
        self.navigation.setStyleSheet(f'QFrame#editor_navigation{{background:{theme.nav};border-radius:7px;}}')
        row = QHBoxLayout(self.navigation); row.setContentsMargins(3, 1, 3, 1); row.setSpacing(4)
        self.navigation_buttons=[]
        for text, callback in [('状态', self.return_to_status), ('设置', self.enter_settings)]:
            item=button(text,callback,'link');item.setCheckable(True)
            item.setStyleSheet(f'QPushButton{{font-size:12px;padding:4px 8px;}}QPushButton:checked{{background:{theme.soft};}}')
            self.navigation_buttons.append(item);row.addWidget(item,1)
        self.navigation.setFixedHeight(32); self.navigation.hide(); outer.addWidget(self.navigation)

    def contextMenuEvent(self, event):
        self.contextRequested.emit(event.globalPos())
        event.accept()

    def sync_navigation(self, key, value):
        pass  # Placement controls are available in the shared context menu.

    def enter_settings(self):
        self.set_page(self.PAGE_SETTINGS)

    def toggle_editor(self):
        if self.pages.currentIndex()==0 and not self.expanded_status:self.enter_settings()
        else:self.set_page(0)

    def return_to_status(self):
        if self.pages.currentIndex()!=0:self.show_status(self._editor_origin_expanded)

    def show_status(self, expanded=True):
        if self.transition_active:self.finish_transition()
        before,start=(self.snapshot(),QRect(self.geometry())) if self.isVisible() else (None,None)
        self.expanded_status=expanded
        self.apply_page(0);target=self.target_geometry()
        if before is not None:self.start_transition(before,self.snapshot(),start,target)
        else:self.setFixedSize(target.size());self.move(target.topLeft())

    # ---- the sheet: characters override these to decorate it ----
    def paint_surface(self, p, rect):
        p.setPen(QPen(QColor(self.THEME.border), 1)); p.setBrush(QColor(self.THEME.surface))
        p.drawRoundedRect(rect.adjusted(.5, .5, -.5, -.5), 18, 18)

    def surface_hot(self, point): return False

    def surface_pressed(self, point): return False

    @property
    def preferred_height(self): return self.page_size(self.pages.currentIndex()).height()

    def page_size(self, index):
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        if index == 0:
            return QSize(360 if self.expanded_status else 268, 188+self.dashboard.panel_height-102+(32 if self.expanded_status else 0))
        return QSize(min(560, area.width()-24), min(600, area.height()-24))

    def target_geometry(self):
        size = self.page_size(self.pages.currentIndex())
        if self.geometry_provider: return self.geometry_provider(size)
        return QRect(self.x(), self.y()+self.height()-size.height(), size.width(), size.height())

    def apply_page(self, index):
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, index == 0)
        self.pages.setCurrentIndex(index); self.back.hide(); self.dot.show()
        expanded=index!=0 or self.expanded_status
        self.message.setVisible(index == 0); self.navigation.setVisible(expanded)
        self.menu_button.icon_name='collapse' if expanded else 'menu'
        self.menu_button.setToolTip('收起' if expanded else '设置');self.menu_button.update()
        editor=index==self.PAGE_SETTINGS
        self.refresh_button.setVisible(not editor)
        self.web_button.set_label(self.ROLE.title() if editor else '')
        self.menu_button.set_label('收起' if editor else '')
        for number,item in enumerate(self.navigation_buttons):item.setChecked(number==(1 if index==self.PAGE_SETTINGS else 0))
        if hasattr(self, 'footer_widget'): self.footer_widget.setVisible(index == 0)
        names = {'settings':'设置', 'actions':'动作', 'quota':'额度'}
        self.heading.setText(self.ROLE.title() + (' · '+names[self.PAGE_NAMES[index]] if index else ''))
        self.content.setFixedSize(self.page_size(index)); self.content.layout().activate()
        self.scroller.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if index in (0, self.PAGE_SETTINGS) else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        for widget in self.content.findChildren(QWidget):
            widget.ensurePolished()
            if widget.layout(): widget.layout().activate()
        self.pages.updateGeometry(); self.content.layout().activate()
        QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        viewport = self.scroller.viewport().size()
        self.pages.resize(viewport.width(), max(viewport.height(), self.pages.minimumSizeHint().height()))
        if self.pages.layout(): self.pages.layout().activate()

    def snapshot(self):
        ratio = self.devicePixelRatioF(); size = self.content.size()
        image = QPixmap(math.ceil(size.width()*ratio), math.ceil(size.height()*ratio))
        image.setDevicePixelRatio(ratio); image.fill(Qt.GlobalColor.transparent)
        self.content.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren | QWidget.RenderFlag.DrawWindowBackground)
        return image

    def set_page(self, index):
        if self.transition_active:
            self.pending_page = index; return
        if index==self.PAGE_SETTINGS and self.pages.currentIndex()==0:self._editor_origin_expanded=self.expanded_status
        if not self.isVisible():
            self.expanded_status=False
            self.apply_page(index); rect = self.target_geometry(); self.setFixedSize(rect.size()); self.move(rect.topLeft())
            self.content.move(0, 0); self.content.show(); return
        if index == self.pages.currentIndex() and not self.expanded_status: return
        before, start = self.snapshot(), QRect(self.geometry())
        self.expanded_status=False
        self.apply_page(index); target = self.target_geometry()
        self.start_transition(before, self.snapshot(), start, target)

    def start_transition(self, before, after, start, target, closing=False):
        self.landing_timer.stop(); self.landing.release()
        self.before, self.after, self.start_rect, self.end_rect = before, after, start, target
        self.closing_surface = closing; self.transition_active = True; self.transition_progress = 0.
        self.canvas_rect = start.united(target)
        self.content.hide()
        self.setMinimumSize(0, 0); self.setMaximumSize(16777215, 16777215)
        self.setGeometry(self.canvas_rect); self.setFixedSize(self.canvas_rect.size())
        self.cover.setGeometry(self.rect()); self.cover.show(); self.cover.raise_()
        self.show(); self.raise_()
        duration = DISMISS_MS if closing else SHRINK_MS if target.width()*target.height() < start.width()*start.height() else EXPAND_MS
        self.animation.setDuration(duration); self.animation.start()

    def advance_transition(self, value):
        self.transition_progress = float(value); self.cover.update()

    def paint_transition(self, p):
        if not self.transition_active: return
        t = self.transition_progress
        f = max(0., dismiss_progress(t)) if self.closing_surface else container_progress(t)
        a, b, c = self.start_rect, self.end_rect, self.canvas_rect
        values = [x+(y-x)*f for x, y in zip((a.x(), a.y(), a.width(), a.height()), (b.x(), b.y(), b.width(), b.height()))]
        rect = QRectF(values[0]-c.x(), values[1]-c.y(), values[2], values[3])
        p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath(); path.addRoundedRect(rect, min(18, rect.height()/2), min(18, rect.height()/2)); p.setClipPath(path)
        p.fillPath(path, QColor(self.THEME.surface))
        for image, opacity in ((self.before, 1-f), (self.after, f)):
            if image is None or opacity <= 0: continue
            p.setOpacity(opacity)
            if self.closing_surface:
                p.drawPixmap(rect, image, QRectF(image.rect()))
            else:
                size = image.deviceIndependentSize()
                p.drawPixmap(round(rect.center().x()-size.width()/2), round(rect.bottom()-size.height()), image)
        p.setClipping(False); p.setOpacity(1.); p.setPen(QPen(QColor(self.THEME.border), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect.adjusted(.5, .5, -.5, -.5), min(18, rect.height()/2), min(18, rect.height()/2))

    def finish_transition(self):
        if not self.transition_active: return
        self.animation.stop(); closing = self.closing_surface
        shrinking = not closing and self.isVisible() and self.end_rect.width()*self.end_rect.height() < self.start_rect.width()*self.start_rect.height()
        if shrinking and self.after is not None: self.landing.present(self.after, self.end_rect)
        if closing: self.hide()
        self.transition_active = False; self.closing_surface = False
        self.setFixedSize(self.content.size()); self.move(self.end_rect.topLeft() if not closing else self.start_rect.topLeft())
        self.content.move(0, 0); self.content.show(); self.cover.hide(); self.before = self.after = None
        if not closing: self.repaint()
        if shrinking: self.landing_timer.start()
        pending, self.pending_page = self.pending_page, None
        if pending is not None and not closing and pending != self.pages.currentIndex():
            QTimer.singleShot(0, lambda: self.set_page(pending))

    def reveal(self, page=None):
        if self.transition_active: self.finish_transition()
        if self.isVisible():
            if page is not None: self.set_page(page)
            self.raise_(); return
        self.set_page(self.pages.currentIndex() if page is None else page)
        target = self.target_geometry(); self.move(target.topLeft())
        start = QRect(target.center().x()-24, target.bottom()-10, 48, 10)
        self.start_transition(None, self.snapshot(), start, target)

    def dismiss(self):
        if self.transition_active: self.finish_transition()
        if not self.isVisible(): return
        start = QRect(self.geometry()); target = QRect(start.center().x()-2, start.bottom()-2, 4, 2)
        self.start_transition(self.snapshot(), None, start, target, closing=True)

    def reposition(self):
        if not self.transition_active:
            rect = self.target_geometry(); self.setFixedSize(rect.size()); self.move(rect.topLeft())

    def hideEvent(self, event):
        self.animation.stop(); self.transition_active = False; self.pending_page = None; self.cover.hide()
        self.landing_timer.stop(); self.landing.release(); self.reset_ticker.stop()
        super().hideEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.set_page(0) if self.pages.currentIndex() else self.dismiss()
            event.accept()
        else: super().keyPressEvent(event)
