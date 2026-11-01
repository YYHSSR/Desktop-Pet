"""Non-modal general and behavior settings with explicit drafts."""
import copy
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,QWidget,
    QCheckBox,QDoubleSpinBox,QPushButton,QComboBox,QLabel,QScrollArea,QLineEdit)
from desktop_core import DEFAULTS
from desktop_services import autostart_enabled,set_autostart
from settings_draft import SettingsDraft
from ui_theme import MUTED,PRIMARY


class SettingsDialog(QDialog):
    def __init__(self,pet,embedded=False):
        super().__init__(pet,Qt.WindowType.Widget if embedded else Qt.WindowType.Dialog);self.pet=pet;self.embedded=embedded;self.fields={}
        self.field_tabs={};self.field_titles={};self.factors={};self._writing_widgets=True;self.draft=None
        if embedded:self.setWindowFlags(Qt.WindowType.Widget)
        self.setWindowTitle('ChatGpt · 设置');self.resize(590,680)
        outer=QVBoxLayout(self);self.tabs=QTabWidget();outer.addWidget(self.tabs,1)
        appearance=self.tab('常规与外观')
        self.section(appearance,'桌面与显示')
        self.startup=QCheckBox('登录 Windows 时启动');appearance.addRow(self.startup)
        self.field_tabs['startup']=self.tabs.count()-1;self.field_titles['startup']='开机启动'
        self.startup.toggled.connect(lambda:self.edited('startup'))
        self.codex_startup=QCheckBox('打开 Codex 时自动启动桌宠');appearance.addRow(self.codex_startup)
        self.field_tabs['codex_startup']=0;self.field_titles['codex_startup']='随 Codex 启动'
        self.codex_startup.toggled.connect(lambda:self.edited('codex_startup'))
        self.number(appearance,'scale','角色大小（倍）',.4,2.5,.1)
        for key,title in [('character_visible','显示人物（关闭后仅保留独立卡片）'),('video_fullscreen_yield','视频全屏时临时取消置顶'),('bubble','显示状态卡片'),('quota_visible','显示额度和重置时间'),('commentary','展示 Codex 回复摘要')]:
            self.check(appearance,key,title)
        self.number(appearance,'card_hide_delay','点击人物后卡片保留（秒）',3,120,1)
        from quick_actions import WEB_TARGETS
        self.web_target=QComboBox()
        for key,title in WEB_TARGETS:self.web_target.addItem(title,key)
        appearance.addRow('卡片浏览器按钮',self.web_target);self.fields['web_button']=self.web_target;self.field_tabs['web_button']=0;self.field_titles['web_button']='卡片浏览器按钮'
        self.web_target.currentIndexChanged.connect(lambda:self.edited('web_button'))
        self.website=QLineEdit();self.website.setPlaceholderText('https://…');self.website.setAccessibleName('自定义网页地址');self.website.setMaxLength(2048)
        appearance.addRow('自定义网页地址',self.website);self.fields['web_url']=self.website;self.field_tabs['web_url']=0;self.field_titles['web_url']='自定义网页地址'
        self.website.textChanged.connect(lambda:self.edited('web_url'))
        behavior=self.tab('动作与陪伴')
        self.section(behavior,'人物行为')
        self.check(behavior,'random_actions','自动随机动作')
        self.check(behavior,'status_actions','根据 Codex 当前状态播放动作（播完后再切换）')
        self.check(behavior,'sound','主动点击人物或手动动作时播放音效')
        self.advanced_button=QPushButton('展开高级参数');self.advanced_button.setCheckable(True);behavior.addRow(self.advanced_button)
        advanced=QWidget();advanced_form=QFormLayout(advanced);advanced_form.setContentsMargins(0,0,0,0)
        self.number(advanced_form,'status_action_interval','单次状态动作重复间隔（秒）',8,120,1)
        self.check(advanced_form,'drag_physics','拖拽松手后启用惯性与反弹')
        for key,title,lo,hi,step in [('playback_speed','播放速度（倍）',.25,3,.25),('action_gap','动作结束后等待（秒）',0,60,1),('random_interval','自主动作间隔（秒）',3,600,1),('move_speed','自主走动速度（像素/秒）',10,300,5)]:self.number(advanced_form,key,title,lo,hi,step)
        self.number(advanced_form,'move_range','自主活动范围',.1,1,.1,factor=100,suffix='% 屏幕')
        self.advanced_card=advanced;self.behavior_form=behavior;behavior.addRow(advanced);behavior.setRowVisible(advanced,False)
        self.advanced_button.toggled.connect(self.set_advanced)
        self.status=QLabel();self.status.setWordWrap(True);outer.addWidget(self.status)
        row=QHBoxLayout()
        self.defaults_button=QPushButton('本页恢复默认');self.defaults_button.clicked.connect(self.defaults);row.addWidget(self.defaults_button)
        self.discard_button=QPushButton('放弃修改');self.discard_button.clicked.connect(self.reload);row.addWidget(self.discard_button)
        self.apply_button=QPushButton('应用');self.apply_button.clicked.connect(self.apply);row.addWidget(self.apply_button)
        button=QPushButton('返回' if embedded else '关闭');button.clicked.connect(self.dismiss);row.addWidget(button)
        for control in self.findChildren(QPushButton):control.setAutoDefault(False)
        self.apply_button.setProperty('role','primary');self.apply_button.setAutoDefault(True);self.apply_button.setDefault(True)
        self.save_shortcut=QShortcut(QKeySequence('Ctrl+S'),self);self.save_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);self.save_shortcut.activated.connect(self.apply)
        self.tabs.tabBar().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        outer.addLayout(row);self.tabs.currentChanged.connect(self.update_draft_state);self.reload()
        if hasattr(pet,'settingsChanged'):pet.settingsChanged.connect(self.sync_from_pet)
    def section(self,form,title):
        name=QLabel(title);name.setStyleSheet(f'font-size:13px;font-weight:600;color:{PRIMARY};margin-top:3px;');form.addRow(name)
    def set_advanced(self,checked):
        # One relayout and one repaint; animating the row resized the whole
        # translucent card every frame and dragged the scroll position along.
        window=self.window();enabled=window.updatesEnabled();window.setUpdatesEnabled(False)
        try:
            self.advanced_button.setText('收起高级参数' if checked else '展开高级参数')
            self.behavior_form.setRowVisible(self.advanced_card,checked)
            page=self.advanced_card.parentWidget()
            if page.layout():page.layout().activate()
        finally:window.setUpdatesEnabled(enabled)
    def tab(self,title):
        widget=QWidget();form=QFormLayout(widget)
        if self.embedded:
            widget.setObjectName('settings_category');widget.setStyleSheet('QWidget#settings_category{background:#f5f2f7;}')
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            area=QScrollArea();area.setWidgetResizable(True)
            # Reserve the gutter so opening a disclosure cannot rewrap its body.
            area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn);area.setWidget(widget)
            index=self.tabs.addTab(area,{'常规与外观':'常规','动作与陪伴':'动作','角色与动作':'角色'}.get(title,title))
            self.tabs.setTabToolTip(index,title)
        else:self.tabs.addTab(widget,title)
        return form
    def dismiss(self):
        if self.embedded:self.pet.bubble.return_to_status()
        else:self.hide()
    def keyPressEvent(self,event):
        if self.embedded and event.key()==Qt.Key.Key_Escape:self.dismiss();event.accept();return
        super().keyPressEvent(event)
    def check(self,form,key,title):
        widget=QCheckBox(title);self.fields[key]=widget;form.addRow(widget);self.field_tabs[key]=self.tabs.count()-1;self.field_titles[key]=title
        widget.toggled.connect(lambda:self.edited(key))
    def number(self,form,key,title,lo,hi,step,factor=1,suffix=''):
        widget=QDoubleSpinBox();widget.setRange(lo*factor,hi*factor);widget.setSingleStep(step*factor);widget.setDecimals(0 if step*factor>=1 else 2);widget.setSuffix(suffix)
        self.fields[key]=widget;self.factors[key]=factor;self.field_tabs[key]=self.tabs.count()-1;self.field_titles[key]=title;form.addRow(title,widget)
        widget.valueChanged.connect(lambda:self.edited(key))
    def fill(self,settings):
        self._writing_widgets=True
        for key,widget in self.fields.items():
            if isinstance(widget,QCheckBox):widget.setChecked(settings.get(key,DEFAULTS[key]))
            elif isinstance(widget,QComboBox):widget.setCurrentIndex(widget.findData(settings.get(key,DEFAULTS[key])))
            elif isinstance(widget,QLineEdit):widget.setText(settings.get(key,DEFAULTS[key]))
            else:widget.setValue(settings.get(key,DEFAULTS[key])*self.factors.get(key,1))
        self.startup.setChecked(bool(settings.get('startup',False)));self.codex_startup.setChecked(bool(settings.get('codex_startup',False)));self._writing_widgets=False
    def values_from_pet(self,read_startup=False):
        values={key:copy.deepcopy(self.pet.settings.get(key,DEFAULTS[key])) for key in self.fields}
        if read_startup:
            from codex_startup import enabled
            try:values['startup']=autostart_enabled();values['codex_startup']=enabled()
            except OSError:self.status.setText('开机启动状态读取失败；其他设置仍可修改。')
        return values
    def reload(self):
        self.status.clear();values=self.values_from_pet(read_startup=True);values.setdefault('startup',False)
        self.draft=SettingsDraft(values);self.fill(self.draft.values);self.update_draft_state()
    def sync_from_pet(self,changes=None,read_startup=False):
        if self.draft is None:return
        self.draft.rebase(self.values_from_pet(read_startup));self.fill(self.draft.values);self.update_draft_state()
    def edited(self,key):
        if self._writing_widgets or self.draft is None:return
        if key=='startup':value=self.startup.isChecked()
        elif key=='codex_startup':value=self.codex_startup.isChecked()
        else:
            widget=self.fields[key];value=widget.isChecked() if isinstance(widget,QCheckBox) else widget.currentData() if isinstance(widget,QComboBox) else widget.text() if isinstance(widget,QLineEdit) else widget.value()/self.factors.get(key,1)
        self.draft.set(key,value);self.status.clear();self.update_draft_state()
    def update_draft_state(self,*args):
        if self.draft is None:return
        self.website.setEnabled(self.web_target.currentData()=='website')
        count=len(self.draft.dirty);self.apply_button.setEnabled(bool(count));self.discard_button.setEnabled(bool(count))
        text=''
        if self.draft.conflicts:
            names='、'.join(self.field_titles[k] for k in sorted(self.draft.conflicts))
            text='外部也修改了：'+names+'。应用将采用此处草稿；放弃修改将采用当前值。'
        self.apply_button.setToolTip(text)
        self.defaults_button.setEnabled(any(tab==self.tabs.currentIndex() and key in DEFAULTS for key,tab in self.field_tabs.items()))
        locked=self.pet.settings['no_move']
        for key in ('drag_physics','move_speed','move_range'):self.fields[key].setEnabled(not locked)
        self.fields['status_action_interval'].setEnabled(self.fields['status_actions'].isChecked())
    def defaults(self):
        for key,tab in self.field_tabs.items():
            if tab==self.tabs.currentIndex() and key in DEFAULTS:self.draft.set(key,DEFAULTS[key])
        self.fill(self.draft.values);self.update_draft_state();self.status.setText('已载入本页默认值，应用后生效；不影响开机启动。')
    def apply(self):
        values=self.draft.changes();startup=values.pop('startup',None);codex_startup=values.pop('codex_startup',None);messages=[]
        if values:
            try:
                self.pet.apply_settings(values)
                for key in values:
                    self.draft.values[key]=copy.deepcopy(self.pet.settings[key]);self.draft.baseline[key]=copy.deepcopy(self.pet.settings[key]);self.draft.conflicts.discard(key)
                messages.append('桌宠设置已保存。')
            except (OSError,ValueError) as error:messages.append('桌宠设置保存失败：'+str(error))
        if startup is not None:
            try:set_autostart(startup);self.draft.rebase({'startup':startup});messages.append('开机启动已保存。')
            except OSError as error:messages.append('开机启动保存失败：'+str(error)+'；可单独重试。')
        if codex_startup is not None:
            from codex_startup import configure
            try:configure(codex_startup);self.draft.rebase({'codex_startup':codex_startup});messages.append('Codex 启动联动已保存。')
            except OSError as error:messages.append('Codex 启动联动保存失败：'+str(error)+'；可单独重试。')
        self.fill(self.draft.values);self.update_draft_state();self.status.setText('\n'.join(messages))
    def closeEvent(self,event):self.hide();event.ignore()
