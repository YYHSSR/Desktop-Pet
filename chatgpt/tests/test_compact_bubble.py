import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import time,unittest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QToolButton
from compact_bubble import CompactBubble
from quota_summary import QuotaSummary

app=QApplication.instance() or QApplication([])

def settle():
    app.processEvents()
    for window in app.topLevelWidgets():
        transition=getattr(window,'size_transition',None)
        if transition:transition.complete()
    app.processEvents()

class BubbleTests(unittest.TestCase):
    def setUp(self):self.bubble=CompactBubble();self.bubble.status='正在检查代码';self.bubble.heading='Codex · 处理中'
    def tearDown(self):self.bubble.close();self.bubble.deleteLater();settle()
    def test_two_quotas_keep_exact_values_and_distinct_reset_times(self):
        now=time.time();self.bubble.windows=[dict(name='5小时',remaining=0,resetsAt=now+3600),dict(name='一周',remaining=100,resetsAt=None)]
        self.bubble.redraw();settle();cards=[d for d in self.bubble.findChildren(QuotaSummary) if d.isVisible()]
        self.assertEqual(len(cards),1);self.assertEqual([w['remaining'] for w in cards[0].items],[0,100]);self.assertIn('重置时间未知',cards[0].accessibleDescription())
        self.assertIn('北京时间',cards[0].accessibleDescription());self.assertEqual(self.bubble.height(),188)
    def test_unavailable_quota_is_not_rendered_as_zero(self):
        card=QuotaSummary([dict(name='5小时',remaining=None,resetsAt=None)]);self.assertIsNone(card.items[0]['remaining'])
        self.assertIn('暂不可用',card.accessibleDescription());self.assertNotIn('剩余额度：0%',card.accessibleDescription())
        card.deleteLater()
    def test_hide_quota_and_show_summary_keeps_popup_small(self):
        self.bubble.show_quota=False;self.bubble.redraw();self.assertLess(self.bubble.height(),80)
        self.assertFalse([d for d in self.bubble.findChildren(QuotaSummary) if d.isVisible()])
    def visible_button(self,name):
        return next(w for w in self.bubble.findChildren(QToolButton) if w.objectName()==name and w.isVisible())
    def test_busy_refresh_state_survives_status_redraw_and_recovers(self):
        events=[];self.bubble.windows=[dict(name='一周',remaining=80)];self.bubble.select_dashboard('reset')
        self.bubble.refreshAllRequested.connect(lambda:events.append('all'))
        self.bubble.set_refresh_busy(True);self.bubble.redraw()
        self.bubble.refresh_button.click();self.assertFalse(events)
        self.assertIn('正在刷新',self.bubble.refresh_button.toolTip())
        self.bubble.finish_refresh();self.bubble.refresh_button.click();self.assertEqual(events,['all'])
    def test_five_hour_quota_precedes_weekly_regardless_of_input_order(self):
        card=QuotaSummary([dict(name='一周',remaining=87),dict(name='5小时',remaining=68)])
        self.assertEqual([w['name'] for w in card.items],['5小时','一周']);card.deleteLater()
    def test_all_shortcut_buttons_fit_inside_compact_bubble_on_both_cards(self):
        for page in ('tokens','reset'):
            self.bubble.select_dashboard(page);settle()
            for button in self.bubble.findChildren(QToolButton):
                if not button.isVisible():continue
                point=button.mapTo(self.bubble,QPoint(0,0))
                self.assertGreaterEqual(point.x(),0);self.assertGreaterEqual(point.y(),0)
                self.assertLessEqual(point.x()+button.width(),self.bubble.width());self.assertLessEqual(point.y()+button.height(),self.bubble.height())
            self.assertEqual(self.bubble.height(),188)

if __name__=='__main__':unittest.main()
