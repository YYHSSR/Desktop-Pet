# -*- coding: utf-8 -*-
"""多开配置隔离：instance_id（--slot / 生小肥鱼）使用独立 config 文件，单开行为不变。"""
from __future__ import annotations

import json

from pet.config import Config


def test_instance_config_is_isolated_from_default(tmp_path):
    instance = Config(base=tmp_path, instance_id="pet2")
    instance.set("rx", 0.5)
    instance.set("ry", 0.6)
    instance.save()

    default = Config(base=tmp_path)
    assert default.get("rx") is None
    assert default.get("ry") is None

    reloaded = Config(base=tmp_path, instance_id="pet2")
    assert reloaded.get("rx") == 0.5
    assert reloaded.get("ry") == 0.6


def test_default_config_still_uses_plain_file(tmp_path):
    default = Config(base=tmp_path)
    assert default.path.name == "config.json"

    instance = Config(base=tmp_path, instance_id="pet3")
    assert instance.path.name == "config-pet3.json"




def test_retired_balance_settings_do_not_persist(tmp_path):
    config = Config(base=tmp_path)
    config.set("balance_tier_labels_mode", "liangwen")
    config.set("balance_tier_label_peak", "peak")
    config.set("balance_tier_label_idle", "idle")
    config.set("balance_tier_color_enabled", False)
    config.set("self_talk_enabled", True)
    assert config.save()

    reloaded = Config(base=tmp_path)
    for key in ("balance_tier_labels_mode", "balance_tier_label_peak",
                "balance_tier_label_idle", "balance_tier_color_enabled"):
        assert key not in reloaded.data
    assert reloaded.get("self_talk_enabled") is True




def test_save_returns_false_on_write_failure(tmp_path):
    """写盘失败（此处置目标为目录迫使 os.replace 失败）时 save 返回 False。"""
    config = Config(base=tmp_path)
    config.path.mkdir(parents=True, exist_ok=True)
    assert config.save() is False




def test_unmodified_save_does_not_overwrite_newer_disk_changes(tmp_path):
    """F01 回归：无脏键时不全量覆盖较新磁盘配置。"""
    cfg_a = Config(base=tmp_path)
    cfg_a.set("scale", 0.72)
    assert cfg_a.save()

    cfg_b = Config(base=tmp_path)
    assert cfg_b.get("scale") == 0.72
    cfg_b.set("scale", 1.75)
    assert cfg_b.save()

    # cfg_a 无任何脏键，此时 save() 不得用 cfg_a 的旧快照冲掉 1.75
    assert cfg_a.save()

    reloaded = Config(base=tmp_path)
    assert reloaded.get("scale") == 1.75


def test_save_redacts_legacy_keys_from_disk_raw(tmp_path):
    """F03 回归：增量合并后最终写入磁盘前再次脱敏，旧磁盘明文 API 密钥不得被保留。"""
    cfg = Config(base=tmp_path)
    assert cfg.save()

    # 模拟磁盘历史遗留明文 key
    disk_data = json.loads(cfg.path.read_text(encoding="utf-8"))
    disk_data["chat"] = {
        "providers": {
            "openai-main": {"api_key": "LEAKED_KEY", "vision_api_key": "LEAKED_VK"}
        }
    }
    cfg.path.write_text(json.dumps(disk_data), encoding="utf-8")

    # 仅修改一个无关配置（如 on_top）
    cfg2 = Config(base=tmp_path)
    cfg2.set("on_top", False)
    assert cfg2.save()

    # 检查磁盘数据：合并后必须脱敏，不能保留 LEAKED_KEY
    new_disk = json.loads(cfg2.path.read_text(encoding="utf-8"))
    provider = new_disk.get("chat", {}).get("providers", {}).get("openai-main", {})
    assert "api_key" not in provider
    assert "vision_api_key" not in provider


def test_set_click_talk_bindings_persists_with_prior_dirty_key(tmp_path):
    """F04 回归：在已有脏键时保存点击动画台词绑定，台词不会丢失。"""
    cfg = Config(base=tmp_path)
    assert cfg.save()

    cfg2 = Config(base=tmp_path)
    cfg2.set("on_top", False)
    cfg2.set_click_talk_bindings("demo_pet", {"click": ["hello world"]})

    reloaded = Config(base=tmp_path)
    assert reloaded.get("on_top") is False
    assert reloaded.click_talk_texts_for("demo_pet", "click") == ["hello world"]
