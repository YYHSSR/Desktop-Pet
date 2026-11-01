"""One ordered, unique action list for character menus and previews."""


def update_pack_policy(root, weights, order):
    """Refresh metadata without re-encoding unchanged animation frames."""
    import json
    from pathlib import Path
    path = Path(root)/'assets/character/character.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    rank = {key:index for index,key in enumerate(order)}
    for item in data['actions']:
        item['randomWeight'] = weights.get(item['id'],0.)
        item['random'] = item['randomWeight'] > 0
    data['actions'].sort(key=lambda item:rank.get(item['id'],len(rank)))
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return data['actions']


def unique_actions(items):
    result, seen = [], set()
    for item in items:
        if not item:
            continue
        identity = item.get('sha256') or item.get('playbackFile') or item.get('file') or item.get('id')
        if identity in seen:
            continue
        seen.add(identity)
        result.append(item)
    return result


def populate_action_menu(menu, items, callback):
    # Qt otherwise wraps a tall menu into multiple columns on small screens.
    from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleFactory
    class SingleColumnStyle(QProxyStyle):
        def styleHint(self, hint, option=None, widget=None, returnData=None):
            if hint == QStyle.StyleHint.SH_Menu_Scrollable:
                return 1
            return super().styleHint(hint, option, widget, returnData)
    # A proxy takes ownership of its base; never give it the application's style.
    base = QStyleFactory.create(QApplication.style().objectName()) or QStyleFactory.create('Fusion')
    style = SingleColumnStyle(base); style.setParent(menu)
    menu.setStyle(style); menu._single_column_style = style
    for item in unique_actions(items):
        action = menu.addAction(item.get('name') or ('待机' if item['id']=='idle' else item['id']))
        action.setData(item['id'])
        action.triggered.connect(lambda checked=False, value=item: callback(value))
