"""Check the actual bundled dependencies and resources without user connections."""
import json
import sys
import traceback
from pathlib import Path


def run(destination):
    report=dict(passed=False,frozen=bool(getattr(sys,'frozen',False)))
    try:
        from PySide6.QtWidgets import QApplication
        from runtime_paths import resource_root
        from typography import register_font
        from material_store import MaterialStore
        from desktop_services import all_items
        from sustained_assets import seam_items
        from PIL import Image
        from tempfile import TemporaryDirectory
        app=QApplication.instance() or QApplication([])
        root=resource_root()
        with TemporaryDirectory(prefix='desktop-pet-bundle-check-') as state:
            store=MaterialStore(root,Path(state));store.verify(store.tier_root('light'),'light')
            assets=store.tier_root('light')
            manifest=json.loads((assets/'素材清单.json').read_text(encoding='utf-8'))
            items=all_items(manifest)+seam_items(manifest)
            for item in items:
                with Image.open(assets/(item.get('playbackFile') or item['file'])) as image:
                    image.seek(0);image.load()
                    if image.size!=(512,512):raise ValueError('轻量资源尺寸不匹配')
            report.update(playbackFiles=len(items),materialChecksums=True,fontLoaded=register_font(),sound=(root/'app/sounds/click.wav').is_file())
            report['hdBuiltin']='hd' in store.embedded
            if report['hdBuiltin']:
                hd=store.ensure('hd')
                with Image.open(hd/'quality-v1/idle.webp') as image:report['hdChecksums']=image.size==(720,720)
        report['passed']=report['playbackFiles']==31 and report['fontLoaded'] and report['sound'] and (report.get('hdChecksums',False) or not report['frozen'])
    except Exception:report['error']=traceback.format_exc()
    path=Path(destination);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
