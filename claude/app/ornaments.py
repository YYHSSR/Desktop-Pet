"""Painted pieces of Claude's paper card: the spark, the ink line, page stack and ribbon."""
import math
import time
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QPushButton, QWidget

# Warm orange on cream paper (Gemini keeps blue-violet, ChatGpt plum porcelain).
PAPER = '#fdf8f0'
PAPER_EDGE = '#efe2d0'
BORDER = '#e3cfb9'
INK = '#4a3a2f'
MUTED = '#9a8270'
ACCENT = QColor('#d97757')
ACCENT_DEEP = QColor('#b9583a')
RIBBON = QColor('#c9563c')
RIBBON_DEEP = QColor('#9e3d28')
SERIF = ('Cambria', 'Georgia', 'Noto Serif SC', 'Source Han Serif SC', 'Source Han Serif',
         'STSong', 'SimSun', 'serif')
SERIF_CSS = 'font-family:' + ','.join(f'"{name}"' for name in SERIF) + ';font-weight:500;'


def spark_path(cx, cy, radius, turn=0., rays=12):
    """Claude's radiating spark: uneven tapered rays around a small heart."""
    path = QPainterPath()
    for index in range(rays):
        angle = math.radians(turn + index*360/rays)
        length = radius*(1. if index % 2 == 0 else .74)*(1-.08*(index % 3 == 1))
        half = math.radians(7.5)
        tip = QPointF(cx+math.cos(angle)*length, cy+math.sin(angle)*length)
        left = QPointF(cx+math.cos(angle-half)*radius*.22, cy+math.sin(angle-half)*radius*.22)
        right = QPointF(cx+math.cos(angle+half)*radius*.22, cy+math.sin(angle+half)*radius*.22)
        ray = QPainterPath(left)
        ray.lineTo(tip)
        ray.lineTo(right)
        ray.closeSubpath()
        path.addPath(ray)
    path.addEllipse(QPointF(cx, cy), radius*.26, radius*.26)
    return path.simplified()


class Spark(QWidget):
    """Header spark: breathes slowly, twirls when clicked, three quick clicks summon a guest."""
    summoned = Signal()
    SUMMON_CLICKS = 3
    SUMMON_WINDOW = 1.4

    def __init__(self):
        super().__init__()
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.glow = 1.
        self.turn = 0.
        self._spin = 0.
        self._clicks = []

    def advance(self, phase, dt):
        self.glow = .5+.5*math.sin(phase*math.tau/3.6)
        self._spin *= math.exp(-dt*3.2)
        self.turn = (self.turn + dt*(6+self._spin)) % 360
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        now = time.monotonic()
        self._clicks = [t for t in self._clicks if now-t < self.SUMMON_WINDOW] + [now]
        self._spin += 420
        if len(self._clicks) >= self.SUMMON_CLICKS:
            self._clicks.clear()
            self.summoned.emit()
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setOpacity(.55+.45*self.glow)
        painter.setBrush(ACCENT)
        painter.drawPath(spark_path(9, 9, 7.2+.9*self.glow, self.turn))


class IconButton(QPushButton):
    def __init__(self, icon, tooltip):
        super().__init__()
        self.icon_name = icon
        self.setFixedSize(25, 25)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse() or self.hasFocus():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#f3e4d3'))
            painter.drawRoundedRect(self.rect(), 7, 7)
        pen = QPen(QColor('#a8674a'), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        name = self.icon_name
        if name == 'refresh':
            painter.drawArc(QRectF(5, 5, 14, 14), 40*16, 280*16)
            painter.drawLine(19, 5, 19, 10)
            painter.drawLine(19, 10, 14, 10)
        elif name == 'focus':  # hourglass
            painter.drawLine(7, 5, 18, 5)
            painter.drawLine(7, 20, 18, 20)
            path = QPainterPath(QPointF(8, 5))
            path.cubicTo(8, 11, 12.5, 11, 12.5, 12.5)
            path.cubicTo(12.5, 14, 8, 14, 8, 20)
            path.moveTo(17, 5)
            path.cubicTo(17, 11, 12.5, 11, 12.5, 12.5)
            path.cubicTo(12.5, 14, 17, 14, 17, 20)
            painter.drawPath(path)
        elif name == 'web':
            painter.drawEllipse(QRectF(5, 5, 15, 15))
            painter.drawEllipse(QRectF(9, 5, 7, 15))
            painter.drawLine(5, 12, 20, 12)
        elif name == 'back':
            painter.drawLine(16, 6, 9, 12)
            painter.drawLine(9, 12, 16, 18)
        else:
            painter.drawLine(5, 7, 14, 7)
            painter.drawLine(5, 12, 12, 12)
            painter.drawLine(5, 17, 14, 17)
            painter.drawLine(16, 10, 20, 14)
            painter.drawLine(20, 14, 16, 18)


class InkLine(QWidget):
    """Progress written as an ink stroke along a ruled line, a small nib at its head."""
    def __init__(self, height=10, weight=2.2):
        super().__init__()
        self.setFixedHeight(height)
        self.weight = weight
        self._value = 0

    def setValue(self, value):
        value = max(0, min(1000, int(value)))
        if value != self._value:
            self._value = value
            self.update()

    def value(self):
        return self._value

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = self.height()/2
        left, right = 3., self.width()-3.
        dotted = QPen(QColor('#dcc7b3'), 1, Qt.PenStyle.DotLine)
        painter.setPen(dotted)
        painter.drawLine(QPointF(left, y), QPointF(right, y))
        head = left+(right-left)*self._value/1000
        if self._value:
            gradient = QLinearGradient(left, 0, right, 0)
            gradient.setColorAt(0, ACCENT_DEEP)
            gradient.setColorAt(1, ACCENT)
            pen = QPen(gradient, self.weight)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(left, y), QPointF(head, y))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ACCENT_DEEP if self._value else QColor('#d6bba4'))
        nib = QPainterPath(QPointF(head, y-self.weight*1.9))
        nib.lineTo(head+self.weight*1.4, y)
        nib.lineTo(head, y+self.weight*1.9)
        nib.lineTo(head-self.weight*1.4, y)
        nib.closeSubpath()
        painter.drawPath(nib)


class PageStack(QWidget):
    """Today's finished pages as a small, slightly fanned stack of paper."""
    SHOWN = 6

    def __init__(self):
        super().__init__()
        self.setFixedSize(26, 18)
        self.pages = 0

    def set_pages(self, pages):
        pages = max(0, int(pages))
        if pages != self.pages:
            self.pages = pages
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        shown = min(self.SHOWN, self.pages)
        if not shown:
            painter.setPen(QPen(QColor('#d4bca6'), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(7.5, 3.5, 11, 12), 1.5, 1.5)
            return
        for index in range(shown):
            painter.save()
            painter.translate(13, 16)
            painter.rotate((index-(shown-1)/2)*7)
            top = index == shown-1
            painter.setPen(QPen(QColor('#c9a68a' if top else '#dcc3ad'), .9))
            painter.setBrush(QColor('#fffdf8' if top else '#f6eadc'))
            painter.drawRoundedRect(QRectF(-5.5, -13, 11, 12.5), 1.3, 1.3)
            if top:
                painter.setPen(QPen(QColor('#d9b49a'), .8))
                for line in (-10, -7.5, -5):
                    painter.drawLine(QPointF(-3.5, line), QPointF(3.5, line))
            painter.restore()


class Ribbon:
    """A bookmark ribbon tucked under the card's top-right corner, hanging down outside it.

    Geometry only; the card owns the timer and paints it. A gentle pendulum
    sway, a little more when hovered, and a springy tug when pulled.
    """
    WIDTH = 8.
    LENGTH = 66.

    def __init__(self, anchor_x, anchor_y):
        self.anchor = QPointF(anchor_x, anchor_y)
        self.angle = 0.
        self.stretch = 0.
        self._tug = None
        self._hover = 0.

    def advance(self, phase, hovered):
        self._hover += ((1. if hovered else 0.)-self._hover)*.15
        self.angle = (3.2+2.6*self._hover)*math.sin(phase*math.tau/3.4)
        self.stretch = 0.
        if self._tug is not None:
            t = time.perf_counter()-self._tug
            if t > 1.2:
                self._tug = None
            else:
                self.stretch = 9*math.exp(-t*4.5)*math.cos(t*math.tau*2.1)
                self.angle += 6*math.exp(-t*3.5)*math.sin(t*math.tau*1.6)

    def tug(self):
        self._tug = time.perf_counter()

    def geometry(self):
        """The ribbon outline and its centre line (for the sheen)."""
        length = self.LENGTH+self.stretch
        drift = length*math.sin(math.radians(self.angle))
        half = self.WIDTH/2
        x0, y0 = self.anchor.x(), self.anchor.y()
        centre = [QPointF(x0+drift*(index/10)**2, y0+length*index/10) for index in range(11)]
        path = QPainterPath(centre[0]-QPointF(half, 0))
        for point in centre[1:]:
            path.lineTo(point-QPointF(half, 0))
        path.lineTo(centre[-1]-QPointF(0, 5))  # swallowtail notch
        for point in reversed(centre):
            path.lineTo(point+QPointF(half, 0))
        path.closeSubpath()
        return path, centre

    def path(self):
        return self.geometry()[0]

    def bounds(self):
        return self.path().boundingRect().adjusted(-3, -3, 3, 3)

    def contains(self, point):
        return self.bounds().contains(point)

    def paint(self, painter):
        path, centre = self.geometry()
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(80, 40, 20, 34))
        painter.drawPath(path.translated(1.2, 1.4))
        gradient = QLinearGradient(self.anchor, self.anchor+QPointF(0, self.LENGTH))
        gradient.setColorAt(0, RIBBON_DEEP)
        gradient.setColorAt(.18, RIBBON)
        gradient.setColorAt(1, RIBBON.lighter(108))
        painter.setBrush(gradient)
        painter.drawPath(path)
        sheen = QPainterPath(centre[1]-QPointF(1.4, 0))
        for point in centre[2:-1]:
            sheen.lineTo(point-QPointF(1.4, 0))
        painter.setPen(QPen(QColor(255, 226, 205, 95), .9))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(sheen)
        # The tuck: a darker fold where the ribbon slips under the page corner.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(RIBBON_DEEP)
        painter.drawRoundedRect(QRectF(self.anchor.x()-self.WIDTH/2-1, self.anchor.y()-3, self.WIDTH+2, 5), 1.5, 1.5)
        painter.restore()
