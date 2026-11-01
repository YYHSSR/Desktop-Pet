"""Expanded quota and Token details."""
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QWidget,QLabel,QVBoxLayout,QHBoxLayout,QTabWidget,QScrollArea,QFrame
from compact_bubble import font,FONT_CSS
from reset_watch import account_reset_text
from ring_widgets import draw_metric_icon
from quota_summary_data import quota_items,today_tokens


class MetricIcon(QWidget):
    def __init__(self,kind,parent=None):
        super().__init__(parent);self.kind=kind;self.setFixedSize(24,24)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#e9e0f1'));p.drawEllipse(QRectF(1,1,22,22))
        draw_metric_icon(p,QPointF(12,12),self.kind,14)


class DetailCard(QWidget):
    def __init__(self,title,warning=False,parent=None):
        super().__init__(parent);self.warning=warning
        self.body=QVBoxLayout(self);self.body.setContentsMargins(10,9,10,10);self.body.setSpacing(6)
        label=self.text(title,size=12,strong=True)
        label.setObjectName('detail_section_title')
    def text(self,text,size=12,strong=False,muted=False,warning=False):
        if muted and not warning:size=min(size,10)
        label=QLabel(str(text));label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True)
        color='#915e74' if warning else '#706879' if muted else '#393343'
        label.setStyleSheet(FONT_CSS+f'font-size:{size}px;font-weight:{600 if strong else 500};color:{color};background:transparent;')
        self.body.addWidget(label);return label
    def add_metric(self,name,value,icon):
        row=QHBoxLayout();row.setSpacing(7);row.addWidget(MetricIcon(icon))
        title=QLabel(name);title.setStyleSheet(FONT_CSS+'font-size:12px;color:#706879;');row.addWidget(title,1)
        number=QLabel(value);number.setStyleSheet(FONT_CSS+'font-size:20px;color:#514360;');row.addWidget(number)
        self.body.addLayout(row)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor('#fbf4f7' if self.warning else '#f5f1f7'))
        p.setPen(QPen(QColor('#e9dce5' if self.warning else '#e9e0f0'),1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),9,9)


class DetailsTabs(QTabWidget):
    def __init__(self,bubble,parent=None):
        super().__init__(parent);self.setObjectName('detail_tabs');self.setFixedHeight(244)
        self.setFont(font(12,True));self.areas={};self.keys=['quota','tokens']
        self.setStyleSheet('QTabWidget::pane{border:1px solid #e7deed;border-radius:10px;background:#fcfafc;top:-1px;}'
            'QTabBar::tab{'+FONT_CSS+'font-size:12px;color:#706879;background:transparent;border:0;padding:7px 15px;margin-bottom:3px;}'
            'QTabBar::tab:selected{color:#514360;background:#eae2f2;border-radius:7px;}'
            'QTabBar::tab:hover{background:#f2edf6;border-radius:7px;}'
            'QScrollArea{border:0;background:transparent;}QScrollBar:vertical{background:transparent;width:8px;margin:2px 0;}'
            'QScrollBar::handle:vertical{background:#cfc0de;border-radius:4px;min-height:24px;}'
            'QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}'
            'QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}')
        quota=self.page('quota','额度');tokens=self.page('tokens','Token')
        card=self.card(quota,'账户额度')
        if not bubble.windows:card.text('账户额度尚未提供，空轨道不代表 0%。',muted=True)
        for item in quota_items(bubble.windows):
            card.add_metric(item['name']+'剩余',item['display'],'bolt' if item['name']=='5小时' else 'calendar')
            card.text(item['reset_text']+' · '+account_reset_text(item['reset_at'])+'（北京时间）',size=11,muted=True)
        card.text(bubble.quota_caption,size=11,warning=any(s in bubble.quota_caption for s in ('上次','不可用','待刷新')),muted=True)
        card=self.card(tokens,'本机 Token 用量')
        snapshot=bubble.token_snapshot
        if not snapshot:card.text('Token 用量正在统计中…',muted=True)
        elif snapshot.get('unavailable'):card.text('Token 用量统计暂不可用，请点击顶部刷新重试。',warning=True)
        else:
            card.add_metric(snapshot.get('month','')+' 累计',f"{snapshot.get('total',0):,}",'tokens')
            card.text(today_tokens(snapshot)['description'],size=11,muted=True)
            if snapshot.get('partial'):card.text('部分日志暂不可读，当前用量统计可能不完整。',size=11,warning=True)
        for layout in (quota,tokens):layout.addStretch()
        self.setCurrentIndex(self.keys.index(bubble.detail_tab) if bubble.detail_tab in self.keys else 0)
        self.currentChanged.connect(lambda i:setattr(bubble,'detail_tab',self.keys[i]))
    def page(self,key,title):
        area=QScrollArea();area.setObjectName('detail_'+key);area.setWidgetResizable(True);area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content=QWidget();content.setStyleSheet('background:transparent;');layout=QVBoxLayout(content)
        layout.setContentsMargins(7,8,7,8);layout.setSpacing(8);area.setWidget(content)
        self.areas[key]=area;self.addTab(area,title);return layout
    def card(self,layout,title,warning=False):
        card=DetailCard(title,warning);layout.addWidget(card);return card
    def restore_scroll(self,positions):
        for key,area in self.areas.items():area.verticalScrollBar().setValue(positions.get(key,0))
