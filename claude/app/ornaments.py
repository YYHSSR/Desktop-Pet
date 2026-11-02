"""Painted pieces of Claude's paper card: the spark, the ink line, page stack and ribbon."""
import math
import time
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QPen

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
