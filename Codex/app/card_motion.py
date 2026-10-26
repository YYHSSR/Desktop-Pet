"""Shared card shape for report motion."""
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPainter,QPainterPath,QColor,QPen
from spring_motion import stage
from surface_morph import PANEL_RADIUS
from ui_theme import SURFACE,BORDER


def paint_card(p,rect,frame,progress,background=SURFACE,inset=0.,content_progress=None):
    if progress<=0. or rect.height()<=0:return
    radius=min(rect.width()/2,rect.height()/2,20.+(PANEL_RADIUS-20.)*min(1.,progress))
    path=QPainterPath();path.addRoundedRect(rect,radius,radius)
    p.save();p.setOpacity(stage(progress,0.,.09));p.fillPath(path,QColor(background));p.setClipPath(path)
    if frame is not None and not frame.isNull():
        entry=stage(progress,.7,1.) if content_progress is None else content_progress
        size=frame.deviceIndependentSize();scale=.975+.025*entry
        w=min(size.width(),rect.width()-2*inset)*scale;h=size.height()*scale
        target=QRectF(rect.center().x()-w/2,rect.center().y()-h/2,max(0.,w),h)
        p.setOpacity(stage(progress,0.,.09)*entry);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(target,frame,QRectF(frame.rect()))
    p.setClipping(False);p.setOpacity(stage(progress,0.,.09));p.setPen(QPen(QColor(BORDER),1));p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(rect.adjusted(.5,.5,-.5,-.5),radius,radius);p.restore()
