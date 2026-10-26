import os,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QPushButton,QScrollArea
import test_settings_journeys as fixtures

APP=QApplication.instance() or QApplication([])


class IntegratedCardTests(unittest.TestCase):
    def setUp(self):self.fixture=fixtures.InteractionTests();self.fixture.setUp()
    def tearDown(self):self.fixture.tearDown()
    def test_advanced_toggle_repaints_once_without_moving_scroll_or_window(self):
        f=self.fixture;s=f.settings();b=f.pet.bubble;native=b.geometry();s.tabs.setCurrentIndex(1);APP.processEvents()
        window=s.window();calls=[]
        original=window.setUpdatesEnabled
        def record(value):calls.append(value);original(value)
        window.setUpdatesEnabled=record
        try:s.advanced_button.click()
        finally:del window.setUpdatesEnabled
        self.assertEqual(calls,[False,True]);self.assertTrue(s.advanced_card.isVisibleTo(s))
        scroll=next(a for a in s.findChildren(QScrollArea) if a.isVisible());value=scroll.verticalScrollBar().value()
        s.advanced_button.click();APP.processEvents()
        self.assertFalse(s.advanced_card.isVisibleTo(s));self.assertEqual(b.geometry(),native)
        self.assertLessEqual(scroll.verticalScrollBar().value(),max(value,scroll.verticalScrollBar().maximum()))
    def test_connection_tab_has_no_path_module(self):
        s=self.fixture.settings();labels={button.text() for button in s.findChildren(QPushButton)}
        self.assertFalse(hasattr(s,'path_toggle'));self.assertFalse(hasattr(s,'paths_card'))
        self.assertNotIn('连接路径与检测报告',labels);self.assertIn('检测连接与额度',labels)
    def test_settings_have_no_maintenance_self_talk_or_update_controls(self):
        s=self.fixture.settings()
        self.assertFalse(hasattr(s,'update_panel'))
        tabs={s.tabs.tabText(i) for i in range(s.tabs.count())}
        self.assertNotIn('维护',tabs)
        labels={button.text() for button in s.findChildren(QPushButton)}
        for label in ('打开配置与数据目录','导出诊断报告','备份设置','恢复设置备份'):self.assertNotIn(label,labels)
        for key in ('update_checks','self_talk','talk_min','talk_max','talk_quiet','bubble_mode','capsule_action'):self.assertNotIn(key,s.fields)


if __name__=='__main__':unittest.main()
