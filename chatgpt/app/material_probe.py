"""Exercise the native-size pack, reduced settings and real tray exit in Qt."""
import json
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


def run(destination):
    from desktop import DesktopPet
    from PIL import Image
    app=QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    p=DesktopPet(monitor=False)
    p.apply_settings(dict(wandering=False,random_actions=False,video_fullscreen_yield=False))
    p.show();p.open_settings()
    target=Path(destination);target.parent.mkdir(parents=True,exist_ok=True)
    checks={};errors=[];expired=[]
    def sample():
        try:
            p.bubble.size_transition.complete();app.processEvents()
            checks['singleNativePack']=set(p.material_store.catalog['tiers'])=={'light'}
            checks['noQualityPanel']=not hasattr(p.settings_dialog,'material_panel')
            checks['twoSettingsTabs']=p.settings_dialog.tabs.count()==2
            checks['embeddedSettings']=not p.settings_dialog.isWindow()
            with Image.open(p.asset_path(p.manifest['idle'])) as im:checks['native512']=im.size==(512,512)
            p.bubble.grab().save(str(target.with_name(target.stem+'-settings.png')))
            p.settings_dialog.tabs.setCurrentIndex(1);app.processEvents()
            p.bubble.grab().save(str(target.with_name(target.stem+'-behavior.png')))
            p.bubble.show_status(True);p.bubble.size_transition.complete();app.processEvents()
            checks['noDuplicateDetailTabs']=p.bubble.details_tabs is None
            checks['todayTokensKept']=p.bubble.today_tokens_card is not None
            p.bubble.grab().save(str(target.with_name(target.stem+'-status.png')))
            p.populate_tray()
            action=next(a for a in p.tray_menu.actions() if a.objectName()=='command_quit')
            QTimer.singleShot(50,action.trigger)
        except Exception as exc:
            errors.append(str(exc));p.close()
    def timeout():expired.append(True);p.close();app.quit()
    QTimer.singleShot(300,sample);QTimer.singleShot(5000,timeout)
    app.exec()
    checks['trayWithdrawn']=not p.tray.isVisible()
    checks['windowClosed']=p.closing and not p.isVisible() and not p.bubble.isVisible()
    checks['eventLoopExited']=not expired
    result=dict(passed=not errors and all(checks.values()),checks=checks,errors=errors)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1
