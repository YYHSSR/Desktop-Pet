"""Tabbed settings with an explicit draft, matching the Gpt editor workflow."""
from PySide6.QtCore import Qt, QObject, Signal, QRectF, QPointF
from PySide6.QtGui import QShortcut, QKeySequence, QPainter, QPen, QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QScrollArea, QLabel, QCheckBox, QComboBox, QLineEdit, QDoubleSpinBox, QPushButton, QStyle, QStyleOptionButton)


class EditorCheckBox(QCheckBox):
    """Keep a visible boxed indicator even under the translucent sheet style."""
    def __init__(self,text,palette):
        super().__init__(text);self.colors=palette

    def paintEvent(self,event):
        option=QStyleOptionButton();self.initStyleOption(option)
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        caption=QStyleOptionButton(option)
        caption.rect=self.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents,option,self)
        self.style().drawControl(QStyle.ControlElement.CE_CheckBoxLabel,caption,painter,self)
        rect=QRectF(self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator,option,self)).adjusted(.5,.5,-.5,-.5)
        painter.setOpacity(1. if self.isEnabled() else .5)
        painter.setPen(QPen(QColor(self.colors.accent if self.isChecked() else self.colors.muted),1))
        painter.setBrush(QColor(self.colors.accent if self.isChecked() else self.colors.surface))
        painter.drawRoundedRect(rect,3,3)
        if self.isChecked():
            pen=QPen(QColor('white'),1.7);pen.setCapStyle(Qt.PenCapStyle.RoundCap);painter.setPen(pen)
            painter.drawPolyline([QPointF(rect.left()+rect.width()*.2,rect.top()+rect.height()*.52),
                                  QPointF(rect.left()+rect.width()*.43,rect.top()+rect.height()*.74),
                                  QPointF(rect.left()+rect.width()*.82,rect.top()+rect.height()*.27)])


class TabSwitch(QObject):
    changed = Signal(int)
    def __init__(self, tabs):
        super().__init__(tabs); self.tabs = tabs; tabs.currentChanged.connect(self.changed)
    def set_index(self, index): self.tabs.setCurrentIndex(index)


class SettingsPanel(QWidget):
    optionChanged = Signal(str, object)
    resetRequested = Signal(list)
    returnRequested = Signal()

    def __init__(self, sections, values, palette, defaults=None):
        super().__init__()
        self.fields, self.scales, self.value_labels, self.units = {}, {}, {}, {}
        self.section_keys = []; self.defaults = dict(defaults or values)
        self.baseline = dict(values); self.values = dict(values); self.dirty = set(); self.conflicts = set()
        self.ratios = {}
        self.writing = False; self.applying = False; self.areas = []
        layout = QVBoxLayout(self); layout.setContentsMargins(9, 9, 9, 9); layout.setSpacing(6)
        self.tabs = QTabWidget(); self.stack = self.tabs; self.switch = TabSwitch(self.tabs)
        for tab_title, rows in sections:
            page = QWidget(); page.setObjectName('settings_category')
            page.setStyleSheet(f'QWidget#settings_category{{background:{palette.tile};}}')
            form = QFormLayout(page); form.setContentsMargins(10, 10, 10, 10)
            form.setVerticalSpacing(9); form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            heading = QLabel({'常规':'桌面与显示', '动作':'人物行为'}.get(tab_title, tab_title))
            heading.setStyleSheet(f'font-size:13px;font-weight:600;margin-top:3px;color:{palette.accent};'); form.addRow(heading)
            keys = []
            for row in rows:
                kind = row[0]
                if kind == 'advanced':
                    self.advanced_button = QPushButton('展开高级参数'); self.advanced_button.setCheckable(True)
                    form.addRow(self.advanced_button)
                    self.advanced_card = QWidget(); advanced_form = QFormLayout(self.advanced_card)
                    advanced_form.setContentsMargins(0,0,0,0); advanced_form.setVerticalSpacing(9)
                    self.behavior_form = form; form.addRow(self.advanced_card)
                    self.advanced_button.toggled.connect(self.set_advanced)
                    form = advanced_form
                    continue
                if kind == 'note':
                    text = QLabel(row[1]); text.setWordWrap(True); form.addRow(text); continue
                if kind == 'link':
                    item = QPushButton(row[1]); item.clicked.connect(row[2]); form.addRow(item); continue
                key, text = row[1:3]; keys.append(key)
                if kind == 'check':
                    item = EditorCheckBox(text,palette); item.setChecked(bool(values.get(key)))
                    item.toggled.connect(lambda value, k=key: self.edit(k, value)); form.addRow(item)
                elif kind == 'ratio':
                    base = row[5]; self.ratios[key] = base
                    item = QDoubleSpinBox(); item.setRange(row[3]/base,row[4]/base)
                    item.setSingleStep(.1); item.setDecimals(2); item.setValue(values.get(key,base)/base)
                    item.valueChanged.connect(lambda value,k=key,b=base:self.edit(k,round(value*b)))
                    form.addRow(text,item)
                elif kind == 'slider':
                    item = QDoubleSpinBox(); item.setRange(row[3], row[4]); scale = row[5] if len(row)>5 else 1
                    item.setSingleStep(1/scale); item.setDecimals(2 if scale != 1 else 0)
                    item.setSuffix(row[6] if len(row)>6 else ''); item.setValue(values.get(key, row[3]))
                    self.scales[key] = scale
                    item.valueChanged.connect(lambda value, k=key, s=scale: self.edit(k, value if s != 1 else int(value)))
                    form.addRow(text, item)
                elif kind == 'choice':
                    item = QComboBox()
                    for data, caption in row[3]: item.addItem(caption, data)
                    item.setCurrentIndex(max(0, item.findData(values.get(key))))
                    item.currentIndexChanged.connect(lambda index, k=key, w=item: self.edit(k, w.itemData(index)))
                    form.addRow(text, item)
                elif kind == 'text':
                    item = QLineEdit(values.get(key) or ''); item.setPlaceholderText(row[3]); item.setMaxLength(row[4])
                    item.setClearButtonEnabled(True); item.textChanged.connect(lambda value, k=key: self.edit(k, value))
                    form.addRow(text, item)
                self.fields[key] = item
            self.section_keys.append(keys)
            area = QScrollArea(); area.setWidgetResizable(True); area.setWidget(page)
            area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
            self.areas.append(area); self.tabs.addTab(area, tab_title)
        layout.addWidget(self.tabs, 1)
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        row = QHBoxLayout()
        self.defaults_button = QPushButton('本页恢复默认'); self.defaults_button.clicked.connect(self.restore_defaults)
        self.discard_button = QPushButton('放弃修改'); self.discard_button.clicked.connect(self.discard)
        self.apply_button = QPushButton('应用'); self.apply_button.setProperty('role', 'primary'); self.apply_button.clicked.connect(self.apply)
        self.return_button = QPushButton('返回'); self.return_button.clicked.connect(self.returnRequested)
        for item in (self.defaults_button, self.discard_button, self.apply_button, self.return_button):
            item.setAutoDefault(False);item.setMinimumHeight(32); row.addWidget(item)
        layout.addLayout(row)
        self.shortcut = QShortcut(QKeySequence('Ctrl+S'), self)
        self.shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut); self.shortcut.activated.connect(self.apply)
        if hasattr(self,'advanced_card'):self.behavior_form.setRowVisible(self.advanced_card,False)
        self.update_status()

    def set_advanced(self,checked):
        window=self.window();enabled=window.updatesEnabled();window.setUpdatesEnabled(False)
        try:
            self.advanced_button.setText('收起高级参数' if checked else '展开高级参数')
            self.behavior_form.setRowVisible(self.advanced_card,checked)
            if self.layout():self.layout().activate()
        finally:window.setUpdatesEnabled(enabled)

    def edit(self, key, value):
        if self.writing: return
        self.values[key] = value
        if value == self.baseline.get(key): self.dirty.discard(key); self.conflicts.discard(key)
        else: self.dirty.add(key)
        self.status.clear(); self.update_status()

    def fill(self, key, value):
        item = self.fields.get(key)
        if item is None: return
        self.writing = True; item.blockSignals(True)
        try:
            if isinstance(item, QCheckBox): item.setChecked(bool(value))
            elif isinstance(item, QComboBox): item.setCurrentIndex(max(0, item.findData(value)))
            elif isinstance(item, QLineEdit): item.setText(value or '')
            else: item.setValue(value/self.ratios[key] if key in self.ratios else value)
        finally: item.blockSignals(False); self.writing = False

    def sync(self, key, value):
        old = self.baseline.get(key); self.baseline[key] = value
        if self.applying or key not in self.dirty or self.values.get(key) == value:
            self.values[key] = value; self.dirty.discard(key); self.conflicts.discard(key); self.fill(key, value)
        elif old != value:
            self.conflicts.add(key)
        self.update_status()

    def update_status(self):
        count = len(self.dirty)
        text='外部设置也有变化；应用采用这里的草稿，放弃修改采用当前值。' if self.conflicts else ''
        self.apply_button.setToolTip(text); self.apply_button.setEnabled(bool(count)); self.discard_button.setEnabled(bool(count))

    def restore_defaults(self):
        for key in self.section_keys[self.tabs.currentIndex()]:
            if key == 'autostart' or key not in self.defaults: continue
            self.fill(key, self.defaults[key]); self.edit(key, self.defaults[key])
        self.status.setText('已载入本页默认值，应用后生效。')

    def discard(self):
        self.values = dict(self.baseline); self.dirty.clear(); self.conflicts.clear()
        for key, value in self.values.items(): self.fill(key, value)
        self.status.clear(); self.update_status()

    def apply(self):
        self.applying = True
        try:
            for key in tuple(sorted(self.dirty)):
                value = self.values[key]; self.optionChanged.emit(key, value)
        finally: self.applying = False
        self.update_status()
        self.status.setText('桌宠设置已保存。' if not self.dirty else '部分修改尚未保存，请检查后重试。')


def companion_sections(role, actions):
    choices=[(key,item['name']) for key,item in actions.items() if key!='idle']
    general=(
        ('check','autostart','登录 Windows 时启动'),
        ('ratio','size','角色大小（倍）',180,460,300),
        ('check','character_visible','显示人物（关闭后仅保留独立卡片）'),
        ('check','fullscreen_yield','视频全屏时自动让位'),
        ('check','bubble','显示状态卡片'),
        ('check','quota_link','读取本机额度'),
        ('slider','card_hide_delay','点击人物后卡片保留（秒）',3,120),
        ('text','web_url','自定义网页地址','https://claude.ai/（默认）' if role=='claude' else 'https://gemini.google.com/（默认）',2048),
    )
    behavior=[
        ('check','random_actions','自动随机动作'),
        ('check','instant_switch','点选动作时立即切换（柔和过渡）'),
        ('advanced',),
        ('slider','random_interval','自主动作间隔（秒）',30,300),
        ('slider','playback_speed','播放速度（倍）',.5,2,4),
        ('choice','poke_action','单击人物',choices),
        ('choice','double_action','双击人物',choices),
    ]
    if role=='gemini':
        behavior.extend((('check','ear_meow','点击状态点时喵一声'),
                         ('check','hop_after_drag','放下后轻轻跳一下'),
                         ('check','sparkles','显示星光效果')))
    return (('常规',general),('动作',tuple(behavior)))
