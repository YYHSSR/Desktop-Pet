"""Pet greeting header: an accessible command using the current menu theme."""
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton, QWidgetAction

from .shared import defer_menu_callback


def add_pet_greeting(menu, pet):
    action = QWidgetAction(menu)
    action.setText("厉害了我的鲸")
    action.setProperty("closeOnTrigger", True)
    button = QPushButton("厉害了我的鲸    请点击 ›", menu)
    button.setObjectName("petGreetingButton")
    button.setAccessibleName("厉害了我的鲸，请点击让鲸鱼娘回应")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setMinimumHeight(40)
    button.setIcon(QIcon(str(Path(__file__).resolve().parents[2] / "assets" / "icon.ico")))
    button.setIconSize(QSize(28, 28))
    button.setFont(menu.font())
    appearance = dict(menu.property("modernAppearance") or {})
    dark = bool(menu.property("modernDark"))
    foreground = appearance.get("dark_foreground" if dark else "light_foreground", "#f3f3f3" if dark else "#171717")
    hover = appearance.get("dark_hover" if dark else "light_hover", "#3a3a3a" if dark else "#eeeeee")
    button.setStyleSheet(
        f"QPushButton {{ border: none; border-radius: 9px; padding: 4px 8px; text-align: left; color: {foreground}; background: transparent; }}"
        f"QPushButton:hover, QPushButton:focus {{ background: {hover}; }}"
        "QPushButton:focus { border: 1px solid #1677e8; }"
    )
    button.clicked.connect(lambda: defer_menu_callback(menu, pet.respond_to_menu_click))
    action.triggered.connect(lambda: defer_menu_callback(menu, pet.respond_to_menu_click))
    action.setDefaultWidget(button)
    menu.addAction(action)
    return action
