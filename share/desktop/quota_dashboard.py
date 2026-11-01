"""Compact quota-first dashboards; model families never invent missing windows."""
import re
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QProgressBar
from .card_kit import CurrentPageStack, button, label
from .quota import reset_text, reset_tooltip


def window_key(name):
    return 'week' if re.search(r'周|weekly|week|7\s*d',name,re.I) else '5h'


def quota_groups(snapshot, role):
    keys = [('Gemini','5h'),('Gemini','week'),('Other Model','5h'),('Other Model','week')] if role == 'gemini' else [('', '5h'),('', 'week')]
    buckets = {key: [] for key in keys}
    for meter in snapshot.meters if snapshot else ():
        family = ('Gemini' if re.search(r'gemini',meter.label,re.I) else 'Other Model') if role == 'gemini' else ''
        buckets[(family,window_key(meter.label))].append(meter)
    rows = []
    for key in keys:
        members = buckets[key]
        # Distinct models need not share a pool: show the least remaining,
        # never average independent model limits into an invented allowance.
        chosen = max(members,key=lambda m:m.used) if members else None
        rows.append(dict(family=key[0],window=key[1],meter=chosen,members=members))
    return rows


class QuotaDashboard(QWidget):
    def __init__(self, owner, quick=()):
        super().__init__()
        self.owner = owner
        self.snapshot = None
        self.panel_height = 186 if owner.ROLE == 'gemini' else 102
        self.setFixedHeight(self.panel_height)
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        self.deck = CurrentPageStack(); root.addWidget(self.deck)
        quotas = QWidget(); grid = QGridLayout(quotas); grid.setContentsMargins(0,0,0,0); grid.setSpacing(6)
        grid.setColumnStretch(0,1); grid.setColumnStretch(1,1)
        self.rows = []
        for index,row in enumerate(quota_groups(None,owner.ROLE)):
            tile = QFrame(); tile.setObjectName('tile'); tile.setCursor(Qt.CursorShape.PointingHandCursor)
            tile.mouseReleaseEvent = lambda event: owner.show_status(True) if event.button()==Qt.MouseButton.LeftButton else None
            box = QVBoxLayout(tile); box.setContentsMargins(9,5,9,5); box.setSpacing(2)
            title = (row['family']+' · ' if row['family'] else '')+('5h 剩余' if row['window']=='5h' else '周剩余')
            name = label(title,'section'); value = label('—','stat'); value.setStyleSheet(owner.THEME.display+'font-size:24px;')
            bar = QProgressBar(); bar.setRange(0,1000); bar.setTextVisible(False); bar.setFixedHeight(4); bar.setValue(0)
            note = label('等待本机同步','muted',True)
            for widget in (name,value,bar,note): box.addWidget(widget)
            grid.addWidget(tile,index//2,index%2)
            self.rows.append((name,value,bar,note))
        self.deck.addWidget(quotas)
        tokens = QWidget(); box=QVBoxLayout(tokens); box.setContentsMargins(3,0,3,0); box.setSpacing(2)
        header=QHBoxLayout(); self.token_caption=label('今日 · —','muted'); header.addWidget(self.token_caption,1)
        self.quota_return=button('返回额度',lambda:self.select(0),'link'); header.addWidget(self.quota_return);box.addLayout(header)
        from .token_report import HourChart
        self.token_chart=HourChart(owner.PALETTE); self.token_chart.setFixedHeight(self.panel_height-23)
        self.token_chart.hovered.connect(lambda text:self.token_chart.setToolTip(text));box.addWidget(self.token_chart)
        self.deck.addWidget(tokens)
        # Controller-owned action state remains available on the full action page.
        self.current=label('待机'); self.current.setParent(self); self.current.hide()
        self.hint=label(''); self.hint.setParent(self); self.hint.hide()
        self.select(0)

    def select(self,index):
        self.deck.setCurrentIndex(index)

    def toggle_tokens(self):
        self.select(1 if self.deck.currentIndex()==0 else 0)

    def minimumSizeHint(self): return QSize(226,self.panel_height)
    def sizeHint(self): return QSize(248,self.panel_height)

    def update_tokens(self,report,today=None):
        from .token_widgets import today_usage
        from .token_report import compact_tokens
        record=today_usage(report,today)
        total=compact_tokens(record.get('total',0)) if report is not None else '—'
        self.token_caption.setText('今日 · '+total); self.token_chart.set_values(record.get('hours',[0]*24))

    def update_quota(self,snapshot):
        self.snapshot=snapshot
        for widgets, row in zip(self.rows,quota_groups(snapshot,self.owner.ROLE)):
            name,value,bar,note=widgets; meter=row['meter']
            if meter is None:
                value.setText('—');bar.setValue(0)
                name.setToolTip('')
                note.setText('来源未提供周额度' if row['window']=='week' and snapshot and snapshot.connected else '等待本机同步')
                note.setToolTip('没有对应窗口数据，空值不代表 0% 或 100%。')
                continue
            value.setText(f'{round(meter.remaining*100)}%');bar.setValue(round(meter.remaining*1000))
            note.setText(reset_text(meter.resets_at,approx=meter.estimated) or ('额度满格' if meter.used<=0 else '重置时间未提供'))
            details='\n'.join(f'{m.label}：剩余 {round(m.remaining*100)}%' for m in row['members'])
            if self.owner.ROLE=='gemini' and row['window']=='5h' and any(not re.search(r'5\s*h|5\s*小时',m.label,re.I) for m in row['members']):
                details+='\n来源只提供当前模型额度，未标注独立周期；此处放在当前额度栏，周额度另行留空。'
            name.setToolTip(details+('\n本组显示最低剩余比例。' if len(row['members'])>1 else ''))
            note.setToolTip(reset_tooltip(meter.resets_at,meter.estimated))
        self.setToolTip(snapshot.message if snapshot else '尚未连接本机额度来源')
