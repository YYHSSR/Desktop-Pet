"""Public contracts for the pet + ChatGPT Work build."""
import json
import sys

from PySide6.QtWidgets import QApplication

from pet.config import Config
from pet.modern_settings_dialog import ModernSettingsDialog


def test_retired_ai_config_does_not_return_from_disk_merge(tmp_path):
    cfg = Config(tmp_path)
    path = cfg.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'chat': {'providers': {'old': {'api_key': 'secret'}}},
                               'proactive_screen': {'enabled': True},
                               'file_interpret': {'enabled': True},
                               'chat_ui_style': 'classic', 'scale': 0.75,
                               'agent_link': {'codex': True}}), encoding='utf-8')
    cfg.reload()
    assert cfg.get('agent_link')['codex'] is True
    assert cfg.save()
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert not {'chat', 'proactive_screen', 'file_interpret', 'chat_ui_style'} & saved.keys()
    assert not {'chat', 'proactive_screen', 'file_interpret', 'chat_ui_style'} & cfg.data.keys()


def test_settings_only_offer_current_pet_capabilities(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = ModernSettingsDialog(Config(tmp_path))
    try:
        labels = [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())]
        assert labels == ['常规', '桌宠', '互动', '菜单', '自动化与联动']
        assert not hasattr(dialog, 'ai_page')
        assert not any(name == 'pet.chat' or name.startswith('pet.chat.') for name in sys.modules)
        assert dialog._write_config()
    finally:
        dialog.close()
        app.processEvents()
