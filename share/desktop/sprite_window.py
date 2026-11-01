"""Transparent sprite surface with shared streaming playback and native hit testing.

Two ways into a new action:
- a handoff (an action ended): the old pose fades while the incoming
  reference pose holds still, then the new action plays its full entrance;
- a takeover (someone chose another action mid-way): both animations keep
  moving while they crossfade, so the switch is immediate but not a cut.
  The outgoing player only drains frames it had already decoded.
"""
import ctypes
from ctypes import wintypes
import time
from PySide6.QtCore import Qt, QTimer, QPoint, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QWidget
from share.pet_engine.loop_cache import DecodedLoopCache
from share.pet_engine.stream_player import StreamPlayer
from .native_coordinates import client_position, message_position

# The idle loop packs to ~30 MiB at 300 px and ~45-50 MiB at 125% scaling.
# Holding it lets every later loop replay from memory (~1 ms/frame) instead
# of re-decoding WebP (~25-30% of a core). ChatGpt keeps the engine default.
LOOP_CACHE_BYTES = 96*2**20
LOOP_ENTRY_BYTES = 64*2**20


def smooth(t):
    t = max(0., min(1., t))
    return t*t*(3-2*t)


class SpriteWindow(QWidget):
    activated = Signal()
    doubleActivated = Signal()
    contextRequested = Signal(QPoint)
    dragged = Signal()
    dragFinished = Signal()
    positionChanged = Signal()
    playbackFinished = Signal(str)
    playbackFailed = Signal(str)
    scaleRequested = Signal(int)
    TAKEOVER_SECONDS = .32

    def __init__(self, pack, size=300):
        super().__init__(None, Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.pack = pack
        self.setFixedSize(size, size)
        self.player = StreamPlayer()
        self.player.loop_cache = DecodedLoopCache(LOOP_CACHE_BYTES)
        self.player.loop_cache.entry_limit = LOOP_ENTRY_BYTES
        self._spare = None
        self.outgoing = None          # player still drawing during a takeover
        self.outgoing_frame = None
        self.takeover_started = 0.
        self.takeover_seconds = self.TAKEOVER_SECONDS
        self.frame = None
        self.previous_frame = None
        self._hit_image = None
        self._hit_source = None
        self.action = None
        self.serial = 0
        self.fade_started = 0
        self.fade_seconds = .18
        self.speed = 1.
        self.locked = False
        self.dragging = False
        self.press_global = None
        self._closing = False
        self._double_handled = False
        self.tick = QTimer(self)
        self.tick.setSingleShot(True)
        self.tick.setTimerType(Qt.TimerType.PreciseTimer)
        self.tick.timeout.connect(self.animate)
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.setInterval(250)
        self.click_timer.timeout.connect(self.activated)

    @property
    def frame_image(self):
        # Hit testing needs CPU pixels, but painting does not: convert the
        # current frame lazily instead of copying ~1 MB on every frame.
        if self.frame is None:
            return None
        if self._hit_source is not self.frame:
            self._hit_image = self.frame.toImage()
            self._hit_source = self.frame
        return self._hit_image

    @property
    def decode_size(self):
        return min(512, max(256, round(self.width() * self.devicePixelRatioF())))

    @property
    def taking_over(self):
        return self.outgoing is not None

    def spare_player(self):
        """A second player that shares the decoded-loop and first-frame caches."""
        if self._spare is None:
            self._spare = StreamPlayer()
            self._spare.loop_cache = self.player.loop_cache
            self._spare.first = self.player.first
        return self._spare

    def play(self, key, blend=True, takeover=False):
        item = self.pack.actions[key]
        held = self.dragging and key == self.pack.data.get('drag') and item.get('dragLoopFile')
        takeover = takeover and self.frame is not None and self.action != key and self.isVisible()
        if takeover:
            self.end_takeover()
            outgoing, self.player, self._spare = self.player, self.spare_player(), None
        try:
            options = dict(start_frame=item['dragStartFrame'],end_frame=item['dragLoopEnd']) if held else {}
            frame = self.player.start(self.pack.path(item), self.decode_size,
                                      item['durationMs'] / 1000, cache_loop=item.get('loop', False),**options)
        except (OSError, ValueError) as error:
            if takeover:
                self._spare, self.player = self.player, outgoing
            self.playbackFailed.emit(str(error))
            return False
        self.serial += 1
        if takeover:
            self.outgoing, self.outgoing_frame = outgoing, self.frame
            self.takeover_started = time.perf_counter()
            self.takeover_seconds = .12 if held else self.TAKEOVER_SECONDS
            self.previous_frame = None
        else:
            self.end_takeover()
            self.previous_frame = self.frame if blend and self.action != key else None
        self.fade_started = time.perf_counter()
        self.action = key
        self.frame = frame
        self.update()
        self.schedule()
        return True

    def end_takeover(self):
        if self.outgoing is not None:
            self.outgoing.close()
            self._spare = self.outgoing
            self.outgoing = self.outgoing_frame = None

    def schedule(self):
        if self._closing or (self.dragging and self.action != self.pack.data.get('drag')) or not self.isVisible():
            return
        delay = self.player.next_delay_ms(self.speed)
        if self.previous_frame is not None or self.outgoing is not None:
            delay = min(16, delay)
        self.tick.start(delay)

    def animate(self):
        if self._closing or (self.dragging and self.action != self.pack.data.get('drag')):
            return
        if self.previous_frame is not None:
            # Keep the incoming reference pose still during the handoff. Its
            # actual entrance starts only once the old idle pose has settled.
            self.player.last_clock = time.perf_counter()
            if time.perf_counter() - self.fade_started < self.fade_seconds:
                self.update()
                self.tick.start(16)
                return
            self.previous_frame = None
        if self.outgoing is not None:
            if time.perf_counter()-self.takeover_started >= self.takeover_seconds:
                self.end_takeover()
            else:
                frame, _ = self.outgoing.advance(self.decode_size, self.speed)
                if frame is not None:
                    self.outgoing_frame = frame
        serial = self.serial
        frame, ended = self.player.advance(self.decode_size, self.speed)
        if frame is not None:
            self.frame = frame
        if ended:
            item = self.pack.actions.get(self.action,{})
            if self.dragging and self.action == self.pack.data.get('drag') and item.get('dragLoopFile') and not self.player.error:
                try:
                    self.frame=self.player.start(self.pack.path({'file':item['dragLoopFile']}),self.decode_size,
                                                 cache_loop=True,end_frame=item['dragLoopFrames']-1)
                    self.update();self.schedule();return
                except (OSError,ValueError) as error:
                    self.playbackFailed.emit(str(error))
            self.end_takeover()
            if self.player.error:
                self.playbackFailed.emit('动画解码失败：' + self.player.error)
            self.playbackFinished.emit(self.action or '')
        self.update()
        if not ended and self.serial == serial:
            self.schedule()

    def paintEvent(self, event):
        if self.frame is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        under, progress = None, 1.
        if self.previous_frame is not None:
            under = self.previous_frame
            progress = smooth((time.perf_counter() - self.fade_started) / self.fade_seconds)
        elif self.outgoing_frame is not None:
            under = self.outgoing_frame
            progress = smooth((time.perf_counter() - self.takeover_started) / self.takeover_seconds)
        if under is not None:
            # Overlap dissolve: the new pose arrives over the first half while
            # the old one stays solid, then the old remnants fade. Where both
            # poses cover a pixel it never turns see-through (a plain or
            # additive crossfade dips there on a transparent window).
            painter.setOpacity(min(1., 2*(1-progress)))
            painter.drawPixmap(self.rect(), under)
            painter.setOpacity(min(1., 2*progress))
        painter.drawPixmap(self.rect(), self.frame)

    def opaque_at(self, x, y):
        image = self.frame_image
        if image is None or not (0 <= x < self.width() and 0 <= y < self.height()):
            return False
        px = min(image.width() - 1, int(x * image.width() / self.width()))
        py = min(image.height() - 1, int(y * image.height() / self.height()))
        return image.pixelColor(px, py).alpha() > 30

    def nativeEvent(self, kind, message):
        if kind in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x84:  # WM_NCHITTEST: do not block desktop in empty art pixels.
                x, y = message_position(msg.lParam)
                point = client_position(msg.hWnd, x, y, self.width(), self.height())
                if point is not None and not self.opaque_at(*point):
                    return True, -1  # HTTRANSPARENT
        return super().nativeEvent(kind, message)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_global = event.globalPosition().toPoint()
            self.press_position = self.pos()
            self.dragging = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.press_global is None or self.locked:
            return
        delta = event.globalPosition().toPoint() - self.press_global
        if not self.dragging and delta.manhattanLength() >= QApplication.startDragDistance():
            self.dragging = True
            self.click_timer.stop()
            self.tick.stop()
            self.dragged.emit()
        if self.dragging:
            self.move(self.constrained(self.press_position + delta))
            self.positionChanged.emit()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        was_dragging = self.dragging
        self.press_global = None
        self.dragging = False
        was_double = self._double_handled
        self._double_handled = False
        if was_dragging:
            self.player.last_clock = time.perf_counter()
            self.previous_frame = None
            self.end_takeover()
            self.dragFinished.emit()
            self.schedule()
        elif not was_double and not self.click_timer.isActive():
            self.click_timer.start()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.click_timer.stop()
            self._double_handled = True
            self.doubleActivated.emit()

    def contextMenuEvent(self, event):
        self.click_timer.stop()
        self.contextRequested.emit(event.globalPos())

    def wheelEvent(self, event):
        self.scaleRequested.emit(12 if event.angleDelta().y() > 0 else -12)
        event.accept()

    def constrained(self, point):
        screen = QApplication.screenAt(point + self.rect().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        return QPoint(max(area.left(), min(point.x(), area.right() - self.width() + 1)),
                      max(area.top(), min(point.y(), area.bottom() - self.height() + 1)))

    def resize_canvas(self, size):
        foot = self.pos() + QPoint(self.width() // 2, self.height())
        self.setFixedSize(size, size)
        self.move(self.constrained(foot - QPoint(size // 2, size)))
        self.end_takeover()
        if self.action:
            try:
                frame = self.player.resize(self.decode_size)
                if frame is not None:
                    self.frame = frame
                    self.previous_frame = None
            except (OSError, ValueError) as error:
                self.playbackFailed.emit(str(error))
        self.update()
        self.schedule()

    def showEvent(self, event):
        super().showEvent(event)
        if self.action and self.player.stop.is_set():
            self.play(self.action, blend=False)
        self.player.last_clock = time.perf_counter()
        self.schedule()

    def hideEvent(self, event):
        self.tick.stop()
        self.end_takeover()
        self.player.close()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._closing = True
        self.tick.stop()
        self.click_timer.stop()
        self.end_takeover()
        self.player.close()
        event.accept()
