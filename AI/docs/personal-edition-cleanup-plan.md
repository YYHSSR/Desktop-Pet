# 任务实施计划：移除顶部显示卡片(灵动岛)、修复快捷启动、退役 DeepSeek 相关内容

> **规范依从**：依据 `SKIll/Agent-Code/SKILL.md` 与 `SKIll/En-SKILL.md`，制定细化实施计划并落盘于 `AI/docs/`。

---

## 一、 任务背景与目标

依据用户最新反馈与实机运行截图：
1. **移除最上方的显示卡片及相关代码**：实机屏幕顶部的胶囊卡片（灵动岛 `dynamic_island`，显示 `shenshen 18:26 🟢`）退役，不再常驻或弹出，下线相关配置与交互面。
2. **修复快捷启动（Quick Launch）**：
   - 现存问题：未配置应用时，菜单中“快捷启动”整项被 `setEnabled(False)` 禁用，呈灰色且无法展开子菜单，用户无法感知也无法在右键菜单中找到添加入口。
   - 改造目标：快捷启动子菜单始终保持可用。当列表为空时，展示“尚未配置快捷项”并提供“管理快捷启动...”动作，点击直接唤起设置面板中的快捷启动配置页；列表非空时列出应用并追加管理入口。
3. **彻底退役 DeepSeek 相关内容与孤立代码**：
   - 菜单中退役 `harness`（启动 DeepSeek Harness）及由其单独构成的空菜单 `tools_help`（工具与帮助）。
   - 移除后台静默拉取/启动 `harness`（`harness_autostart`）设置与相关逻辑。
   - 移除文案与风格定义中的专属品牌标识（如将“肥鱼版 DeepSeek”重命名为“现代宽屏风格”，清理计费文案中的 DeepSeek 专属字眼）。
   - 将默认 Provider / 模型占位从 DeepSeek 改为通用标准接口。

---

## 二、 变更范围与责任文件清单

### 1. 顶部卡片（灵动岛）下线
- [pet/app.py](file:///e:/CODE/desktop-pet/pet/app.py)：
  - 修改 `_sync_dynamic_island`：不再创建/显示 `DynamicIsland`，彻底静默下线。
  - `_island_chat_available` 直接返回 `False`，避免桌宠隐藏时误唤起岛聊天。
- [pet/config.py](file:///e:/CODE/desktop-pet/pet/config.py)：
  - 将 `dynamic_island` 默认数据的 `enabled` 设为 `False`，配置清洗时强制禁用，彻底杜绝老配置复活卡片。
- [pet/modern_settings_dialog.py](file:///e:/CODE/desktop-pet/pet/modern_settings_dialog.py)：
  - 移除“灵动岛”独立设置页及相关的 15 个 `SettingRow`，大幅缩减代码行数。
- [pet/settings_pet_controls.py](file:///e:/CODE/desktop-pet/pet/settings_pet_controls.py) & [pet/slot_manager.py](file:///e:/CODE/desktop-pet/pet/slot_manager.py)：
  - 移除/安全兼容 `spawn_inherit_dynamic_island`。

### 2. 快捷启动菜单交互修复
- [pet/context_menus/registry.py](file:///e:/CODE/desktop-pet/pet/context_menus/registry.py)：
  - 调整 `quick_launch` 的 `MenuActionSpec`，移除 `enabled=lambda pet: bool(...)` 的全局禁用限制，使其始终可展开。
- [pet/context_menus/quick_launch.py](file:///e:/CODE/desktop-pet/pet/context_menus/quick_launch.py)：
  - `add_quick_launch_menu` 改造：末尾统一追加“管理快捷启动...”选项；支持回调拉起 `pet.on_open_modern_settings`，让用户一键进入设置页管理应用。

### 3. DeepSeek 内容与代码清理
- [pet/context_menus/registry.py](file:///e:/CODE/desktop-pet/pet/context_menus/registry.py) & [pet/context_menus/shared.py](file:///e:/CODE/desktop-pet/pet/context_menus/shared.py)：
  - 移除 `harness` 动作及 `add_harness` 相关代码。
- [pet/menu_templates/modern-default-v1.json](file:///e:/CODE/desktop-pet/pet/menu_templates/modern-default-v1.json)：
  - 移除 `tools_help`（工具与帮助）子菜单及 `harness` 节点。
- [pet/menu_templates/modern.json](file:///e:/CODE/desktop-pet/pet/menu_templates/modern.json) & [pet/menu_templates/legacy.json](file:///e:/CODE/desktop-pet/pet/menu_templates/legacy.json) & [pet/context_menu.py](file:///e:/CODE/desktop-pet/pet/context_menu.py)：
  - 从各模板中移除 `harness` 项。
- [pet/modern_settings_dialog.py](file:///e:/CODE/desktop-pet/pet/modern_settings_dialog.py)：
  - 移除 `harness_autostart` 设置项。
  - 清理“DeepSeek 视觉单次约 ¥0.003”等品牌文案。
- [pet/chat/themes.py](file:///e:/CODE/desktop-pet/pet/chat/themes.py) & [pet/chat/ai_settings_page.py](file:///e:/CODE/desktop-pet/pet/chat/ai_settings_page.py)：
  - 将 `肥鱼版 DeepSeek` 重构为通用的 `现代宽屏风格`。
- [pet/config.py](file:///e:/CODE/desktop-pet/pet/config.py) & [pet/chat/models.py](file:///e:/CODE/desktop-pet/pet/chat/models.py) & [pet/vision.py](file:///e:/CODE/desktop-pet/pet/vision.py)：
  - 替换 DeepSeek 默认端点与模型名称为通用标准规范。

---

## 三、 执行步骤与依赖顺序

1. **第 1 步：修复快捷启动交互**（修改 `quick_launch.py` 与 `registry.py`，使子菜单始终可交互并可直达设置）。
2. **第 2 步：退役菜单中的 DeepSeek Harness 与工具与帮助**（更新菜单模板、注册表与回退模板）。
3. **第 3 步：下线顶部卡片（灵动岛）展示与设置**（更新 `config.py`、`app.py`、`modern_settings_dialog.py`）。
4. **第 4 步：清理品牌文案、模型预设与自启配置**（更新 `themes.py`、`ai_settings_page.py`、`vision.py`）。
5. **第 5 步：运行自动化测试与架构红线核验**（保证 `test_architecture.py` 行数预算达标，全量 pytest 绿灯）。
6. **第 6 步：重新打包验证**（使用已配置好的 `build_onedir.ps1` 输出最新 exe）。
