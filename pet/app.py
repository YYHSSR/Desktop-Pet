# -*- coding: utf-8 -*-
"""应用入口和运行期编排。

AppShell 管理实例集合、进程级共享服务和设置子进程；PetInstance 管理每只
桌宠的配置、动画库、碰撞会话与设置窗口。托盘状态由 TrayController 管理。"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
import weakref
from logging.handlers import RotatingFileHandler
from pathlib import Path

import shiboken6
from PySide6.QtGui import QIcon
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import autostart as autostart_mod
from . import catalog
from . import slot_manager as slot_manager_mod
from . import webm_clip as webm_clip_mod
from .config import APP_DIR_NAME, Config, _default_base
from .instance_launcher import launch_new_pet
from .library import MovieLibrary
from .window import PetWindow
from .runtime_cleanup import cleanup_stale_runtime_dirs
from .session_watcher import install_session_watcher
from .collision_ipc import CollisionIpcSession
from .decode_fanout import DecodeFanoutHub
from .tray_controller import TrayController


# 存活 AppShell 注册表（测试收口用，与 collision_ipc._live_sessions /
# agent_link._LIVE_AGENT_LINK_MANAGERS 同一纪律）。多窗共享子系统
# 持有无主 QTimer（`QTimer()` + timeout.connect），其连接从 Qt C++ 侧强引用
# 住整个 shell 对象图，Python 的 gc.collect() 回收不掉；解释器退出时的 GC
# 才最终化这些 Qt 对象 → 原生访问违规（Windows 0xC0000005，崩溃点落在
# "Garbage-collecting / <no Python frame>"）。WeakSet 只弱引用 shell 本身，
# 测试收口时逐对象停表并释放反向引用。
_LIVE_SHELLS: "weakref.WeakSet" = weakref.WeakSet()


# 多窗日志用 [slot-N] 前缀区分。单进程多窗共享一份日志文件，
# 故用线程本地记录「当前执行的窗」由日志 Filter 加前缀；flag 关（单进程单窗）
# 时前缀为 None，日志格式与现状逐位一致。
_pet_log_slot = threading.local()


class _SlotLogFilter(logging.Filter):
    """按线程本地槽位给日志记录加 [slot-N] 前缀（flag 开/多窗时）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        slot = getattr(_pet_log_slot, "slot", None)
        if slot:
            record.msg = f"[{slot}] {record.msg}"
        return True


def _setup_logging(config: Config) -> None:
    config.dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        str(config.dir / f'pet-{os.getpid()}.log'),  # 多开实例日志按 PID 隔离，避免互相覆盖
        maxBytes=1_000_000, backupCount=2, encoding='utf-8',
    )  # 滚动日志：1MB×2，不再无限增长
    handler.addFilter(_SlotLogFilter())
    logging.basicConfig(
        handlers=[handler],
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        encoding='utf-8',
    )
    _cleanup_old_pet_logs(config.dir)


def _cleanup_old_pet_logs(log_dir, *, max_age_days: float = 7.0) -> int:
    """启动时清理过期的 pet-<pid>.log（含滚动备份 .log.1/.2）。

    每实例每次启动都产生新文件，不清理会无界累积（审查 GLM-M2）。
    只删本变体命名空间下超龄文件；失败静默（清理不影响启动）。
    """
    removed = 0
    try:
        cutoff = time.time() - max_age_days * 86400
        for path in Path(log_dir).glob('pet-*.log*'):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
    except OSError:
        pass
    return removed


def _show_startup_error(title: str, message: str) -> None:
    QMessageBox.critical(None, title, message)


def _cleanup_stale_runtime_dirs() -> None:
    """清理 PyInstaller onefile 遗留的 ``_MEI*`` 临时目录。

    只扫描系统临时目录中超过 24 小时的目录，并始终跳过当前进程的
    ``sys._MEIPASS``。删除失败只记录日志，不接管 ACL，也不影响启动。
    """
    if not getattr(sys, "frozen", False):
        return
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return

    current = Path(meipass).resolve(strict=False)
    result = cleanup_stale_runtime_dirs(current_dir=current)
    for directory in result.removed:
        logging.info("已清理遗留 PyInstaller 缓存目录: %s", directory)
    for directory, error in result.failed.items():
        logging.warning("清理 PyInstaller 缓存目录失败: %s (%s)", directory, error)


def _read_spawn_offset_env() -> int:
    """P0-1：读取 spawn 子进程路径写入的 DSH_PET_SPAWN_OFFSET_INDEX，显式传给
    主窗 PetInstance.spawn_offset（进程 spawn 路径依赖它错开落位）。

    flag 关（生小肥鱼走独立进程）时 instance_launcher 写该 env、子进程 main()
    启动须把它接到主窗的 spawn_offset 构造参数——否则 _apply_spawn_offset 的
    index 恒为 0，新孵化的桌宠直接与母桌宠完全重叠（flag 关行为回归）。
    """
    try:
        return max(0, int(os.environ.get('DSH_PET_SPAWN_OFFSET_INDEX', '0') or '0'))
    except (TypeError, ValueError):
        return 0

class PetInstance:
    """每只桌宠的配置、窗口、动画库、碰撞会话与设置窗口。"""

    def __init__(self, shell: "AppShell", config: Config,
                 slot_handle=None, slot_id: int | None = None,
                 spawn_offset: int = 0) -> None:
        self.shell: AppShell = shell
        self.config = config
        self.slot_handle = slot_handle
        self.slot_id = slot_id
        self._spawn_offset = max(0, int(spawn_offset if spawn_offset is not None else 0))
        self.win: PetWindow | None = None
        self.modern_settings_dialog = None
        # 碰撞会话移回**本窗**自持（每窗一个，经
        # collision_ipc._local_election_names 同进程收敛成「一协调者 + N 客户端」），
        # 每窗 runtime_id 由各自 instance_id 派生 → 两窗互撞与多进程双开等价；
        # 「退出这只」只停本窗，switch_character 只重建本窗。
        self.collision_ipc = CollisionIpcSession(config, self.shell)
        # 各窗共用进程级解码 hub，解码共享与碰撞协调相互独立。
        self.broker_facade = getattr(self.shell, '_decode_hub', None)


    # ------------------------------------------------------------ 窗口构建
    def _create_library(self, character_id: str) -> MovieLibrary:
        # 预热策略：默认 balanced（瞬时交互核 pinned 预热首帧，随机动作池
        # 后台预热（此处经 prewarm_enabled 传入，设置保存后由
        # _sync_animation_prewarm 同步）。media_prewarm 键保留给高级用户。
        prewarm = str(self.config.get("media_prewarm", "balanced") or "balanced")
        # 首帧缓存全局预算（可在 config.json 调整低内存机器的缓存预算）；
        # 进程级设置，幂等，切角色重复调用无害。
        webm_clip_mod.set_first_frame_budget(
            int(self.config.get("first_frame_cache_max_mb", 8)) * 1024 * 1024
        )
        lib = MovieLibrary(
            character_id=character_id,
            prewarm_policy=prewarm,
            prewarm_enabled=True,
        )
        # UI 就绪后统一调度预热：高优先级立即后台跑（带 0~0.05s 错峰），
        # 随机动作池延迟 2s 补全，避免多开启动时 ffmpeg 进程洪峰。
        lib.schedule_high_priority_warm()
        lib.schedule_low_priority_warm()
        logging.info('素材加载完成：%s %d 段动画', character_id, len(lib.names()))
        return lib

    def _slot_wrap(self, fn):
        """包一层：调用回调时把线程本地日志槽位设为本窗 slot（）。

        flag 关（单窗）时槽位为 None，日志格式与现状逐位一致；flag 开/多窗
        时槽位为 'slot-N'，由 _SlotLogFilter 加 [slot-N] 前缀。
        """
        if fn is None:
            return None
        slot = f"slot-{self.slot_id}" if self.slot_id is not None else "slot-0"

        def wrapper(*args, **kwargs):
            prev = getattr(_pet_log_slot, "slot", None)
            # P1-2：窗级逻辑一律读进程级 flag 快照（shell._single_process_spawn），
            # 不读每窗 config（第二窗 config-slot-N 里该键无效）。
            if self.shell._single_process_spawn:
                _pet_log_slot.slot = slot
            else:
                _pet_log_slot.slot = None
            try:
                return fn(*args, **kwargs)
            finally:
                _pet_log_slot.slot = prev

        wrapper.__name__ = getattr(fn, "__name__", "wrapper")
        wrapper.__doc__ = getattr(fn, "__doc__", None)
        return wrapper

    def _wire_window(self, win: PetWindow) -> None:
        """绑定新窗口的回调接线（创建与角色切换共用，两处历史逐行重复）。

        两段原始代码逐行一致（并集 = 该段本身，未发现任一方多设回调），
        后续新增回调只改这一处即可保证两个入口同步。
        进程级操作（生小肥鱼/系统通知）经 ``self.shell`` 路由，
        其余均为本窗操作。用 ``_slot_wrap`` 给每窗回调加日志槽位。
        """
        win.on_switch_character = self._slot_wrap(self.switch_character)
        win.on_open_modern_settings = self._slot_wrap(self.open_modern_settings)
        # 反馈面可用性探针：隐藏期联动监视器是否跳过低功耗暂停（mixin 消费）。
        win.on_spawn_pet = self._slot_wrap(self.shell.spawn_pet)
        # 「退出子肥鱼」只挂给主肥鱼（instance_id 为空）：子肥鱼进程里该入口的
        # pid==os.getpid() 自我保护会跳过子鱼自己、把主鱼当子鱼 taskkill 掉
        #（实机事故：从子鱼触发清除 → 主鱼被杀、触发的那只子鱼存活）。
        win.on_clear_spawned_pets = (
            self._slot_wrap(self.shell.clear_spawned_pets)
            if not self.config.instance_id else None)
        win.on_hidden = self._slot_wrap(self._notify_pet_hidden)
        # 右键「退出」注入窗级「退出这只」只在 flag 开（多窗）时；
        # flag 关（单窗）不注入 → _request_quit 走旧 app.quit 分支，逐位一致。
        if self.shell._single_process_spawn:
            win.on_exit_window = self._slot_wrap(self._request_exit_window)
        else:
            win.on_exit_window = None

    def _build_window(self, character_id: str, lib: MovieLibrary | None = None,
                      build_tray: bool = True) -> PetWindow:
        """创建并接线窗口；新窗口就绪后延迟释放旧窗口和托盘。

        切换角色可预先传入动画库，加载失败时保留当前角色。非主窗复用进程托盘。"""
        if lib is None:
            lib = self._create_library(character_id)
        # flag 开时各窗引用同一份进程级共享子系统（agent_link /
        shared = getattr(self.shell, "_shared", None)
        # 窗自身构造期日志（恢复位置/runtime 标记等）加 [slot-N] 前缀
        _prev_slot = getattr(_pet_log_slot, "slot", None)
        if shared is not None and self.slot_id is not None:
            _pet_log_slot.slot = f"slot-{self.slot_id}"
        try:
            win = PetWindow(lib, self.config, collision_session=self.collision_ipc,
                            broker_facade=self.broker_facade,
                            single_process_spawn=self.shell._single_process_spawn,
                            agent_link_manager=shared.agent_link if shared else None
                            )
        finally:
            _pet_log_slot.slot = _prev_slot
        # P1-2：窗级 runtime 标记版本化 / 日志前缀读进程级 flag 快照（不读每窗 config）。
        # N-1：快照经构造参数在 _restore_position 之前生效（窗构造期就会写标记）。
        self._wire_window(win)
        win.show()

        tray = self.shell.tray_controller.build(win) if build_tray else None

        # 清理旧对象（热切换时使用）
        old_win = self.win
        old_tray = self.shell.tray
        self.win = win
        if build_tray:
            self.shell.tray = tray
        self.shell.tray_controller.sync_checks()
        # 接入共享联动链必须在 self.win = win 之后——
        # 扇出按 instances[].win 动态遍历，早了会让新窗永远拿不到 provider。
        if shared is not None:
            self.shell._wire_shared_subsystems()

        if old_win is not None:
            old_win.hide(notify=False)
            QTimer.singleShot(0, old_win.deleteLater)
            # 仅主窗（build_tray=True）换托盘；非主窗绝不 hide/deleteLater 共享托盘。

            if build_tray and old_tray is not None:
                old_tray.hide()
                QTimer.singleShot(0, old_tray.deleteLater)
        return win

    def _create_ui(self, character_id: str) -> None:
        self._build_window(character_id)

    # ------------------------------------------------------------ 角色切换
    def switch_character(self, character_id: str) -> None:
        if self.win is None:
            return
        current = str(self.config.get('character', catalog.DEFAULT_CHARACTER))
        if character_id == current:
            return

        # 先保存配置，即使后续加载失败也记住用户选择
        self.config.set('character', character_id)
        self.config.save()

        try:
            # 预创建新库，失败则保留当前角色（在动旧窗口之前完成）
            lib = self._create_library(character_id)
        except Exception as exc:
            logging.exception('切换角色失败: %s', character_id)
            _show_startup_error('切换角色失败', str(exc))
            return

        logging.info('切换角色: %s -> %s', current, character_id)

        # 碰撞会话由**本窗**自持（每窗一个）——热切换
        # 只重建本窗的 session（detach 旧窗 client → 停/重建本窗会话 →
        # 新窗 attach 到新会话）。C2 前向地雷（多窗下任一窗热切换拆共享进程级
        # IPC）随「不再共享」自然消解。
        # 共享解码为进程级 hub（DecodeFanoutHub），不随热切换停；
        # 窗侧只经 _broker_unregister 逐素材收尾。
        old_win = self.win
        old_win.detach_collision_session()
        # 停本窗旧碰撞会话并重建（影响仅限本窗，不碰其它窗）
        try:
            self.collision_ipc.stop()
        except Exception:
            logging.exception("切换角色：停止本窗碰撞会话失败")
        self.collision_ipc = CollisionIpcSession(self.config, self.shell)
        self.collision_ipc.start()
        if getattr(old_win, 'agent_link_manager', None) is not None:
            old_win.agent_link_manager.shutdown()
        # 主窗热切换才换托盘（进程级单托盘）；非主窗热切换不动共享托盘。
        self._build_window(character_id, lib=lib, build_tray=(self is self.shell.instance))
        # P1-4：任一窗切换后刷新托盘菜单（per-window 区闭包指向新窗，防陈旧窗）
        self.shell.tray_controller.refresh()

    def _apply_spawn_offset(self) -> None:
        """让新孵化的桌宠与母桌宠错开，避免两个窗口完全重叠。

        偏移量改为实例属性（显式传递），不再读进程级
        DSH_PET_SPAWN_OFFSET_INDEX 环境变量——单进程多窗下环境变量是
        进程级的，无法区分各窗（§1.2）。
        """
        if self.win is None:
            return
        index = self._spawn_offset
        if index <= 0:
            return
        scr = self.win.screen_available()
        if scr is None:
            return
        available = scr.availableGeometry()
        horizontal = -1 if self.win.geometry().center().x() > available.center().x() else 1
        vertical = -1 if self.win.geometry().center().y() > available.center().y() else 1
        # 虚拟窗口坐标：贴边状态下实际窗口位置不含绘制偏移，错开要按
        # 角色自然位置算；未支持统一出口的窗口回退实际位置（= 改造前）。
        vp_fn = getattr(self.win, '_virtual_pos', None)
        base = vp_fn() if callable(vp_fn) else QPoint(self.win.x(), self.win.y())
        x = base.x() + horizontal * 48 * index
        y = base.y() + vertical * 32 * index
        mover = getattr(self.win, '_move_window_towards', None)
        if callable(mover):
            mover(x, y)  # 统一出口自带工作区钳位（含小屏兜底）
            return
        # 小屏（可用区比窗口还窄/矮）时上界 < 下界，min/max 会互相打架把
        # 窗口推出屏幕外；先判边界再钳制。
        max_x = available.right() - self.win.width() + 1
        max_y = available.bottom() - self.win.height() + 1
        x = available.left() if max_x < available.left() else min(max(x, available.left()), max_x)
        y = available.top() if max_y < available.top() else min(max(y, available.top()), max_y)
        self.win.move(x, y)

    # ------------------------------------------------------------ 对话框呈现


    def _present_dialog(self, dialog, before_present=None, attempt: int = 0) -> None:
        """菜单关闭后再呈现非模态设置窗口，避免原生菜单跟踪会话抑制新窗口。

        弹出菜单未结束时最多重试 60 次，防止无限等待。"""
        if attempt > 60:
            return
        if QApplication.activePopupWidget() is not None:
            QTimer.singleShot(60, lambda: self._present_dialog(dialog, before_present, attempt + 1))
            return
        if before_present is not None:
            before_present()
        if dialog.isMinimized():
            dialog.showNormal()
        else:
            dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    # ------------------------------------------------------------ 设置


    def _update_bubble_suppression_for_settings(self) -> None:
        """任一设置窗口打开/独立设置进程存活时暂停桌宠气泡，避免气泡盖住设置界面。"""
        if getattr(self, "win", None) is None:
            return
        shell = getattr(self, "shell", None)
        # 独立设置进程在跑时主进程没有对话框对象，只能看 shell 上的存活标记：
        # 锁文件存在期由 AppShell 维护（watcher 立即 + 3s 轮询兜底清除）。
        external_settings = bool(getattr(shell, "_settings_child_active", False)) if shell is not None else False
        any_open = (
            getattr(self, "modern_settings_dialog", None) is not None
            or external_settings
        )
        self.win.set_bubble_suppressed(any_open)

    def open_modern_settings(self) -> None:
        # 默认路径：设置页拉到独立进程（关窗即进程退出，OS 回收首开留下的
        # 字体/样式/模块高水位）。只有开关关闭或 startDetached 失败时才回退
        # 下面的进程内路径——功能绝不丢。
        if self._try_open_settings_process():
            return
        from .modern_settings_dialog import ModernSettingsDialog
        if self.modern_settings_dialog is None:
            self._dock_icon_before_settings = bool(self.config.get("show_dock_icon", True))
            dialog = ModernSettingsDialog(
                self.config,
                self.win,

            )
            dialog.finished.connect(self._modern_settings_finished)
            self.modern_settings_dialog = dialog
        self._update_bubble_suppression_for_settings()
        # 在 show 之前定位，避免 Windows 上窗口先显示默认位置再跳走（闪现小窗）
        self._present_dialog(
            self.modern_settings_dialog,
            before_present=self.modern_settings_dialog.move_away_from_pet,
        )

    def _try_open_settings_process(self) -> bool:
        """尝试走独立设置进程；True = 已交给独立进程（不要再开进程内对话框）。"""
        shell = getattr(self, "shell", None)
        opener = getattr(shell, "open_settings_process", None)
        if not callable(opener):
            return False
        try:
            return bool(opener(self))
        except Exception:
            logging.exception("独立设置进程链路异常，回退进程内设置页")
            return False

    def _modern_settings_finished(self, result: int) -> None:
        self.modern_settings_dialog = None
        self._update_bubble_suppression_for_settings()
        # 新版设置在关闭时一律落盘（closeEvent 自动保存，「保存并退出」同样走
        # _write_config），因此无论 Accepted/Rejected 都把改动应用到桌宠。
        # 此前只有 Accepted 才刷新：直接 X 关闭时保存生效但桌宠不更新。
        #
        # 应用链与 watcher 路径共用 AppShell._apply_external_config_change；但
        # 旧测试桩（AppShell.__new__ + 只打桩原内联 seam，没有 _instances）仍走
        # 原内联序列，保证进程内路径的既有测试/时序逐位不变。
        shell = self.shell
        apply_change = getattr(shell, "_apply_external_config_change", None)
        if callable(apply_change) and getattr(shell, "_instances", None) is not None:
            apply_change()
        else:
            if self.win is not None:
                self.win.refresh_pet_settings()
            # 设置保存后同步动画预热
            self._sync_animation_prewarm()
            _mac_set_dock_icon_visible(bool(self.config.get("show_dock_icon", True)))
        if (
            getattr(self, "_dock_icon_before_settings", None) is True
            and not bool(self.config.get("show_dock_icon", True))
        ):
            self._hint_dock_hidden_recovery()


    def _dock_hidden_recovery_message(self) -> str:
        return (
            "已隐藏 Dock 图标，桌宠仍会常驻。需要恢复时：点菜单栏托盘图标 → "
            "「桌宠设置」→ 重新勾选「显示 Dock 图标」；找不到桌宠也从托盘菜单「显示 / 隐藏」恢复。"
        )

    def _hint_dock_hidden_recovery(self) -> None:
        if sys.platform != "darwin":
            return
        win = self.win
        if win is not None and callable(getattr(win, "show_bubble", None)) and win.isVisible():
            win.show_bubble(self._dock_hidden_recovery_message(), duration_ms=7000)
            return
        tray = getattr(self.shell, "tray", None)
        if tray is not None and callable(getattr(tray, "showMessage", None)):
            tray.showMessage(
                "桌宠设置",
                self._dock_hidden_recovery_message(),
                QSystemTrayIcon.MessageIcon.Information,
                7000,
            )

    def _sync_animation_prewarm(self) -> None:
        """同步动画预热；隐藏期间暂停后台预热。"""
        win = self.win
        lib = getattr(win, "lib", None) if win is not None else None
        setter = getattr(lib, "set_prewarm_enabled", None)
        if not callable(setter):
            return
        visible = None
        is_visible = getattr(win, "isVisible", None) if win is not None else None
        if callable(is_visible):
            visible = bool(is_visible())
        setter(True, visible=visible)

    # ------------------------------------------------------------ 其它窗口级

    def _check_autostart_wanted(self) -> None:
        if self.config.get("autostart_wanted", False) and not autostart_mod.is_enabled() and self.win is not None:
            self.win.show_bubble("检测到开机自启已被系统或安全软件关闭，可在托盘中重新启用。", duration_ms=7000)

    def _notify_pet_hidden(self) -> None:
        """用户主动隐藏后说明统一恢复入口。"""
        if self.shell.tray is None:
            return
        message = "在托盘选择「显示 / 隐藏所有桌宠」即可恢复。"
        self.shell.tray.showMessage(
            "桌宠已隐藏",
            message,
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def _request_exit_window(self) -> None:
        """窗级「退出这只」：委托 AppShell 收口本窗资源（）。"""
        if self.win is None:
            return
        self.shell._on_window_exit_requested(self)


class AppShell:
    """管理桌宠实例集合、共享解码、系统通知及进程生命周期。"""

    def __init__(self, app: QApplication, config: Config,
                 slot_handle=None, slot_id: int | None = None,
                 spawn_offset: int = 0) -> None:
        self.app = app
        self.config = config
        self._slot_id = slot_id
        self.tray: QSystemTrayIcon | None = None
        self.tray_controller = TrayController(self)
        self.dock_menu: QMenu | None = None
        self._spawned_pet_count = 0
        self._on_about_to_quit_connected = False

        # 进程级 flag 快照——启动期从主窗 config 读一次存
        # _single_process_spawn；窗级逻辑（runtime 标记版本化、日志前缀、
        # 退出分派、spawn 分发）一律读本快照，不读每窗 config。第二窗的
        # config-slot-N.json 里该键不再有任何作用，运行期手改 config.json
        # 翻 flag 也因此失效（需重启）。
        self._single_process_spawn = bool(config.get('experimental_single_process_spawn', False))
        # 进程级共享解码 hub（同角色帧扇出）——`experimental_shared_decode`
        # 默认开，但 `experimental_single_process_spawn` 关时整条 fan-out 不激活
        #（单窗无共享可言）。门关 = 每窗各自独立解码（形态，hub 恒回 local）。
        self._decode_hub = DecodeFanoutHub(
            enabled=bool(config.get('experimental_shared_decode', True))
            and self._single_process_spawn)
        # 全屏 watcher），各窗经 PetWindow 构造参数引用同一份，崩溃/换角色不重建；
        # flag 关时保持 None = 每窗各自创建（现状逐位一致）。
        #（位置在 _instances 就绪之后，共享 manager 构造期即遍历窗集合）。
        self._shared = None
        # 碰撞会话/broker 移回各 PetInstance 自持（不再由 AppShell 持有）；
        # 每窗一个，经 collision_ipc._local_election_names 同进程收敛。
        # 每窗容器：单进程单窗仅一个；spike 扩成多窗集合
        #（self.instance 指主窗 = instances[0]，兼容既有调用面）。
        self._instances: list[PetInstance] = []
        # 清除子肥鱼链式关闭进行中标记（重复点击忽略，保持幂等）。
        self._clear_spawned_pending = False
        # 设置进程隔离：独立设置进程存活标记 + config 目录 watcher/定时器
        #（懒安装，见 _install_config_watcher）。默认关的键下完全不用它们。
        self._settings_child_active = False
        self._settings_launch_at = 0.0
        self._config_watcher = None
        self._config_reload_timer = None
        self._settings_watch_timer = None
        self._last_config_signature = None
        self.instance = PetInstance(
            self, config, slot_handle=slot_handle,
            slot_id=slot_id, spawn_offset=spawn_offset,
        )
        self._instances.append(self.instance)
        if self._single_process_spawn:
            from .multi_window_shared import SharedSubsystems

            self._shared = SharedSubsystems(self)
        _LIVE_SHELLS.add(self)


    @property
    def slot_id(self) -> int | None:
        """主窗 slot（E2：主窗实例 slot_id 为权威，本属性只读转发）。"""
        inst = getattr(self, 'instance', None)
        if inst is not None and getattr(inst, 'slot_id', None) is not None:
            return inst.slot_id
        return self._slot_id

    @property
    def instances(self) -> list[PetInstance]:
        return self._instances

    # --- 进程级功能（通知与托盘）的鸭式访问器：转发到主窗实例 ---
    @property
    def win(self) -> PetWindow | None:
        """主窗窗口（无窗时 None）。"""
        inst = getattr(self, 'instance', None)
        return inst.win if inst is not None else None

    @win.setter
    def win(self, value) -> None:
        """Legacy compatibility setter routed to the primary instance."""
        inst = getattr(self, 'instance', None)
        if inst is not None:
            inst.win = value


    # ------------------------------------------------------------ 设置进程隔离
    def _apply_external_config_change(self) -> None:
        """把「配置已在别处落盘」同步到运行期（独立设置进程 / watcher 路径）。

        与进程内对话框 finished 的应用链同源（PetInstance._modern_settings_finished
        在真实壳上委托到这里）；多实例时扇出到每个 PetInstance 的窗口，而不是
        只看主窗——外部改配置的那个实例不一定是主窗。
        """
        for inst in getattr(self, "_instances", []):
            win = getattr(inst, "win", None)
            if win is not None:
                win.refresh_pet_settings()
        # 设置保存后同步动画预热
        for inst in getattr(self, "_instances", []):
            prewarm = getattr(inst, "_sync_animation_prewarm", None)
            if callable(prewarm):
                prewarm()
        _mac_set_dock_icon_visible(bool(self.config.get("show_dock_icon", True)))


    def _install_session_watcher(self) -> None:
        """安装会话结束探测器（幂等；实例属性强引用保活，不跨实例共享）。"""
        if getattr(self, "_session_watcher", None) is not None:
            return
        try:
            self._session_watcher = install_session_watcher(
                app=self.app, on_session_end=self._on_session_end,
            )
        except Exception:
            logging.exception("安装会话结束探测器失败")

    def _on_session_end(self) -> None:
        """会话结束（关机/注销）：冻结各窗并停止全部 ffmpeg reader（issue #111）。

        幂等：重复的会话结束信号（WM_QUERYENDSESSION 之后又有 WM_ENDSESSION、
        Qt 的 commitDataRequest/aboutToQuit）只收口一次。

        只做正常退出路径（``_on_about_to_quit``）不做、且关机场景必需的三件事：
        关 ffmpeg spawn 闸门、冻结窗口动画（``match_shutdown``）、把各窗素材库
        里**已建的全部 clip** 一起停掉（不只是各窗当前在播的那个：圈末软停驻留
        的 clip 仍持有一个存活但空闲的 ffmpeg 进程，关机时一并收口）、留一行日志。

        刻意**不**做会话保存/写盘/槽位解锁：关机时登录会话已在拆除，那些收尾
        既非必需（多开文件锁由操作系统在进程退出时释放）又会拉长清理窗口，
        与「静默、快速、不再派生任何进程」的目标相反。
        """
        if getattr(self, "_session_end_done", False):
            return
        self._session_end_done = True
        self._mark_session_ending()
        stopped = 0
        for inst in self._instances:
            win = getattr(inst, "win", None)
            match_shutdown = getattr(win, "match_shutdown", None)
            if callable(match_shutdown):
                try:
                    match_shutdown()
                except Exception:
                    logging.exception("会话结束时冻结窗口失败")
            lib = getattr(win, "lib", None)
            stop_all = getattr(lib, "stop_all_clips", None)
            if callable(stop_all):
                try:
                    stop_all()
                    stopped += 1
                except Exception:
                    logging.exception("会话结束时停止素材库 clip 失败")
        logging.info(
            "会话结束：已停止全部 ffmpeg reader（%d 个素材库收口），进入静默退出", stopped,
        )

    def _mark_session_ending(self) -> None:
        """置位进程级 ffmpeg spawn 闸门（webm_clip.set_session_ending）。

        覆盖「已进入退出流程、但原生 WM_QUERYENDSESSION 未被观测到」的路径
        （如托盘退出、Qt aboutToQuit、测试直接调收口）。
        """
        try:
            webm_clip_mod.set_session_ending(True)
        except Exception:
            logging.exception("置位会话结束闸门失败")


    def _create_ui_with_character_fallback(self, character_id: str) -> None:
        """启动路径创建主窗；配置记住的角色素材目录已被删/搬走（如 DLC 卸载）
        时回退默认角色重试一次，而不是直接弹错退出。默认角色也缺素材则照常
        抛出，由上层弹启动错误。"""
        try:
            self.instance._create_ui(character_id)
        except FileNotFoundError:
            if character_id == catalog.DEFAULT_CHARACTER:
                raise
            logging.warning('角色 %s 素材缺失，回退默认角色 %s', character_id, catalog.DEFAULT_CHARACTER)
            character_id = catalog.DEFAULT_CHARACTER
            self.config.set('character', character_id)
            self.instance._create_ui(character_id)

    # ------------------------------------------------------------ 退出收口
    def _on_about_to_quit(self) -> None:
        """关闭 ffmpeg 派生闸门，保存各窗位置并释放窗口与进程级服务。"""
        # 先关 ffmpeg spawn 闸门，再走正常退出收口——正常退出路径
        # （托盘退出/最后窗口关闭）同样落在关机前后，绝不能在里面再派生 reader。
        self._mark_session_ending()
        # 窗级收口：逐窗保存位置、停本窗预热与 Agent、释放本窗 slot 锁
        for inst in self._instances:
            win = inst.win
            if win is not None:
                try:
                    win.save_position()
                except Exception:
                    logging.exception("退出时保存位置失败")
                try:
                    if getattr(win, 'lib', None) is not None:
                        win.lib.pause_warm()
                except Exception:
                    logging.exception("退出时暂停预热失败")
                if getattr(win, 'agent_link_manager', None) is not None:
                    try:
                        win.agent_link_manager.shutdown()
                    except Exception:
                        logging.exception("退出时关闭 Agent 失败")
            if inst.slot_handle is not None:
                try:
                    slot_manager_mod._unlock_file(inst.slot_handle)
                except Exception:
                    pass
                inst.slot_handle = None
            # 每窗碰撞会话逐窗收口；共享解码只在进程退出时统一停止。
            try:
                inst.collision_ipc.stop()
            except Exception:
                logging.exception("退出时停止碰撞会话失败")
        # 单窗关闭（退出这只）不触发——只有「全部退出」才停共享子系统。
        if self._shared is not None:
            try:
                self._shared.stop_all()
            except Exception:
                logging.exception("退出时关闭共享子系统失败")
        # 进程级共享解码 hub 收口（全部退出时才停；各窗的源/订阅早已
        # 由窗 closeEvent/_switch 的 shareable_end 逐素材收敛）。
        try:
            self._decode_hub.stop_all()
        except Exception:
            logging.exception("退出时关闭共享解码 hub 失败")
        # 设置页进程隔离：释放 config 目录 watcher 与两个定时器（无主 QTimer 的
        # timeout 连接会从 Qt C++ 侧强引用住本对象图，不停则阻碍回收）。
        self._teardown_config_watcher()
        self.tray_controller.shutdown()

    @classmethod
    def _shutdown_live_for_tests(cls) -> None:
        """释放测试创建的共享服务、托盘和配置监视器；不保存用户位置或退出应用。"""
        for shell in tuple(_LIVE_SHELLS):
            try:
                shell.tray_controller.shutdown()
                if getattr(shell, "_shared", None) is not None:
                    shell._shared.stop_all()
                if getattr(shell, "instance", None) is not None:
                    win = getattr(shell.instance, "win", None)
                    lib = getattr(win, "lib", None)
                    if lib is not None:
                        lib.pause_warm()
                if getattr(shell, "_on_about_to_quit_connected", False):
                    try:
                        shell.app.aboutToQuit.disconnect(shell._on_about_to_quit)
                    except (RuntimeError, TypeError):
                        pass
                    shell._on_about_to_quit_connected = False
                # 设置页进程隔离：watcher/定时器同属"无主 Qt 对象"一族，收口
                #（不停会让后续测试凭空多一条 3s 轮询，并阻碍对象图回收）。
                teardown_watcher = getattr(shell, "_teardown_config_watcher", None)
                if callable(teardown_watcher):
                    try:
                        teardown_watcher()
                    except Exception:
                        logging.debug("测试收口 config watcher 失败", exc_info=True)
                shell._settings_child_active = False
                shell._instances = []
            except Exception:
                logging.debug("测试收口 AppShell 失败", exc_info=True)

    def _on_shared_fullscreen(self, hit: bool) -> None:
        """共享全屏 watcher 广播 → 扇出到各窗的 _on_fullscreen_changed。

        逐窗动态遍历（读 _instances 而非绑定某窗），任一窗退出/重建后自动忽略它。
        经窗口公开信号回传全屏状态。
        """
        if getattr(self, "_shared", None) is None:
            return
        for inst in self._instances:
            win = inst.win
            if win is None or not shiboken6.isValid(win):
                continue
            # 复审 P1-2：全屏广播按每窗配置过滤——关掉「全屏自动隐藏」的窗
            # 不得被无关广播隐藏/恢复（光标路径的每窗 gate 在窗内已有，
            # 该窗的 _on_cursor_visibility_changed 首行自过滤，无需重复）。
            if not getattr(win, "auto_hide_fullscreen", False):
                continue
            try:
                win.fullscreen_changed.emit(hit)
            except (AttributeError, RuntimeError):
                logging.exception("扇出全屏状态到窗口失败")

    def _on_shared_cursor(self, visibility: str) -> None:
        """共享光标可见性广播 → 扇出到各窗的 _on_cursor_visibility_changed。"""
        if getattr(self, "_shared", None) is None:
            return
        for inst in self._instances:
            win = inst.win
            if win is None or not shiboken6.isValid(win):
                continue
            try:
                win.cursor_visibility_changed.emit(visibility)
            except (AttributeError, RuntimeError):
                logging.exception("扇出光标状态到窗口失败")

    def _wire_shared_subsystems(self) -> None:
        """把新窗接入进程级共享子系统（agent_link 联动动作链分发）。

        共享 manager 在 AppShell.__init__ 已创建（此刻尚无窗，set_link_next_provider
        落入空集），新窗出现后经 proxy 重新分发；
        全屏 watcher 经 _on_shared_fullscreen/_on_shared_cursor 动态遍历，无需单独连。
        """
        shared = self._shared
        if shared is None:
            return
        try:
            shared.proxy.set_link_next_provider(shared.agent_link._next_busy_anim)
        except (AttributeError, RuntimeError):
            logging.exception("把窗口接入共享 Agent 联动链失败")


    # -------------------------------------------------------- 岛对话气泡


    # ------------------------------------------------------------ 生小肥鱼 / 多窗
    def spawn_pet(self) -> None:
        """按 feature flag 决定是 spawn 新进程还是进程内建第二个 PetInstance。

        flag ``experimental_single_process_spawn`` 默认关 = 走 ``launch_new_pet``
        独立进程路径（行为与现状逐位一致）。开 = 进程内创建新窗（spike）。
        """
        if not self._single_process_spawn:
            try:
                self._spawned_pet_count += 1
                launch_new_pet(self._spawned_pet_count)
            except OSError as exc:
                self._spawned_pet_count = max(0, self._spawned_pet_count - 1)
                logging.exception('生小肥鱼失败')
                _show_startup_error('生小肥鱼失败', str(exc))
            return
        try:
            self._spawned_pet_count += 1
            self.spawn_in_process_window(self._spawned_pet_count)
        except Exception as exc:
            self._spawned_pet_count = max(0, self._spawned_pet_count - 1)
            logging.exception('进程内生成小肥鱼失败')
            _show_startup_error('生小肥鱼失败', str(exc))

    def clear_spawned_pets(self) -> None:
        """右键菜单快捷入口：一键静默退出所有小肥鱼（设置与数据保留）。

        按用户要求去掉确认框与结果框——操作本身不删数据、子肥鱼可
        随时重新生成，无需确认；子肥鱼消失本身就是反馈，结果写日志。
        """
        from .child_pet_cleanup import clear_spawned_pets as cleanup_slots

        if self._clear_spawned_pending:
            # 链式关闭进行中：重复点击直接忽略（同一任务会清干净，保持幂等）。
            return
        # 单进程模式前置：进程内「非主窗」小肥鱼（PID=主进程）会被文件级清理的
        # pid==os.getpid() 自我保护跳过而永远清不掉，先按进程内子窗登记表枚举。
        # 关闭走 QTimer.singleShot(0) 逐只链式执行（每只之间让出事件循环），且
        # 每窗的重资源回收（Agent shutdown/碰撞会话停止，各有界
        # 阻塞秒级）挪到后台 reaper 线程（，_on_window_exit_requested 的
        # defer_heavy_teardown 路径），UI 线程只留关窗/摘标记等毫秒级必做步骤。
        # 全部关完再走文件级清理杀多进程子进程（同样在后台线程跑，taskkill
        # 不再冻 UI）。两条路径都幂等，清完不留 runtime 标记残留。
        refs = [weakref.ref(inst) for inst in self._instances
                if inst is not self.instance]
        # 进行中标记两条路径统一前置：链式与纯文件级清理都覆盖（文件级
        # 清理改后台线程，执行期间重复点击同样忽略）。
        self._clear_spawned_pending = True
        if not refs:
            self._finish_clear_spawned_pets(cleanup_slots)
            return
        QTimer.singleShot(
            0, lambda: self._clear_spawned_chain(refs, 0, cleanup_slots))

    def _clear_spawned_chain(self, refs, index: int, cleanup_slots) -> None:
        """逐只异步关闭进程内子窗（每只之间让出事件循环，UI 不冻结）。

        窗口已销毁（弱引用失效）或已被关闭（不在登记表）则跳过；链尾执行
        文件级收尾（杀残余多进程子进程）并弹结果框。异常只记录不中断，
        保证进行中标记一定复位。
        """
        if index >= len(refs):
            self._finish_clear_spawned_pets(cleanup_slots)
            return
        inst = refs[index]()
        if inst is not None and inst in self._instances:
            try:
                # 链式路径重资源回收后台化（Agent/碰撞的有界 join
                # 移出 UI 线程），每窗 UI 线程单步阻塞压到毫秒级。
                self._on_window_exit_requested(inst, defer_heavy_teardown=True)
            except Exception:
                logging.exception(
                    "清除子肥鱼：关闭进程内小肥鱼失败 (slot=%s)",
                    getattr(inst, "slot_id", None))
        QTimer.singleShot(
            0, lambda: self._clear_spawned_chain(refs, index + 1, cleanup_slots))

    def _finish_clear_spawned_pets(self, cleanup_slots) -> None:
        """链式关闭收口：文件级退出残余子进程，并复位进行中标记。

        文件级清理（逐 pid taskkill）移到后台线程——在 UI 线程同步执行
        会冻结主桌宠（实机复现）；完成经 QTimer.singleShot 回 UI 线程复位标记。
        按用户要求去掉结果弹窗——子肥鱼消失本身就是反馈，结果写日志。
        """
        config_dir = self.config.dir

        def sweep() -> None:
            try:
                result = cleanup_slots(config_dir)
            except Exception:
                logging.exception("退出子肥鱼：文件级清理失败")
                result = {"killed_pids": [], "failed_pids": []}
            logging.info(
                "退出子肥鱼：已退出 %d 只，未能退出 %d 只",
                len(result.get("killed_pids", [])),
                len(result.get("failed_pids", [])))
            # 带 context 的 singleShot：从后台线程安全投递回 UI 线程。
            QTimer.singleShot(0, self.app, self._clear_spawned_sweep_done)

        threading.Thread(
            target=sweep, daemon=True, name="pet-clear-spawned-sweep").start()

    def _clear_spawned_sweep_done(self) -> None:
        """文件级清理完成回调（UI 线程）：复位进行中标记。"""
        self._clear_spawned_pending = False

    def spawn_in_process_window(self, offset_index: int = 1) -> PetInstance:
        """创建使用独立配置、动画库和碰撞会话的桌宠窗口。

        仅在单进程多窗模式下使用；共享服务和解码由当前 AppShell 提供。"""
        config_dir = self.config.dir
        # 单进程内 slot 语义 = 窗身份分配：不能再用跨进程文件锁做同进程竞争
        #（同一进程可再次锁住已持有的 slot-N 锁，导致两窗撞同一 slot）。先
        # 收集本进程已占用的 slot_id，再逐位申请未被占用且未被它进程持有的。
        used = {inst.slot_id for inst in self._instances}
        slot_id = None
        slot_handle = None
        candidate = 0
        # P2-1：slot 扫描加上限（max_scan_slots=128）。超限/持续失败抛
        # SlotManagerError，由 spawn_pet 的 except 捕获走 _show_startup_error，
        # 不许无限循环（持续 IO 失败 / 128 个槽全部被占时）。
        while candidate < 128:
            if candidate not in used:
                try:
                    slot_id, slot_handle = slot_manager_mod.acquire_pet_slot(
                        config_dir, preferred_slot=candidate)
                    break
                except slot_manager_mod.SlotLockError:
                    pass
            candidate += 1
        else:
            raise slot_manager_mod.SlotManagerError(
                "进程内生小肥鱼：前 128 个槽位均被占用或无法获取锁")
        instance_id = slot_manager_mod.slot_to_instance_id(slot_id)
        # 新 slot 落种：走共享落种函数。无存档 slot 按主设置落种；存在但未在该
        # 子肥鱼设置界面自定义过的 slot 按主设置刷新；已自定义（user_customized）
        # 的 slot 一个键都不碰。落种/刷新永不写位置键。
        slot_manager_mod.seed_slot_config_from_main(self.config.dir, slot_id)
        # 复用主窗同一配置根目录（AppShell.config.dir 的父目录），使所有窗的
        # config-slot-N.json 落在同一 APP_DIR_NAME 下，仅按
        # instance_id 区分；显式传 instance_id，不再依赖进程级 DSH_PET_INSTANCE。
        new_config = Config(base=self.config.dir.parent, instance_id=instance_id)
        character_id = str(new_config.get('character', catalog.DEFAULT_CHARACTER))
        inst = PetInstance(
            self, new_config,
            slot_handle=slot_handle, slot_id=slot_id, spawn_offset=offset_index,
        )
        # P1-6 移除——进程内多窗不再停用任何窗的共享解码；新窗与主窗
        # 共用同一进程级 DecodeFanoutHub（同素材首窗发布、同速窗进食）。
        # 新窗自持碰撞会话需先 start，新窗 attach 才走 QLocal 收敛。
        inst.collision_ipc.start()
        # build_tray=False：非主窗不再新建/替换进程级托盘，改由 tray_controller.refresh 刷新。
        inst._build_window(character_id, build_tray=False)
        self._instances.append(inst)
        # 硬墙钩子只在碰撞体 start 时挂过一轮：新窗补挂，否则新鱼会穿过岛。
        inst._apply_spawn_offset()
        self.tray_controller.refresh()
        # _check_autostart_wanted 逐窗（读各自 config），新窗入列后补一次。
        QTimer.singleShot(3500, inst._check_autostart_wanted)
        # N-5：msg 不手写 [slot-N] 前缀——_slot_wrap/_SlotLogFilter 会加调用方
        # 槽位前缀，叠加成双前缀纯噪音；新窗身份保留在正文里。
        logging.info("进程内新窗已创建 (slot=%s, instance=%s)", slot_id, instance_id)
        return inst

    def _on_window_exit_requested(self, instance: PetInstance,
                                  *, defer_heavy_teardown: bool = False) -> None:
        """保存位置，释放本窗资源并从实例集合中移除。

        主窗退出后提升集合中的首窗；最后一窗退出时关闭应用。
        批量清除时可把 Agent 和碰撞线程的有界 join/wait 放到后台回收队列，
        GUI 线程只处理窗口、运行标记和槽位锁，避免连续退出多只宠物时卡顿。"""
        win = instance.win
        heavy_jobs: list[tuple[str, object]] = []  # defer 模式的重回收任务
        if win is not None:
            try:
                win.save_position()
            except Exception:
                logging.exception("退出这只：保存位置失败")
            try:
                if getattr(win, 'lib', None) is not None:
                    win.lib.pause_warm()
            except Exception:
                logging.exception("退出这只：暂停预热失败")
            agent_mgr = getattr(win, 'agent_link_manager', None)
            if agent_mgr is not None:
                if defer_heavy_teardown:
                    # 摘下引用再关窗：closeEvent 也会调 shutdown()，不在 UI
                    # 线程重复 join（reaper 统一收口，shutdown 幂等）。
                    win.agent_link_manager = None
                    heavy_jobs.append(("关闭 Agent", agent_mgr.shutdown))
                else:
                    try:
                        agent_mgr.shutdown()
                    except Exception:
                        logging.exception("退出这只：关闭 Agent 失败")
        self._close_instance_subwindows(instance)
        if win is not None:
            marker_remover = getattr(win, 'remove_runtime_marker', None)
            if callable(marker_remover):
                try:
                    marker_remover()
                except Exception:
                    logging.exception("退出这只：删除 runtime 标记失败")
        if instance.slot_handle is not None:
            try:
                slot_manager_mod._unlock_file(instance.slot_handle)
            except Exception:
                pass
            instance.slot_handle = None
        # defer 模式下碰撞会话的 stop（QThread.wait 最多 3s+1s）挪到
        # reaper 线程；stop 内部对 worker 的调用是 queued 语义，线程安全。
        if defer_heavy_teardown:
            heavy_jobs.append(("停止碰撞会话", instance.collision_ipc.stop))
        else:
            try:
                instance.collision_ipc.stop()
            except Exception:
                logging.exception("退出这只：停止碰撞会话失败")
        try:
            if win is not None:
                win.close()
        except Exception:
            logging.exception("退出这只：关闭窗口失败")
        was_primary = instance is self.instance
        if instance in self._instances:
            self._instances.remove(instance)
        if was_primary:
            # P1-3：主窗退出后把列表头提升为新主窗（更新 self.instance），
            # 托盘/Dock 动作永远指向存活实例，防「复活」已退出的主窗。
            self.instance = self._instances[0] if self._instances else None
        self.tray_controller.refresh()
        if heavy_jobs:
            self._enqueue_heavy_teardown(instance, heavy_jobs)
        if not self._instances:
            # 最后一窗关闭 → 走全部退出语义（进程级共享服务收口）
            self.app.quit()

    def _teardown_reaper_queue(self) -> "queue.Queue":
        """懒创建的后台资源回收队列，串行关闭 Agent 与碰撞线程。

        仅执行线程 join/wait，不触碰 Qt 窗口；任务失败记录日志后继续。"""
        q = getattr(self, "_teardown_queue", None)
        if q is None:
            q = queue.Queue()

            def reap() -> None:
                while True:
                    jobs = q.get()
                    for label, fn in jobs:
                        try:
                            fn()
                        except Exception:
                            logging.exception("退出子肥鱼：后台重回收失败 (%s)", label)

            threading.Thread(
                target=reap, daemon=True, name="pet-teardown-reaper").start()
            self._teardown_queue = q
        return q

    def _enqueue_heavy_teardown(self, instance: PetInstance, jobs: list) -> None:
        """把一窗的重回收任务排进 reaper（幂等：同一实例只排一次）。"""
        if getattr(instance, "_heavy_teardown_enqueued", False):
            return
        instance._heavy_teardown_enqueued = True
        self._teardown_reaper_queue().put(jobs)

    def _close_instance_subwindows(self, instance: PetInstance) -> None:
        """关闭本窗的设置对话框，并释放实例对它的引用。"""
        for attr in ('modern_settings_dialog',):
            dialog = getattr(instance, attr, None)
            if dialog is None:
                continue
            try:
                dialog.close()
            except Exception:
                logging.exception("退出这只：关闭子窗失败 (%s)", attr)
            try:
                # N-4：WA_DeleteOnClose 的对话框 close() 已调度销毁，再排
                # deleteLater 会对已删 C++ 对象抛 RuntimeError（噪音）。
                if not dialog.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose):
                    QTimer.singleShot(0, dialog.deleteLater)
            except Exception:
                pass
            setattr(instance, attr, None)


    def _install_macos_dock_menu(self) -> QMenu | None:
        """Install the native Dock context menu as an independent recovery path."""
        if sys.platform != "darwin":
            self.dock_menu = None
            return None
        menu = QMenu()

        def show_pet() -> None:
            if self.instance is None:
                return
            win = self.instance.win
            if win is None:
                return
            win.show()
            win.raise_()

        # N-2：Dock 菜单只装一次，动作必须动态解析当前主窗实例——
        # 主窗经「退出这只」退掉并提升新主窗后，绑旧实例会把死窗复活。
        menu.addAction("显示桌宠", show_pet)
        menu.addAction("桌宠设置", lambda: self.instance is not None and self.instance.open_modern_settings())
        menu.addSeparator()
        quit_callback = getattr(self.app, "quit", None)
        if callable(quit_callback):
            menu.addAction("退出", quit_callback)
        install_dock_menu = getattr(menu, "setAsDockMenu", None)
        dock_menu_installed = callable(install_dock_menu)
        if dock_menu_installed:
            install_dock_menu()
        menu.setProperty("dockMenuInstalled", dock_menu_installed)
        self.dock_menu = menu
        return menu


    def open_settings_process(self, instance=None) -> bool:
        """拉起独立设置进程；True = 已交给独立进程（不得再开进程内对话框）。

        False = 开关关闭或 startDetached 失败，由调用方回退进程内设置页。
        """
        if not bool(self.config.get("settings_process_isolation", True)):
            return False
        self._install_config_watcher()
        if self._settings_process_running():
            # 单实例：已有设置进程在跑（可能不是本主进程拉起的）→ 不再拉起，
            # 但仍按"设置开着"抑制气泡并盯住它的锁文件。
            logging.info("独立设置进程已在运行，不重复拉起")
            self._mark_settings_child(True)
            return True
        if self._settings_launch_pending():
            # 刚拉起、子进程还没来得及建锁：连点场景视为已在启动，避免双开。
            self._mark_settings_child(True)
            return True
        if not self._launch_settings_process(instance):
            return False
        self._settings_launch_at = time.monotonic()
        self._mark_settings_child(True)
        return True

    def _settings_process_running(self) -> bool:
        """settings.lock 是否被活着的设置进程持有。

        QLockFile 会把「pid 已死」的残留锁判为陈旧并接管，因此设置进程崩溃
        残留的锁文件不会永久堵住设置入口。
        """
        from PySide6.QtCore import QLockFile

        lock_path = self.config.dir / "settings.lock"
        lock = QLockFile(str(lock_path))
        lock.setStaleLockTime(30000)
        try:
            if lock.tryLock(0):
                lock.unlock()
                return False
        except Exception:
            logging.exception("探测设置进程锁失败")
            return True  # 探测异常按"已在运行"保守处理，宁可不开第二份
        if not lock_path.exists():
            # 拿不到锁但锁文件并不存在 = 目录不可写之类的环境错误，不是"已有设置
            # 进程"；否则用户会彻底打不开设置页。
            logging.warning("设置进程锁探测失败且锁文件不存在：%s", lock_path)
            return False
        return True

    def _settings_launch_pending(self) -> bool:
        """刚拉起独立设置进程的启动窗口（子进程建锁前的连点保护）。"""
        started = float(getattr(self, "_settings_launch_at", 0.0) or 0.0)
        return bool(started) and (time.monotonic() - started) <= 5.0

    def _launch_settings_process(self, instance=None) -> bool:
        """startDetached 独立设置进程；冻结包与源码运行分流。

        源码运行要走 `-m pet`（工作目录取仓库根），冻结包直接复用 exe 的参数
        分流入口（--settings）——与 --uninstall-cleanup 同一范式。
        """
        from PySide6.QtCore import QProcess

        if getattr(sys, "frozen", False):
            program = sys.executable
            arguments = ["--settings"]
            workdir = str(Path(sys.executable).parent)
        else:
            program = sys.executable
            arguments = ["-m", "pet", "--settings"]
            workdir = str(Path(__file__).resolve().parent.parent)
        if not program:
            logging.warning("sys.executable 为空，无法拉起独立设置进程")
            return False
        instance_id = str(getattr(getattr(instance, "config", None), "instance_id", "") or "")
        if instance_id and instance_id != (os.environ.get("DSH_PET_INSTANCE") or "").strip():
            # 进程内多窗（experimental_single_process_spawn）下第二窗的 instance_id
            # 不等于进程级 env：显式传参，否则独立设置进程会打开主窗的配置。
            # 主窗/独立槽位进程 env 已一致，命令保持 ["--settings"] 原样。
            arguments += ["--instance", instance_id]
        try:
            started, _pid = QProcess.startDetached(program, arguments, workdir)
        except Exception:
            logging.exception("拉起独立设置进程异常")
            return False
        if not started:
            logging.warning("startDetached 未启动独立设置进程，回退进程内设置页")
        return bool(started)

    def _mark_settings_child(self, active: bool) -> None:
        """记录独立设置进程存活态，并同步各窗气泡抑制与存活轮询。"""
        self._settings_child_active = bool(active)
        timer = getattr(self, "_settings_watch_timer", None)
        if timer is not None:
            if active:
                if not timer.isActive():
                    timer.start()
            else:
                self._settings_launch_at = 0.0
                timer.stop()
        for inst in getattr(self, "_instances", []):
            update = getattr(inst, "_update_bubble_suppression_for_settings", None)
            if not callable(update):
                continue
            try:
                update()
            except Exception:
                logging.exception("同步设置期气泡抑制状态失败")

    def _poll_settings_process(self) -> None:
        """设置进程存活轮询：崩溃/漏事件时兜底解除气泡抑制。"""
        if not bool(getattr(self, "_settings_child_active", False)):
            return
        if self._settings_process_running():
            # 子进程已建锁 = 启动窗口结束：此后锁一消失就可立即解除抑制。
            self._settings_launch_at = 0.0
            return
        if self._settings_launch_pending():
            return
        self._mark_settings_child(False)

    def _install_config_watcher(self) -> None:
        """盯 config.json 所在目录 + 文件，把外部写盘合并进运行期（幂等）。

        盯目录而不是只盯文件：config.save() 用 os.replace 落盘会换 inode，
        QFileSystemWatcher 对消失的路径会停止监视，只盯文件必丢后续事件。
        目录信号不带文件名，故 basename 过滤交给 fileChanged（带路径），
        目录信号负责换 inode 后重新 addPath、以及 settings.lock 出现/消失。
        300ms 去抖：一次保存可能伴随目录多次变动。进程内保存同样触发——
        去抖窗口内合并即可；finished 路径不改成走 watcher，保持原时序语义。
        """
        if getattr(self, "_config_watcher", None) is not None:
            return
        if not bool(self.config.get("settings_process_isolation", True)):
            return
        from PySide6.QtCore import QFileSystemWatcher, QTimer

        try:
            self.config.dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logging.warning("配置目录不可创建，跳过 config 变更监视：%s", self.config.dir)
            return
        watcher = QFileSystemWatcher()
        watcher.directoryChanged.connect(self._on_config_dir_changed)
        watcher.fileChanged.connect(self._on_config_file_changed)
        if not watcher.addPath(str(self.config.dir)):
            logging.warning("无法监视配置目录：%s", self.config.dir)
            return
        self._config_watcher = watcher
        self._last_config_signature = self._config_signature()
        self._config_reload_timer = QTimer()
        self._config_reload_timer.setSingleShot(True)
        self._config_reload_timer.setInterval(300)
        self._config_reload_timer.timeout.connect(self._on_config_change_debounced)
        self._settings_watch_timer = QTimer()
        self._settings_watch_timer.setInterval(3000)
        self._settings_watch_timer.timeout.connect(self._poll_settings_process)
        self._watch_config_file()

    def _watch_config_file(self) -> None:
        """确保 config.json 在监视列表里（os.replace 换 inode 后被 Qt 自动移除）。"""
        watcher = getattr(self, "_config_watcher", None)
        if watcher is None:
            return
        try:
            path = str(self.config.path)
            if self.config.path.exists() and path not in watcher.files():
                watcher.addPath(path)
        except OSError:
            pass

    def _config_signature(self):
        """(mtime_ns, size) 签名：目录信号不带文件名，用它兜底判断 config 是否变了。"""
        try:
            stat = self.config.path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _arm_config_reload(self) -> None:
        """重启去抖窗口：窗口内的多次变动合并成一次 reload+应用。"""
        timer = getattr(self, "_config_reload_timer", None)
        if timer is not None:
            timer.start()

    def _on_config_file_changed(self, path: str) -> None:
        if Path(path).name != self.config.path.name:
            return  # 只认本配置文件的 basename（同目录还有 settings.lock 等）
        self._watch_config_file()
        self._arm_config_reload()

    def _on_config_dir_changed(self, path: str) -> None:
        self._watch_config_file()
        if self._config_signature() != getattr(self, "_last_config_signature", None):
            self._arm_config_reload()
        # 锁文件出现 = 设置进程已起来（启动窗口结束）；锁文件消失 = 设置进程
        # 退出（QLockFile 解锁即删文件）→ 立即解除气泡抑制。
        lock_path = self.config.dir / "settings.lock"
        if lock_path.exists():
            self._settings_launch_at = 0.0
        elif (bool(getattr(self, "_settings_child_active", False))
                and not self._settings_launch_pending()):
            self._mark_settings_child(False)

    def _on_config_change_debounced(self) -> None:
        self.config.reload()
        try:
            self._apply_external_config_change()
        except Exception:
            logging.exception("应用外部配置变更失败")
        finally:
            self._last_config_signature = self._config_signature()

    def _teardown_config_watcher(self) -> None:
        """释放 watcher 与两个定时器（退出/测试收口共用）。"""
        watcher = getattr(self, "_config_watcher", None)
        if watcher is not None:
            for signal, slot in (
                (watcher.directoryChanged, self._on_config_dir_changed),
                (watcher.fileChanged, self._on_config_file_changed),
            ):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
            self._config_watcher = None
        for name in ("_config_reload_timer", "_settings_watch_timer"):
            timer = getattr(self, name, None)
            if timer is None:
                continue
            try:
                timer.stop()
            except RuntimeError:
                pass

    def start(self) -> None:
        # aboutToQuit 只在控制器层绑定一次：角色热切换会重建窗口，逐个
        # connect win.save_position 会在旧窗口延迟销毁后残留失效引用。
        # 统一走 _on_about_to_quit，在信号触发时读取当前有效窗口。
        if not self._on_about_to_quit_connected:
            self.app.aboutToQuit.connect(self._on_about_to_quit)
            self._on_about_to_quit_connected = True
        self.instance.collision_ipc.start()
        character_id = str(self.config.get('character', catalog.DEFAULT_CHARACTER))
        logging.info('当前形象: %s', character_id)
        self._create_ui_with_character_fallback(character_id)
        # 进程级共享全屏 watcher 在主窗就绪后启动（自省任一窗是否需要，
        # 无需窗——环则空转）；flag 关时 _shared 为 None，no-op。
        if self._shared is not None:
            self._shared.start()
        self._install_macos_dock_menu()
        self.instance._apply_spawn_offset()
        # 设置页进程隔离：启动即装 config 目录 watcher，独立设置进程落盘后由它
        # 合并进运行期（开关关闭时不装，完全走旧路径）。
        self._install_config_watcher()
        QTimer.singleShot(3500, self.instance._check_autostart_wanted)
        # 会话结束（Windows 关机/注销）探测器。必须在窗口就绪后安装
        # ——它要在关机窗口期到来**之前**就位，才能抢在会话拆除前关掉 ffmpeg
        # 派生（否则系统会弹 0xc0000142 阻塞关机）。
        self._install_session_watcher()


def _mac_set_dock_icon_visible(visible: bool) -> None:
    """Switch the macOS application policy without restarting the pet.

    The speech bubble itself owns the non-activating window flags; application
    activation policy must not be used as a focus workaround because Accessory
    Regular (0) displays a Dock item; Accessory (1) keeps the application out
    of the Dock. Pet tool windows own their independent visibility/focus flags.
    """
    if sys.platform != 'darwin':
        return
    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc') or '/usr/lib/libobjc.A.dylib')
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.objc_getClass.restype = ctypes.c_void_p
        msg = objc.objc_msgSend
        msg.restype = ctypes.c_void_p
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        shared = msg(
            objc.objc_getClass(b'NSApplication'),
            objc.sel_registerName(b'sharedApplication'),
        )
        # NSApplicationActivationPolicyRegular = 0; Accessory = 1
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        msg(shared, objc.sel_registerName(b'setActivationPolicy:'), 0 if visible else 1)
    except Exception:
        pass


def _default_xcb_platform_on_wayland() -> None:
    """Linux Wayland 会话下把 Qt 平台插件默认设为 xcb（XWayland）。

    Wayland 协议不允许客户端自行移动顶层窗口，桌宠拖动依赖的
    QWidget.move() 会被合成器静默忽略（表现为无法拖动）；透明无边框
    窗口在原生 wayland 插件下还存在重绘残留（拖影）。须在创建
    QApplication 之前调用。用户显式设置 QT_QPA_PLATFORM 时尊重其选择。
    """
    if not sys.platform.startswith("linux"):
        return
    if "QT_QPA_PLATFORM" in os.environ:
        return
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def _configure_linux_fcitx_input_method() -> None:
    """为 PySide6 冻结版选择与内置 Qt ABI 兼容的 Fcitx 输入法前端。"""
    # Linux 成品随包携带按 PySide6 Qt ABI 编译的 Fcitx 插件；未指定时默认选中 fcitx 上下文。
    if not sys.platform.startswith("linux"):
        return
    if os.environ.get("XMODIFIERS", "").strip() != "@im=fcitx":
        return
    if not os.environ.get("QT_IM_MODULE", "").strip():
        os.environ["QT_IM_MODULE"] = "fcitx"


# Historical public name retained for integrations and older tests.
PetApp = AppShell


def main(argv: list[str] | None = None) -> int:
    _default_xcb_platform_on_wayland()
    # 必须在 QApplication 构造前设置，Qt 才会按随包 Fcitx 插件创建输入法上下文。
    _configure_linux_fcitx_input_method()
    argv = list(argv if argv is not None else sys.argv)
    preferred_slot = None

    if "--slot" in argv:
        index = argv.index("--slot")
        if index + 1 < len(argv):
            try:
                preferred_slot = int(argv[index + 1])
                if preferred_slot < 0 or preferred_slot > 127:
                    logging.error("无效的 --slot 参数 (必须在 0~127 范围内): %s", argv[index + 1])
                    return 1
            except ValueError:
                logging.error("无效的 --slot 参数: %s", argv[index + 1])
                return 1
        else:
            logging.error("缺少 --slot 参数值")
            return 1

    app = QApplication(argv)
    app.setApplicationName(APP_DIR_NAME)
    app.setApplicationDisplayName("鲸鱼娘")
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / "assets" / "icon.ico")))
    app.setQuitOnLastWindowClosed(False)

    # 确定配置根目录
    config_dir = _default_base() / APP_DIR_NAME

    # 执行槽位竞争取得排他锁
    slot_handle = None
    slot_id = None

    try:
        try:
            slot_id, slot_handle = slot_manager_mod.acquire_pet_slot(config_dir, preferred_slot=preferred_slot)
        except Exception as exc:
            logging.exception("获取桌宠槽位锁失败")
            _show_startup_error("dsh-pet-standalone", str(exc))
            return 1

        instance_id = slot_manager_mod.slot_to_instance_id(slot_id)
        os.environ["DSH_PET_INSTANCE"] = instance_id

        # 迁移旧 spawn 实例（主槽或无并发运行旧实例时触发）
        if slot_id == 0:
            slot_manager_mod.migrate_legacy_spawns(config_dir)

        # 新 slot 落种：走共享落种函数。无存档 slot 按主设置落种；存在但未在该
        # 子肥鱼设置界面自定义过的 slot 按主设置刷新；已自定义（user_customized）
        # 的 slot 一个键都不碰。落种/刷新永不写位置键。
        slot_manager_mod.seed_slot_config_from_main(config_dir, slot_id)

        config = Config(instance_id=instance_id)
        _mac_set_dock_icon_visible(bool(config.get("show_dock_icon", True)))
        _setup_logging(config)

        logging.info("dsh-pet-standalone 启动 (slot: %s, instance: %s)", slot_id, instance_id)
        threading.Thread(target=_cleanup_stale_runtime_dirs, daemon=True).start()
        stale_removed = autostart_mod.cleanup_stale_entries()
        if stale_removed:
            logging.info("已清理 %d 个指向不存在路径的开机自启项", stale_removed)

        controller = AppShell(app, config, slot_handle=slot_handle, slot_id=slot_id,
                              spawn_offset=_read_spawn_offset_env())
        try:
            controller.start()
        except Exception as exc:
            logging.exception("启动失败")
            _show_startup_error("dsh-pet-standalone", str(exc))
            return 1

        logging.info("进入事件循环")
        return app.exec()
    finally:
        if slot_handle is not None:
            try:
                slot_manager_mod._unlock_file(slot_handle)
            except Exception:
                pass
            slot_handle = None


if __name__ == '__main__':
    sys.exit(main())
