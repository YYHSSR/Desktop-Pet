"""Common Conda native-library handling for both Windows build entry points."""
import os
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
