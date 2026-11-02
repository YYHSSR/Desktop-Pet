import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'app'), str(ROOT.parent)]
from datetime import date
from model import (FocusClock, ActionDirector, normalized, atomic_json, load_settings,
                   time_greeting, week_key, load_focus_record)
from share.desktop import desktop_integration

# Tests never look at the real foreground window or write to the real Startup folder.
STARTUP = tempfile.TemporaryDirectory(prefix='gemini-startup-')
desktop_integration.startup_folder = lambda: Path(STARTUP.name)
desktop_integration.fullscreen_foreground = lambda: None


class FocusTests(unittest.TestCase):
    def test_pause_retains_time_and_resume_excludes_break(self):
        clock = FocusClock()
        clock.start(2, now=10)
        clock.pause(now=40)
        self.assertEqual(clock.remaining(now=4000), 90)
        clock.resume(now=5000)
        self.assertEqual(clock.remaining(now=5020), 70)
        self.assertFalse(clock.poll(now=5089))
        self.assertTrue(clock.poll(now=5090))
        self.assertFalse(clock.poll(now=6000))

    def test_reset_does_not_count_an_abandoned_session(self):
        clock = FocusClock()
        clock.start(1, now=0)
        clock.reset()
        self.assertFalse(clock.poll(now=1000))
        self.assertEqual(clock.state, 'idle')
        self.assertEqual(clock.remaining(now=1000), 60)

    def test_monotonic_clock_regression_cannot_add_time(self):
        clock = FocusClock()
        clock.start(1, now=10)
        self.assertEqual(clock.remaining(now=9), 60)


class StarJarTests(unittest.TestCase):
    def test_every_hour_has_a_cat_greeting(self):
        for hour in range(24):
            self.assertIn('喵', time_greeting(hour))
        self.assertNotEqual(time_greeting(8), time_greeting(20))

    def test_week_stars_survive_a_new_day_but_reset_next_week(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'focus.json'
            atomic_json(path, dict(date='2026-10-27', sessions=2, minutes=50,
                                   week=week_key(date(2026, 10, 27)), week_stars=5))
            self.assertEqual(load_focus_record(path, date(2026, 10, 27)), (2, 50, 5))
            self.assertEqual(load_focus_record(path, date(2026, 10, 29)), (0, 0, 5))
            self.assertEqual(load_focus_record(path, date(2026, 11, 2)), (0, 0, 0))

    def test_old_and_corrupt_records_are_tolerated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'focus.json'
            atomic_json(path, dict(date='2026-10-31', sessions=3, minutes=75))
            self.assertEqual(load_focus_record(path, date(2026, 10, 31)), (3, 75, 3))
            atomic_json(path, dict(date='2026-10-31', sessions='x', minutes=True, week_stars=[1]))
            self.assertEqual(load_focus_record(path, date(2026, 10, 31)), (0, 0, 0))
            path.write_text('[1, 2]')
            self.assertEqual(load_focus_record(path, date(2026, 10, 31)), (0, 0, 0))


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.director = ActionDirector(dict(idle={}, meow={}, catch={}, hop={}))

    def test_background_action_never_interrupts_interaction(self):
        self.assertEqual(self.director.request('meow'), 'meow')
        self.assertIsNone(self.director.request('hop', automatic=True))
        self.assertEqual(self.director.current, 'meow')

    def test_completion_waits_for_current_action_then_runs_before_idle(self):
        self.director.request('meow')
        self.assertIsNone(self.director.request('catch', completion=True))
        self.assertEqual(self.director.finished(), 'catch')
        self.assertEqual(self.director.finished(), 'idle')

    def test_drag_defers_completion_and_ignores_random_action(self):
        self.assertIsNone(self.director.request('catch', completion=True, dragging=True))
        self.assertIsNone(self.director.request('hop', automatic=True, dragging=True))
        self.assertEqual(self.director.finished(), 'catch')

    def test_unknown_action_cannot_replace_registered_action(self):
        self.director.request('meow')
        self.assertIsNone(self.director.request('../unknown'))
        self.assertEqual(self.director.current, 'meow')

    def test_manual_actions_wait_for_the_current_tail_and_keep_latest_choice(self):
        self.director.request('meow')
        self.assertIsNone(self.director.request('hop'))
        self.assertEqual(self.director.current, 'meow')
        self.assertIsNone(self.director.request('catch'))
        self.assertEqual(self.director.finished(), 'catch')
        self.assertEqual(self.director.finished(), 'idle')

    def test_completion_takes_priority_without_losing_the_queued_manual_action(self):
        self.director.request('meow')
        self.director.request('hop')
        self.director.request('catch', completion=True)
        self.assertEqual(self.director.finished(), 'catch')
        self.assertEqual(self.director.finished(), 'hop')
        self.assertEqual(self.director.finished(), 'idle')


class SettingsTests(unittest.TestCase):
    def test_invalid_json_does_not_prevent_starting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'settings.json'
            path.write_text('{broken', encoding='utf-8')
            self.assertEqual(load_settings(path)['size'], 300)

    def test_untrusted_values_are_bounded_and_unknown_keys_are_discarded(self):
        settings = normalized(dict(size=float('nan'), opacity=-10, on_top='false',
                                   random_interval=1e8, position=[0, 'a'], api_key='discard'))
        self.assertEqual(settings['size'], 300)
        self.assertEqual(settings['opacity'], 65)
        self.assertTrue(settings['on_top'])
        self.assertIsNone(settings['position'])
        self.assertTrue(settings['wander'])
        self.assertNotIn('api_key', settings)
        self.assertNotIn('random_interval', settings)

    def test_atomic_save_can_be_read_without_touching_other_role(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chatgpt = root/'BailongEnhanced/settings.json'
            atomic_json(chatgpt, {'marker': 'existing'})
            gemini = root/'GeminiDesktopPet/settings.json'
            atomic_json(gemini, dict(size=340, position=[-1200, 500]))
            self.assertEqual(load_settings(gemini)['position'], [-1200, 500])
            self.assertEqual(json.loads(chatgpt.read_text()), {'marker': 'existing'})
            self.assertFalse(gemini.with_suffix('.tmp').exists())


from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QPoint
from share.pet_engine.character_pack import CharacterPack
from share.desktop.sprite_window import SpriteWindow
APP = QApplication.instance() or QApplication([])
from share.desktop.typography import install_ui_font
install_ui_font(APP)


def fixture(root):
    assets = root/'assets/character'
    assets.mkdir(parents=True)
    frames = []
    for value in (100, 130, 160):
        image = Image.new('RGBA', (512, 512))
        ImageDraw.Draw(image).ellipse((96, 64, 416, 480), fill=(value, 90, 210, 255))
        frames.append(image)
    path = assets/'test.webp'
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=42, lossless=True)
    import hashlib
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    keys = ('idle', 'pout', 'curious', 'meow', 'hop', 'catch')
    actions = [dict(id=key, name=key, group='test', file='test.webp', durationMs=126,
                    frames=3, loop=key=='idle', random=key=='meow', bytes=path.stat().st_size,
                    sha256=checksum) for key in keys]
    (assets/'character.json').write_text(json.dumps(dict(idle='idle', actions=actions)), encoding='utf-8')
    return assets


class ResourceTests(unittest.TestCase):
    def test_every_frame_and_checksum_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = CharacterPack(fixture(Path(directory)))
            self.assertEqual(len(pack.verify()), 6)
            (pack.root/'test.webp').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, '校验失败'):
                pack.verify()

    def test_descriptor_cannot_read_outside_character_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = fixture(Path(directory))
            data = json.loads((assets/'character.json').read_text())
            data['actions'][0]['file'] = '../outside.webp'
            (assets/'character.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, '越界'):
                CharacterPack(assets)


class SpriteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.sprite = SpriteWindow(CharacterPack(fixture(Path(self.temporary.name))))
        self.sprite.show()
        self.sprite.play('idle')
        APP.processEvents()

    def tearDown(self):
        self.sprite.close()
        APP.processEvents()
        from share.pet_engine.decode_runtime import STATS
        STATS.drain()
        self.temporary.cleanup()

    def test_transparent_canvas_does_not_hit_and_character_does(self):
        self.assertFalse(self.sprite.opaque_at(0, 0))
        self.assertTrue(self.sprite.opaque_at(150, 150))
        self.assertFalse(self.sprite.opaque_at(-1, 150))

    def test_hidden_then_recovered_character_has_a_new_running_decoder(self):
        original_stop = self.sprite.player.stop
        self.sprite.hide()
        self.assertTrue(original_stop.is_set())
        self.sprite.show()
        APP.processEvents()
        self.assertIsNot(self.sprite.player.stop, original_stop)
        self.assertFalse(self.sprite.player.stop.is_set())

    def test_size_change_preserves_feet_and_uses_bounded_decode_canvas(self):
        self.sprite.move(80, 80)
        foot = self.sprite.y()+self.sprite.height()
        self.sprite.resize_canvas(240)
        self.assertEqual(self.sprite.y()+self.sprite.height(), foot)
        self.assertLessEqual(self.sprite.decode_size, 512)

    def test_drag_moves_character_without_emitting_a_click(self):
        clicked, released = [], []
        self.sprite.activated.connect(lambda: clicked.append(True))
        self.sprite.dragFinished.connect(lambda: released.append(True))
        self.sprite.move(40, 40)
        before = self.sprite.pos()
        QTest.mousePress(self.sprite, Qt.MouseButton.LeftButton, pos=QPoint(150, 150))
        QTest.mouseMove(self.sprite, QPoint(240, 150), delay=10)
        QTest.mouseRelease(self.sprite, Qt.MouseButton.LeftButton, pos=QPoint(240, 150))
        QTest.qWait(300)
        self.assertNotEqual(self.sprite.pos(), before)
        self.assertEqual(released, [True])
        self.assertEqual(clicked, [])

    def test_double_click_does_not_also_toggle_the_panel(self):
        single, double = [], []
        self.sprite.activated.connect(lambda: single.append(True))
        self.sprite.doubleActivated.connect(lambda: double.append(True))
        QTest.mouseDClick(self.sprite, Qt.MouseButton.LeftButton, pos=QPoint(150, 150))
        QTest.mouseRelease(self.sprite, Qt.MouseButton.LeftButton, pos=QPoint(150, 150))
        QTest.qWait(300)
        self.assertEqual(double, [True])
        self.assertEqual(single, [])

    def test_a_cut_has_no_fade_and_a_blend_never_freezes_the_incoming_clip(self):
        self.sprite.play('curious', blend=False)
        self.assertIsNone(self.sprite.outgoing)
        old = self.sprite.player
        self.sprite.play('meow')
        self.assertIs(self.sprite.outgoing, old)
        pump(150)
        self.assertGreater(self.sprite.player.frame_index, 0)


def pump(ms):
    """Run the event loop while letting decoder threads have the GIL (QTest.qWait keeps it)."""
    end = time.perf_counter()+ms/1000
    while time.perf_counter() < end:
        APP.processEvents()
        time.sleep(.004)


def _varint(value):
    out = bytearray()
    while True:
        byte, value = value & 0x7f, value >> 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _field(number, payload):
    if isinstance(payload, int):
        return _varint(number << 3) + _varint(payload)
    if isinstance(payload, float):
        import struct
        return _varint(number << 3 | 5) + struct.pack('<f', payload)
    payload = payload.encode() if isinstance(payload, str) else payload
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def antigravity_status(models, plan='Google AI Pro', email='someone@example.com'):
    """A user status shaped like Antigravity's cache: base64(outer{key, value{base64(inner)}})."""
    import base64
    inner = _field(3, email)
    for label, remaining, reset in models:
        quota = _field(1, remaining) + _field(2, _field(1, reset))
        inner += _field(4, _field(1, label) + _field(2, _field(1, 1000)) + _field(15, quota))
    inner += _field(5, _field(1, 'g1-pro-tier') + _field(2, plan) + _field(3, plan))
    wrapped = _field(1, _field(1, 'userStatusSentinelKey') + _field(2, _field(1, base64.b64encode(inner).decode())))
    return base64.b64encode(wrapped).decode()


class AntigravityTests(unittest.TestCase):
    MODELS = [('Gemini 3.8 Flash (High)', .4, 1_800_000_000), ('Gemini 3.8 Flash (Low)', .4, 1_800_000_000),
              ('Claude Opus 4.6 (Thinking)', .15, 1_800_003_600)]

    def database(self, directory, value):
        import sqlite3
        path = Path(directory)/'state.vscdb'
        connection = sqlite3.connect(path)
        connection.execute('CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)')
        connection.execute('INSERT INTO ItemTable VALUES (?, ?)', ('antigravityUnifiedStateSync.userStatus', value))
        connection.execute('INSERT INTO ItemTable VALUES (?, ?)', ('antigravityUnifiedStateSync.oauthToken', 'secret'))
        connection.commit()
        connection.close()
        return path

    def test_plan_and_model_quota_are_decoded_without_the_email(self):
        from antigravity_link import AntigravityQuotaReader, decode
        plan, models = decode(antigravity_status(self.MODELS))
        self.assertEqual(plan, 'Google AI Pro')
        self.assertEqual([m[0] for m in models], [m[0] for m in self.MODELS])
        self.assertAlmostEqual(models[2][1], .15, places=5)
        with tempfile.TemporaryDirectory() as directory:
            path = self.database(directory, antigravity_status(self.MODELS))
            snapshot = AntigravityQuotaReader(str(path), running=lambda: True)()
            self.assertTrue(snapshot.connected and snapshot.running)
            self.assertEqual(snapshot.plan, 'Google AI Pro')
            self.assertEqual(snapshot.meters[0].label, 'Gemini 3.8 Flash · 高')
            self.assertAlmostEqual(snapshot.lowest_remaining, .15, places=5)
            self.assertNotIn('example.com', repr(snapshot))
            self.assertNotIn('secret', repr(snapshot))

    def test_broken_or_missing_cache_is_reported_not_raised(self):
        from antigravity_link import AntigravityQuotaReader
        with tempfile.TemporaryDirectory() as directory:
            path = self.database(directory, 'not-base64!!')
            snapshot = AntigravityQuotaReader(str(path), running=lambda: False)()
            self.assertFalse(snapshot.meters)
            missing = AntigravityQuotaReader(str(Path(directory)/'none.vscdb'), running=lambda: False)()
            self.assertFalse(missing.connected)

    def test_variants_with_the_same_quota_share_one_row(self):
        from share.desktop.card_kit import grouped_meters
        from share.desktop.quota import Meter
        rows = grouped_meters([Meter('Gemini 3.8 Flash · 高', .6), Meter('Gemini 3.8 Flash · 低', .6),
                               Meter('Claude Opus 4.6 · 思考', .85)])
        self.assertEqual([row['label'] for row in rows], ['Gemini 3.8 Flash · 高/低', 'Claude Opus 4.6 · 思考'])


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        fixture(self.root)
        from companion import Companion
        self.companion = Companion(APP, self.root/'state', root=self.root, tray=False,
                                   entry=ROOT/'app/main.py')
        self.companion.next_action = float('inf')

    def tearDown(self):
        self.companion.shutdown()
        APP.processEvents()
        from share.pet_engine.decode_runtime import STATS
        STATS.drain()
        self.temporary.cleanup()

    def test_character_appears_before_the_card_is_built(self):
        from companion import Companion
        c = Companion(APP, self.root/'lazy', root=self.root, tray=False)
        try:
            self.assertTrue(c.sprite.isVisible())
            self.assertFalse(c.card_ready)
            pump(150)
            self.assertTrue(c.card_ready)
        finally:
            c.shutdown()


    def test_status_dot_preserves_meow_interaction_without_a_card_animation_timer(self):
        companion = self.companion
        companion.show_panel(); companion.card.finish_transition()
        companion.card.dot.click()
        self.assertEqual(companion.sprite.action, 'meow')
        companion.card.dot.click()
        self.assertEqual(companion.director.queued, None)
        companion.card.hide()

    def test_ear_petting_can_be_turned_off(self):
        companion = self.companion
        companion.set_option('ear_meow', False)
        companion.card.earPetted.emit()
        self.assertEqual(companion.sprite.action, 'idle')

    def test_a_new_choice_takes_over_at_once(self):
        companion = self.companion
        companion.card.action_buttons['meow'].click()
        self.assertEqual(companion.sprite.action, 'meow')
        companion.play('curious')
        self.assertEqual(companion.sprite.action, 'curious')
        self.assertIsNotNone(companion.sprite.outgoing)
        self.assertTrue(companion.card.action_buttons['curious'].property('playing'))

    def test_hop_after_drag_and_sparkles_follow_their_settings(self):
        companion = self.companion
        companion.drag_finished()
        self.assertEqual(companion.sprite.action, 'hop')
        companion.finished('hop')
        companion.set_option('hop_after_drag', False)
        companion.drag_finished()
        self.assertEqual(companion.sprite.action, 'idle')
        companion.set_option('sparkles', False)
        self.assertFalse(companion.sprite.sparkles)

    def test_panel_actions_route_to_playback_and_preferences_stay_isolated(self):
        companion = self.companion
        companion.card.action_buttons['meow'].click()
        self.assertEqual(companion.sprite.action, 'meow')
        companion.set_option('size', 340)
        companion.save()
        saved = json.loads((self.root/'state/settings.json').read_text())
        self.assertEqual(saved['size'], 340)
        self.assertFalse((self.root/'BailongEnhanced').exists())

    def test_recovery_and_small_screen_panel_keep_all_controls_scrollable(self):
        companion = self.companion
        companion.card.set_page(companion.card.PAGE_SETTINGS)
        companion.card.content.setFixedHeight(220)
        companion.card.show()
        APP.processEvents()
        self.assertTrue(companion.card.settings_panel.areas[0].widgetResizable())
        companion.sprite.hide()
        companion.recover()
        APP.processEvents()
        self.assertTrue(companion.sprite.isVisible())
        self.assertFalse(companion.sprite.player.stop.is_set())


    def test_default_card_is_compact_and_disconnected_platform_values_are_not_zero(self):
        card = self.companion.card
        self.assertEqual((card.width(), card.height()), (268, 272))
        card.update_quota(None)
        self.assertIn('尚未连接', card.quota_panel.status.text())
        self.assertFalse(hasattr(card, 'quota_chip'))
        self.assertFalse(hasattr(card, 'total_minutes'))

    def test_every_page_fits_without_clipping_or_scrollbars(self):
        card = self.companion.card
        card.show()
        for index in range(len(card.PAGE_NAMES)):
            for section in range(card.settings_panel.tabs.count() if index == card.PAGE_SETTINGS else 1):
                card.settings_panel.switch.set_index(section)
                card.set_page(index)
                card.finish_transition()
                APP.processEvents()
                APP.processEvents()
                with self.subTest(page=index, section=section):
                    self.assertEqual(card.scroller.verticalScrollBar().maximum(), 0)


    def test_antigravity_quota_reaches_the_card_and_she_reacts(self):
        from share.desktop.quota import Meter, QuotaSnapshot
        companion = self.companion
        low = QuotaSnapshot('Antigravity', connected=True, running=True, message='已连接 Antigravity',
                            meters=(Meter('Gemini 3.8 Flash · 高', .5), Meter('Claude Opus 4.6 · 思考', .85)))
        companion.quota_changed((None, low))
        self.assertEqual(companion.card.dashboard.rows[0][1].text(), '50%')
        self.assertEqual(companion.card.dashboard.rows[2][1].text(), '15%')
        self.assertEqual(companion.card.dashboard.rows[1][1].text(), '—')
        before = QuotaSnapshot('Antigravity', connected=True, meters=(Meter('Gemini 3.8 Flash · 高', .5),
                                                                       Meter('Claude Opus 4.6 · 思考', .5)))
        companion.react_to_quota(before, low)
        self.assertIn('只剩 15%', companion.card.said())
        self.assertEqual(companion.sprite.action, 'pout')

    def test_random_weights_keep_catch_manual(self):
        from model import action_weight
        self.assertEqual(action_weight('catch', 12), 0)
        self.assertGreater(action_weight('stretch', 7), action_weight('stretch', 11))
        self.assertLess(action_weight('chase', 2), action_weight('chase', 20))

    def test_sparkle_phase_is_not_restarted_when_an_action_changes(self):
        sprite = self.companion.sprite
        epoch = sprite.sparkle_epoch
        sprite.play('meow')
        self.assertEqual(sprite.sparkle_epoch, epoch)
        self.assertAlmostEqual(sprite.sparkle_phase(epoch+3.6), 1)

    def test_tray_menu_recovers_character_and_quits_its_decoder(self):
        companion = self.companion
        companion.populate_menu(companion.tray_menu)
        self.assertFalse(any('网页' in action.text() for action in companion.tray_menu.actions()))
        companion.sprite.hide()
        next(action for action in companion.tray_menu.actions() if action.text() == '查看状态').trigger(); APP.processEvents()
        self.assertTrue(companion.sprite.isVisible())
        next(action for action in companion.tray_menu.actions() if action.text() == '退出Gemini').trigger(); APP.processEvents()
        self.assertTrue(companion.closing)
        self.assertTrue(companion.sprite.player.stop.is_set())

    def test_legacy_focus_settings_do_not_restore_removed_ui_or_timer(self):
        c = self.companion
        old = dict(c.settings, focus_minutes=90, quiet_focus=True, daily_goal=8, impostor=True, finale='flower')
        cleaned = normalized(old, c.SCHEMA)
        for key in ('focus_minutes', 'quiet_focus', 'daily_goal', 'impostor', 'finale'):
            self.assertNotIn(key, cleaned)
            self.assertNotIn(key, c.card.settings_panel.fields)
        self.assertNotIn('focus', c.card.PAGE_NAMES)
        self.assertNotIn('history', c.card.PAGE_NAMES)
        self.assertFalse(hasattr(c, 'focus'))
        c.poll()
        self.assertFalse((self.root/'state/focus.json').exists())

    def test_today_tokens_footer_uses_local_day_and_opens_inline_hour_chart(self):
        from datetime import datetime, timedelta
        from share.desktop.token_report import add, merge, summarize
        c = self.companion
        days, merged = {}, {}
        now = datetime.now()
        add(days, now, 'test model', (500, 0, 0, 500), 'a')
        add(days, now-timedelta(days=1), 'test model', (9000, 0, 0, 0), 'old')
        merge(merged, days)
        c.card.update_tokens(summarize(merged, c.NAME))
        c.show_panel(); c.card.finish_transition(); APP.processEvents()
        self.assertIn('今日 Token', c.card.footer_widget.text())
        self.assertEqual(c.card.footer_widget.amount, '1K')
        c.card.footer_widget.click(); APP.processEvents()
        self.assertEqual(c.card.dashboard.deck.currentIndex(), 1)
        self.assertEqual(sum(c.card.dashboard.token_chart.values), 1000)
        self.assertEqual(c.card.size().toTuple(), (268, 272))
        self.assertEqual(c.card.scroller.verticalScrollBar().maximum(), 0)
        self.assertFalse(hasattr(c.card, 'report_button'))
        self.assertNotIn('report', c.card.PAGE_NAMES)
        c.card.dashboard.quota_return.click()
        self.assertEqual(c.card.dashboard.deck.currentIndex(),0)
        self.assertFalse(c.card.quick_buttons)
        c.card.update_tokens({'error': 'read failed'})
        self.assertEqual(c.card.footer_widget.amount, '1K')
        c.card.footer_widget.refresh(now.date()+timedelta(days=1))
        self.assertEqual(c.card.footer_widget.amount, '0')

    def test_context_menu_matches_gpt_structure_and_desktop_controls_work(self):
        from PySide6.QtWidgets import QMenu
        c = self.companion
        menu = QMenu(); c.populate_menu(menu)
        roots = menu.actions()
        self.assertEqual([a.text() for a in roots[:4]], ['查看状态', '暂停自主走动', '桌面操作', '角色动作'])
        self.assertTrue(roots[4].isSeparator())
        self.assertEqual([a.text() for a in roots[5:]], ['桌宠设置…', '退出'+c.NAME])
        commands = {a.objectName(): a for a in roots[2].menu().actions() if not a.isSeparator()}
        self.assertEqual(list(commands), ['command_character','command_pin','command_lock','command_bubble','command_recover','command_position'])
        commands['command_character'].trigger(); APP.processEvents()
        self.assertFalse(c.sprite.isVisible())
        c.populate_menu(menu)
        desktop = menu.actions()[2].menu()
        recovery = next(a for a in desktop.actions() if a.objectName() == 'command_recover')
        recovery.trigger(); APP.processEvents()
        self.assertTrue(c.sprite.isVisible())
        c.execute_command('lock', True); self.assertTrue(c.sprite.locked)
        c.execute_command('bubble', False); self.assertFalse(c.card.isVisible())
        c.execute_command('settings'); c.card.finish_transition()
        self.assertEqual(c.card.pages.currentIndex(), c.card.PAGE_SETTINGS)
        c.populate_menu(menu, tray=True)
        self.assertEqual([a.objectName() for a in menu.actions() if not a.isSeparator()],
                         ['command_recover','command_status','command_settings','command_character','command_quit'])


class AntigravityTokenTests(unittest.TestCase):
    def conversation(self, path, generations):
        import sqlite3
        connection = sqlite3.connect(path)
        connection.execute('CREATE TABLE steps (idx integer, metadata blob)')
        connection.execute('CREATE TABLE gen_metadata (idx integer, data blob, size integer)')
        for index, (step, seconds, label, usage) in enumerate(generations):
            connection.execute('INSERT INTO steps VALUES (?, ?)', (step, _field(1, _field(1, seconds))))
            counts = b''.join(_field(key, value) for key, value in usage.items())
            top = (_field(4, counts) + _field(21, label)
                   + _field(20, _field(1, 'last_step_index') + _field(2, str(step))))
            connection.execute('INSERT INTO gen_metadata VALUES (?, ?, 0)', (index, _field(1, top)))
        connection.commit()
        connection.close()

    def test_generations_are_tallied_by_model_and_step_time(self):
        import threading
        from datetime import datetime
        from antigravity_tokens import AntigravityTokens
        from share.desktop.token_report import TokenLedger
        noon = int(datetime(2026, 10, 29, 12, 30).timestamp())
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)/'conversations'
            folder.mkdir()
            self.conversation(folder/'c1.db', [(0, noon, 'Gemini 3.8 Flash (High)', {1: 100, 2: 20, 3: 7, 5: 1000}),
                                               (4, noon+3600, 'Claude Opus 4.6 (Thinking)', {1: 100, 2: 5, 3: 3})])
            report = TokenLedger(AntigravityTokens([folder]), Path(directory)/'cache.json').refresh(threading.Event())
            day = report['days']['2026-10-29']
            self.assertEqual(day['models'], {'Gemini 3.8 Flash (High)': 1127, 'Claude Opus 4.6 (Thinking)': 108})
            self.assertEqual((day['hours'][12], day['hours'][13], day['sessions']), (1127, 108, 1))
            self.assertEqual(report['favorite'], 'Gemini 3.8 Flash (High)')


if __name__ == '__main__':
    unittest.main()
