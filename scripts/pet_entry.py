"""Frozen executable entry; use scripts/build_onedir.ps1 to build the onedir bundle."""

import sys

if "--native-self-test" in sys.argv:
    from pet.native.diagnostics import main as native_self_test_main

    sys.exit(native_self_test_main())

if "--settings" in sys.argv:
    # exe 自启动参数分流：设置页独立进程必须在 import pet.app 之前分流，否则子进程
    # 会把整个桌宠（素材库/ffmpeg/托盘/灵动岛）再拉一份，独立进程省内存的前提就没了。
    # 用绝对导入：pet/__main__.py 的相对导入在 PyInstaller 顶层入口会解析失败
    #（见本文件模块 docstring），但作为包内模块 import 进来时相对导入正常。
    from pet.__main__ import _run_settings

    sys.exit(_run_settings())

from pet.app import main

if __name__ == "__main__":
    sys.exit(main())
