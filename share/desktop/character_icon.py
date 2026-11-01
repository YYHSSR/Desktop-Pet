"""Small, transparent character portraits made from the current idle image."""
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QBitmap, QIcon, QImageReader, QPixmap, QRegion


def character_icon(path):
    reader = QImageReader(str(path))
    image = reader.read()
    if image.isNull():
        raise ValueError(f'Cannot read character icon: {path}')
    bounds = QRegion(QBitmap.fromImage(image.createAlphaMask())).boundingRect()
    if bounds.isEmpty():
        bounds = image.rect()
    # Use the upper part of the character so the face stays readable at 16px.
    side = min(bounds.width(), round(bounds.height() * .62))
    portrait = image.copy(QRect(bounds.center().x() - side // 2, bounds.top(), side, side))
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(portrait.scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)))
    return icon
