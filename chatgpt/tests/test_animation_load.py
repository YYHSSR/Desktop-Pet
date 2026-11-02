"""Real chart layers/navigation: bounded work, stable layout and readable text."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import time
import unittest
from unittest.mock import patch
from test_daily_report import APP,sample
from compact_bubble import CompactBubble
from daily_report import DailyReport
from quota_summary import QuotaSummary

class AnimationLoadTests(unittest.TestCase):
    def setUp(self):
        self.b=CompactBubble();self.b.windows=[dict(name='一周',remaining=73,resetsAt=time.time()+86400)]
        self.b.token_snapshot=sample();self.b.redraw();self.b.move(100,650);self.b.show();APP.processEvents()
    def tearDown(self):
        self.b.size_transition.complete();self.b.close();self.b.deleteLater();APP.processEvents()
    def finish(self):self.b.size_transition.complete();APP.processEvents()
    def test_unified_refresh_does_not_depend_on_card_selection(self):
        b=self.b;seen=[];b.refreshAllRequested.connect(lambda:seen.append('all'))
        b.set_refresh_busy(True);b.select_dashboard('reset');self.assertFalse(b.refresh_button.isEnabled())
        b.finish_refresh();b.refresh_button.click();b.select_dashboard('tokens');b.refresh_button.click()
        self.assertEqual(seen,['all']);self.assertFalse(b.refresh_button.isEnabled())
        self.assertFalse(b.token_refresh_buttons);self.assertFalse(b.reset_refresh_buttons)
    def test_quota_animation_never_rasterizes_labels_again(self):
        quota=self.b.findChild(QuotaSummary);quota.begin_reveal();builds=quota.layer_builds;quota.start_reveal()
        with patch('quota_summary.font',side_effect=AssertionError('font work on animation frame')):
            for ms in range(0,421,20):quota.animation.setCurrentTime(ms);quota.grab()
        self.assertEqual(quota.layer_builds,builds)
    def test_report_scrollbar_gutter_is_ready_before_animation_finishes(self):
        r=DailyReport(self.b);self.b.report=r;r.set_snapshot(sample());r.open()
        snapshot=(r.scroll.viewport().size(),r.plot.width())
        r.animation.setCurrentTime(r.animation.duration());landed=(r.scroll.viewport().size(),r.plot.width());APP.processEvents()
        self.assertEqual(snapshot,landed);self.assertEqual(landed,(r.scroll.viewport().size(),r.plot.width()))
        self.assertFalse(r.scroll.verticalScrollBar().isVisible())
        self.assertEqual(r.scroll.verticalScrollBar().maximum(),0)
        self.assertIn('font-size:10px',r.note_label.styleSheet());self.assertIn('font-weight:600',r.note_label.styleSheet())
        self.assertFalse(hasattr(r,'analogy'))
    def test_landing_cache_is_ready_before_first_motion_frame(self):
        self.b.toggle_details();t=self.b.size_transition
        self.assertTrue(t.running);self.assertIsNotNone(t.morph._landing)
        cached=t.morph._landing;key=cached[1][0].cacheKey()
        t.animation.setCurrentTime(round(t.animation.duration()*.95));self.b.grab()
        self.assertIs(cached,t.morph._landing);self.assertEqual(key,t.morph._landing[1][0].cacheKey())

if __name__=='__main__':unittest.main()
