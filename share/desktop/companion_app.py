"""Behaviour shared by the Claude and Gemini companions.

The character appears first; her card is built right after the first frame.
Manual action choices take over at once with a live crossfade (or wait for
the current tail if the person prefers). Fullscreen programs make her step
aside, which also stops decoding. A subclass supplies the card, icon, lines
and her own touches through small hooks.
"""
import argparse
import hashlib
import os
from pathlib import Path
import random
import sys
import time
import traceback
from PySide6.QtCore import Qt, QTimer, QPoint, QUrl, QRect
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon
from share.pet_engine.action_picker import ActionPicker
from share.pet_engine.action_catalog import populate_action_menu
from share.pet_engine.character_pack import CharacterPack
from .companion_state import SCHEMA, ActionDirector, atomic_json, normalized
from .local_store import LocalStore
from .quota import QuotaWatcher
from .token_report import TokenWatcher
from .context_menu import populate_menu as populate_shared_menu
from .sprite_window import SpriteWindow
from .character_icon import character_icon
from . import desktop_integration as integration

CARD_WARMUP_MS = 60

SHARED_LINES = {
    'settings_failed': '设置暂时无法保存，本次调整仍然有效。',
    'web_failed': '浏览器暂时没有打开，请稍后重试。',
    'playback_failed': '这一段动作暂时无法播放，请换一个动作。',
    'already': '正在做这个动作呢。',
    'autostart_failed': '开机启动没有设置成功，请稍后再试。',
    'autostart_on': '好，下次登录时我会自己出现。',
    'autostart_off': '已取消开机启动。',
    'reset_done': '这一页的设置已恢复默认。',
    'yield_back': '全屏结束啦，我回来了。',
    'back_to_idle': '当前动作收尾后，回到待机。',
    'quota_refreshed': '额度刷新啦，又可以放心用了。',
    'quota_high': '{label}额度已用 {used}%，留一点给重要的事吧。',
}
QUOTA_POLL_MS = 60000
QUOTA_REFRESH_DROP = .15     # used share falling this much means the window reset
QUOTA_HIGH = .8




def install_crash_log(path):
    """A windowed build has no console: keep unexpected errors in diagnostics.log."""
    def record(kind, value, trace):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as stream:
                stream.write(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] unexpected error\n')
                stream.writelines(traceback.format_exception(kind, value, trace))
        except OSError:
            pass
        if sys.stderr is not None:
            sys.__excepthook__(kind, value, trace)
    sys.excepthook = record


def instance_server(name, callback):
    socket = QLocalSocket()
    socket.connectToServer(name)
    if socket.waitForConnected(250):
        socket.write(b'show')
        socket.flush()
        socket.waitForBytesWritten(500)
        return None
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(name):
        raise OSError(server.errorString())
    peers = []
    def incoming():
        peer = server.nextPendingConnection()
        if peer is None:
            return
        peers.append(peer)
        def receive():
            peer.readAll()
            callback()
            peer.disconnectFromServer()
        peer.readyRead.connect(receive)
        peer.disconnected.connect(lambda: peers.remove(peer) if peer in peers else None)
        peer.disconnected.connect(peer.deleteLater)
        if peer.bytesAvailable():
            receive()
    server.newConnection.connect(incoming)
    return server


class CompanionApp:
    CHARACTER = 'pet'
    NAME = '桌宠'
    TITLE = '桌宠'
    APP_NAME = 'DesktopPet'      # data folder, Qt app name and startup entry
    INSTANCE = 'desktop-pet-local'
    WEB_URL = 'https://example.com/'
    WEB_TITLE = '打开网页'
    SCHEMA = SCHEMA
    DEFAULT_SIDE = 'left'        # where she first appears
    LINES = {}
    QUOTA_CELEBRATE = None       # action when the home app's allowance resets
    QUOTA_WORRY = None           # action when it is nearly used up

    def __init__(self, app, state_dir, *, root, tray=True, rng=None, entry=None):
        self.app = app
        self.closing = False
        self.rng = rng or random.Random()
        self.entry = entry
        self.lines = dict(SHARED_LINES, **self.LINES)
        self.store = LocalStore(state_dir, self.SCHEMA)
        self.state_dir = self.store.root
        self.settings = self.store.settings()
        self.pack = CharacterPack(Path(root)/'assets/character')
        self.director = ActionDirector(self.pack.actions, self.pack.idle)
        self.picker = ActionPicker(rng=self.rng)
        self.icon = self.make_icon()
        self._card = None
        self._line = None
        self.timings = {}
        self.yielded = False
        self.yield_override = None
        self.quota = None
        self.quota_watcher = None
        self.tokens = None
        self.card_timer = QTimer()
        self.card_timer.timeout.connect(self.auto_conceal)

        # The character is what people wait for: show her before anything else.
        self.sprite = self.make_sprite()
        self.sprite.setWindowTitle(self.TITLE)
        self.sprite.setWindowIcon(self.icon)
        self.apply_options()
        self.restore_position()
        if self.settings['character_visible']:
            self.sprite.show()
        self.sprite.play(self.pack.idle, blend=False)
        self.sprite.activated.connect(self.poke)
        self.sprite.doubleActivated.connect(self.double_poke)
        self.sprite.contextRequested.connect(self.open_menu)
        self.sprite.positionChanged.connect(self.follow_sprite)
        self.sprite.dragged.connect(self.drag_started)
        self.sprite.dragFinished.connect(self.drag_finished)
        self.sprite.scaleRequested.connect(lambda delta: self.set_option('size', self.settings['size']+delta))
        self.sprite.playbackFinished.connect(self.finished)
        self.sprite.playbackFailed.connect(self.report_error)

        self.save_timer = self.single_shot(350, self.save)
        self.clock_timer = QTimer()
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self.poll)
        self.clock_timer.start()
        self.tray = QSystemTrayIcon(self.icon)
        self.tray.setToolTip(self.NAME)
        self.tray.activated.connect(self.tray_activated)
        self.tray_menu = QMenu()
        self.tray_menu.aboutToShow.connect(lambda: self.populate_menu(self.tray_menu, tray=True))
        self.tray.setContextMenu(self.tray_menu)
        if tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.next_action = time.monotonic()+self.picker.delay(self.settings['random_interval'])
        for screen in app.screens():
            self.watch_screen(screen)
        app.screenAdded.connect(self.watch_screen)
        app.screenRemoved.connect(lambda screen: self.ensure_visible())
        app.aboutToQuit.connect(self.flush)
        QTimer.singleShot(0, lambda: self.mark('first_frame'))
        QTimer.singleShot(CARD_WARMUP_MS, self.warm_up)

    # ---- hooks for a character ----
    def make_icon(self):
        return character_icon(self.pack.path(self.pack.actions[self.pack.idle]))

    def make_sprite(self):
        return SpriteWindow(self.pack, self.settings['size'])

    def create_card(self):
        raise NotImplementedError

    def connect_card(self, card):
        """Wire character-only card signals."""



    def after_drag(self):
        """Called when a drag ends and nothing important is waiting."""

    def drag_release_action(self):
        return None

    def extra_menu(self, menu):
        """Add character-only menu entries."""

    def extra_snapshot(self):
        return {}

    def make_quota_reader(self):
        """A callable returning a QuotaSnapshot from the home app, or None."""
        return None

    def make_token_source(self):
        """A TokenSource for the daily report, or None."""
        return None

    def action_weight(self, key, hour):
        """How likely an action is as a random activity; 0 keeps it manual-only."""
        return 1. if self.pack.actions[key].get('random') else 0.

    def on_option(self, key, value):
        """React to a character-only setting."""

    def message_for(self, key):
        if key == self.pack.idle:
            return self.card.idle_message()
        return self.lines.get(key) or self.card.idle_message()

    # ---- plumbing ----
    @staticmethod
    def single_shot(interval, callback):
        timer = QTimer()
        timer.setSingleShot(True)
        timer.setInterval(interval)
        timer.timeout.connect(callback)
        return timer

    def mark(self, name):
        self.timings.setdefault(name, time.time())

    def watch_screen(self, screen):
        screen.availableGeometryChanged.connect(lambda rect: self.ensure_visible())

    # ---- the card is built lazily, once ----
    @property
    def card_ready(self):
        return self._card is not None

    @property
    def card(self):
        if self._card is None:
            self._card = self.build_card()
            self.mark('card_ready')
        return self._card

    def build_card(self):
        card = self.create_card()
        card.setWindowIcon(self.icon)
        card.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.settings['on_top'])
        card.actionRequested.connect(self.play)
        card.optionChanged.connect(self.set_option)
        card.resetRequested.connect(self.reset_options)
        card.webRequested.connect(self.open_web)
        card.geometry_provider = self.panel_geometry
        card.refreshRequested.connect(self.refresh_card)
        card.layoutChanged.connect(self.position_panel)
        card.contextRequested.connect(self.open_menu)
        self.connect_card(card)
        card.sync_option('autostart', integration.autostart_enabled(self.APP_NAME))
        card.set_action(self.director.current, self.director.pending or self.director.queued)
        if self.quota is not None:
            card.update_quota(self.quota)
        if self.tokens is not None and self.tokens.report is not None:
            card.update_tokens(self.tokens.report)
        if self._line:
            card.say(self._line)
        return card

    def warm_up(self):
        if not self.closing:
            self.card
            # The home-app link is read a moment later, off the startup path.
            QTimer.singleShot(400, self.start_quota)
            QTimer.singleShot(1500, self.start_tokens)

    # ---- the daily token report (local transcripts, background thread) ----
    def start_tokens(self):
        if self.closing or self.tokens is not None:
            return
        source = self.make_token_source()
        if source is None:
            return
        self.tokens = TokenWatcher(source, self.state_dir/'token_cache.json', interval_ms=60000)
        self.tokens.changed.connect(self.tokens_changed)
        self.tokens.start()

    def tokens_changed(self, report):
        if self._card is not None:
            self._card.update_tokens(report)

    # ---- the home app's quota ----
    def start_quota(self):
        if self.closing or not self.settings['quota_link'] or self.quota_watcher is not None:
            return
        reader = self.make_quota_reader()
        if reader is None:
            return
        self.quota_watcher = QuotaWatcher(reader, QUOTA_POLL_MS)
        self.quota_watcher.changed.connect(self.quota_changed)
        self.quota_watcher.start()

    def stop_quota(self):
        if self.quota_watcher is not None:
            self.quota_watcher.stop()
            self.quota_watcher.deleteLater()
            self.quota_watcher = None
        self.quota = None
        if self._card is not None:
            self._card.update_quota(None)
        self.tray.setToolTip(self.NAME)

    def quota_changed(self, change):
        previous, snapshot = change
        self.quota = snapshot
        if self._card is not None:
            self._card.update_quota(snapshot)
        self.tray.setToolTip(self.NAME)
        self.react_to_quota(previous, snapshot)

    def react_to_quota(self, previous, snapshot):
        """Celebrate a reset, warn when an allowance is nearly spent; silent on the first read."""
        if previous is None or not previous.meters or not snapshot.meters:
            return
        before = {m.label: m.used for m in previous.meters}
        refreshed = [m for m in snapshot.meters if before.get(m.label, 0)-m.used >= QUOTA_REFRESH_DROP]
        crossed = [m for m in snapshot.meters if m.used >= QUOTA_HIGH > before.get(m.label, 0)]
        # Act first, speak second: the action's own line must not replace the news.
        if refreshed:
            if self.QUOTA_CELEBRATE in self.pack.actions:
                self.play(self.QUOTA_CELEBRATE, automatic=True)
            self.say(self.lines['quota_refreshed'])
        elif crossed:
            meter = max(crossed, key=lambda m: m.used)
            if self.QUOTA_WORRY in self.pack.actions:
                self.play(self.QUOTA_WORRY, automatic=True)
            self.say(self.lines['quota_high'].format(label=meter.label, used=round(meter.used*100),
                                                     left=round(meter.remaining*100)))

    def say(self, text):
        self._line = text
        if self._card is not None:
            self._card.say(text)



    def show_action(self, current, queued=None):
        if self._card is not None:
            self._card.set_action(current, queued)

    # ---- persistence ----
    def save(self):
        self.settings['position'] = [self.sprite.x(), self.sprite.y()]
        try:
            self.store.save_settings(self.settings)
        except OSError as error:
            self.say(self.lines['settings_failed'])
            self.store.log(f'settings: {error}')

    def flush(self):
        """Write anything still pending; safe to call more than once."""
        self.save_timer.stop()
        self.save()

    # ---- placement ----
    def home_point(self):
        area = self.app.primaryScreen().availableGeometry()
        x = area.left()+40 if self.DEFAULT_SIDE == 'left' else area.right()-self.sprite.width()-40
        return QPoint(x, area.bottom()-self.sprite.height()-24)

    def restore_position(self):
        position = self.settings['position']
        point = QPoint(*position) if position is not None else self.home_point()
        self.sprite.move(self.sprite.constrained(point))

    def ensure_visible(self):
        self.sprite.move(self.sprite.constrained(self.sprite.pos()))
        self.follow_sprite()

    def screen_area(self):
        screen = self.app.screenAt(self.sprite.geometry().center()) or self.app.primaryScreen()
        return screen.availableGeometry()

    def follow_sprite(self):
        self.position_panel()

    def position_panel(self):
        if self._card is None:
            return
        self._card.reposition()

    def panel_geometry(self, size):
        """Use the same above/below character anchor as Gpt's card."""
        area = self.screen_area()
        x = self.sprite.x()+(self.sprite.width()-size.width())//2
        y = self.sprite.y()-size.height()-8
        if y < area.top()+8:
            y = self.sprite.y()+self.sprite.height()+8
        x = max(area.left()+8, min(x, area.right()-size.width()-7))
        y = max(area.top()+8, min(y, area.bottom()-size.height()-7))
        return QRect(x, y, size.width(), size.height())

    def recover(self):
        found = integration.fullscreen_foreground()
        self.yield_override = found[0] if found else None
        self.yielded = False
        self.settings['character_visible'] = self.settings['bubble'] = True
        self.save_timer.start()
        self.sprite.show()
        self.sprite.raise_()
        self.ensure_visible()
        self.show_panel(0)

    # ---- options ----
    def apply_options(self):
        windows = [self.sprite] + ([self._card] if self._card is not None else [])
        for window in windows:
            shown = window.isVisible()
            window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.settings['on_top'])
            if shown:
                window.show()
        self.sprite.setWindowOpacity(self.settings['opacity']/100)
        self.sprite.speed = self.settings['playback_speed']
        self.sprite.locked = self.settings['lock_position']
        self.card_timer.setInterval(self.settings['card_hide_delay']*1000)

    def set_option(self, key, value):
        if key == 'autostart':
            return self.set_autostart(bool(value))
        if key not in self.settings:
            return
        self.settings = normalized(dict(self.settings, **{key: value}), self.SCHEMA)
        if key == 'character_visible':
            self.sprite.setVisible(bool(self.settings[key]) and not self.yielded)
        elif key == 'bubble':
            if self.settings[key]:
                self.show_panel(0)
            elif self._card is not None:
                self._card.hide()
        elif key == 'size':
            self.sprite.resize_canvas(self.settings['size'])
            self.follow_sprite()
        elif key in ('on_top', 'opacity', 'playback_speed', 'lock_position', 'card_hide_delay'):
            self.apply_options()
        elif key == 'random_interval':
            self.next_action = time.monotonic()+self.picker.delay(self.settings['random_interval'])
        elif key == 'fullscreen_yield' and not self.settings[key] and self.yielded:
            self.end_yield()
        elif key == 'quota_link':
            self.start_quota() if self.settings[key] else self.stop_quota()
        if self._card is not None:
            self._card.sync_option(key, self.settings[key])
        self.on_option(key, self.settings[key])
        self.save_timer.start()

    def reset_options(self, keys):
        defaults = normalized({}, self.SCHEMA)
        for key in keys:
            if key == 'autostart':
                continue
            if key in defaults and self.settings.get(key) != defaults[key]:
                self.set_option(key, defaults[key])
        self.say(self.lines['reset_done'])

    def set_autostart(self, enabled):
        try:
            entry = self.entry or Path(sys.argv[0]).resolve()
            integration.set_autostart(self.APP_NAME, enabled, integration.launch_command(entry),
                                      Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(entry).parent)
            self.say(self.lines['autostart_on' if enabled else 'autostart_off'])
        except OSError as error:
            self.store.log(f'autostart: {error}')
            self.say(self.lines['autostart_failed'])
        if self._card is not None:
            self._card.sync_option('autostart', integration.autostart_enabled(self.APP_NAME))

    # ---- actions ----
    def play(self, key, *, automatic=False, completion=False):
        if key == self.pack.idle and self.director.current == key and self.sprite.action == key:
            self.say(self.message_for(key))
            return True
        manual = not automatic and not completion
        busy = self.director.current != self.pack.idle
        interrupt = manual and self.settings['instant_switch']
        requested = self.director.request(key, automatic=automatic, completion=completion,
                                          dragging=self.sprite.dragging, interrupt=interrupt)
        if requested is None:
            if manual and key == self.director.current:
                self.say(self.lines['already'])
            self.show_action(self.director.current, self.director.pending or self.director.queued)
            return False
        if self.sprite.play(requested, takeover=busy):
            self.show_action(key, self.director.pending)
            self.say(self.message_for(key))
            self.next_action = time.monotonic()+self.picker.delay(self.settings['random_interval'])
            return True
        self.director.current = self.pack.idle
        return False

    def finished(self, key):
        if self.sprite.dragging and key == self.pack.data.get('drag'):
            self.sprite.play(key, blend=False)
            return
        following = self.director.finished()
        if following == self.pack.idle and key != following:
            # A breather after every action, however long it ran.
            self.next_action = max(self.next_action, time.monotonic()+self.settings['random_interval']*.35)
        outgoing = self.pack.actions.get(key, {})
        incoming = self.pack.actions[following]
        matched = outgoing.get('referencePose') and outgoing.get('referencePose') == incoming.get('referencePose')
        self.sprite.play(following, blend=key != following and not matched)
        self.show_action(following, self.director.pending or self.director.queued)
        if key != following and self.speaks_on_finish():
            self.say(self.message_for(following))

    def speaks_on_finish(self):
        return True

    def refresh_card(self):
        if self.quota_watcher is not None:
            self.quota_watcher.poll()
        if self.tokens is not None:
            self.tokens.refresh()
        if self.director.current != self.pack.idle:
            if self.settings['instant_switch']:
                self.director.current = self.pack.idle
                self.director.queued = None
                self.sprite.play(self.pack.idle, takeover=True)
                self.say(self.card.idle_message())
            else:
                self.director.queued = self.pack.idle
                self.say(self.lines['back_to_idle'])
        else:
            self.say(self.card.idle_message())
        self.show_action(self.director.current, self.director.pending or self.director.queued)

    def poke(self):
        if self.card.isVisible():
            self.card.dismiss()
        else:
            self.show_panel(0)
            action = self.settings.get('poke_action')
            if self.director.current == self.pack.idle and action in self.pack.actions:
                self.play(action)

    def double_poke(self):
        action = self.settings.get('double_action')
        if action in self.pack.actions:
            self.play(action)

    def drag_started(self):
        if self._card is not None:
            self._card.hide()
        key = self.pack.data.get('drag')
        if key in self.pack.actions and self.sprite.play(key, takeover=True):
            self.director.current = key
            self.show_action(key, self.director.pending or self.director.queued)

    def drag_finished(self):
        self.save_timer.start()
        if self.director.current == self.pack.data.get('drag'):
            item=self.pack.actions[self.director.current]
            if item.get('dragLoopFile'):
                following=self.director.finished()
                self.sprite.play(following,takeover=True)
                self.show_action(following,self.director.pending or self.director.queued)
                return
            release = self.drag_release_action()
            if release in self.pack.actions and not self.director.pending and not self.director.queued:
                self.director.queued = release
            self.show_action(self.director.current, self.director.pending or self.director.queued)
            return
        if self.director.pending and self.director.current == self.pack.idle:
            self.sprite.play(self.director.finished())
        elif not self.director.pending:
            self.after_drag()

    def show_panel(self, page=None):
        if page in (None, 0) and not self.settings['bubble']:
            return
        card = self.card
        card.reveal(page)
        self.card_timer.start(self.settings['card_hide_delay']*1000)

    def auto_conceal(self):
        card = self._card
        if card is None or card.underMouse() or card.pages.currentIndex() in card.STAY_OPEN:
            return
        card.dismiss()
        self.card_timer.stop()



    def random_activity(self, now):
        hour = time.localtime().tm_hour
        weights = {key: self.action_weight(key, hour) for key in self.pack.actions if key != self.pack.idle}
        pool = [self.pack.actions[key] for key, weight in weights.items() if weight > 0]
        chosen = self.picker.pick(pool, weight=lambda item: weights[item['id']])
        if chosen:
            self.play(chosen['id'], automatic=True)

    def can_act_alone(self):
        return (self.settings['random_actions'] and not self.yielded and self.sprite.isVisible()
                and not self.sprite.dragging and self.director.current == self.pack.idle)

    def poll(self):
        self.check_fullscreen()
        now = time.monotonic()
        if now >= self.next_action and self.can_act_alone():
            self.next_action = now+self.picker.delay(self.settings['random_interval'])
            self.random_activity(now)

    # ---- stepping aside for fullscreen programs ----
    def check_fullscreen(self):
        if self.closing or not self.settings['fullscreen_yield']:
            return
        found = integration.fullscreen_foreground()
        if found is None:
            self.yield_override = None
            if self.yielded:
                self.end_yield()
            return
        hwnd, monitor = found
        covering = monitor == integration.monitor_of(int(self.sprite.winId()))
        if covering and hwnd != self.yield_override and not self.yielded:
            self.yielded = True
            self.sprite.hide()
            if self._card is not None:
                self._card.hide()
            self.on_yield()
        elif self.yielded and (not covering or hwnd == self.yield_override):
            self.end_yield()

    def on_yield(self):
        """Stop character-only overlays while a fullscreen program runs."""

    def end_yield(self):
        self.yielded = False
        if self.settings['character_visible']:
            self.sprite.show()
        self.say(self.lines['yield_back'])

    # ---- menus, web, errors ----
    def menu_command(self, menu, command):
        labels = dict(status='查看状态', settings='桌宠设置…', character='显示人物',
                      pin='始终置顶', lock='锁定人物位置（含拖动）', bubble='显示气泡',
                      recover='找回全部组件', position='回到当前屏幕右下角', quit='退出'+self.NAME,
                      walk='暂停自主活动' if self.settings['random_actions'] else '恢复自主活动')
        action = menu.addAction(labels[command]); action.setObjectName('command_'+command)
        key = dict(character='character_visible', pin='on_top', lock='lock_position', bubble='bubble').get(command)
        if key:
            action.setCheckable(True); action.setChecked(self.settings[key])
        action.triggered.connect(lambda value=False, c=command: QTimer.singleShot(0, self.sprite, lambda: self.execute_command(c, value)))
        return action

    def execute_command(self, command, checked=False):
        keys = dict(character='character_visible', pin='on_top', lock='lock_position', bubble='bubble')
        if command in keys:
            self.set_option(keys[command], checked)
        elif command == 'walk':
            self.set_option('random_actions', not self.settings['random_actions'])
        elif command == 'settings':
            self.show_panel(self.card.PAGE_SETTINGS)
        elif command == 'position':
            area = self.screen_area()
            self.sprite.move(self.sprite.constrained(QPoint(area.right()-self.sprite.width()-24, area.bottom()-self.sprite.height()-24)))
            self.follow_sprite(); self.save_timer.start()
        elif command in ('status', 'recover'):
            self.recover()
        elif command == 'quit':
            self.shutdown()

    def populate_menu(self, menu, tray=False):
        populate_shared_menu(menu, self.menu_command,
                            lambda actions: populate_action_menu(actions, self.pack.actions.values(), lambda item: self.play(item['id'])),
                            tray=tray)

    def open_menu(self, point):
        menu = QMenu()
        self.populate_menu(menu)
        menu.exec(point)

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.recover()

    def open_web(self):
        if not QDesktopServices.openUrl(QUrl(self.settings['web_url'] or self.WEB_URL)):
            self.say(self.lines['web_failed'])

    def report_error(self, text):
        self.say(self.lines['playback_failed'])
        self.store.log(f'playback: {text}')

    def snapshot(self):
        return dict(character=self.CHARACTER, current_action=self.sprite.action, actions=len(self.pack.actions),
                    position=[self.sprite.x(), self.sprite.y()], size=self.sprite.width(),
                    panel_visible=self.card_ready and self._card.isVisible(), card_ready=self.card_ready,
                    decoder_queue=self.sprite.player.frames.qsize(),
                    source_frame=self.sprite.player.frame_index, timings=dict(self.timings),
                    independent_state_dir=str(self.state_dir),
                    quota_connected=bool(self.quota and self.quota.connected),
                    tokens_ready=bool(self.tokens and self.tokens.report and not self.tokens.report.get('error')),
                    editor_tabs=[self.card.settings_panel.tabs.tabText(i) for i in range(self.card.settings_panel.tabs.count())] if self.card_ready else [],
                    editor_navigation=[item.text() for item in self.card.navigation_buttons] if self.card_ready else [],
                    **self.extra_snapshot())

    def close_extras(self):
        """Close character-only windows on exit."""

    def shutdown(self):
        if self.closing:
            return
        self.closing = True
        self.clock_timer.stop()
        self.card_timer.stop()
        if self.quota_watcher is not None:
            self.quota_watcher.stop()
        if self.tokens is not None:
            self.tokens.stop()
        self.flush()
        self.close_extras()
        self.tray.hide()
        if self._card is not None:
            self._card.close()
        self.sprite.close()
        self.app.quit()


def default_state_dir(app_name):
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))/app_name


def run(companion_class, *, source_root, bundle_root, entry, argv=None, configure=None, started=None):
    """Shared entry point: arguments, state folder, single instance, smoke tests and captures."""
    launched = time.time()
    parser = argparse.ArgumentParser(description=companion_class.TITLE)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--capture-dir', type=Path)
    parser.add_argument('--no-tray', action='store_true')
    parser.add_argument('--show-panel', action='store_true')
    if configure:
        configure(parser)
    args = parser.parse_args(argv)
    if args.state_dir:
        state = args.state_dir
    elif args.smoke_test:
        if getattr(sys, 'frozen', False):
            import tempfile
            state = Path(tempfile.gettempdir())/f'{companion_class.APP_NAME}-smoke'
        else:
            state = Path(source_root)/'build/smoke-state'
    else:
        state = default_state_dir(companion_class.APP_NAME)
    install_crash_log(state/'diagnostics.log')
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(companion_class.APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    from .typography import install_ui_font
    install_ui_font(app)
    name = companion_class.INSTANCE
    if args.smoke_test or args.state_dir:
        name += '-'+hashlib.sha256(str(state.resolve()).encode()).hexdigest()[:12]
    companion = None
    try:
        server = instance_server(name, lambda: companion.recover() if companion else None)
        if server is None:
            return 0
        companion = companion_class(app, state, root=bundle_root, tray=not args.no_tray, entry=entry)
        companion.timings['launched'] = launched
    except (OSError, ValueError, KeyError) as error:
        if args.smoke_test:
            print(str(error), file=sys.stderr)
        else:
            QMessageBox.critical(None, f'{companion_class.NAME}启动失败', str(error))
        return 1
    if args.show_panel or args.capture_dir:
        QTimer.singleShot(250, companion.show_panel)
    if started:
        started(companion, args)
    if args.capture_dir:
        QTimer.singleShot(1400, lambda: capture(companion, app, args.capture_dir))
    if args.smoke_test:
        def record():
            atomic_json(state/'smoke-result.json', companion.snapshot())
            companion.shutdown()
        QTimer.singleShot(2800, record)
    result = app.exec()
    server.close()
    return result


def capture(companion, app, folder):
    folder.mkdir(parents=True, exist_ok=True)
    prefix = companion.CHARACTER
    companion.sprite.grab().save(str(folder/f'{prefix}-pet.png'))
    card = companion.card
    for index, key in ((0,'card'),(card.PAGE_SETTINGS,'settings')):
        card.set_page(index)
        card.finish_transition()
        sections = getattr(card, 'settings_panel', None)
        app.processEvents()
        app.processEvents()
        card.grab().save(str(folder/f'{prefix}-{key}.png'))
        if sections is not None and index == card.PAGE_SETTINGS:
            for part in range(1, sections.stack.count()):
                sections.switch.set_index(part)
                card.set_page(index)
                card.finish_transition()
                app.processEvents()
                app.processEvents()
                card.grab().save(str(folder/f'{prefix}-{key}-{part}.png'))
            sections.advanced_button.setChecked(True);app.processEvents();app.processEvents()
            card.grab().save(str(folder/f'{prefix}-settings-advanced.png'))
            sections.advanced_button.setChecked(False)
            sections.switch.set_index(0)
    card.show_status(True);card.finish_transition();app.processEvents();app.processEvents()
    card.grab().save(str(folder/f'{prefix}-status.png'))
    card.set_page(0)
    card.finish_transition()
