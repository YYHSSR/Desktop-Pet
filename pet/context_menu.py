"""Fixed modern pet menu; persistent preferences belong to one surface."""
from __future__ import annotations

import json
from importlib import resources
from PySide6.QtWidgets import QMenu
from .context_menus.registry import MENU_ACTIONS
from .context_menus.menu_styles import apply_modern_menu_style, install_modern_check_indicators
from .context_menus.menu_styles.common import install_responsive_menu_style, install_stay_open_interaction


def load_default_menu_layout() -> dict:
    path = resources.files("pet.menu_templates").joinpath("modern-default-v1.json")
    return json.loads(path.read_text(encoding="utf-8"))


def populate_context_menu(menu: QMenu, pet) -> None:
    apply_modern_menu_style(menu, pet.cfg.get("context_menu_appearance", {}))
    available = MENU_ACTIONS.available_ids(pet)

    def supported(nodes):
        result = []
        for node in nodes:
            if node.get("type") == "submenu":
                node = dict(node, children=supported(node.get("children", [])))
                if node["children"]:
                    result.append(node)
            elif node.get("type") == "separator" or node.get("id") in available:
                result.append(node)
        return result

    MENU_ACTIONS.populate(menu, pet, supported(load_default_menu_layout()["nodes"]))
    install_modern_check_indicators(menu)
    install_responsive_menu_style(menu)
    install_stay_open_interaction(menu)
