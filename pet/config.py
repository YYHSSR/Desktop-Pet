# -*- coding: utf-8 -*-
"""配置读取与持久化；迁移退役设置并保留桌宠与工作状态偏好。"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import catalog
from .report_gates import (
    LEGACY_PERCENT_GATES,
    LEGACY_SWITCH_GATES,
    REPORT_GATE_DEFAULTS,
    clean_report_gates,
)


DEFAULT_ANIMATION_GAP_SECONDS = 0.0
DEFAULT_SELF_TALK_MIN_INTERVAL = 20.0
DEFAULT_SELF_TALK_MAX_INTERVAL = 60.0
DEFAULT_SELF_TALK_DURATION_SECONDS = 3.2
DEFAULT_SELF_TALK_TEXTS = json.loads((Path(__file__).with_name("persona_presets") / "self_talk.json").read_text(encoding="utf-8"))
DEFAULT_SELF_TALK_BUBBLE_STYLE = "classic_top"
# 自言自语出图概率（百分比 0~100）：先决定"这次出图还是出文本"，再在对应池里等权
# 抽一条。默认 30%——图片目录常有几十张图，若与文本等权随机会让图片彻底压过文本
# （实测某配置 24 图 + 5 句 → 出图 82.8%，点击几乎总是弹图）。
DEFAULT_SELF_TALK_IMAGE_CHANCE = 30
DEFAULT_DIALOGUE_PHRASES = {}
DEFAULT_COLLISION_SETTINGS = {
    "collision_enabled": True,
    "collision_restitution": 0.82,
    "collision_friction": 0.08,
    "collision_mass_scale": 1.0,
    "collision_impulse_cap": 9000.0,
}
SELF_TALK_BUBBLE_STYLES = {
    "classic_top",
    "paper_left",
    "glass_right",
    "soft_blue_top",
    "breath_bubble",
}
DEFAULT_CONTEXT_MENU_APPEARANCE = {
    "theme": "system",
    "density": "standard",
    "corner_radius": 12,
    "ui_font": "system",
    "ui_font_size": 13,
    "translucent": True,
    "opacity": 0.94,
    "light_background": "#ffffff",
    "light_foreground": "#171717",
    "light_hover": "#eeeeee",
    "dark_background": "#252525",
    "dark_foreground": "#f3f3f3",
    "dark_hover": "#3a3a3a",
}
DEFAULT_QUICK_LAUNCH_APPS = []
DEFAULT_QUICK_URLS = []


def _clean_color(value, default):
    value = str(value or "").strip()
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value.lower()
        except ValueError:
            pass
    return default


def _clean_menu_appearance(value):
    value = value if isinstance(value, dict) else {}
    defaults = DEFAULT_CONTEXT_MENU_APPEARANCE
    theme = str(value.get("theme", "system"))
    density = str(value.get("density", "standard"))
    try:
        radius = int(value.get("corner_radius", 12))
    except (TypeError, ValueError):
        radius = 12
    try:
        font_size = int(value.get("ui_font_size", 13))
    except (TypeError, ValueError):
        font_size = 13
    result = {
        "theme": theme if theme in {"system", "light", "dark"} else "system",
        "density": density if density in {"compact", "standard", "spacious"} else "standard",
        "corner_radius": max(6, min(18, radius)),
        "ui_font": str(value.get("ui_font") or "system")[:80],
        "ui_font_size": max(10, min(18, font_size)),
        "translucent": bool(value.get("translucent", True)),
        "opacity": _float_or_default(value.get("opacity"), 0.94, 0.72, 1.0),
    }
    for key in (
        "light_background",
        "light_foreground",
        "light_hover",
        "dark_background",
        "dark_foreground",
        "dark_hover",
    ):
        result[key] = _clean_color(value.get(key), defaults[key])
    return result


_RETIRED_BALANCE_KEYS = frozenset({
    "agent_cost_enabled", "click_show_balance", "balance_refresh_minutes",
    "balance_tier_labels_mode", "balance_tier_label_peak", "balance_tier_label_idle",
    "balance_tier_color_enabled",
})


def _clean_quick_launch_apps(value):
    if not isinstance(value, list):
        return [dict(item) for item in DEFAULT_QUICK_LAUNCH_APPS]
    cleaned = []
    for item in value[:20]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "application")
        path = str(item.get("path") or "").strip()
        name = str(item.get("name") or "").strip()[:60]
        if kind == "application" and path and name:
            cleaned.append({"name": name, "path": path, "kind": "application"})
    return cleaned


def _clean_quick_urls(value):
    if not isinstance(value, list):
        return [dict(item) for item in DEFAULT_QUICK_URLS]
    cleaned = []
    for item in value[:30]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        name = str(item.get("name") or "").strip()[:60]
        if url and name:
            cleaned.append({"name": name, "url": url})
    return cleaned


def _default_agent_link_data() -> dict:
    return {
        "codex": False,
        "cursor": False,
        # 自定义联动 Agent（协议见 README 的“自定义联动事件”）：只读监听
        # 用户指定的事件文件，不写外部配置、无需授权弹窗，默认空
        "custom_agents": [],
        # 事件气泡触发概率（默认值见 pet/report_gates.py）：设置页把它们收进
        # 「自动化与联动 → 事件气泡触发概率」下的可折叠框，按事件聚合类别逐类调。
        # 值是**通过概率** 0.00–1.00（0 = 该类完全不汇报，1 = 全部汇报），没有布尔开关。
        "report_gates": dict(REPORT_GATE_DEFAULTS),
        # 卡住检测（默认开）：有工具结果事件时，根据工具成败/超时/错误
        # 推断「Agent 钻牛角尖了」，档位 1 播焦急动画、档位 2 弹持续提醒气泡。
        "stuck_detect": True,
        "stuck_worried_threshold": 3,
        "stuck_intervene_threshold": 5,
        "stuck_window_seconds": 90,
        "stuck_cooldown_seconds": 300,
        "stuck_reminder_text": "",
        "exploration_watchdog_enabled": True,
        "exploration_watchdog_warning_threshold": 3,
        "exploration_watchdog_control_threshold": 5,
        "exploration_watchdog_cooldown_steps": 3,
        "exploration_watchdog_early_grace_minutes": 5,
        "exploration_watchdog_long_run_minutes": 10,
        "exploration_watchdog_long_think_seconds": 120,
    }


# 内置联动 Agent 键：custom_agents 的 key 不得与之重复
_AGENT_LINK_BUILTIN_KEYS = ("codex", "cursor")
# 自定义联动 Agent 条目上限（防配置文件被塞爆）
_CUSTOM_AGENT_MAX = 8


def _clean_custom_agents(raw: Any) -> list[dict]:
    """清洗自定义联动 Agent 列表（agent_link.custom_agents）。

    条目 {key, name, path}：key 为小写标识（不得与内置键/其他条目重复），
    name 为显示名（缺省用 key），path 为事件文件路径（支持 ~，允许暂不存在）。
    非法条目直接丢弃，超出上限截断。"""
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if len(result) >= _CUSTOM_AGENT_MAX:
            break
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", key):
            continue
        if key in _AGENT_LINK_BUILTIN_KEYS or key in seen:
            continue
        path = str(item.get("path") or "").strip()[:500]
        if not path:
            continue
        name = str(item.get("name") or "").strip()[:50] or key
        seen.add(key)
        result.append({"key": key, "name": name, "path": path})
    return result


def _clean_agent_link_data(raw: Any) -> dict:
    defaults = _default_agent_link_data()
    if not isinstance(raw, dict):
        return dict(defaults)
    result = dict(defaults)
    # 保留传入的额外合法键（例如 thinking_text, thinking_texts 等）
    custom = _clean_custom_agents(raw.get("custom_agents"))
    allowed = set(defaults) | {"thinking_text", "thinking_texts"} | {item["key"] for item in custom}
    result.update({key: value for key, value in raw.items() if key in allowed})
    result["custom_agents"] = _clean_custom_agents(raw.get("custom_agents"))
    for key in (
        "codex",
        "cursor",
    ):
        if key in raw:
            result[key] = _bool_or_default(raw[key], defaults[key])
    # 事件汇报概率门：新形状（report_gates 字典）优先；旧键一次性迁移——
    # 布尔开关 → 1.0/0.0，旧百分比 report_probability(0-100) → activity 概率。
    # 迁移后**不再写出旧键**，配置里不留兼容别名（用户可编辑文案的键名另见
    # persona_presets/ 中的预设结构）。
    raw_gates = raw.get("report_gates")
    gates = clean_report_gates(raw_gates)
    if not isinstance(raw_gates, dict):
        for legacy_key, gate in LEGACY_SWITCH_GATES.items():
            if legacy_key in raw:
                gates[gate] = 1.0 if bool(raw[legacy_key]) else 0.0
        for legacy_key, gate in LEGACY_PERCENT_GATES.items():
            if legacy_key in raw:
                percent = _float_or_default(raw.get(legacy_key), REPORT_GATE_DEFAULTS[gate] * 100.0, 0.0, 100.0)
                gates[gate] = min(1.0, max(0.0, percent / 100.0))
    result["report_gates"] = gates
    for legacy_key in (*LEGACY_SWITCH_GATES, *LEGACY_PERCENT_GATES):
        result.pop(legacy_key, None)
    return result


def _merge_agent_link_data(raw: Any) -> dict:
    return _clean_agent_link_data(raw)


def _default_base():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home())
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path.home() / ".config"


def _app_dir_name() -> str:
    """打包变体的独立数据目录名；源码运行时回退到共享目录。

    构建脚本（scripts/build_onedir.ps1）会在打包前生成
    build-onedir/build_variant.py（VARIANT = "webm-chat" 等），
    使 Chat / 无 Chat 等变体各自使用独立的配置目录、会话与自启项。
    """
    try:
        from build_variant import VARIANT  # 仅打包产物中存在

        name = str(VARIANT).strip()
        if name:
            return f"dsh-pet-standalone-{name}"
    except Exception:
        pass
    return "dsh-pet-standalone"


APP_DIR_NAME = _app_dir_name()


def _float_or_default(value, default, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        # OverflowError：json.loads 会把超长整数字面量解析成 Python int，
        # float(10**400) 直接抛——不接住就是 Config() 构造失败、启动崩。
        return default
    return max(minimum, min(maximum, number))


def _bool_or_default(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return bool(default)


def _clean_self_talk_texts(value):
    if not isinstance(value, list):
        return list(DEFAULT_SELF_TALK_TEXTS)
    texts = []
    for item in value:
        text = str(item).strip()
        if text and text not in texts:
            texts.append(text[:120])
    return texts or list(DEFAULT_SELF_TALK_TEXTS)


def _clean_character_profiles(value) -> dict:
    """角色档案：当前先承载 click_talk_bindings，后续可扩展头像/人设字段。"""
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for character_id, profile in value.items():
        if not isinstance(profile, dict):
            continue
        bindings_raw = profile.get("click_talk_bindings")
        bindings = {}
        if isinstance(bindings_raw, dict):
            for action_id, texts in bindings_raw.items():
                if not isinstance(texts, list):
                    continue
                items = []
                for item in texts:
                    text = str(item).strip()
                    if text and text not in items:
                        items.append(text[:120])
                if items:
                    bindings[str(action_id)] = items
        entry = dict(profile)
        entry["click_talk_bindings"] = bindings
        cleaned[str(character_id)] = entry
    return cleaned


def _clean_collision_data(value: dict) -> dict:
    """归一化碰撞开关、恢复系数、摩擦、质量缩放和冲量上限。"""
    result = dict(value)
    result["collision_enabled"] = _bool_or_default(value.get("collision_enabled"), True)
    result["collision_restitution"] = _float_or_default(value.get("collision_restitution"), 0.82, 0.0, 1.0)
    result["collision_friction"] = _float_or_default(value.get("collision_friction"), 0.08, 0.0, 0.30)
    result["collision_mass_scale"] = _float_or_default(value.get("collision_mass_scale"), 1.0, 0.5, 2.0)
    result["collision_impulse_cap"] = _float_or_default(value.get("collision_impulse_cap"), 9000.0, 1000.0, 12000.0)
    return result


@contextmanager
def _config_file_lock(lock_path: Path, timeout: float = 1.0):
    """跨进程排他文件锁上下文管理器（F02），保护配置读-合-写原子临界区。"""
    try:
        import msvcrt
    except ImportError:
        msvcrt = None
    try:
        import fcntl
    except ImportError:
        fcntl = None

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fh = open(lock_path, "a+b")
    except OSError:
        yield False
        return

    deadline = time.monotonic() + max(0.01, timeout)
    acquired = False
    try:
        while True:
            fileno = fh.fileno()
            if msvcrt is not None:
                try:
                    fh.seek(0)
                    msvcrt.locking(fileno, msvcrt.LK_NBLCK, 1)
                    acquired = True
                    break
                except (OSError, IOError):
                    pass
            elif fcntl is not None:
                try:
                    fh.seek(0)
                    fcntl.flock(fileno, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except (BlockingIOError, OSError, IOError):
                    pass
            else:
                acquired = True
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        yield acquired
    finally:
        if acquired:
            try:
                fileno = fh.fileno()
                if msvcrt is not None:
                    fh.seek(0)
                    msvcrt.locking(fileno, msvcrt.LK_UNLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(fileno, fcntl.LOCK_UN)
            except Exception:
                pass
        try:
            fh.close()
        except Exception:
            pass


class Config:
    def __init__(self, base=None, instance_id: str | None = None):
        base = Path(base) if isinstance(base, str) else (base or _default_base())
        self.dir = base / APP_DIR_NAME
        # 多开隔离：--instance <id> 或 DSH_PET_INSTANCE 时使用独立配置文件，
        # 位置/大小/朝向等不再互相覆盖；不传时完全保持原行为。
        self.instance_id = (instance_id or os.environ.get("DSH_PET_INSTANCE", "") or "").strip()
        self.path = self.dir / f"config-{self.instance_id}.json" if self.instance_id else self.dir / "config.json"
        self._modified_keys: set[str] = set()
        self._migrate_legacy_config(base)
        # 副槽落种仅在该槽位还没有个体配置时进行；已有存档的 slot（用户改过
        # 的）一律不动——「生小肥鱼」复用旧槽位时同样保留原槽设置。
        if self.instance_id and not self.path.exists():
            self._seed_slot_config_from_main()
        self.data = {
            "version": 4,
            "rx": None,
            "ry": None,
            "screen_name": None,
            "facing": "left",
            "scale": catalog.DEFAULT_SCALE,
            "spawn_inherit_size": True,  # 生小肥鱼继承主肥鱼大小（False 用 spawn_scale）
            "spawn_scale": catalog.DEFAULT_SCALE,  # 关闭继承时生小肥鱼使用的尺寸
            "user_customized": False,  # 仅当用户在该子肥鱼自己的设置界面保存过才置真
            "on_top": True,
            "show_dock_icon": True,
            "no_move": False,
            "character": catalog.DEFAULT_CHARACTER,
            "playback_speed": 1.0,
            "animation_gap_seconds": DEFAULT_ANIMATION_GAP_SECONDS,
            "self_talk_enabled": False,
            "self_talk_min_interval": DEFAULT_SELF_TALK_MIN_INTERVAL,
            "self_talk_max_interval": DEFAULT_SELF_TALK_MAX_INTERVAL,
            "self_talk_duration_seconds": DEFAULT_SELF_TALK_DURATION_SECONDS,
            "self_talk_image_scale": 100,  # 气泡配图显示尺寸百分比（50~300，100 = 默认）
            "self_talk_image_chance": DEFAULT_SELF_TALK_IMAGE_CHANCE,  # 出图概率百分比（0~100）
            "bubble_text_scale": 100,  # 气泡文字显示尺寸百分比（50~300，100 = 默认；气泡与字号一起放大）
            "self_talk_texts": list(DEFAULT_SELF_TALK_TEXTS),
            "self_talk_image_dir": "assets/big_blue_fat_fish",
            "self_talk_bubble_style": DEFAULT_SELF_TALK_BUBBLE_STYLE,
            # Existing event wording: legacy is deliberately the default.
            "dialogue_mode": "legacy",
            "dialogue_phrases": dict(DEFAULT_DIALOGUE_PHRASES),
            "dialogue_last_scope": "",  # 台词编辑上次打开的层（""=全局；设置页专属文案入口记忆）
            "mouse_through": False,
            "cursor_hidden_passthrough": True,
            "drag_physics": False,
            "lock_position": False,  # 锁定位置：桌宠不可拖动（点击仍有效）
            "shift_drag": False,  # 按住 SHIFT+左键才能拖动
            "pet_opacity": 100,  # 桌宠窗口不透明度 10-100
            "context_menu_appearance": dict(DEFAULT_CONTEXT_MENU_APPEARANCE),
            "quick_launch_apps": [dict(item) for item in DEFAULT_QUICK_LAUNCH_APPS],
            "quick_urls": [dict(item) for item in DEFAULT_QUICK_URLS],
            "auto_hide_fullscreen": True,  # 全屏应用自动隐藏（Windows）
            "slingshot_enabled": True,  # 弹弓弹射
            "throw_strength": "standard",  # gentle / standard / strong / crazy
            "click_show_self_talk": False,  # 点击反馈气泡默认关闭
            "golden_spin_on_click": False,  # 点击回应动画结束后自动接一段黄金回旋
            "golden_spin_direct": False,  # 点击触发黄金回旋时跳过点击动画，直接回旋并逐圈加速
            "edge_probe_enabled": False,  # 拖到屏幕左右边缘后自动进入探头姿态
            "autostart_wanted": False,  # 用户曾开启过开机自启（用于启动自检：被安全软件清理时提醒）
            "stream_capture_mode": False,  # 直播捕获兼容模式（Windows：Tool 窗口直播姬/OBS 枚举不到）
            "character_aliases": {},  # 角色显示名别名 {角色id: 自定义名}，空名=恢复默认
            "character_profiles": {},  # 角色档案：{角色id: {click_talk_bindings: {动画id: [台词]}}}
            "agent_link": _default_agent_link_data(),
            **DEFAULT_COLLISION_SETTINGS,
            "media_prewarm": "balanced",  # full / balanced / minimal 素材首帧预热力度
            # 默认 32→8MB。预测式预热落地后，首帧 LRU 只需
            # 装「瞬时交互核 pinned（click/turn/drag）+ 1-2 个预测位」；idle/move
            # 由预测机制与 LRU 热度自然覆盖，不再常驻。
            "first_frame_cache_max_mb": 8,  # 首帧缓存全局预算（MB），低配机可调小
            # 当前动画墙钟剩余 ≤ 该提前量（毫秒）时，
            # 帧驱动提前掷骰决定下一动画并在后台预解码其首帧进 LRU（Phase 1）。
            "predict_prewarm_lead_ms": 350,  # 提前量（ms），范围 200-600
            # ffmpeg 圈边界定期回收阈值（分钟）。长寿循环 reader 在圈
            # 边界驻留时按进程存活时长评估回收：达到该值 → 不 park/re-arm，正常
            # 退出杀进程、下一次 start() 自然 fresh spawn（把 47→64MB 的 ffmpeg
            # 内部累积周期性清零）。0 = 关闭回收（回退保险）；否则范围 [2, 120]。
            "ffmpeg_recycle_minutes": 10,
            # 开 = 「生小肥鱼」从 spawn 新进程改为进程内
            # 创建第二个 PetInstance。关 = 行为与现状逐位一致（回退保险）。
            "experimental_single_process_spawn": False,
            # 同角色共享解码链（进程内帧扇出）开关，默认开。仅当
            # experimental_single_process_spawn（多窗）也为开时才真正激活——
            # 单窗无共享可言，双门关任一即回每窗独立解码。
            "experimental_shared_decode": True,
            # 设置页进程隔离：默认开 = 设置页拉到独立进程（--settings），关窗即
            # 进程退出，OS 连锅端走首开留下的字体/样式/模块高水位（无卸载 API）；
            # False = 完全回退进程内对话框旧路径（排障/回退保险，不新增控件）。
            "settings_process_isolation": True,
        }
        self.reload()
        self._clean_retired_data(self.data)
        self._normalize_pet_settings()

    def _migrate_legacy_config(self, base) -> None:
        """首次使用变体独立目录时复制旧版配置，已有配置保持不变。"""
        if self.instance_id:
            return  # 多开实例不参与旧版迁移，避免把单开配置复制给每个实例
        if APP_DIR_NAME == "dsh-pet-standalone" or self.path.exists():
            return
        legacy = base / "dsh-pet-standalone"
        if not (legacy / "config.json").is_file():
            return
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy / "config.json", self.path)
        except OSError:
            pass

    def _seed_slot_config_from_main(self) -> None:
        """新建副槽时继承主配置（）：委托 slot_manager 的共享落种函数。

        只在该槽位还没有个体配置文件时执行；已有存档的 slot-N 配置（用户改过
        的）一律保持独立记忆，「生小肥鱼」复用旧槽位也不覆盖。副本生成逻辑
        （spawn_inherit_size / spawn_scale、位置键
        剔除、脱敏、user_customized 置假）统一收敛在
        ``slot_manager.seed_slot_config_from_main``，这里只负责把 instance_id
        解析成 slot_id 后转发。
        """
        if not self.instance_id:
            return
        if not self.instance_id.startswith("slot-"):
            return
        suffix = self.instance_id[len("slot-") :]
        if not suffix.isdigit():
            # 非数值 slot 标识（如碰撞 IPC 测试用 slot-a/slot-p）不做落种。
            return
        slot_id = int(suffix)
        from . import slot_manager as slot_manager_mod

        slot_manager_mod.seed_slot_config_from_main(self.dir, slot_id)

    def reload(self):
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            from . import slot_manager as slot_manager_mod

            slot_manager_mod.backup_corrupt_config(self.path)
            return
        if not isinstance(raw, dict):
            from . import slot_manager as slot_manager_mod

            slot_manager_mod.backup_corrupt_config(self.path)
            return
        self._clean_retired_data(raw)
        try:
            old_version = int(raw.get("version", 1) or 1)
        except (TypeError, ValueError):
            old_version = 1  # 脏数据（手改/损坏）不得导致启动崩溃
        if old_version < 2:
            raw.pop("scale", None)
        for key in (
            "rx",
            "ry",
            "screen_name",
            "facing",
            "scale",
            "on_top",
            "show_dock_icon",
            "no_move",
            "character",
            "spawn_inherit_size",
            "spawn_scale",
            "user_customized",
            "playback_speed",
            "animation_gap_seconds",
            "self_talk_enabled",
            "self_talk_min_interval",
            "self_talk_max_interval",
            "self_talk_texts",
            "self_talk_duration_seconds",
            "self_talk_image_dir",
            "self_talk_image_scale",
            "self_talk_image_chance",
            "bubble_text_scale",
            "self_talk_bubble_style",
            "mouse_through",
            "cursor_hidden_passthrough",
            "drag_physics",
            "dialogue_mode",
            "dialogue_phrases",
            "dialogue_last_scope",
            "lock_position",
            "shift_drag",
            "pet_opacity",
            "context_menu_appearance",
            "quick_launch_apps",
            "quick_urls",
            "auto_hide_fullscreen",
            "slingshot_enabled",
            "throw_strength",
            "click_show_self_talk",
            "autostart_wanted",
            "stream_capture_mode",
            "golden_spin_on_click",
            "golden_spin_direct",
            "edge_probe_enabled",
            "character_aliases",
            "character_profiles",
            "collision_enabled",
            "collision_restitution",
            "collision_friction",
            "collision_mass_scale",
            "collision_impulse_cap",
            "media_prewarm",
            "first_frame_cache_max_mb",
            "predict_prewarm_lead_ms",
            "ffmpeg_recycle_minutes",
            "experimental_single_process_spawn",
            "experimental_shared_decode",
            "settings_process_isolation",
        ):
            if key in raw and raw[key] is not None:
                self.data[key] = raw[key]
        if "agent_link" in raw:
            self.data["agent_link"] = _merge_agent_link_data(raw["agent_link"])
        self._migrate_decode_broker_config(raw)
        self.data["version"] = 4
        self._normalize_pet_settings()
        if old_version < 4:
            self._modified_keys.add("version")


    def _migrate_decode_broker_config(self, raw: dict) -> None:
        """decode_broker_enabled 退役（shm broker 下线，共享解码改由
        进程内 DecodeFanoutHub 承担）。迁移语义（SETTINGS-CHANGE-GATES）：读旧值
        → 记一次 info → 忽略（键从 defaults/白名单移除，不再归一/进入 self.data）。"""
        if getattr(self, "_decode_broker_migrated", False):
            return
        if "decode_broker_enabled" in raw:
            old = raw.get("decode_broker_enabled")
            logging.getLogger(__name__).info("配置键 decode_broker_enabled 已退役（批5.3 共享解码改为进程内 fan-out），忽略旧值 %r", old)
            raw.pop("decode_broker_enabled", None)
        self._decode_broker_migrated = True

    @staticmethod
    def _clean_phrase_events(events) -> dict:
        """清洗单层 dialogue 事件映射 {event: list[str] | str}（值上限 8 条/240 字符）。"""
        if not isinstance(events, dict):
            return {}
        cleaned = {}
        for key, value in events.items():
            if not str(key).strip():
                continue
            if isinstance(value, list):
                items = [item.strip()[:240] for item in value if isinstance(item, str) and item.strip()]
                if not items:
                    continue
                cleaned[str(key)] = items[:8]
            elif isinstance(value, str) and value.strip():
                cleaned[str(key)] = value.strip()[:240]
        return cleaned

    # dialogue 文案占位符迁移表：旧字段名（链路语义曾错位/曾与协议保留字段撞名）
    # → 新字段名。加载时幂等替换（新文案不含旧占位符即 no-op），只在用户
    # 自定义 dialogue_phrases 上执行；内置 preset JSON 直接改源文件。
    _DIALOGUE_PLACEHOLDER_MIGRATIONS = (
        ("{source}", "{failureType}"),
        ("{errorText}", "{errorMessage}"),
    )

    # 事件键改名表：旧事件键（曾按状态码命名）→ 新语义键。内置 preset JSON 直接
    # 改源文件；用户自定义 dialogue_phrases 里的旧键在加载时迁移一次（幂等）。
    # 新键已存在时以新配置为准，丢弃旧键（不合并、不留别名）。
    _DIALOGUE_EVENT_KEY_MIGRATIONS = (
        ("rate_limit.one", "model_access.one"),
        ("rate_limit.many", "model_access.many"),
    )

    @classmethod
    def _migrate_dialogue_phrase_fields(cls, phrases) -> None:
        """迁移 dialogue_phrases（global/agents 各层文案）里的旧事件键与旧占位符。

        先按 ``_DIALOGUE_EVENT_KEY_MIGRATIONS`` 改键，再把 list/str 值里的旧占位符
        替换为新名（``_DIALOGUE_PLACEHOLDER_MIGRATIONS``）。原地修改；对新配置
        （无旧键、无旧占位符）幂等无副作用。
        """
        if not isinstance(phrases, dict):
            return
        stack = [phrases]
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                continue
            for old_key, new_key in cls._DIALOGUE_EVENT_KEY_MIGRATIONS:
                if old_key not in node:
                    continue
                if new_key in node:
                    node.pop(old_key)  # 新配置优先：同名新键已在，丢弃旧键
                else:
                    node[new_key] = node.pop(old_key)
            for key, value in node.items():
                if isinstance(value, str):
                    replaced = value
                    for old, new in cls._DIALOGUE_PLACEHOLDER_MIGRATIONS:
                        replaced = replaced.replace(old, new)
                    if replaced != value:
                        node[key] = replaced
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if not isinstance(item, str):
                            continue
                        replaced = item
                        for old, new in cls._DIALOGUE_PLACEHOLDER_MIGRATIONS:
                            replaced = replaced.replace(old, new)
                        if replaced != item:
                            value[i] = replaced
                elif isinstance(value, dict):
                    stack.append(value)

    def _normalize_pet_settings(self):
        for key in _RETIRED_BALANCE_KEYS:
            self.data.pop(key, None)
        dialogue_mode = str(self.data.get("dialogue_mode") or "legacy").lower()
        self.data["dialogue_mode"] = dialogue_mode if dialogue_mode in {"legacy", "whale_maid", "custom"} else "legacy"
        raw_phrases = self.data.get("dialogue_phrases")
        if isinstance(raw_phrases, dict) and ("global" in raw_phrases or "agents" in raw_phrases):
            # 统一预设双层 {global: events, agents: {agent_key: events}}
            preset = {}
            global_events = raw_phrases.get("global")
            preset["global"] = self._clean_phrase_events(global_events)
            agents = {}
            raw_agents = raw_phrases.get("agents")
            if isinstance(raw_agents, dict):
                for agent_key, events in raw_agents.items():
                    agent_cleaned = self._clean_phrase_events(events)
                    if str(agent_key).strip() and agent_cleaned:
                        agents[str(agent_key)] = agent_cleaned
            preset["agents"] = agents
            self.data["dialogue_phrases"] = preset
        else:
            # 旧单层 {event: [...]}：视为 global
            self.data["dialogue_phrases"] = self._clean_phrase_events(raw_phrases)
        # 旧占位符迁移（{source}→{failureType} 等；新配置幂等 no-op）
        self._migrate_dialogue_phrase_fields(self.data.get("dialogue_phrases"))
        from . import physics as physics_mod

        self.data["playback_speed"] = _float_or_default(self.data.get("playback_speed"), 1.0, 0.1, 8.0)
        self.data["animation_gap_seconds"] = _float_or_default(self.data.get("animation_gap_seconds"), DEFAULT_ANIMATION_GAP_SECONDS, 0.0, 3600.0)
        minimum = _float_or_default(self.data.get("self_talk_min_interval"), DEFAULT_SELF_TALK_MIN_INTERVAL, 5.0, 3600.0)
        maximum = _float_or_default(self.data.get("self_talk_max_interval"), DEFAULT_SELF_TALK_MAX_INTERVAL, 5.0, 3600.0)
        self.data["self_talk_min_interval"] = min(minimum, maximum)
        self.data["self_talk_max_interval"] = max(minimum, maximum)
        self.data["self_talk_duration_seconds"] = _float_or_default(
            self.data.get("self_talk_duration_seconds"),
            DEFAULT_SELF_TALK_DURATION_SECONDS,
            1.0,
            300.0,
        )
        self.data["self_talk_image_dir"] = str(self.data.get("self_talk_image_dir") or "").strip()[:500]
        self.data["self_talk_image_scale"] = int(_float_or_default(self.data.get("self_talk_image_scale"), 100.0, 50.0, 300.0))
        self.data["self_talk_image_chance"] = int(_float_or_default(self.data.get("self_talk_image_chance"), float(DEFAULT_SELF_TALK_IMAGE_CHANCE), 0.0, 100.0))
        self.data["bubble_text_scale"] = int(_float_or_default(self.data.get("bubble_text_scale"), 100.0, 50.0, 300.0))
        self.data["self_talk_enabled"] = bool(self.data.get("self_talk_enabled", False))
        self.data["cursor_hidden_passthrough"] = _bool_or_default(self.data.get("cursor_hidden_passthrough"), True)
        self.data["spawn_inherit_size"] = _bool_or_default(self.data.get("spawn_inherit_size"), True)
        self.data["spawn_scale"] = _float_or_default(self.data.get("spawn_scale"), catalog.DEFAULT_SCALE, 0.1, 4.0)
        self.data["show_dock_icon"] = bool(self.data.get("show_dock_icon", True))
        self.data["self_talk_texts"] = _clean_self_talk_texts(self.data.get("self_talk_texts"))
        bubble_style = str(self.data.get("self_talk_bubble_style") or "")
        self.data["self_talk_bubble_style"] = bubble_style if bubble_style in SELF_TALK_BUBBLE_STYLES else DEFAULT_SELF_TALK_BUBBLE_STYLE
        self.data["context_menu_appearance"] = _clean_menu_appearance(self.data.get("context_menu_appearance"))
        self.data["quick_launch_apps"] = _clean_quick_launch_apps(self.data.get("quick_launch_apps"))
        self.data["quick_urls"] = _clean_quick_urls(self.data.get("quick_urls"))
        self.data["character_profiles"] = _clean_character_profiles(self.data.get("character_profiles"))
        self.data["slingshot_enabled"] = bool(self.data.get("slingshot_enabled", True))
        strength = physics_mod.normalize_throw_strength(str(self.data.get("throw_strength") or "standard"))
        self.data["throw_strength"] = strength
        # 终审 P1-3：必须用 _bool_or_default——bool("false") is True，字符串
        # 布尔（外部手改配置/旧版导出）会被误开；与其它布尔键同规。
        # 上游 #60 系统通知开关：同规防字符串布尔误开（bool("false") is True）。
        # 黄金回旋 / 边缘探头：与其它布尔键同规，防手改字符串布尔误开。
        self.data["golden_spin_on_click"] = _bool_or_default(self.data.get("golden_spin_on_click"), False)
        self.data["golden_spin_direct"] = _bool_or_default(self.data.get("golden_spin_direct"), False)
        self.data["edge_probe_enabled"] = _bool_or_default(self.data.get("edge_probe_enabled"), False)
        self.data["agent_link"] = _clean_agent_link_data(self.data.get("agent_link"))
        prewarm = str(self.data.get("media_prewarm", "balanced") or "balanced").strip().lower()
        self.data["media_prewarm"] = prewarm if prewarm in {"full", "balanced", "minimal"} else "balanced"
        # 默认 32→8（预测式预热使能）；32 是引入仅一天的旧默认，
        # 视为遗留值一并迁移（想调大可设 16/64 等非 32 值，32 本身被保留为迁移哨兵）。
        _ffb = _float_or_default(self.data.get("first_frame_cache_max_mb"), 8, 4, 64)
        self.data["first_frame_cache_max_mb"] = 8 if int(_ffb) == 32 else int(_ffb)
        # 夹到 [200, 600] 毫秒（默认 350）。
        self.data["predict_prewarm_lead_ms"] = int(_float_or_default(self.data.get("predict_prewarm_lead_ms"), 350, 200, 600))
        # ffmpeg 圈边界回收阈值（分钟）。0 = 关闭回收；否则夹到
        # [2, 120]（默认 10）。
        _ffr = _float_or_default(self.data.get("ffmpeg_recycle_minutes"), 10, 0, 120)
        self.data["ffmpeg_recycle_minutes"] = 0 if _ffr <= 0 else int(max(2.0, _ffr))
        # 同其它布尔键规约，防字符串布尔误开。
        self.data["experimental_single_process_spawn"] = _bool_or_default(self.data.get("experimental_single_process_spawn"), False)
        # 同规防字符串布尔误开（默认开）。
        self.data["experimental_shared_decode"] = _bool_or_default(self.data.get("experimental_shared_decode"), True)
        # 设置页进程隔离：同规防字符串布尔误开；默认开（关掉 = 回退进程内设置页）。
        self.data["settings_process_isolation"] = _bool_or_default(self.data.get("settings_process_isolation"), True)
        self.data.update(_clean_collision_data(self.data))

    def get(self, key, default=None):
        return self.data.get(key, default)

    def character_alias(self, character_id: str) -> str:
        """用户自定义的角色显示名；未设置返回空串。"""
        aliases = self.data.get("character_aliases")
        if isinstance(aliases, dict):
            return str(aliases.get(character_id, "") or "").strip()
        return ""

    def set_character_alias(self, character_id: str, name: str) -> None:
        """设置角色显示名别名（最长 24 字符）；空名表示恢复默认。"""
        aliases = self.data.setdefault("character_aliases", {})
        if not isinstance(aliases, dict):
            aliases = {}
            self.data["character_aliases"] = aliases
        name = (name or "").strip()[:24]
        if name:
            aliases[character_id] = name
        else:
            aliases.pop(character_id, None)
        if hasattr(self, "_modified_keys"):
            self._modified_keys.add("character_aliases")
        self.save()

    def character_display_name(self, character_id: str) -> str:
        """角色显示名：用户别名优先，未设置回退目录显示名（manifest name/角色 id）。

        展示给用户或注入 AI 提示（如识屏自我识别）的场合一律走本方法，
        不要直取 catalog.character_display_name 而绕过用户重命名。
        """
        return self.character_alias(character_id) or catalog.character_display_name(character_id)

    def character_profile(self, character_id: str) -> dict:
        """返回角色档案；不存在时返回空档案。"""
        profiles = self.data.get("character_profiles")
        if isinstance(profiles, dict):
            profile = profiles.get(str(character_id))
            if isinstance(profile, dict):
                return profile
        return {}

    def click_talk_bindings(self, character_id: str) -> dict:
        """返回某角色的点击动画台词绑定：{动画id: [台词, ...]}。"""
        profile = self.character_profile(character_id)
        bindings = profile.get("click_talk_bindings")
        return bindings if isinstance(bindings, dict) else {}

    def click_talk_texts_for(self, character_id: str, action_id: str) -> list[str]:
        """返回某点击动画绑定的台词；未绑定返回空列表。"""
        bindings = self.click_talk_bindings(character_id)
        texts = bindings.get(str(action_id))
        return texts if isinstance(texts, list) else []

    def set_click_talk_bindings(self, character_id: str, bindings: dict) -> None:
        """保存某角色的点击动画台词绑定并立即落盘。"""
        profiles = self.data.setdefault("character_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
            self.data["character_profiles"] = profiles
        profile = profiles.setdefault(str(character_id), {})
        if not isinstance(profile, dict):
            profile = {}
            profiles[str(character_id)] = profile
        profile["click_talk_bindings"] = bindings
        self.data["character_profiles"] = _clean_character_profiles(profiles)
        if hasattr(self, "_modified_keys"):
            self._modified_keys.add("character_profiles")
        self.save()

    def set(self, key, value):
        if key in _RETIRED_BALANCE_KEYS:
            return
        self.data[key] = value
        if hasattr(self, "_modified_keys"):
            self._modified_keys.add(key)
        if key in {
            "playback_speed",
            "animation_gap_seconds",
            "self_talk_enabled",
            "self_talk_min_interval",
            "self_talk_max_interval",
            "self_talk_texts",
            "self_talk_duration_seconds",
            "self_talk_image_dir",
            "self_talk_image_scale",
            "self_talk_image_chance",
            "bubble_text_scale",
            "self_talk_bubble_style",
            "context_menu_appearance",
            "quick_launch_apps",
            "quick_urls",
            "slingshot_enabled",
            "throw_strength",
            "agent_link",
            "media_prewarm",
            "first_frame_cache_max_mb",
            "predict_prewarm_lead_ms",
            "ffmpeg_recycle_minutes",
            "spawn_inherit_size",
            "spawn_scale",
            "character_profiles",
        }:
            self._normalize_pet_settings()


    def _data_for_save(self) -> dict:
        """复制待写数据并清理已退出功能的配置字段。"""
        write_data = copy.deepcopy(self.data)
        return self._clean_retired_data(write_data)

    def save(self, force: bool = False) -> bool:
        """通过跨进程锁保护读取、合并和原子写入；成功返回 True。

        只合并当前实例修改的键，避免覆盖其他进程的新设置。待写对象统一清理
        旧功能字段；无修改时保留较新的磁盘数据。"""
        try:
            self._normalize_pet_settings()
            self.dir.mkdir(parents=True, exist_ok=True)

            lock_path = self.path.with_name(f"{self.path.name}.lock")
            with _config_file_lock(lock_path) as acquired:
                if not acquired:
                    logging.warning("获取配置保存锁超时: %s", lock_path)
                    return False

                # F01：如果文件已存在且未发生任何脏修改（且非强制全量写），跳过写盘避免旧内存覆盖新数据
                disk_raw = None
                if self.path.is_file():
                    try:
                        disk_raw = json.loads(self.path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        pass
                if not force and isinstance(disk_raw, dict) and not getattr(self, "_modified_keys", None):
                    cleaned_disk = self._clean_retired_data(copy.deepcopy(disk_raw))
                    if cleaned_disk == disk_raw:
                        return True
                    write_dict = cleaned_disk
                else:
                    write_dict = self._data_for_save()

                if self.path.is_file() and getattr(self, "_modified_keys", None):
                    try:
                        disk_raw = json.loads(self.path.read_text(encoding="utf-8"))
                        if isinstance(disk_raw, dict):
                            merged = dict(disk_raw)
                            for key in self._modified_keys:
                                if key in write_dict:
                                    merged[key] = write_dict[key]
                                elif key in merged:
                                    merged.pop(key, None)
                            write_dict = merged
                    except Exception:
                        pass

                # F03：写入前对最终对象再次统一脱敏，防范 disk_raw 遗留的明文 key 漏写
                write_dict = self._clean_retired_data(write_dict)

                temp = self.path.with_name(f"{self.path.name}.{os.getpid()}_{time.time_ns()}.tmp")
                temp.write_text(
                    json.dumps(write_dict, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                os.replace(temp, self.path)
                if hasattr(self, "_modified_keys"):
                    self._modified_keys.clear()
        except OSError as exc:
            logging.warning("保存配置失败: %s (%s)", self.path, exc)
            return False
        return True

    @staticmethod
    def _clean_retired_data(data: dict) -> dict:
        """Migrate removed integrations even when merging another process's data."""
        for key in ('system_notifications_enabled', 'context_menu_layout', 'context_menu_template', 'dynamic_island', 'idle_low_fps_enabled', 'idle_low_fps_threshold', 'menu_easter_egg', 'spawn_inherit_dynamic_island', 'todo_reminder_enabled', 'todo_reminder_lead_minutes'):
            data.pop(key, None)
        if data.get("self_talk_texts") == ["好女孩……", "好模型……", "欧鲸鲸……", "今天也要认真工作呀。", "再陪你一会儿。"]:
            data["self_talk_texts"] = list(DEFAULT_SELF_TALK_TEXTS)
        for key in tuple(data):
            if key.startswith(("click_sound", "collision_sound", "voice_chime", "self_talk_voice", "self_talk_speak", "festival_")) or key == "click_self_talk_speak":
                data.pop(key, None)
                continue
            if key in {"chat", "proactive_screen", "file_interpret", "vision_api_key"} or key.startswith(("chat_", "modern_chat_", "vision_")):
                data.pop(key, None)
        for key in (*_RETIRED_BALANCE_KEYS, "pnpm_bin"):
            data.pop(key, None)
        if "agent_link" in data:
            data["agent_link"] = _clean_agent_link_data(data["agent_link"])
        if "quick_launch_apps" in data:
            data["quick_launch_apps"] = _clean_quick_launch_apps(data["quick_launch_apps"])
        return data
