# -*- coding: utf-8 -*-
"""Stable leaf-menu primitives shared by the two independent layouts."""
from __future__ import annotations

import logging

import shiboken6

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QActionGroup, QIcon, QPixmap
from PySide6.QtWidgets import QMenu

from .. import catalog
from .icons import fitted_pet_pixmap_icon, pet_avatar_menu_icon, vector_menu_icon
from .menu_styles.common import inherit_menu_style

log = logging.getLogger(__name__)

class _AnimationIconSignals(QObject):
    ready = Signal(object)


class _AnimationIconWorker(QRunnable):
    def __init__(self, loader, animation_name: str):
        super().__init__()
        self.loader = loader
        self.animation_name = animation_name
        self.signals = _AnimationIconSignals()

    def run(self) -> None:
        self.signals.ready.emit(self.loader(self.animation_name))


class _AnimationIconApplier(QObject):
    """GUI 线程槽：接收 worker 解码完成信号并更新 QAction。

    挂在 submenu 下随菜单生命周期存在；worker 线程只负责解码，
    ready 信号经 Qt 自动队列投递到本对象（GUI 线程），避免跨线程
    操作 QMenu/QAction（Qt 未定义行为，可致偶发崩溃/图标错乱）。
    """

    def __init__(self, submenu, action, worker, pump, parent=None):
        super().__init__(parent)
        self._submenu = submenu
        self._action = action
        self._worker = worker
        self._pump = pump

    @Slot(object)
    def on_ready(self, image) -> None:
        submenu = self._submenu
        if shiboken6.isValid(submenu) is False:
            return
        if self._worker in submenu._animation_icon_workers:
            submenu._animation_icon_workers.remove(self._worker)
        # setIcon() invalidates QMenu's action geometry. Doing
        # that dozens of times on a visible, scrollable menu
        # corrupts its scroll layout and blocks hover events.
        if (
            not submenu.isVisible()
            and image is not None
            and not image.isNull()
        ):
            self._action.setIcon(fitted_pet_pixmap_icon(submenu, QPixmap.fromImage(image)))
            submenu.update()
        pump = self._pump
        if callable(pump):
            pump()


def _root_menu(menu: QMenu) -> QMenu:
    root = menu
    while isinstance(root.parent(), QMenu):
        root = root.parent()
    return root


def take_deferred_menu_callbacks(menu: QMenu) -> list:
    """Take commands that must run after the native menu tracking loop."""
    callbacks = list(getattr(menu, "_deferred_callbacks", ()))
    menu._deferred_callbacks = []
    return callbacks


def defer_menu_callback(menu: QMenu, callback) -> bool:
    """Run a command after native menu tracking ends when the menu is open."""
    if not menu.isVisible():
        callback()
        return False
    root = _root_menu(menu)
    root._deferred_callbacks = list(
        getattr(root, "_deferred_callbacks", ())
    ) + [callback]
    root.close()
    return True


def connect_action(action, callback) -> None:
    def invoke(_checked=False, action=action, callback=callback) -> None:
        parent = action.parent()
        if (
            bool(action.property("closeOnTrigger"))
            and isinstance(parent, QMenu)
            and parent.isVisible()
        ):
            defer_menu_callback(parent, callback)
            return
        callback()

    action.triggered.connect(invoke)


def add_action(
    menu: QMenu, text: str, icon_name: str | None, callback=None, *,
    close_on_trigger: bool = False,
):
    action = menu.addAction(vector_menu_icon(menu, icon_name) if icon_name else QIcon(), text)
    action.setProperty("closeOnTrigger", bool(close_on_trigger))
    if callback is not None:
        connect_action(action, callback)
    return action


def add_submenu(menu: QMenu, text: str, icon_name: str | None = None) -> QMenu:
    submenu = QMenu(text, menu)
    menu.addMenu(submenu)
    menu._owned_submenus = getattr(menu, "_owned_submenus", []) + [submenu]
    inherit_menu_style(menu, submenu)
    if icon_name:
        submenu.setIcon(vector_menu_icon(menu, icon_name))
    return submenu


def _populate_animation_category(
    submenu: QMenu, pet, entries, callback, leaf_role_icons: bool,
) -> None:
    """首次展开动画分类子菜单时才填充动作，避免根菜单构建时遍历 91 个动画。"""
    if getattr(submenu, "_animation_populated", False):
        return
    submenu._animation_populated = True

    icon_actions = []
    lazy_actions = []
    for name in entries:
        action = submenu.addAction(QIcon(), name) if leaf_role_icons else submenu.addAction(name)
        connect_action(action, lambda name=name, callback=callback: callback(name))
        if leaf_role_icons:
            icon_actions.append((action, name))
            cached_loader = getattr(pet, "animation_icon_cached_image", None)
            cached = cached_loader(name) if callable(cached_loader) else None
            if cached is not None and not cached.isNull():
                action.setIcon(fitted_pet_pixmap_icon(submenu, QPixmap.fromImage(cached)))
            else:
                # A neutral loading glyph avoids a blank/jumping text
                # column while the representative frame is decoded.
                action.setIcon(vector_menu_icon(submenu, "loading"))
                lazy_actions.append((action, name))

    if not lazy_actions:
        return

    # Decoding dozens of WebM frames while the root menu is being constructed
    # made the very first right-click block for seconds. Load only the category
    # the user actually opens in a two-thread pool and keep completed icons on
    # their QAction for later opens.
    def refresh_cached_icons(
        submenu=submenu, icon_actions=tuple(icon_actions), pet=pet,
    ) -> None:
        """Only alter QAction geometry before show or after hide."""
        # aboutToHide 会排队 singleShot 刷新，菜单可能已销毁
        if shiboken6.isValid(submenu) is False:
            return
        if submenu.isVisible():
            return
        cached_loader = getattr(pet, "animation_icon_cached_image", None)
        if not callable(cached_loader):
            return
        for action, animation_name in icon_actions:
            image = cached_loader(animation_name)
            if image is not None and not image.isNull():
                action.setIcon(fitted_pet_pixmap_icon(submenu, QPixmap.fromImage(image)))

    def start_loading(submenu=submenu, lazy_actions=tuple(lazy_actions), pet=pet) -> None:
        loader = getattr(pet, "animation_icon_image", None)
        if not callable(loader):
            return
        if not hasattr(submenu, "_animation_icon_pending"):
            submenu._animation_icon_pending = list(lazy_actions)
            submenu._animation_icon_requested = set()

        def pump() -> None:
            while (
                len(submenu._animation_icon_workers) < 2
                and submenu._animation_icon_pending
            ):
                action, animation_name = submenu._animation_icon_pending.pop(0)
                if animation_name in submenu._animation_icon_requested:
                    continue
                submenu._animation_icon_requested.add(animation_name)
                launch(action, animation_name)

        def launch(action, animation_name) -> None:
            worker = _AnimationIconWorker(loader, animation_name)
            # 解码完成信号经队列投递到 GUI 线程的 applier 槽：
            # 菜单销毁时连接随 applier（submenu 子对象）自动断开。
            applier = _AnimationIconApplier(
                submenu, action, worker, pump, parent=submenu
            )
            worker.signals.ready.connect(applier.on_ready)
            submenu._animation_icon_workers.append(worker)
            submenu._animation_icon_pool.start(worker)

        pump()

    submenu.aboutToShow.connect(refresh_cached_icons)
    submenu.aboutToShow.connect(start_loading)
    submenu.aboutToHide.connect(
        lambda refresh=refresh_cached_icons, submenu=submenu: QTimer.singleShot(0, submenu, refresh)
    )
    pool = QThreadPool(submenu)
    pool.setMaxThreadCount(2)
    submenu._animation_icon_pool = pool
    submenu._animation_icon_workers = []
    # 首次填充时立刻启动解码；后续 aboutToShow 继续由连接驱动
    start_loading()


def build_animation_categories(
    menu: QMenu, pet, *, icons: bool, legacy_labels: bool = False,
    leaf_role_icons: bool = False,
) -> None:
    categories = (
        ("待机", pet.idles, pet.switch_clip),
        ("转向", pet.turns, pet.switch_clip),
        ("移动", pet.moves, pet.trigger_move),
        ("点击回应", pet.clicks, pet.switch_clip),
        ("随机动作", pet.acts, pet.switch_clip),
    )
    for label, entries, callback in categories:
        if not entries:
            continue
        submenu = QMenu(f"动画 · {label}" if legacy_labels else label, menu)
        menu.addMenu(submenu)
        menu._owned_submenus = getattr(menu, "_owned_submenus", []) + [submenu]
        inherit_menu_style(menu, submenu)
        if icons:
            submenu.setIcon(vector_menu_icon(menu, "play"))
        # 首次展开该分类子菜单时才填充动作：根菜单构建不再遍历 91 个动画
        submenu.aboutToShow.connect(
            lambda s=submenu, e=entries, c=callback, l=leaf_role_icons, p=pet:
                _populate_animation_category(s, p, e, c, l)
        )


def build_speed_menu(menu: QMenu, pet, *, icons: bool = True) -> QMenu:
    submenu = add_submenu(menu, "播放速率", "speed" if icons else None)
    group = QActionGroup(submenu)
    group.setExclusive(True)
    for i in range(10, 21):
        value = i / 10.0
        action = submenu.addAction(f"{value:.1f}x")
        action.setCheckable(True)
        action.setChecked(abs(pet.playback_speed - value) < 0.01)
        group.addAction(action)
        connect_action(action, lambda value=value: pet.set_playback_speed(value))
    return submenu


def build_character_menu(menu: QMenu, pet, *, icons: bool = True) -> QMenu:
    submenu = add_submenu(menu, "切换角色", "character" if icons else None)
    group = QActionGroup(submenu)
    group.setExclusive(True)
    current = str(pet.cfg.get("character", catalog.DEFAULT_CHARACTER))
    for character_id in catalog.list_available_characters():
        alias_fn = getattr(pet.cfg, 'character_alias', None)
        alias = alias_fn(character_id) if callable(alias_fn) else ''
        label = alias or catalog.character_display_name(character_id)
        action = submenu.addAction(label)
        action.setCheckable(True)
        action.setChecked(character_id == current)
        group.addAction(action)
        action.setProperty("closeOnTrigger", True)
        connect_action(action, lambda character_id=character_id: pet.request_switch_character(character_id))
    # 角色显示名别名（空名恢复默认）
    rename = getattr(pet, "rename_character", None)
    if callable(rename):
        submenu.addSeparator()
        add_action(submenu, "重命名当前角色…", None, rename, close_on_trigger=True)
    return submenu


def build_size_menu(menu: QMenu, pet, *, icons: bool = True) -> QMenu:
    submenu = add_submenu(menu, "大小", "size" if icons else None)
    group = QActionGroup(submenu)
    group.setExclusive(True)
    for scale in catalog.SCALE_STEPS:
        px = int(round(catalog.CANVAS_W * scale))
        action = submenu.addAction(f"{px}px")
        action.setCheckable(True)
        action.setChecked(abs(pet.scale - scale) < 0.02)
        group.addAction(action)
        connect_action(action, lambda scale=scale: pet.change_scale(scale))
    return submenu


def add_drag_physics(menu: QMenu, pet, *, icons: bool = True):
    action = add_action(menu, "拖动物理", "physics" if icons else None)
    action.setCheckable(True)
    action.setChecked(pet.drag_physics)
    action.toggled.connect(lambda enabled, pet=pet: pet.set_drag_physics(enabled))
    return action


def add_return_corner(menu: QMenu, pet, *, icons: bool = True):
    return add_action(menu, "回到右下角", "corner" if icons else None, pet.go_default_corner)


def add_no_move(menu: QMenu, pet, *, icons: bool = True):
    action = add_action(menu, "不移动", "pause" if icons else None)
    action.setCheckable(True)
    action.setChecked(pet.no_move)
    action.toggled.connect(lambda enabled, pet=pet: pet.set_no_move(enabled))
    return action


def add_on_top(menu: QMenu, pet, *, icons: bool = True):
    action = add_action(menu, "窗口置顶", "pin" if icons else None)
    action.setCheckable(True)
    action.setChecked(bool(pet.cfg.get("on_top", True)))
    action.toggled.connect(lambda enabled, pet=pet: pet.set_on_top(enabled))
    return action


def add_spawn_pet(menu: QMenu, pet):
    callback = getattr(pet, "on_spawn_pet", None)
    if callback is None:
        return None
    if str(menu.property("menuStyle") or "") == "modern":
        icon = pet_avatar_menu_icon(menu, pet)
    else:
        icon = QIcon()
    action = menu.addAction(icon, "生小肥鱼")
    action.setProperty("closeOnTrigger", True)
    connect_action(action, callback)
    return action


def add_clear_spawned_pets(menu: QMenu, pet, *, icons: bool = True):
    """右键菜单快捷入口：退出所有小肥鱼（slot-N），设置与数据保留。"""
    callback = getattr(pet, "on_clear_spawned_pets", None)
    if callback is None:
        return None
    return add_action(
        menu,
        "退出子肥鱼",
        "clear" if icons else None,
        callback,
        close_on_trigger=True,
    )


def add_golden_spin(menu: QMenu, pet, *, icons: bool = True):
    """右键菜单快捷入口：让桌宠原地逆时针旋转一圈。"""
    callback = getattr(pet, "trigger_golden_spin", None)
    return add_action(
        menu,
        "黄金回旋",
        "play" if icons else None,
        callback,
        close_on_trigger=True,
    )


def add_edge_probe(menu: QMenu, pet, *, icons: bool = True):
    """右键菜单开关：开启/关闭拖到屏幕边缘后的自动探头。"""
    action = add_action(menu, "边缘探头", "corner" if icons else None)
    action.setCheckable(True)
    action.setChecked(bool(pet.cfg.get("edge_probe_enabled", False)))
    action.toggled.connect(
        lambda enabled, pet=pet: pet.set_edge_probe_enabled(enabled)
    )
    return action


def add_quit(menu: QMenu, pet, *, icons: bool = True):
    return add_action(menu, "退出", "exit" if icons else None, pet.request_quit, close_on_trigger=True)
