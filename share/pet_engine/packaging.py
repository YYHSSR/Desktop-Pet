"""Common Conda native-library handling and Qt trimming for the Windows builds."""
import os
import shutil
import sys
from pathlib import Path


def native_build_environment(command):
    env = os.environ.copy()
    native = Path(sys.base_prefix)/'Library/bin'
    if native.is_dir():
        env['PATH'] = str(native)+os.pathsep+env.get('PATH', '')
        for name in ('ffi.dll', 'sqlite3.dll', 'liblzma.dll', 'LIBBZ2.dll', 'libexpat.dll', 'libmpdec-4.dll'):
            path = native/name
            if path.is_file():
                command.extend(['--add-binary', str(path)+';.'])
    return env


# Qt pieces the Claude and Gemini companions never touch: QML/Quick/PDF/SVG
# stacks, the software OpenGL fallback, translations, and image/TLS plugins
# (frames arrive as raw RGBA; the single-instance socket is local only).
COMPANION_EXCLUDES = ('imageio_ffmpeg', 'numpy', 'cv2', 'psutil', 'msgspec', 'comtypes', 'tkinter',
                      'PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.QtPdf', 'PySide6.QtSvg',
                      'PySide6.QtOpenGL', 'PySide6.QtDBus', 'PIL.AvifImagePlugin', 'PIL._avif', 'ssl', '_ssl')
COMPANION_PRUNED = ('PySide6/opengl32sw.dll', 'PySide6/translations', 'PySide6/plugins/imageformats',
                    'PySide6/plugins/iconengines', 'PySide6/plugins/tls', 'PySide6/plugins/networkinformation',
                    'PySide6/plugins/generic', 'PySide6/plugins/platforminputcontexts',
                    'PySide6/Qt6Pdf.dll', 'PySide6/Qt6Qml.dll', 'PySide6/Qt6QmlModels.dll', 'PySide6/Qt6Quick.dll',
                    'PySide6/Qt6Svg.dll', 'PySide6/Qt6OpenGL.dll', 'PySide6/Qt6VirtualKeyboard.dll',
                    'PySide6/Qt6QmlMeta.dll', 'PySide6/Qt6QmlWorkerScript.dll')


def prune_qt(internal):
    """Delete unused Qt files from a folder build; returns the bytes removed."""
    removed = 0
    for relative in COMPANION_PRUNED:
        path = Path(internal)/relative
        if path.is_dir():
            removed += sum(item.stat().st_size for item in path.rglob('*') if item.is_file())
            shutil.rmtree(path)
        elif path.is_file():
            removed += path.stat().st_size
            path.unlink()
    return removed
