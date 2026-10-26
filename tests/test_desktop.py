import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PIL import Image
from PySide6.QtWidgets import QApplication,QMenu,QToolButton
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from desktop_core import ActionGate,physics_step,normalized,relative_position,restore_position
from stream_player import StreamPlayer
from desktop_services import validate_character,import_character
from desktop import DesktopPet

app=QApplication.instance() or QApplication([])

def settle():
    app.processEvents()
    for window in app.topLevelWidgets():
        transition=getattr(window,'size_transition',None)
        if transition:transition.complete()
    app.processEvents()

def until(check,seconds=4):
    deadline=time.monotonic()+seconds
    while not check() and time.monotonic()<deadline:QTest.qWait(15)
    return check()

class CoreTests(unittest.TestCase):
    def test_priority_and_deferred_completion(self):
        gate=ActionGate();self.assertTrue(gate.request('drag'))
        self.assertFalse(gate.request('task',{'id':'done'}));self.assertFalse(gate.request('variant'))
        self.assertEqual(gate.finish(),('task',{'id':'done'}));self.assertTrue(gate.request('click'));self.assertTrue(gate.request('drag'))
    def test_throw_bounces_and_stops_inside_bounds(self):
        x,y,vx,vy=98,30,1500,-400
        for _ in range(160):
            x,y,vx,vy,done=physics_step(x,y,vx,vy,.033,(0,0,100,100))
            self.assertTrue(0<=x<=100 and 0<=y<=100)
        self.assertTrue(done);self.assertLess(abs(vx)+abs(vy),1)
    def test_normalized_position_survives_changed_resolution(self):
        saved=relative_position(-1500,200,256,256,(-1920,0,1920,1080),'second')
        x,y=restore_position(saved,384,384,(0,0,2560,1440))
        self.assertTrue(0<=x<=2176 and 0<=y<=1056)
        cleaned=normalized({'scale':float('nan'),'self_talk':True,'talk_min':80,'talk_max':20,'talk_lines':['x'],'character_preferences':{'a':{'talk_lines':['x']}}})
        for key in ('self_talk','talk_min','talk_max','talk_quiet','talk_lines'):self.assertNotIn(key,cleaned)
        self.assertNotIn('talk_lines',cleaned['character_preferences'].get('a',{}))
    def test_removed_chat_preference_is_dropped(self):
        self.assertNotIn('chat_follow',normalized({'chat_follow':True}))
    def test_decoder_bounded_and_cancelled(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'a.gif';frames=[Image.new('RGBA',(64,64),(i*10,0,0,255)) for i in range(20)]
            frames[0].save(path,save_all=True,append_images=frames[1:],duration=40,loop=0)
            player=StreamPlayer();player.start(path,128);time.sleep(.2)
            self.assertLessEqual(player.frames.qsize(),6)
            # A live scale change must never reinterpret old RGBA bytes as a larger buffer.
            pixmap,done=player.advance(512);self.assertEqual(pixmap.width(),128)
            thread=player.thread;player.close()
            from decode_runtime import STATS
            self.assertTrue(STATS.drain());self.assertFalse(thread.is_alive())
    def test_import_validation_rejects_escaping_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'素材清单.json').write_text(json.dumps(dict(idle=dict(id='a',file='../escape.gif'),variants=[])))
            with self.assertRaises(ValueError):validate_character(root)
    def test_webm_import_preserves_transparent_background(self):
        import subprocess,imageio_ffmpeg
        from PIL import ImageDraw
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';(source/'idle').mkdir(parents=True)
            image=Image.new('RGBA',(64,64),(0,0,0,0));ImageDraw.Draw(image).rectangle((20,20,44,44),fill=(255,255,255,255));image.save(root/'frame.png')
            result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-loop','1','-i',str(root/'frame.png'),'-t','0.2','-c:v','libvpx-vp9','-pix_fmt','yuva420p','-auto-alt-ref','0','-y',str(source/'idle/a.webm')],capture_output=True,timeout=30,creationflags=0x08000000 if os.name=='nt' else 0)
            self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
            key,m=import_character(source,root/'characters')
            with Image.open(root/'characters'/key/m['idle']['playbackFile']) as converted:
                rgba=converted.convert('RGBA');self.assertEqual(rgba.getpixel((0,0))[3],0);self.assertGreater(rgba.getpixel((360,360))[3],240)

class DesktopUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patches=[patch('enhanced.CONFIG',self.root/'settings.json'),patch('enhanced.STATE_DIR',self.root),patch('desktop.CONFIG',self.root/'settings.json'),patch('desktop.STATE_DIR',self.root)]
        for p in self.patches:p.start()
        self.pet=DesktopPet(monitor=False);self.pet.show();self.pet.apply_settings(dict(card_hide_delay=120),save=False);self.pet.reveal_card();self.pet.bubble.redraw();settle()
    def tearDown(self):
        self.pet.close();settle()
        for p in self.patches:p.stop()
        self.tmp.cleanup()
    def test_real_player_starts_without_pinning_all_assets(self):
        self.assertFalse(self.pet.pinned_frames);self.assertEqual(len(self.pet.frames),1)
        self.assertTrue(until(lambda:self.pet.player.frames.qsize()>0));self.assertLessEqual(self.pet.player.frames.qsize(),6)
    def test_scale_keeps_feet_anchor_and_pet_always_accepts_input(self):
        self.pet.move(250,200);foot=self.pet.y()+self.pet.height()
        self.pet.apply_settings({'scale':1.2,'mouse_through':True})
        self.assertEqual(self.pet.y()+self.pet.height(),foot)
        self.assertNotIn('mouse_through',self.pet.settings)
        self.assertFalse(self.pet.windowFlags()&Qt.WindowType.WindowTransparentForInput)
        self.pet.recover();self.assertTrue(self.pet.isVisible())
    def test_task_completion_survives_drag_and_protects_bubble(self):
        self.pet.dragging=True;self.pet.gate.state='drag'
        with patch.object(self.pet,'notify'),patch.object(self.pet,'refresh_quota'):
            self.pet.on_activity(dict(kind='complete',title='完成样例'))
        self.assertIsNotNone(self.pet.pending_completion)
        self.assertEqual(self.pet.bubble.status_indicator.visual(),'attention')
        before=self.pet.bubble.status;self.pet.choose(self.pet.variants[0]);self.assertEqual(self.pet.bubble.status,before)
        self.pet.dragging=False;self.pet.gate.state='idle';self.pet.complete_animation(self.pet.pending_completion)
        self.assertNotEqual(self.pet.mode,'task')
        self.pet.player.ended=True
        with patch('desktop.time.monotonic',return_value=time.monotonic()+12),patch.object(self.pet.player,'advance',return_value=(None,True)):
            self.pet.animate()
        self.assertEqual(self.pet.mode,'task')
    def test_indicator_updates_even_while_message_is_held(self):
        self.pet.status_hold=time.monotonic()+30
        self.pet.on_activity(dict(kind='status',state='working',active=1,text='工作中'))
        self.assertEqual(self.pet.bubble.status_indicator.visual(),'busy')
        self.pet.on_activity(dict(kind='token_usage',snapshot={}))
        self.assertEqual(self.pet.bubble.status_indicator.visual(),'busy')
        self.pet.on_activity(dict(kind='monitor_error',text='监听不可用'))
        self.assertEqual(self.pet.bubble.status_indicator.visual(),'warning')

    def test_reply_acknowledgement_survives_held_status_text(self):
        with patch.object(self.pet,'notify'),patch.object(self.pet,'refresh_quota'):
            self.pet.on_activity(dict(kind='complete',session='a',turn='1'))
        icon=self.pet.bubble.status_indicator
        self.pet.status_hold=time.monotonic()+30
        self.pet.on_activity(dict(kind='status',state='thinking',session='b',user_message=True,active=1))
        self.assertEqual(icon.unread,[('a','1')])
        self.pet.on_activity(dict(kind='status',state='thinking',session='a',user_message=True,active=1))
        self.assertFalse(icon.unread);self.assertEqual(icon.visual(),'complete')

    def test_hidden_pet_hides_bubble_on_quota_redraw(self):
        self.pet.toggle_pet();self.pet.update_quota([dict(name='一周',remaining=80,resetsAt=None)],time.time(),'live')
        self.assertFalse(self.pet.bubble.isVisible())
    def test_nonmodal_settings_window_reuse(self):
        with patch('desktop_settings.autostart_enabled',return_value=False):self.pet.open_settings()
        dialog=self.pet.settings_dialog;self.assertFalse(dialog.isModal())
        with patch('desktop_settings.autostart_enabled',return_value=False):self.pet.open_settings()
        self.assertIs(self.pet.settings_dialog,dialog)
    def test_integrated_pages_stay_interactive_and_follow_topmost_setting(self):
        with patch('desktop_settings.autostart_enabled',return_value=False):self.pet.open_settings()
        settle();panel=self.pet.settings_dialog
        self.assertIs(panel.parentWidget(),self.pet.bubble.editor_stack);self.assertFalse(panel.isWindow())
        self.assertFalse(self.pet.bubble.windowFlags()&Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertFalse(self.pet.bubble.windowFlags()&Qt.WindowType.WindowTransparentForInput)
        with patch.object(self.pet.bubble,'raise_') as raise_bubble:
            self.pet.position_bubble();self.pet.flush_status();raise_bubble.assert_not_called()
        self.pet.apply_settings({'on_top':False})
        self.assertFalse(self.pet.bubble.windowFlags()&Qt.WindowType.WindowStaysOnTopHint)
        self.pet.apply_settings({'on_top':True})
        self.assertTrue(self.pet.bubble.windowFlags()&Qt.WindowType.WindowStaysOnTopHint)
        self.assertFalse(self.pet.bubble.windowFlags()&Qt.WindowType.WindowTransparentForInput)
        self.pet.bubble.show_status()
        self.assertFalse(self.pet.bubble.windowHandle().flags()&Qt.WindowType.WindowTransparentForInput)
        self.assertTrue(self.pet.bubble.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
        settle()
        self.assertTrue(until(lambda:not self.pet.bubble.size_transition.running
                              and self.pet.bubble.size_transition.landing.image is None))
        with patch.object(self.pet.bubble,'raise_') as raise_bubble:
            self.pet.position_bubble();raise_bubble.assert_called_once()
    def test_page_switch_and_status_updates_preserve_drafts_and_editor_position(self):
        with patch('desktop_settings.autostart_enabled',return_value=False):self.pet.open_settings()
        settings=self.pet.settings_dialog;settle()
        self.pet.bubble.set_quota_busy(True);self.pet.bubble.set_reset_busy(True);self.pet.bubble.set_token_busy(True)
        settings.fields['move_speed'].setValue(123)
        position=self.pet.bubble.pos();stack=self.pet.bubble.editor_stack
        for i in range(10):self.pet.bubble.message('new status '+str(i));self.pet.position_bubble()
        self.assertEqual(settings.fields['move_speed'].value(),123);self.assertIs(settings.parentWidget(),stack)
        self.assertEqual(self.pet.bubble.pos(),position)
        self.pet.start_walk();self.assertFalse(self.pet.walking)
        self.pet.bubble.show_status()
        with patch('desktop_settings.autostart_enabled',return_value=False):self.pet.open_settings()
        self.assertEqual(settings.fields['move_speed'].value(),123)
    def test_settings_menu_waits_until_menu_event_has_finished(self):
        menu=QMenu();self.pet.build_menu(menu)
        action=next(a for a in menu.actions() if a.text()=='桌宠设置…')
        menu.popup(self.pet.pos());settle()
        with patch.object(self.pet.bubble,'raise_') as raise_bubble:
            self.pet.position_bubble();raise_bubble.assert_not_called()
        menu.close()
        with patch('desktop_settings.autostart_enabled',return_value=False):
            action.trigger();self.assertIsNone(self.pet.settings_dialog)
            settle();self.assertTrue(self.pet.settings_dialog.isVisible())
    def test_alpha_hit_keeps_transparent_corners_clear(self):
        self.assertFalse(self.pet.alpha_hit(0,0));self.assertFalse(self.pet.alpha_hit(-1,-1))
        self.assertTrue(any(self.pet.alpha_hit(x,y) for x in range(20,240,20) for y in range(20,240,20)))
    def test_bubble_refresh_coalesces_requests_without_sound_or_gestures(self):
        self.pet.choose(self.pet.variants[0]);current=self.pet.current;mode=self.pet.mode;status=self.pet.bubble.status
        with patch('enhanced.QuotaWorker') as worker,patch('pet.Pet.play_click_sound') as sound:
            self.pet.bubble.quota_refresh_button.click();self.pet.refresh_quota()
            self.assertEqual(worker.call_count,1);self.assertTrue(self.pet.quota_inflight)
            self.assertFalse(self.pet.bubble.quota_refresh_button.isEnabled())
            self.assertIs(self.pet.current,current);self.assertEqual(self.pet.mode,mode);self.assertEqual(self.pet.bubble.status,status);sound.assert_not_called()
            self.pet.quota_failed('simulated failure');self.assertTrue(self.pet.bubble.quota_refresh_button.isEnabled())
            self.pet.bubble.quota_refresh_button.click();self.assertEqual(worker.call_count,2)
            self.pet.quota_ready([dict(name='一周',remaining=80,resetsAt=None)])
            self.assertFalse(self.pet.bubble.quota_busy);self.assertIs(self.pet.current,current);sound.assert_not_called()
    def test_one_header_refresh_also_requests_reset_without_per_card_button(self):
        worker=Mock();worker.request_refresh.return_value=1;self.pet.reset_worker=worker
        self.pet.bubble.windows=[dict(name='一周',remaining=80)];self.pet.bubble.select_dashboard('reset')
        with patch('enhanced.QuotaWorker'):
            self.pet.bubble.refresh_button.click();self.pet.refresh_all()
            worker.request_refresh.assert_called_once();self.assertTrue(self.pet.bubble.reset_busy)
            self.assertEqual(self.pet.bubble.reset_refresh_buttons,[])
            self.pet.quota_failed('simulated');self.pet._reset_refresh_finished(1,True)
            self.assertFalse(self.pet.bubble.refresh_busy)
        self.pet.reset_worker=None
    def test_unified_token_refresh_keeps_sound_and_status_unchanged(self):
        worker=Mock();worker.request_tokens.return_value=1;self.pet.activity=worker;status=self.pet.bubble.status
        with patch('pet.Pet.play_click_sound') as sound:
            with patch('enhanced.QuotaWorker'):
                self.pet.bubble.refresh_button.click();self.pet.refresh_all()
                worker.request_tokens.assert_called_once();self.assertTrue(self.pet.bubble.token_busy)
                self.assertEqual(self.pet.bubble.token_refresh_buttons,[])
                self.pet.quota_failed('simulated');self.pet.refresh_flow.result('token',1,True)
            self.assertEqual(self.pet.bubble.status,status);sound.assert_not_called()
        self.pet.activity=None
    def test_bubble_expanded_controls_reuse_windows_and_persist_options(self):
        self.pet.bubble.toggle_details();settle()
        def button(name):return next(b for b in self.pet.bubble.findChildren(QToolButton) if b.objectName()==name and b.isVisible())
        with patch('desktop_settings.autostart_enabled',return_value=False),patch('desktop.open_codex') as open_codex:
            button('bubble_settings').click();settle();self.assertTrue(self.pet.settings_dialog.isVisible())
            button('open_codex').click();deadline=time.monotonic()+2
            while not open_codex.called and time.monotonic()<deadline:app.processEvents();time.sleep(.003)
            open_codex.assert_called_once()
        button('bubble_pin').click();self.assertFalse(self.pet.settings['on_top']);self.assertFalse(self.pet.bubble.pinned)
        self.pet.apply_settings({'no_move':True});settle();self.assertFalse(button('bubble_move').isEnabled())
        self.assertFalse(any(b.objectName()=='bubble_chat' for b in self.pet.bubble.findChildren(QToolButton)))

if __name__=='__main__':unittest.main()
