"""Action registration and tree rendering for the shared Menu Action Model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import QMenu

from .icons import vector_menu_icon
from .quick_launch import add_quick_launch_menu
from .quick_urls import add_quick_urls_menu
from .pet_header import add_pet_greeting
from .shared import (
    add_action,
    add_clear_spawned_pets,
    add_drag_physics,
    add_edge_probe,
    add_golden_spin,
    add_no_move,
    add_on_top,
    add_quit,
    add_return_corner,
    add_spawn_pet,
    add_submenu,
    build_animation_categories,
    build_character_menu,
    build_size_menu,
    build_speed_menu,
)


Builder = Callable[[QMenu, object], object]
Availability = Callable[[object], bool]


ACTION_ICONS = {
    "animations_hub": "play", "character": "character", "playback_speed": "speed",
    "size": "size", "drag_physics": "physics", "no_move": "pause",
    "on_top": "pin",
    "return_corner": "corner",
    "spawn_pet": "spawn", "clear_spawned_pets": "clear",
    "golden_spin": "play", "edge_probe": "corner",
    "pet_controls": "pet",
    "quick_launch": "application",
    "quick_urls": "web",
    "modern_settings": "settings", "quit": "quit",
}

@dataclass(frozen=True)
class MenuActionSpec:
    build: Builder
    available: Availability = lambda _pet: True


def _callback_available(name: str) -> Availability:
    return lambda pet: callable(getattr(pet, name, None))


def _build_animations(menu, pet):
    submenu = add_submenu(menu, "播放动画", "play")
    build_animation_categories(submenu, pet, icons=False, leaf_role_icons=True)
    return submenu


def _build_settings(menu, pet):
    return add_action(menu, "桌宠设置", "settings", pet.on_open_modern_settings, close_on_trigger=True)


class MenuActionRegistry:
    """Resolve capability-aware action IDs and render a resolved menu tree."""

    def __init__(self) -> None:
        self._specs = {
            "pet_greeting": MenuActionSpec(add_pet_greeting, _callback_available("respond_to_menu_click")),
            "animations_hub": MenuActionSpec(_build_animations),
            "character": MenuActionSpec(lambda menu, pet: build_character_menu(menu, pet)),
            "playback_speed": MenuActionSpec(lambda menu, pet: build_speed_menu(menu, pet)),
            "size": MenuActionSpec(lambda menu, pet: build_size_menu(menu, pet)),
            "drag_physics": MenuActionSpec(add_drag_physics),
            "no_move": MenuActionSpec(add_no_move),
            "on_top": MenuActionSpec(add_on_top),
            "return_corner": MenuActionSpec(add_return_corner),
            "spawn_pet": MenuActionSpec(add_spawn_pet, _callback_available("on_spawn_pet")),
            "clear_spawned_pets": MenuActionSpec(
                add_clear_spawned_pets,
                _callback_available("on_clear_spawned_pets"),
            ),
            "golden_spin": MenuActionSpec(
                add_golden_spin,
                _callback_available("trigger_golden_spin"),
            ),
            "edge_probe": MenuActionSpec(add_edge_probe),
            "quick_launch": MenuActionSpec(
                lambda menu, pet: add_quick_launch_menu(menu, pet),
            ),
            "quick_urls": MenuActionSpec(
                lambda menu, pet: add_quick_urls_menu(menu, pet),
            ),
            "modern_settings": MenuActionSpec(
                _build_settings, _callback_available("on_open_modern_settings")
            ),
            "quit": MenuActionSpec(add_quit),
        }


    def available_ids(self, pet) -> frozenset[str]:
        return frozenset(
            action_id
            for action_id, spec in self._specs.items()
            if spec.available(pet)
        )


    def populate(self, menu: QMenu, pet, nodes) -> None:
        for node in nodes:
            kind = node.get("type")
            if kind == "separator":
                if menu.actions() and not menu.actions()[-1].isSeparator():
                    menu.addSeparator()
            elif kind == "submenu":
                submenu = add_submenu(menu, node.get("label", ""))
                name = ACTION_ICONS.get(node.get("id"), "")
                if name:
                    submenu.menuAction().setIcon(vector_menu_icon(menu, name))
                self.populate(submenu, pet, node.get("children", []))
            else:
                spec = self._specs.get(node.get("id"))
                if spec is not None and spec.available(pet):
                    spec.build(menu, pet)
        if menu.actions() and menu.actions()[-1].isSeparator():
            menu.removeAction(menu.actions()[-1])


MENU_ACTIONS = MenuActionRegistry()
