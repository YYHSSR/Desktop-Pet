import os
import unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtCore import QRect
from compact_bubble import CompactBubble
from ui_theme import contrast,SURFACE,INK,MUTED,ACCENT
APP=QApplication.instance() or QApplication([])


class BubbleStateTests(unittest.TestCase):
    def setUp(self):self.b=CompactBubble();self.b.move(100,550);self.b.show();APP.processEvents()
    def tearDown(self):self.b.size_transition.complete();self.b.close();self.b.deleteLater();APP.processEvents()
    def finish(self):self.b.size_transition.complete();APP.processEvents()
    def test_palette_contrast(self):
        for fg in (INK,MUTED):self.assertGreaterEqual(contrast(fg,SURFACE),4.5)
        self.assertGreaterEqual(contrast(ACCENT,SURFACE),3)
    def test_status_updates_do_not_open_details_or_editors(self):
        self.b.quota([dict(name='一周',remaining=80)]);self.b.message('新额度')
        self.b.status_indicator.observe(dict(state='working',active=1))
        self.assertFalse(self.b.expanded);self.assertEqual(self.b.panel_page,'status')
    def test_native_canvas_remains_fixed_through_details_and_back(self):
        for _ in range(2):
            self.b.toggle_details();t=self.b.size_transition;rect=QRect(self.b.geometry());handle=int(self.b.winId())
            for ms in range(0,280,20):
                t.animation.setCurrentTime(ms);self.assertEqual(self.b.geometry(),rect);self.assertEqual(int(self.b.winId()),handle)
            self.finish();self.assertTrue(self.b.content.isVisible());self.assertIsNone(t.cover.image);self.assertIsNone(t.before)
    def test_navigation_during_transition_keeps_latest_request(self):
        self.b.show_page('settings',QWidget());t=self.b.size_transition;t.animation.setCurrentTime(100)
        self.b.collapse_to_normal();self.finish();self.finish()
        self.assertEqual(self.b.panel_page,'status');self.assertFalse(self.b.expanded)
    def test_read_completion_disappears_and_retains_other_running_conversation(self):
        b=self.b;icon=b.status_indicator;clock=[0.];icon.clock=lambda:clock[0]
        for sid,state in [('a','complete'),('b','working')]:b.roster.observe(dict(session=sid,state=state,title='会话'+sid))
        icon.notify_complete(dict(session='a',turn='turn-a'));icon.observe(dict(session='b',state='working',active=1));b.redraw()
        self.assertEqual(len(b.status_view.text().splitlines()),2)
        clock[0]=3.;self.assertTrue(icon.acknowledge_seen([('a','turn-a')]));b.redraw()
        self.assertEqual(icon.visual(),'busy');self.assertNotIn('会话a',b.status_view.text());self.assertIn('会话b',b.status_view.text())


class ChartEntryTests(unittest.TestCase):
    def test_entry_starts_at_zero_survives_status_refresh_and_stops_when_hidden(self):
        from token_charts import TokenPlot
        b=CompactBubble();b.show();APP.processEvents()
        try:
            b.select_token_range('day');plot=next(w for w in b.findChildren(TokenPlot) if w.isVisible())
            self.assertEqual(plot.reveal.progress,0.);plot.reveal.animation.setCurrentTime(180);progress=plot.reveal.progress
            b.message('新状态，不应重播图表');fresh=next(w for w in b.findChildren(TokenPlot) if w.isVisible())
            self.assertAlmostEqual(fresh.reveal.progress,progress);b.hide();APP.processEvents()
            self.assertFalse(fresh.reveal.animation.state().value)
        finally:b.close();b.deleteLater();APP.processEvents()
    def test_curve_head_follows_actual_segments(self):
        from chart_reveal import trace_head
        from PySide6.QtCore import QPointF
        points=[QPointF(0,0),QPointF(10,20),QPointF(20,0)]
        self.assertEqual(trace_head(points,.25),QPointF(5,10));self.assertEqual(trace_head(points,.75),QPointF(15,10))

if __name__=='__main__':unittest.main()
