from datetime import date, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'app'), str(ROOT.parent)]
from model import (SCHEMA, FocusLedger, ActionDirector, normalized,
                   atomic_json, load_settings)
from share.desktop import desktop_integration
from share.desktop.local_store import LocalStore

# Tests never look at the real foreground window or write to the real Startup folder.
STARTUP = tempfile.TemporaryDirectory(prefix='claude-startup-')
desktop_integration.startup_folder = lambda: Path(STARTUP.name)
desktop_integration.fullscreen_foreground = lambda: None


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.director = ActionDirector(dict(idle={}, meow={}, catch={}, hop={}))

    def test_background_action_never_interrupts_interaction(self):
        self.assertEqual(self.director.request('meow'), 'meow')
        self.assertIsNone(self.director.request('hop', automatic=True))
        self.assertIsNone(self.director.request('hop', automatic=True, interrupt=True))
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
        self.assertIsNone(self.director.request('../unknown', interrupt=True))
        self.assertEqual(self.director.current, 'meow')

    def test_without_takeover_manual_actions_wait_and_keep_the_latest_choice(self):
        self.director.request('meow')
        self.assertIsNone(self.director.request('hop'))
        self.assertIsNone(self.director.request('catch'))
        self.assertEqual(self.director.finished(), 'catch')
        self.assertEqual(self.director.finished(), 'idle')

    def test_takeover_replaces_the_current_action_but_keeps_a_waiting_completion(self):
        self.director.request('meow')
        self.director.request('catch', completion=True)
        self.assertEqual(self.director.request('hop', interrupt=True), 'hop')
        self.assertIsNone(self.director.request('hop', interrupt=True))
        self.assertEqual(self.director.finished(), 'catch')
        self.assertEqual(self.director.finished(), 'idle')

    def test_dragging_still_queues_a_takeover(self):
        self.director.request('meow')
        self.assertIsNone(self.director.request('hop', interrupt=True, dragging=True))
        self.assertEqual(self.director.queued, 'hop')


class SettingsTests(unittest.TestCase):
    def test_invalid_json_does_not_prevent_starting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'settings.json'
            path.write_text('{broken', encoding='utf-8')
            self.assertEqual(load_settings(path, SCHEMA)['size'], 300)

    def test_untrusted_values_are_bounded_and_unknown_keys_are_discarded(self):
        settings = normalized(dict(size=float('nan'), opacity=-10, on_top='false', random_interval=1e8,
                                   position=[0, 'a'], api_key='discard', playback_speed=1.4,
                                   web_url='javascript:alert(1)', nickname='  小\n读者  ',
                                   finale='explode', poke_action='../idle', wander='no'), SCHEMA)
        self.assertEqual(settings['size'], 300)
        self.assertEqual(settings['opacity'], 65)
        self.assertTrue(settings['on_top'])
        self.assertIsNone(settings['position'])
        self.assertTrue(settings['wander'])
        self.assertEqual(settings['web_url'], '')
        self.assertEqual(settings['nickname'], '小读者')
        # Action pacing and click reactions are built in, not settings.
        for removed in ('api_key', 'finale', 'random_interval', 'playback_speed', 'poke_action'):
            self.assertNotIn(removed, settings)

    def test_web_address_accepts_only_plain_http_pages(self):
        ok = normalized(dict(web_url='https://claude.ai/new'), SCHEMA)['web_url']
        self.assertEqual(ok, 'https://claude.ai/new')
        for bad in ('file:///C:/x', 'https://user:pw@x.com/', 'https://x.com:99999/', 'claude.ai'):
            self.assertEqual(normalized(dict(web_url=bad), SCHEMA)['web_url'], '')

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


class LedgerTests(unittest.TestCase):
    def test_history_week_streak_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'focus.json'
            ledger = FocusLedger()
            monday = date(2026, 10, 26)
            for offset, minutes in ((0, 25), (1, 25), (1, 30), (2, 25)):
                ledger.add(monday+timedelta(days=offset), minutes)
            day = monday+timedelta(days=2)
            self.assertEqual(ledger.today(day), (1, 25))
            self.assertEqual(ledger.week_total(day), 4)
            self.assertEqual(ledger.streak(day), 3)
            self.assertEqual([s for _, s, _ in ledger.recent(day, 3)], [1, 2, 1])
            atomic_json(path, ledger.record(day))
            again = FocusLedger.load(path)
            self.assertEqual(again.totals(), (4, 105))
            self.assertEqual(again.week_total(day+timedelta(days=7)), 0)

    def test_old_one_day_records_still_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'focus.json'
            atomic_json(path, dict(date='2026-10-31', sessions=3, minutes=75))
            self.assertEqual(FocusLedger.load(path).today(date(2026, 10, 31)), (3, 75))
            atomic_json(path, dict(date='today', sessions=True, minutes=-10))
            self.assertEqual(FocusLedger.load(path).totals(), (0, 0))
            path.write_text('[1]')
            self.assertEqual(FocusLedger.load(path).totals(), (0, 0))

    def test_history_is_trimmed_to_two_months(self):
        ledger = FocusLedger()
        today = date(2026, 10, 31)
        ledger.add(today-timedelta(days=200), 25)
        ledger.add(today, 25)
        self.assertEqual(list(ledger.record(today)['history']), ['2026-10-31'])



from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QPoint
from share.pet_engine.character_pack import CharacterPack
from share.desktop.sprite_window import SpriteWindow
APP = QApplication.instance() or QApplication([])
from share.desktop.typography import install_ui_font
install_ui_font(APP)


def pump(ms):
    """Run the event loop while letting decoder threads have the GIL (QTest.qWait keeps it)."""
    end = time.perf_counter()+ms/1000
    while time.perf_counter() < end:
        APP.processEvents()
        time.sleep(.004)


def fixture(root, frames=3):
    assets = root/'assets/character'
    assets.mkdir(parents=True)
    images = []
    for index in range(frames):
        image = Image.new('RGBA', (512, 512))
        ImageDraw.Draw(image).ellipse((96, 64, 416, 480), fill=(100+index*10 % 120, 90, 210, 255))
        images.append(image)
    path = assets/'test.webp'
    images[0].save(path, save_all=True, append_images=images[1:], duration=42, lossless=True)
    import hashlib
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    keys = ('idle', 'drag', 'wave', 'peek', 'wind', 'bow', 'sparkles', 'flower', 'idea', 'walk-left', 'walk-right')
    actions = [dict(id=key, name=key, group='test', file='test.webp', durationMs=42*frames,
                    frames=frames, loop=key == 'idle', random=False, bytes=path.stat().st_size,
                    sha256=checksum) for key in keys]
    for item in actions[-2:]:
        item['walk'] = dict(direction=-1 if item['id'] == 'walk-left' else 1, start=0, end=frames-1)
    (assets/'character.json').write_text(json.dumps(dict(idle='idle', actions=actions)), encoding='utf-8')
    return assets


class ResourceTests(unittest.TestCase):
    def test_every_frame_and_checksum_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = CharacterPack(fixture(Path(directory)))
            self.assertEqual(len(pack.verify()), 11)
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
        self.sprite = SpriteWindow(CharacterPack(fixture(Path(self.temporary.name), frames=40)))
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

    def test_locked_character_cannot_be_dragged_but_still_clicks(self):
        clicked = []
        self.sprite.activated.connect(lambda: clicked.append(True))
        self.sprite.locked = True
        self.sprite.move(40, 40)
        before = self.sprite.pos()
        QTest.mousePress(self.sprite, Qt.MouseButton.LeftButton, pos=QPoint(150, 150))
        QTest.mouseMove(self.sprite, QPoint(240, 150), delay=10)
        QTest.mouseRelease(self.sprite, Qt.MouseButton.LeftButton, pos=QPoint(240, 150))
        QTest.qWait(300)
        self.assertEqual(self.sprite.pos(), before)
        self.assertEqual(clicked, [True])

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
        self.sprite.play('wave', blend=False)
        self.assertIsNone(self.sprite.outgoing)
        old = self.sprite.player
        self.sprite.play('peek')
        self.assertIs(self.sprite.outgoing, old)
        pump(150)
        self.assertGreater(self.sprite.player.frame_index, 0)

    def test_takeover_crossfades_two_live_animations_then_releases_the_old_one(self):
        self.sprite.play('wave', blend=False)
        pump(120)
        old = self.sprite.player
        self.assertTrue(self.sprite.play('peek', takeover=True))
        self.assertIs(self.sprite.outgoing, old)
        self.assertIsNotNone(self.sprite.outgoing_frame)
        self.assertIs(self.sprite.player.loop_cache, old.loop_cache)
        pump(450)
        self.assertIsNone(self.sprite.outgoing)
        self.assertTrue(old.stop.is_set())
        self.assertGreater(self.sprite.player.frame_index, 0)

    def test_the_next_automatic_clip_is_decoded_ahead_and_dropped_if_plans_change(self):
        self.sprite.prepare('wave')
        segment = self.sprite.upcoming[1]
        self.assertTrue(segment.ready.wait(2))
        self.assertTrue(self.sprite.play('wave', blend=False))
        self.assertIsNone(self.sprite.upcoming)
        self.assertIs(self.sprite.player.frames, segment.frames)
        self.sprite.prepare('peek')
        stale = self.sprite.upcoming[1]
        self.assertTrue(self.sprite.play('bow', takeover=True))
        self.assertTrue(stale.stop.is_set())
        self.assertIsNone(self.sprite.upcoming)

    def test_a_walk_carries_the_window_with_an_eased_start_and_stop(self):
        from share.desktop.sprite_window import stride
        self.assertEqual(stride(0), 0); self.assertEqual(stride(1), 1)
        self.assertLess(stride(.05), .05); self.assertGreater(stride(.95), .95)
        area = APP.primaryScreen().availableGeometry()
        self.sprite.move(area.left()+40, area.top()+100)
        origin = self.sprite.pos()
        self.sprite.travel = dict(key='walk-right', origin=origin, distance=120, frames=(0, 39))
        self.sprite.play('walk-right', blend=False)
        steps = []
        for _ in range(60):
            pump(60)
            steps.append(self.sprite.x())
            if self.sprite.player.ended:
                break
        self.assertEqual(self.sprite.pos(), origin+QPoint(120, 0))
        self.assertEqual(steps, sorted(steps))
        self.sprite.travel = dict(key='walk-right', origin=self.sprite.pos(), distance=120, frames=(0, 39))
        self.sprite.play('peek', takeover=True)
        pump(120)
        self.assertIsNone(self.sprite.travel)


class CompanionCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        fixture(self.root)
        from companion import Companion
        self.companion = Companion(APP, self.root/'state', root=self.root, tray=False,
                                   entry=ROOT/'app/main.py')

    def tearDown(self):
        self.companion.shutdown()
        APP.processEvents()
        from share.pet_engine.decode_runtime import STATS
        STATS.drain()
        self.temporary.cleanup()


class ClaudeTests(CompanionCase):
    def test_drag_animation_keeps_playing_and_completion_waits_for_release(self):
        c = self.companion
        c.pack.data['drag'] = 'drag'
        c.sprite.dragging = True
        c.drag_started()
        self.assertEqual(c.sprite.action, 'drag')
        self.assertEqual(c.director.current, 'drag')
        self.assertTrue(c.sprite.tick.isActive())
        c.play('idea')
        c.play('flower', completion=True)
        self.assertEqual(c.director.pending, 'flower')
        c.finished('drag')
        self.assertEqual(c.sprite.action, 'drag')
        c.sprite.dragging = False
        c.drag_finished(); c.finished('drag')
        self.assertEqual(c.sprite.action, 'flower')
        c.finished('flower')
        self.assertEqual(c.sprite.action, 'idea')

    def test_role_action_menu_is_unique_flat_and_scrolls_as_one_column(self):
        from PySide6.QtWidgets import QMenu, QStyle
        from share.pet_engine.action_catalog import populate_action_menu
        menu = QMenu()
        seen = []
        populate_action_menu(menu, [dict(id='a',name='a',file='a.webp'),
                                   dict(id='copy',name='a copy',file='a.webp'),
                                   dict(id='b',name='b',file='b.webp')], lambda item:seen.append(item['id']))
        self.assertEqual([a.text() for a in menu.actions()], ['a','b'])
        self.assertTrue(all(a.menu() is None for a in menu.actions()))
        self.assertEqual(menu.style().styleHint(QStyle.StyleHint.SH_Menu_Scrollable),1)
        menu.actions()[-1].trigger(); self.assertEqual(seen,['b'])
        self.companion.populate_menu(self.companion.tray_menu)
        self.assertEqual(self.companion.tray_menu.actions()[-1].text(),'退出Claude')
        titles = [a.text() for a in self.companion.tray_menu.actions()]
        self.assertEqual(titles[0], '查看状态')
        self.assertFalse({'专注时光', '专注记录', '偏好设置', '找回人物', '保持置顶'} & set(titles))

    def test_character_appears_before_the_card_is_built(self):
        from companion import Companion
        c = Companion(APP, self.root/'lazy', root=self.root, tray=False)
        try:
            self.assertTrue(c.sprite.isVisible())
            self.assertFalse(c.card_ready)
            QTest.qWait(150)
            self.assertTrue(c.card_ready)
            self.assertLess(c.timings['first_frame'], c.timings['card_ready'])
        finally:
            c.shutdown()


    def test_a_new_choice_takes_over_at_once(self):
        c = self.companion
        c.card.action_buttons['wave'].click()
        self.assertEqual(c.sprite.action, 'wave')
        c.card.action_buttons['peek'].click()
        self.assertEqual(c.sprite.action, 'peek')
        self.assertIsNotNone(c.sprite.outgoing)
        self.assertEqual(c.card.action_buttons['peek'].property('playing'), True)
        c.card.action_buttons['peek'].click()
        self.assertEqual(c.card.said(), c.lines['already'])

    def test_without_instant_switch_choices_wait_for_the_tail(self):
        c = self.companion
        c.set_option('instant_switch', False)
        c.play('wave'); c.play('peek'); c.play('idea')
        self.assertEqual(c.sprite.action, 'wave')
        self.assertEqual(c.director.queued, 'idea')
        c.finished('wave')
        self.assertEqual(c.sprite.action, 'idea')

    def test_header_refresh_returns_to_reading_at_once(self):
        c = self.companion
        c.play('wave')
        c.card.refresh_button.click()
        self.assertEqual(c.sprite.action, 'idle')
        c.set_option('instant_switch', False)
        c.play('wave')
        c.card.refresh_button.click()
        self.assertEqual(c.sprite.action, 'wave')
        self.assertEqual(c.director.queued, 'idle')

    def test_selecting_reading_again_does_not_restart_the_book_mid_page(self):
        c = self.companion
        serial = c.sprite.serial
        c.play('idle')
        self.assertEqual(c.sprite.serial, serial)


    def test_settings_persist_and_resize_preserves_foot_position(self):
        c = self.companion
        foot = c.sprite.y()+c.sprite.height()
        c.set_option('size', 340); c.save()
        self.assertEqual(c.sprite.y()+c.sprite.height(), foot)
        self.assertEqual(load_settings(c.store.settings_path, SCHEMA)['size'], 340)

    def test_character_settings_apply_only_on_confirmation_and_reset_to_defaults(self):
        c = self.companion
        panel = c.card.settings_panel
        self.assertNotIn('lock_position',panel.fields)
        c.set_option('lock_position',True)
        for removed in ('playback_speed', 'random_interval', 'poke_action', 'double_action'):
            self.assertNotIn(removed, panel.fields)
        panel.fields['card_hide_delay'].setValue(30)
        panel.fields['wander'].setChecked(False)
        self.assertTrue(c.sprite.locked)
        self.assertTrue(panel.dirty)
        self.assertTrue(c.settings['wander'])
        panel.apply()
        self.assertTrue(c.sprite.locked)
        self.assertEqual(c.card_timer.interval(), 30000)
        self.assertFalse(c.settings['wander'])
        c.double_poke()
        self.assertIn(c.sprite.action, ('wave', 'bow', 'sparkles'))
        c.reset_options(panel.section_keys[0]+panel.section_keys[1])
        self.assertTrue(c.sprite.locked)
        c.set_option('lock_position',False)
        self.assertFalse(c.sprite.locked)
        self.assertTrue(c.settings['wander'])
        self.assertNotIn('lock_position',panel.fields)

    def test_walks_only_happen_while_she_may_wander_and_never_from_menus(self):
        c = self.companion
        area = c.screen_area()
        c.sprite.move(area.left()+(area.width()-c.sprite.width())//2, area.top()+80)
        self.assertIsNotNone(c.walk_choice())
        c.set_option('wander', False)
        self.assertIsNone(c.walk_choice())
        c.set_option('wander', True)
        c.set_option('lock_position', True)
        self.assertIsNone(c.walk_choice())
        c.set_option('lock_position', False)
        from PySide6.QtWidgets import QMenu
        menu, listed = QMenu(), []
        with patch('share.desktop.companion_app.populate_action_menu',
                   lambda target, items, callback: listed.extend(item['id'] for item in items)):
            c.populate_menu(menu)
        self.assertIn('wave', listed)
        self.assertFalse({'walk-left', 'walk-right'} & set(listed))
        self.assertFalse({'walk-left', 'walk-right'} & set(c.card.action_buttons))
        walk = next(action for action in menu.actions() if action.objectName() == 'command_walk')
        self.assertEqual(walk.text(), '暂停自主走动')
        walk.trigger(); pump(30)
        self.assertFalse(c.settings['wander'])
        c.set_option('wander', True)
        # Only the walk is left to choose once random actions are off.
        c.set_option('random_actions', False)
        start = c.sprite.x()
        c.random_activity(time.monotonic())
        self.assertIn(c.boundary_action, ('walk-left', 'walk-right'))
        c.finished('idle')
        self.assertIn(c.director.current, ('walk-left', 'walk-right'))
        self.assertIsNotNone(c.sprite.travel)
        for _ in range(40):
            pump(30)
            if c.director.current == 'idle':
                break
        self.assertEqual(c.director.current, 'idle')
        self.assertNotEqual(c.sprite.x(), start)
        self.assertIsNone(c.sprite.travel)


    def test_nickname_and_custom_web_page(self):
        c = self.companion
        c.set_option('nickname', '小满')
        self.assertTrue(c.card.idle_message().startswith('小满，'))
        c.set_option('web_url', 'https://example.org/read')
        with patch('share.desktop.companion_app.QDesktopServices.openUrl', return_value=True) as opened:
            c.open_web()
        self.assertEqual(opened.call_args[0][0].toString(), 'https://example.org/read')

    def test_autostart_writes_and_removes_a_startup_entry(self):
        c = self.companion
        c.card.settings_panel.fields['autostart'].setChecked(True)
        c.card.settings_panel.apply()
        entry = Path(STARTUP.name)/'ClaudeDesktopPet.vbs'
        self.assertTrue(entry.is_file())
        self.assertIn('main.py', entry.read_text(encoding='utf-16'))
        c.card.settings_panel.fields['autostart'].setChecked(False)
        c.card.settings_panel.apply()
        self.assertFalse(entry.exists())


    def test_fullscreen_programs_make_her_step_aside_and_come_back(self):
        c = self.companion
        monitor = desktop_integration.monitor_of(int(c.sprite.winId()))
        with patch('share.desktop.desktop_integration.fullscreen_foreground', return_value=(4242, monitor)):
            c.poll()
            self.assertTrue(c.yielded)
            self.assertFalse(c.sprite.isVisible())
            c.next_action = 0
            self.assertFalse(c.can_act_alone())
        c.poll()
        self.assertFalse(c.yielded)
        self.assertTrue(c.sprite.isVisible())

    def test_card_pages_fit_and_quota_starts_unlinked(self):
        p = self.companion.card
        p.show()
        for page in range(len(p.PAGE_NAMES)):
            for section in range(p.settings_panel.tabs.count() if page == p.PAGE_SETTINGS else 1):
                p.settings_panel.switch.set_index(section)
                p.set_page(page); p.finish_transition(); APP.processEvents(); APP.processEvents()
                with self.subTest(page=page, section=section):
                    self.assertEqual(p.scroller.verticalScrollBar().maximum(), 0)
        self.assertIn('尚未连接', p.quota_panel.status.text())


    def test_long_lines_are_elided_but_kept_whole_in_the_tooltip(self):
        card = self.companion.card
        text = '这一句话非常非常长，'*6
        card.say(text)
        self.assertEqual(card.said(), text)
        self.assertNotEqual(card.message.text(), text)
        self.assertEqual(card.message.toolTip(), text)

    def test_recover_after_hiding_restarts_decoder_and_tray_exit_closes_it(self):
        c = self.companion
        c.sprite.hide(); c.recover(); APP.processEvents()
        self.assertTrue(c.sprite.isVisible())
        self.assertFalse(c.sprite.player.stop.is_set())
        c.populate_menu(c.tray_menu)
        self.assertFalse(any('网页' in action.text() for action in c.tray_menu.actions()))
        c.tray_menu.actions()[-1].trigger(); APP.processEvents()
        self.assertTrue(c.closing)
        self.assertTrue(c.sprite.player.stop.is_set())

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


    def test_repeated_status_clicks_cannot_start_the_removed_scene(self):
        c = self.companion
        for _ in range(3): c.card.dot.click()
        self.assertFalse(hasattr(c, 'summon_impostor'))
        self.assertFalse(hasattr(c, 'scene'))
        self.assertNotIn('impostor', c.settings)

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
        self.assertEqual(c.card.size().toTuple(), (268, 188))
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


class QuotaTests(CompanionCase):
    def snapshot(self, five_hour, week, running=True):
        from share.desktop.quota import Meter, QuotaSnapshot
        from datetime import datetime
        return QuotaSnapshot('Claude 桌面端', connected=True, running=running, message='已连接 Claude 桌面端',
                             meters=(Meter('5 小时', five_hour), Meter('本周', week)), updated_at=datetime(2026, 10, 31, 9))

    def test_claude_desktop_history_is_parsed_without_reset_guesses(self):
        from claude_link import ClaudeUsageReader
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'plan-usage-history.json'
            stamp = int(time.time()*1000)
            path.write_text(json.dumps(dict(version=2, samples=[
                dict(t=stamp-60000, org='x', u=dict(fh=20, sd=5)), dict(t=stamp, org='x', u={})])), encoding='utf-8')
            snapshot = ClaudeUsageReader(path, running=lambda: True)()
            self.assertTrue(snapshot.connected)
            self.assertEqual([(m.label, m.used, m.resets_at) for m in snapshot.meters],
                             [('5 小时', .2, None), ('本周', .05, None)])
            self.assertEqual(snapshot.message, '已连接 Claude 桌面端')
            stopped = ClaudeUsageReader(path, running=lambda: False)()
            self.assertIn('未运行', stopped.message)
            path.write_text('{broken', encoding='utf-8')
            self.assertFalse(ClaudeUsageReader(path, running=lambda: False)().meters)
        self.assertFalse(ClaudeUsageReader(Path(directory)/'none.json', running=lambda: False)().connected)
        with patch('claude_link.history_file', return_value=None):
            self.assertIn('没有找到', ClaudeUsageReader(running=lambda: False)().message)

    def test_quota_shows_on_the_dashboard_without_a_focus_footer(self):
        c = self.companion
        card = c.card
        self.assertFalse(hasattr(card, 'history_link'))
        c.quota_changed((None, self.snapshot(.31, .11)))
        self.assertEqual(card.dashboard.rows[0][1].text(), '69%')
        self.assertFalse(hasattr(card, 'history_link'))
        self.assertFalse(hasattr(card, 'quota_chip'))
        self.assertEqual(c.tray.toolTip(), 'Claude')
        rows = [(name.text(), value.text()) for box, name, value, bar in card.quota_panel.rows if not box.isHidden()]
        self.assertEqual(rows, [('5 小时', '已用 31%'), ('本周', '已用 11%')])
        c.set_option('quota_link', False)
        self.assertTrue(all(value.text() == '—' for _, value, _, _ in card.dashboard.rows))

    def test_she_celebrates_a_reset_and_warns_when_nearly_spent(self):
        c = self.companion
        c.react_to_quota(None, self.snapshot(.9, .5))
        self.assertEqual(c.sprite.action, 'idle')
        c.react_to_quota(self.snapshot(.5, .5), self.snapshot(.85, .5))
        self.assertIn('已用 85%', c.card.said())
        self.assertEqual(c.sprite.action, 'peek')
        c.finished('peek')
        c.react_to_quota(self.snapshot(.85, .5), self.snapshot(.02, .5))
        self.assertEqual(c.card.said(), c.lines['quota_refreshed'])
        self.assertEqual(c.sprite.action, 'sparkles')

    def test_watcher_reads_later_and_only_emits_changes(self):
        from share.desktop.quota import QuotaWatcher
        values = iter([self.snapshot(.1, .1), self.snapshot(.1, .1), self.snapshot(.2, .1)])
        watcher = QuotaWatcher(lambda: next(values), 60000)
        seen = []
        watcher.changed.connect(seen.append)
        watcher.poll(); watcher.poll(); watcher.poll()
        self.assertEqual(len(seen), 2)
        broken = QuotaWatcher(lambda: 1/0)
        self.assertIn('ZeroDivisionError', broken.poll().message)

    def test_random_weights_keep_the_flower_manual_and_follow_the_clock(self):
        from model import action_weight
        self.assertGreater(action_weight('flower',10),0)
        self.assertLess(action_weight('flower',10),action_weight('wind',10))
        self.assertEqual(action_weight('drag', 14), 0)
        self.assertGreater(action_weight('wave', 8), action_weight('wave', 14))
        self.assertGreater(action_weight('wave', 10), action_weight('bow', 10))
        c = self.companion
        picked = set()
        for _ in range(30):
            c.director.current = 'idle'
            c.random_activity(0)
            if c.boundary_action:
                c.finished('idle')
            picked.add(c.sprite.action)
        self.assertNotIn('drag', picked)
        self.assertGreater(len(picked), 3)


    def test_automatic_actions_wait_for_the_idle_seam_and_cut_in(self):
        c = self.companion
        c.play('idle')
        self.assertEqual(c.sprite.action, 'idle')
        c.random_activity(0)
        chosen = c.boundary_action
        self.assertIsNotNone(chosen)
        self.assertEqual(c.sprite.action, 'idle')
        c.finished('idle')
        self.assertEqual(c.sprite.action, chosen)
        self.assertIsNone(c.sprite.outgoing)
        self.assertIsNone(c.boundary_action)
        c.director.current = 'idle'
        c.sprite.play('idle', blend=False)
        c.random_activity(0)
        c.play('wave')
        self.assertIsNone(c.boundary_action)


class StoreTests(unittest.TestCase):
    def test_diagnostics_log_is_capped(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalStore(directory)
            store.log_path.write_text('x'*(300*1024), encoding='utf-8')
            store.log('next')
            self.assertLess(store.log_path.stat().st_size, 100)
            self.assertTrue(store.log_path.with_suffix('.old.log').exists())

    def test_unexpected_errors_are_written_to_the_diagnostics_log(self):
        import main
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'diagnostics.log'
            previous = sys.excepthook
            try:
                main.install_crash_log(path)
                with patch('sys.stderr', None):
                    try:
                        raise RuntimeError('ink spilled')
                    except RuntimeError:
                        sys.excepthook(*sys.exc_info())
            finally:
                sys.excepthook = previous
            self.assertIn('ink spilled', path.read_text(encoding='utf-8'))


class ResetAndTokenTests(unittest.TestCase):
    def test_reset_is_inferred_by_chaining_windows(self):
        from datetime import datetime
        from claude_link import estimated_reset, SPANS
        at = lambda h, m: datetime(2026, 10, 30, h, m)
        points = [(at(17, 19), 0), (at(18, 2), 23), (at(22, 13), 35), (at(22, 28), 5), (at(23, 28), 31)]
        reset = estimated_reset(points, SPANS['fh'])
        # The first window opened 17:19-17:28 (it closed 22:19-22:28), so the
        # second opened 22:19-22:28 and closes about five hours later.
        self.assertEqual((reset.hour, reset.minute), (3, 23))
        self.assertIsNone(estimated_reset([(at(18, 0), 20)], SPANS['fh']))  # too vague to show
        self.assertIsNone(estimated_reset([(at(18, 0), 20), (at(18, 30), 0)], SPANS['fh']))

    def test_countdown_text(self):
        from datetime import datetime, timedelta
        from share.desktop.quota import reset_text
        now = datetime(2026, 10, 31, 2, 0)
        self.assertEqual(reset_text(now+timedelta(minutes=61), now, approx=True), '约1小时01分后重置')
        self.assertEqual(reset_text(now+timedelta(minutes=5), now), '5分钟后重置')
        self.assertEqual(reset_text(now+timedelta(days=6, hours=15), now), '6天15小时后重置')
        self.assertEqual(reset_text(now-timedelta(minutes=1), now), '已到重置时间')

    def test_claude_code_transcripts_are_counted_once_and_incrementally(self):
        import threading
        from claude_tokens import ClaudeCodeTokens, model_name
        from share.desktop.token_report import TokenLedger
        self.assertEqual(model_name('claude-opus-5-5'), 'Opus 5.5')
        self.assertEqual(model_name('claude-sonnet-4-5-20250929'), 'Sonnet 4.5')
        reply = lambda ident, stamp, out: json.dumps(dict(type='assistant', sessionId='s1', timestamp=stamp,
            message=dict(id=ident, model='claude-opus-5-5', usage=dict(input_tokens=1, cache_creation_input_tokens=10,
                                                                         cache_read_input_tokens=100, output_tokens=out))))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)/'projects'/'p'
            folder.mkdir(parents=True)
            log = folder/'s1.jsonl'
            # One reply split over two lines, a user line, and a half-written line.
            log.write_bytes((reply('m1', '2026-10-30T10:00:00Z', 5)+'\n'+reply('m1', '2026-10-30T10:00:00Z', 5)+'\n'
                             + json.dumps(dict(type='user', message=dict(content='hi')))+'\n'
                             + reply('m2', '2026-10-30T11:00:00Z', 7)[:40]).encode())
            ledger = TokenLedger(ClaudeCodeTokens([Path(directory)/'projects']), Path(directory)/'cache.json')
            report = ledger.refresh(threading.Event())
            self.assertEqual((report['total'], report['messages'], report['sessions']), (116, 1, 1))
            self.assertEqual(report['favorite'], 'Opus 5.5')
            with log.open('ab') as handle:  # the half line is finished, another reply follows
                handle.write((reply('m2', '2026-10-30T11:00:00Z', 7)[40:]+'\n').encode())
            report = TokenLedger(ClaudeCodeTokens([Path(directory)/'projects']), Path(directory)/'cache.json').refresh()
            self.assertEqual((report['total'], report['messages']), (116+118, 2))
            day = next(iter(report['days'].values()))
            self.assertEqual(day['parts'], [2, 20, 200, 12])

