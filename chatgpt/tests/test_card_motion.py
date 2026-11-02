import os,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QPushButton
import test_settings_journeys as fixtures

APP=QApplication.instance() or QApplication([])


class IntegratedCardTests(unittest.TestCase):
    def setUp(self):self.fixture=fixtures.InteractionTests();self.fixture.setUp()
    def tearDown(self):self.fixture.tearDown()
    def test_settings_have_no_maintenance_self_talk_or_update_controls(self):
        s=self.fixture.settings()
        self.assertFalse(hasattr(s,'update_panel'))
        tabs={s.tabs.tabText(i) for i in range(s.tabs.count())}
        self.assertNotIn('维护',tabs)
        labels={button.text() for button in s.findChildren(QPushButton)}
        for label in ('打开配置与数据目录','导出诊断报告','备份设置','恢复设置备份'):self.assertNotIn(label,labels)
        for key in ('update_checks','self_talk','talk_min','talk_max','talk_quiet','bubble_mode','capsule_action'):self.assertNotIn(key,s.fields)


if __name__=='__main__':unittest.main()
