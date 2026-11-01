"""A short painted handoff for gestures interrupted by a click or drag."""
import time
import math
from PySide6.QtCore import QRectF


class PoseHandoff:
    def __init__(self):
        self.frame = None
        self.image = None
        self.item = None
        self.started = 0.
        self.duration = .2

    def begin(self, frame, item, duration=.2):
        self.frame = frame
        self.image = frame.toImage()
        self.item = dict(item or {})
        self.started = time.monotonic()
        self.duration = duration

    def active(self, now=None):
        if self.frame is None:
            return False
        if (time.monotonic() if now is None else now)-self.started >= self.duration:
            self.frame = None
            self.image = None
            return False
        return True

    def target(self, canvas):
        scale = self.item.get('renderScale', 1.)
        dx, dy = self.item.get('renderOffset', [0., 0.])
        width, height = canvas.width()*scale, canvas.height()*scale
        return QRectF(canvas.x()+(canvas.width()-width)/2+canvas.width()*dx,
                      canvas.y()+canvas.height()-height+canvas.height()*dy, width, height)

    def opacity(self):
        elapsed = max(0., min(1., (time.monotonic()-self.started)/self.duration))
        return 1-elapsed*elapsed*(3-2*elapsed)

    def hit(self, point, canvas):
        if not self.active():
            return False
        target = self.target(canvas)
        if target.isEmpty() or not target.contains(point):
            return False
        x = math.floor((point.x()-target.x())/target.width()*self.image.width())
        y = math.floor((point.y()-target.y())/target.height()*self.image.height())
        return (0 <= x < self.image.width() and 0 <= y < self.image.height()
                and self.image.pixelColor(x,y).alpha()*self.opacity() >= 12)

    def paint(self, painter, canvas):
        if not self.active():
            return
        target = self.target(canvas)
        painter.save()
        # The incoming character is already opaque beneath this fading pose.
        painter.setOpacity(self.opacity())
        painter.drawPixmap(target, self.frame, QRectF(self.frame.rect()))
        painter.restore()
