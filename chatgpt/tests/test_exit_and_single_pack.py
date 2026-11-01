"""Real event-loop shutdown from both menus after opening the embedded editor."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ExitAndPackTests(unittest.TestCase):
    def test_context_and_tray_exit_after_settings_with_or_without_running_worker(self):
        script=r'''
import json,sys,threading
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QThread,QTimer
from PySide6.QtWidgets import QApplication,QMenu,QLabel
from desktop import DesktopPet
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
pet=DesktopPet(monitor=False);pet.show()
with patch('desktop_settings.autostart_enabled',return_value=False),patch('codex_startup.enabled',return_value=False):pet.open_settings()
pet.bubble.size_transition.complete();app.processEvents()
assert not hasattr(pet.settings_dialog,'path_job')
assert not hasattr(pet.settings_dialog,'material_panel')
labels=[w.text() for w in pet.settings_dialog.findChildren(QLabel)]
assert not any(any(word in text for word in ('登录时运行','完成提醒确认后','内置 ChatGpt画质')) for text in labels)
assert pet.settings_dialog.fields['video_fullscreen_yield'].text()=='视频全屏时临时取消置顶'
pet.bubble.show_status(True);pet.bubble.size_transition.complete();app.processEvents()
assert pet.bubble.details_tabs is None
assert pet.bubble.today_tokens_card is not None
assert not pet.material_store.available('hd')
class Worker(QThread):
    def __init__(self,parent):super().__init__(parent);self.cancel=threading.Event()
    def run(self):self.cancel.wait(2)
if sys.argv[2]=='worker':pet.worker=Worker(pet);pet.worker.start()
menu=QMenu();pet.build_menu(menu,tray=sys.argv[1]=='tray')
action=next(a for a in menu.actions() if a.objectName()=='command_quit')
exited=[];app.aboutToQuit.connect(lambda:exited.append(True))
expired=[]
def timeout():expired.append(True);app.quit()
QTimer.singleShot(2500,timeout);QTimer.singleShot(50,action.trigger)
app.exec()
assert exited and not expired,'exit did not stop the application event loop'
assert not pet.tray.isVisible() and not pet.bubble.isVisible() and not pet.isVisible()
assert not pet.worker or not pet.worker.isRunning()
print('EXIT PASS')
'''
        for menu in ('context','tray'):
            for worker in ('idle','worker'):
                with self.subTest(menu=menu,worker=worker),tempfile.TemporaryDirectory() as tmp:
                    env=os.environ.copy()
                    env.update(LOCALAPPDATA=tmp,APPDATA=str(Path(tmp)/'roaming'),CODEX_HOME=str(Path(tmp)/'codex'),
                               QT_QPA_PLATFORM='offscreen',PYTHONPATH=str(ROOT/'app'))
                    result=subprocess.run([sys.executable,'-c',script,menu,worker],cwd=ROOT,env=env,
                                          capture_output=True,timeout=10)
                    self.assertEqual(result.returncode,0,(result.stdout+result.stderr).decode(errors='replace'))
                    self.assertIn(b'EXIT PASS',result.stdout)

    def test_native_pack_has_no_hd_contract_and_ignores_old_hd_preference(self):
        from material_store import MaterialStore
        catalog=json.loads((ROOT/'app/material_catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(set(catalog['tiers']),{'light'})
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)
            (state/'material-preferences.json').write_text('{"tier":"hd"}')
            store=MaterialStore(ROOT,state)
            self.assertEqual((store.preferred,store.current),('light','light'))
            self.assertFalse(store.available('hd'))


if __name__=='__main__':unittest.main()
