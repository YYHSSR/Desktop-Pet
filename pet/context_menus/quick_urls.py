# -*- coding: utf-8 -*-
"""Configurable URL shortcuts used only by the modern menu."""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMenu

from ..config import DEFAULT_QUICK_URLS, _clean_quick_urls
from .icons import vector_menu_icon
from .shared import add_submenu, connect_action


def configured_quick_urls(config) -> list[dict]:
    value = config.get("quick_urls", DEFAULT_QUICK_URLS)
    return _clean_quick_urls(value)


def launch_quick_url(item: dict) -> bool:
    url = str(item.get("url") or "").strip()
    if not url:
        return False
    if not url.startswith(("http://", "https://", "ftp://")):
        url = "https://" + url
    qurl = QUrl(url)
    if qurl.isValid():
        return bool(QDesktopServices.openUrl(qurl))
    return bool(webbrowser.open(url))


def add_quick_urls_menu(menu: QMenu, pet_or_cfg) -> QMenu:
    cfg = getattr(pet_or_cfg, "cfg", pet_or_cfg)
    urls = configured_quick_urls(cfg)
    submenu = add_submenu(menu, "快捷网址", "web")
    if not urls:
        placeholder = submenu.addAction("尚未配置快捷网址")
        placeholder.setEnabled(False)
    else:
        for item in urls:
            action = submenu.addAction(vector_menu_icon(submenu, "web"), str(item.get("name") or "网址"))
            action.setProperty("closeOnTrigger", True)
            action.setToolTip(str(item.get("url") or ""))
            connect_action(action, lambda item=dict(item): launch_quick_url(item))
    submenu.addSeparator()
    manage_act = submenu.addAction(vector_menu_icon(submenu, "settings"), "管理快捷网址...")
    manage_act.setProperty("closeOnTrigger", True)
    open_settings = getattr(pet_or_cfg, "on_open_modern_settings", None)
    if callable(open_settings):
        connect_action(manage_act, lambda: open_settings())
    return submenu
