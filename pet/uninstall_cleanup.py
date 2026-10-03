# -*- coding: utf-8 -*-
"""卸载清理：删除自启项。

供 `--uninstall-cleanup` 参数使用——安装包（Inno Setup）卸载时调用。
该路径不启动 QApplication/事件循环，只做必要的清理，便于「无 Qt 依赖路径」
（仍可 import Qt 模块，但不建窗口）下执行。

多实例占用判断由 agent_link 模块统一提供（语义并集：当前变体目录 + <base>
下全部变体任一认为在用即保留），本模块只负责消费。
"""

from __future__ import annotations

def run_uninstall_cleanup(config=None) -> dict:
    """执行卸载清理，返回结果字典（供测试与日志）。

    只删除当前变体的开机自启项。
    """
    from . import autostart

    if config is None:
        from .config import Config
        config = Config()
    del config

    return {"autostart": bool(autostart.disable())}
