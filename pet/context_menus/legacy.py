# -*- coding: utf-8 -*-
"""Legacy context-menu layout.

Keep this module intentionally independent from ``modern.py``: preserving the
original interaction model is more important than sharing layout code.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMenu

from .shared import (
    add_action,
    add_agent_link_menu,
    add_autostart,
    add_clear_spawned_pets,
    add_drag_physics,
    add_edge_probe,
    add_golden_spin,
    add_mouse_through,
    add_no_move,
    add_on_top,
    add_quit,
    add_return_corner,
    add_spawn_pet,
    add_template_switch,
    build_animation_categories,
    build_character_menu,
    build_size_menu,
    build_speed_menu,
)


def build_legacy_menu(menu: QMenu, pet, template: dict) -> None:
    """Build only the classic flat menu and its original settings entry."""
    settings = getattr(pet, "on_open_modern_settings", None)
    if callable(settings):
        add_action(menu, "桌宠设置", None, settings, close_on_trigger=True)

    menu.addSeparator()
    build_animation_categories(menu, pet, icons=False, legacy_labels=True)
    build_speed_menu(menu, pet, icons=False)
    add_drag_physics(menu, pet, icons=False)
    build_character_menu(menu, pet, icons=False)

    menu.addSeparator()
    add_return_corner(menu, pet, icons=False)
    add_on_top(menu, pet, icons=False)
    add_no_move(menu, pet, icons=False)
    add_mouse_through(menu, pet, icons=False)
    add_autostart(menu, icons=False)
    add_spawn_pet(menu, pet)
    add_clear_spawned_pets(menu, pet, icons=False)
    add_golden_spin(menu, pet, icons=False)
    add_edge_probe(menu, pet, icons=False)
    build_size_menu(menu, pet, icons=False)

    menu.addSeparator()
    add_agent_link_menu(menu, pet, icons=False)

    menu.addSeparator()
    add_template_switch(menu, pet, str(template["switch_label"]), str(template["switch_to"]), icons=False)

    menu.addSeparator()
    add_quit(menu, pet, icons=False)
