"""Gemini-only ambient star layer; its phase survives every action handoff."""
import math
import time
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath
from gemini_motion import GeminiMotionSprite


class GeminiSprite(GeminiMotionSprite):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sparkle_epoch = time.perf_counter()
        self.sparkles = True

    def sparkle_phase(self, now=None):
        return ((time.perf_counter() if now is None else now)-self.sparkle_epoch) / 3.6

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.frame is None or not self.sparkles:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(0, 0, 0, 0))
        phase = self.sparkle_phase()
        for index, (nx, ny) in enumerate(((.11, .26), (.88, .43), (.10, .68))):
            pulse = max(0., math.sin(math.tau*(phase+index/3)))**2
            if pulse < .015:
                continue
            x, y = nx*self.width(), ny*self.height()
            radius = (2.2+1.2*pulse)*self.width()/300
            path = QPainterPath(QPointF(x, y-radius))
            for px, py in ((x+radius*.24,y-radius*.24),(x+radius,y),
                           (x+radius*.24,y+radius*.24),(x,y+radius),
                           (x-radius*.24,y+radius*.24),(x-radius,y),(x-radius*.24,y-radius*.24)):
                path.lineTo(px, py)
            path.closeSubpath()
            painter.fillPath(path, QColor(161, 141, 202, round(150*pulse)))
