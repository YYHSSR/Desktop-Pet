"""One menu structure for all three desktop companions."""


def populate_menu(menu, add_command, add_actions, *, tray=False):
    menu.clear()
    if tray:
        for command in ('recover', 'status', 'settings', 'character'):
            add_command(menu, command)
        menu.addSeparator()
        add_command(menu, 'quit')
        menu.command_actions = menu.actions()
        return
    for command in ('status', 'walk'):
        add_command(menu, command)
    desktop = menu.addMenu('桌面操作')
    menu.desktop_menu = desktop
    for command in ('character', 'pin', 'lock', 'bubble'):
        add_command(desktop, command)
    desktop.addSeparator()
    for command in ('recover', 'position'):
        add_command(desktop, command)
    actions = menu.addMenu('角色动作')
    menu.role_actions_menu = actions
    add_actions(actions)
    menu.addSeparator()
    for command in ('settings', 'quit'):
        add_command(menu, command)
    # Keep wrappers alive while a dynamic menu is open and across Qt callbacks.
    desktop.command_actions = desktop.actions()
    actions.command_actions = actions.actions()
    menu.command_actions = menu.actions()
