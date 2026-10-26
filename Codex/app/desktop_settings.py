"""Non-modal settings, live controls and character diagnostics."""
import copy
import threading
from PySide6.QtCore import Qt,QThread,Signal
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,QWidget,
    QCheckBox,QDoubleSpinBox,QPushButton,QComboBox,QLabel,QFileDialog,QScrollArea,QLineEdit)
from desktop_core import DEFAULTS
from desktop_services import autostart_enabled,set_autostart,import_character,validate_character,all_items
from settings_draft import SettingsDraft
from connection_widgets import CapabilityPanel
from ui_theme import MUTED,PRIMARY

class ConnectionJob(QThread):
    report=Signal(object)
    def __init__(self,parent=None):super().__init__(parent);self.cancel=threading.Event()
    def run(self):
        from codex_connection import check_connection
        try:self.report.emit(check_connection(cancel=self.cancel))
        except Exception:self.report.emit(dict(summary='连接检查暂不可用，请稍后重试。'))

class LibraryJob(QThread):
    result=Signal(object);failed=Signal(str)
    def __init__(self,source,destination=None,parent=None):super().__init__(parent);self.source=source;self.destination=destination
    def run(self):
        try:
            if self.destination:self.result.emit(import_character(self.source,self.destination))
            else:self.result.emit(validate_character(self.source))
        except Exception as error:self.failed.emit(str(error)[:250])

class ConverterJob(LibraryJob):
    def run(self):
        from optional_tools import save_ffmpeg
        try:save_ffmpeg(self.source);self.result.emit(str(self.source))
        except (OSError,ValueError) as error:self.failed.emit(str(error))

class SettingsDialog(QDialog):
    def __init__(self,pet,embedded=False):
        super().__init__(pet,Qt.WindowType.Widget if embedded else Qt.WindowType.Dialog);self.pet=pet;self.embedded=embedded;self.fields={};self.job=None;self.connection_job=None
        self.field_tabs={};self.field_titles={};self.factors={};self._writing_widgets=True;self.draft=None
        if embedded:self.setWindowFlags(Qt.WindowType.Widget)
        self.setWindowTitle('白龙桌宠 · 设置');self.resize(590,680)
        outer=QVBoxLayout(self);self.tabs=QTabWidget();outer.addWidget(self.tabs,1)
        appearance=self.tab('常规与外观')
        self.section(appearance,'桌面与显示','这里的偏好点击“应用”后生效；切页会保留草稿。')
        self.startup=QCheckBox('登录 Windows 时启动');appearance.addRow(self.startup)
        self.field_tabs['startup']=self.tabs.count()-1;self.field_titles['startup']='开机启动'
        self.startup.toggled.connect(lambda:self.edited('startup'))
        self.codex_startup=QCheckBox('打开 Codex 时自动启动桌宠');appearance.addRow(self.codex_startup)
        self.field_tabs['codex_startup']=0;self.field_titles['codex_startup']='随 Codex 启动'
        self.codex_startup.toggled.connect(lambda:self.edited('codex_startup'))
        note=QLabel('登录时运行轻量监听；识别 Codex 桌面端，不依赖 Codex++。手动退出桌宠后，本次 Codex 使用期间不再拉起。关闭 Codex 不会强制退出桌宠。');note.setWordWrap(True);note.setStyleSheet(f'font-size:10px;color:{MUTED};');appearance.addRow(note)
        self.number(appearance,'scale','角色大小（倍）',.4,2.5,.1)
        for key,title in [('character_visible','显示人物（关闭后仅保留独立卡片）'),('on_top','始终置顶'),('video_fullscreen_yield','视频全屏时临时取消置顶（完成提醒优先）'),('bubble','显示状态卡片'),('quota_visible','显示额度和重置时间'),('commentary','展示 Codex 回复摘要')]:
            self.check(appearance,key,title)
            if key=='video_fullscreen_yield':
                note=QLabel('完成提醒确认后，视频仍全屏则继续让位；退出全屏恢复当前置顶设置。')
                note.setWordWrap(True);note.setStyleSheet(f'font-size:10px;color:{MUTED};');appearance.addRow(note)
        self.number(appearance,'card_hide_delay','点击人物后卡片保留（秒）',3,120,1)
        from quick_actions import WEB_TARGETS
        self.web_target=QComboBox()
        for key,title in WEB_TARGETS:self.web_target.addItem(title,key)
        appearance.addRow('卡片浏览器按钮',self.web_target);self.fields['web_button']=self.web_target;self.field_tabs['web_button']=0;self.field_titles['web_button']='卡片浏览器按钮'
        self.web_target.currentIndexChanged.connect(lambda:self.edited('web_button'))
        self.website=QLineEdit();self.website.setPlaceholderText('https://…');self.website.setAccessibleName('自定义网页地址');self.website.setMaxLength(2048)
        appearance.addRow('自定义网页地址',self.website);self.fields['web_url']=self.website;self.field_tabs['web_url']=0;self.field_titles['web_url']='自定义网页地址'
        self.website.textChanged.connect(lambda:self.edited('web_url'))
        note=QLabel('状态卡片平时隐藏，点击人物后显示，鼠标离开且无操作时按上方时间自动收起；完成提醒会自动弹出。仅卡片时可拖动卡片空白处。人物隐藏后暂停动画，Codex 联动继续。');note.setWordWrap(True);appearance.addRow(note)
        behavior=self.tab('动作与陪伴')
        self.section(behavior,'人物行为','先选择陪伴方式，再按需展开高级参数。')
        self.check(behavior,'no_move','锁定人物位置（禁止拖动和自主走动）')
        self.check(behavior,'wandering','允许自主走动（不影响手动拖动）')
        self.movement_note=QLabel();self.movement_note.setWordWrap(True);behavior.addRow(self.movement_note)
        self.check(behavior,'random_actions','自动随机动作')
        self.check(behavior,'status_actions','根据 Codex 当前状态播放动作（播完后再切换）')
        self.check(behavior,'sound','主动点击人物或手动动作时播放音效')
        self.advanced_button=QPushButton('展开高级参数');self.advanced_button.setCheckable(True);behavior.addRow(self.advanced_button)
        advanced=QWidget();advanced_form=QFormLayout(advanced);advanced_form.setContentsMargins(0,0,0,0)
        self.number(advanced_form,'status_action_interval','单次状态动作重复间隔（秒）',8,120,1)
        self.check(advanced_form,'drag_physics','拖拽松手后启用惯性与反弹')
        for key,title,lo,hi,step in [('playback_speed','播放速度（倍）',.25,3,.25),('action_gap','动作结束后等待（秒）',0,60,1),('random_interval','自主动作间隔（秒）',3,600,1),('move_speed','自主走动速度（像素/秒）',10,300,5)]:self.number(advanced_form,key,title,lo,hi,step)
        self.number(advanced_form,'move_range','自主活动范围',.1,1,.1,factor=100,suffix='% 屏幕')
        note=QLabel('思考/阅读和处理任务在状态稳定1.5秒后进入，保持中段循环，状态改变后自然收尾。其他动作完整播放并按间隔检查。完成消息立即提醒，庆祝等待安全边界。');note.setWordWrap(True);note.setStyleSheet('font-size:10px;color:#706879;');behavior.addRow(note)
        self.advanced_card=advanced;self.behavior_form=behavior;behavior.addRow(advanced);behavior.setRowVisible(advanced,False)
        self.advanced_button.toggled.connect(self.set_advanced)
        connection=self.tab('连接与数据')
        self.section(connection,'Codex 连接健康','各项独立检测；失败不会当作已读、零额度或零用量。')
        self.connection_button=QPushButton('检测连接与额度');self.connection_button.setProperty('role','primary');self.connection_button.clicked.connect(self.check_connection);connection.addRow(self.connection_button)
        self.health_panel=CapabilityPanel();self.health_panel.set_snapshot(pet.connection_health.snapshot());connection.addRow(self.health_panel)
        pet.connectionHealthChanged.connect(self.health_panel.set_snapshot)
        row=QWidget();buttons=QHBoxLayout(row);buttons.setContentsMargins(0,0,0,0);self.refresh_buttons={}
        for key,title,slot in [('quota','刷新额度',pet.refresh_quota),('reset','刷新重置消息',pet.refresh_reset_feed),('token','刷新 Token',pet.refresh_tokens)]:
            button=QPushButton(title);button.clicked.connect(slot);buttons.addWidget(button);self.refresh_buttons[key]=(button,title)
        connection.addRow(row)
        library=self.tab('角色与动作')
        if hasattr(pet,'materials'):
            self.section(library,'内置白龙画质','两种画质均已内置；切换立即执行，不属于设置草稿。')
            from material_controller import MaterialPanel
            self.material_panel=MaterialPanel(pet.materials);library.addRow(self.material_panel)
        self.section(library,'角色资源','切换、导入和预览立即执行；预览始终静音。')
        self.characters=QComboBox();library.addRow('当前角色',self.characters)
        button=QPushButton('切换到所选角色');button.clicked.connect(self.switch_character);library.addRow(button)
        button=QPushButton('导入角色文件夹（WebP / GIF / WebM）');button.clicked.connect(self.import_pack);library.addRow(button)
        tool=QPushButton('WebM 转换工具…');tool.clicked.connect(self.select_converter);library.addRow(tool)
        self.actions=QComboBox();library.addRow('动作分类与预览',self.actions)
        button=QPushButton('静音预览所选动作');button.clicked.connect(self.preview);library.addRow(button)
        button=QPushButton('检查所有素材');button.clicked.connect(self.validate);library.addRow(button)
        self.library_status=QLabel();self.library_status.setWordWrap(True);library.addRow(self.library_status)
        self.draft_status=QLabel();self.draft_status.setWordWrap(True);outer.addWidget(self.draft_status)
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
        pet.bubble.dataBusyChanged.connect(self.update_refresh_state)
        for key in self.refresh_buttons:self.update_refresh_state(key,getattr(pet.bubble,key+'_busy'))
    def section(self,form,title,note):
        name=QLabel(title);name.setStyleSheet(f'font-size:13px;font-weight:600;color:{PRIMARY};margin-top:3px;');form.addRow(name)
        label=QLabel(note);label.setWordWrap(True);label.setStyleSheet(f'font-size:10px;color:{MUTED};margin-bottom:3px;');form.addRow(label)
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
    def update_refresh_state(self,key,busy):
        button,title=self.refresh_buttons[key];button.setEnabled(not busy);button.setText('查询中…' if busy else title)
    def tab(self,title):
        widget=QWidget();form=QFormLayout(widget)
        if self.embedded:
            widget.setObjectName('settings_category');widget.setStyleSheet('QWidget#settings_category{background:#f5f2f7;}')
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            area=QScrollArea();area.setWidgetResizable(True)
            # Reserve the gutter so opening a disclosure cannot rewrap its body.
            area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn);area.setWidget(widget)
            index=self.tabs.addTab(area,{'常规与外观':'常规','动作与陪伴':'动作','角色与动作':'角色','连接与数据':'连接'}.get(title,title))
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
        self.draft=SettingsDraft(values);self.fill(self.draft.values);self.refresh_library();self.update_draft_state()
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
        text=f'有 {count} 项未保存修改 · Ctrl+S 应用 · 切页保留草稿' if count else '设置已保存 · Ctrl+S 应用修改'
        if self.draft.conflicts:
            names='、'.join(self.field_titles[k] for k in sorted(self.draft.conflicts))
            text+='\n外部也修改了：'+names+'。应用将采用此处草稿；放弃修改将采用当前值。'
        self.draft_status.setText(text)
        self.defaults_button.setEnabled(any(tab==self.tabs.currentIndex() and key in DEFAULTS for key,tab in self.field_tabs.items()))
        locked=self.fields['no_move'].isChecked()
        for key in ('wandering','drag_physics','move_speed','move_range'):self.fields[key].setEnabled(not locked)
        self.movement_note.setText('位置已锁定：禁止拖动和自主走动；下方移动偏好会保留，解除锁定后恢复。' if locked else '自主走动关闭时仍可手动拖动；工作动作优先于自动随机动作。')
        self.fields['status_action_interval'].setEnabled(self.fields['status_actions'].isChecked())
    def defaults(self):
        for key,tab in self.field_tabs.items():
            if tab==self.tabs.currentIndex() and key in DEFAULTS:self.draft.set(key,DEFAULTS[key])
        self.fill(self.draft.values);self.update_draft_state();self.status.setText('已载入本页默认值，应用后生效；不影响开机启动和角色。')
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
    def refresh_library(self):
        self.characters.clear()
        for key,name in self.pet.character_choices():self.characters.addItem(name,key)
        self.characters.setCurrentIndex(self.characters.findData(self.pet.settings.get('character','builtin')))
        self.actions.clear()
        for group,items in self.pet.action_groups().items():
            for item in items:self.actions.addItem(group+' / '+item.get('name',item['id']),item)
        self.library_status.setText(f'当前 {len(all_items(self.pet.manifest))} 段素材；缺省类别使用待机或现有动作回退。')
    def switch_character(self):
        try:self.pet.switch_character(self.characters.currentData());self.refresh_library()
        except (OSError,ValueError,KeyError) as error:self.library_status.setText('切换失败：'+str(error))
    def preview(self):
        item=self.actions.currentData()
        if item:self.pet.choose(item,interactive=False,manual=True)
    def select_converter(self):
        if self.job and self.job.isRunning():self.library_status.setText('正在检查或导入，请稍等…');return
        path,_=QFileDialog.getOpenFileName(self,'选择 FFmpeg 转换工具（仅导入 WebM 时使用）','','FFmpeg (ffmpeg*.exe);;所有文件 (*)')
        if not path:return
        self.library_status.setText('正在后台验证转换工具…')
        self.job=ConverterJob(path,None,self)
        self.job.result.connect(lambda _:self.library_status.setText('转换工具已验证，导入 WebM 时使用；日常动画播放不依赖它。'))
        self.job.failed.connect(self.library_status.setText);self.job.start()
    def import_pack(self):
        source=QFileDialog.getExistingDirectory(self,'选择包含素材清单或分类素材文件夹的角色包')
        if source:self.start_job(source,self.pet.character_dir)
    def validate(self):self.start_job(self.pet.asset_root)
    def start_job(self,source,destination=None):
        if self.job and self.job.isRunning():self.library_status.setText('正在检查或导入，请稍等…');return
        self.library_status.setText('后台检查 / 转换中，桌宠仍可操作…')
        self.job=LibraryJob(source,destination,self)
        self.job.result.connect(lambda value:self.job_done(value,destination));self.job.failed.connect(lambda error:self.library_status.setText('素材检查失败：'+error));self.job.start()
    def job_done(self,value,destination):
        self.refresh_library();self.library_status.setText('角色已导入，可在上方切换。' if destination else '所有素材已逐帧检查，可正常读取。')
    def check_connection(self):
        if self.connection_job and self.connection_job.isRunning():return
        self.connection_button.setEnabled(False);self.connection_button.setText('检测中…')
        self.connection_job=ConnectionJob(self);self.connection_job.report.connect(self.connection_done)
        self.connection_job.finished.connect(lambda:(self.connection_button.setEnabled(True),self.connection_button.setText('检测连接与额度')));self.connection_job.start()
    def connection_done(self,report):
        self.pet.update_connection_health(report.get('capabilities',{}))
        if 'capabilities' not in report:self.status.setText(report.get('summary','连接检查暂不可用，请稍后重试。'))
        else:self.status.setText('连接检测完成，结果已更新到上方各项状态。')
    def closeEvent(self,event):self.hide();event.ignore()
