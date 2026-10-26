"""Capability failures, honest statistics and keyboard/pointer user journeys."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import copy,json,sqlite3,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QRect
from PySide6.QtWidgets import QToolButton
from PySide6.QtTest import QTest
from connection_health import CapabilityHealth,sample
from codex_connection import data_home,check_connection
from session_read_state import read_tracking_probe,seen_completed_turns
from enhanced_core import RolloutTail
from token_calendar import TokenUsageIndex
from ui_theme import contrast,PRIMARY,ON_PRIMARY,SURFACE,INK,MUTED
import test_settings_journeys as journeys
from test_daily_report import sample as report_sample
APP=journeys.APP


class HealthTests(unittest.TestCase):
    def test_failure_keeps_last_success_and_each_capability_is_independent(self):
        now=[1000.];h=CapabilityHealth('home',clock=lambda:now[0]);h.record('tasks',sample('available'))
        now[0]=1002;h.record('read',sample('unavailable','read_schema'));h.record('tasks',sample('degraded','logs_unreadable'))
        s=h.snapshot()['capabilities'];self.assertEqual(s['tasks']['last_success'],1000)
        self.assertIsNone(s['read']['last_success']);self.assertEqual(s['quota']['state'],'unknown')
        self.assertEqual(s['tasks']['code'],'logs_unreadable')
    def test_stale_and_restart_never_claim_a_current_connection(self):
        now=[1000.];h=CapabilityHealth('home',clock=lambda:now[0]);h.record('read',sample('available'))
        now[0]=1030;self.assertEqual(h.snapshot()['capabilities']['read']['code'],'stale')
        fresh=CapabilityHealth('home',h.snapshot(),clock=lambda:now[0]);self.assertEqual(fresh.records['read']['state'],'unknown')
        self.assertEqual(fresh.records['read']['last_success'],1000)
        other=CapabilityHealth('another-home',h.snapshot(),clock=lambda:now[0]);self.assertIsNone(other.records['read']['last_success'])
    def test_untrusted_state_and_errors_are_reduced_to_safe_codes(self):
        h=CapabilityHealth('home',previous=['bad schema']);h.record('quota',dict(state='unavailable',code='PRIVATE ERROR body',success_at=float('nan')))
        text=json.dumps(h.snapshot());self.assertNotIn('PRIVATE',text);self.assertIsNone(h.records['quota']['last_success'])
        h=CapabilityHealth('home',dict(home_key=h.home_key,capabilities={'read':{'last_success':float('nan')}}));self.assertIsNone(h.records['read']['last_success'])
    def test_zero_and_unknown_are_not_interchangeable_for_token_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'sessions').mkdir();p=root/'sessions/rollout-test.jsonl'
            index=TokenUsageIndex(root/'usage.sqlite',root);s=index.poll();self.assertTrue(s['unavailable']);self.assertFalse(s['report'])
            p.write_text('{"unknown":"format"}\n',encoding='utf-8');s=index.poll();self.assertTrue(s['unavailable']);self.assertTrue(s['format_unknown'])
            p.write_text(json.dumps(dict(type='session_meta',payload=dict(id='a')))+'\n',encoding='utf-8')
            # A rewritten file with equal length is a different fixture/index.
            s=TokenUsageIndex(root/'valid.sqlite',root).poll();self.assertFalse(s.get('unavailable',False));self.assertEqual(s['all_total'],0)
    def test_rollout_health_distinguishes_missing_unknown_and_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);tail=RolloutTail(home);tail.poll();self.assertEqual(tail.health['code'],'logs_missing')
            (home/'sessions').mkdir();p=home/'sessions/rollout-test.jsonl';p.write_text('{"unsupported":true}\n',encoding='utf-8')
            tail=RolloutTail(home);tail.poll();self.assertEqual(tail.health['code'],'logs_schema')
            p.write_text('{"type":"session_meta","payload":{"id":"a"}}\n',encoding='utf-8')
            tail=RolloutTail(home);tail.poll();self.assertEqual(tail.health['state'],'available')


class ProbeTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def marker(self,value=None):
        p=self.home/'.codex-global-state.json';p.write_text(json.dumps(value if value is not None else {'electron-thread-read-state-v1':dict(version=1,unreadByIdentity={'u':{'local:h':[]}})}),encoding='utf-8');return p
    def test_empty_supported_markers_need_publication_schema_and_never_ack_on_failure(self):
        self.marker();self.assertNotEqual(read_tracking_probe(self.home)['state'],'available')
        with sqlite3.connect(self.home/'state_5.sqlite') as db:db.execute('CREATE TABLE thread_read_receipts(thread_id TEXT,last_published_turn TEXT)')
        db.close()
        before=(self.home/'state_5.sqlite').read_bytes();self.assertEqual(read_tracking_probe(self.home)['state'],'available')
        self.assertEqual((self.home/'state_5.sqlite').read_bytes(),before)
        self.marker([]);self.assertNotEqual(read_tracking_probe(self.home)['state'],'available')
        self.assertEqual(seen_completed_turns(self.home,[('a','turn-a')]),[])
    def test_locked_database_is_degraded_and_does_not_forge_read_receipts(self):
        self.marker();db=sqlite3.connect(self.home/'state_5.sqlite');db.execute('CREATE TABLE thread_read_receipts(thread_id TEXT,last_published_turn TEXT)');db.commit()
        try:
            db.execute('BEGIN EXCLUSIVE');p=read_tracking_probe(self.home);self.assertEqual(p['code'],'database_busy');self.assertNotEqual(p['state'],'available')
        finally:db.rollback();db.close()
    def test_schema_changed_can_use_valid_history_fallback(self):
        self.marker()
        with sqlite3.connect(self.home/'state_5.sqlite') as db:db.execute('CREATE TABLE thread_read_receipts(changed TEXT)')
        db.close()
        with sqlite3.connect(self.home/'thread_history_1.sqlite') as db:db.execute('CREATE TABLE thread_turns(thread_id TEXT,turn_id TEXT,status TEXT,rollout_ordinal INTEGER)')
        db.close()
        self.assertEqual(read_tracking_probe(self.home)['state'],'available')
    def test_old_saved_path_file_is_ignored_and_environment_wins(self):
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.home),'CODEX_HOME':'','BAILONG_CODEX_HOME':''}),patch('codex_connection.user_environment',return_value=''):
            folder=self.home/'custom';(folder/'sessions').mkdir(parents=True)
            (self.home/'BailongEnhanced').mkdir();(self.home/'BailongEnhanced/connection-paths.json').write_text(json.dumps(dict(home=str(folder))),encoding='utf-8')
            self.assertNotEqual(data_home(),folder.resolve())
            with patch.dict(os.environ,{'BAILONG_CODEX_HOME':str(folder)}):self.assertEqual(data_home(),folder.resolve())
    def test_manual_quota_probe_without_windows_is_not_reported_full_or_zero(self):
        with patch('codex_connection.data_home',return_value=self.home),patch('codex_connection.find_executable',return_value='cli'),patch('desktop_services.codex_desktop_open',return_value=False),patch('quota.read_quota',return_value={'rateLimits':{'primary':None,'secondary':None}}):
            r=check_connection();self.assertTrue(r['quota_read']);self.assertEqual(r['capabilities']['quota']['code'],'no_windows');self.assertNotEqual(r['capabilities']['quota']['state'],'available')


class VisualInteractionTests(unittest.TestCase):
    tearDown=journeys.InteractionTests.tearDown
    def setUp(self):
        journeys.InteractionTests.setUp(self);self.pet.bubble.redraw();journeys.settle(self.pet)
    settings=journeys.InteractionTests.settings
    def test_normal_header_has_accessible_names_and_non_overlapping_icon_targets(self):
        b=self.pet.bubble;b.collapse_to_normal();journeys.settle(self.pet);targets=[]
        for name in ('bubble_refresh_all','bubble_report','bubble_web','bubble_details'):
            button=next(w for w in b.findChildren(QToolButton) if w.objectName()==name and w.isVisible())
            self.assertEqual(button.width(),28);self.assertEqual(button.height(),28);self.assertFalse(button.text());self.assertTrue(button.accessibleName())
            rect=QRect(button.mapToGlobal(QPoint()),button.size());self.assertTrue(QRect(b.mapToGlobal(QPoint()),b.size()).contains(rect));targets.append(rect)
            self.assertEqual(button.focusPolicy(),Qt.FocusPolicy.NoFocus)
        for i,a in enumerate(targets):
            for other in targets[i+1:]:self.assertFalse(a.intersects(other))
    def test_editors_offer_keyboard_focus_save_and_return(self):
        s=self.settings();s.fields['scale'].setValue(1.25);s.fields['scale'].setFocus();APP.processEvents()
        QTest.keyClick(s.fields['scale'],Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier);journeys.settle(self.pet)
        self.assertEqual(self.pet.settings['scale'],1.25);self.assertFalse(s.draft.dirty)
        toolbar=next(w for w in self.pet.bubble.findChildren(QToolButton) if w.objectName()=='bubble_settings' and w.isVisible())
        self.assertEqual(toolbar.focusPolicy(),Qt.FocusPolicy.StrongFocus)
        QTest.keyClick(s,Qt.Key.Key_Escape);journeys.settle(self.pet);self.assertEqual(self.pet.bubble.panel_page,'status')
    def test_primary_secondary_and_destructive_controls_have_distinct_roles(self):
        s=self.settings();self.assertEqual(s.apply_button.property('role'),'primary');self.assertIsNone(s.discard_button.property('role'))
        self.assertGreaterEqual(contrast(ON_PRIMARY,PRIMARY),4.5)
        for fg in (INK,MUTED):self.assertGreaterEqual(contrast(fg,SURFACE),4.5)
    def test_health_failure_keeps_notification_and_cards_show_last_success(self):
        s=self.settings();icon=self.pet.bubble.status_indicator;icon.notify_complete(dict(session='a',turn='1'))
        self.pet.update_connection_health({'tasks':sample('available'),'read':sample('unavailable','read_schema')})
        self.assertEqual(s.health_panel.labels['tasks'][0].text(),'正常');self.assertEqual(s.health_panel.labels['read'][0].text(),'不可用')
        self.assertEqual(icon.unread,[('a','1')]);self.pet.connection_health.records['tasks']['checked']=time.time()-100
        self.pet.record_state();self.assertEqual(s.health_panel.labels['tasks'][0].text(),'受限');self.assertEqual(icon.unread,[('a','1')])
    def test_connection_tab_has_no_path_editor_or_report_text(self):
        s=self.settings();from PySide6.QtWidgets import QPushButton,QPlainTextEdit
        labels={b.text() for b in s.findChildren(QPushButton)}
        for label in ('连接路径与检测报告','验证并保存路径','改为自动识别'):self.assertNotIn(label,labels)
        self.assertFalse(s.findChildren(QPlainTextEdit));self.assertFalse(hasattr(s,'path_fields'))
        s.connection_done(dict(summary='x',capabilities={'tasks':sample('available')}))
        self.assertIn('连接检测完成',s.status.text());self.assertEqual(s.health_panel.labels['tasks'][0].text(),'正常')
    def test_model_filter_explains_denominator_and_clear_preserves_plot(self):
        self.pet.open_report();r=self.pet.bubble.report;r.set_snapshot(report_sample());r.animation.setCurrentTime(r.animation.duration());APP.processEvents();r.set_page('models');APP.processEvents()
        plot=r.plot;series=r._series();model=series['models'][0]['model'];r.select_model(model)
        self.assertIn(model,r.filter_label.text());self.assertTrue(r.clear_filter.isVisible())
        self.assertEqual(r.model_rows[0].total,series['total']);self.assertTrue(r.model_rows[0].isChecked())
        r.clear_filter.click();self.assertIsNone(r.selected_model);self.assertIs(r.plot,plot);self.assertFalse(r.clear_filter.isVisible())
    def test_removed_selected_model_resets_filter_and_stale_report_is_labeled(self):
        self.pet.open_report();r=self.pet.bubble.report;r.set_snapshot(report_sample());r.animation.setCurrentTime(r.animation.duration());APP.processEvents();r.set_page('models');r.select_model('gpt-6.1-sol')
        fresh=copy.deepcopy(report_sample());fresh['report']['daily_models']=[v for v in fresh['report']['daily_models'] if v['model']!='gpt-6.1-sol'];fresh['unavailable']=True
        r.set_snapshot(fresh);self.assertIsNone(r.selected_model);self.assertIn('上次成功',r.note_label.text())

if __name__=='__main__':unittest.main()
