# 纯桌宠清理与重新打包报告（2026-10-03）

基线：本轮修改前的工作区快照 `before-pure-pet.zip`；保留用户原有改动。
本报告承接 [上一轮 Work/Codex 联动报告](PR-REPORT-CHATGPT-LINK-2026-10-03.md)。

## 核心特性

按用户授权移除内置 AI 对话、识屏、主动识屏、快速聊天和文件解读，保留桌宠与 ChatGPT Work/Codex 状态联动、打开桌面端。
本轮删除 24 个 Python 功能模块、15 个退役测试文件，并清理混合测试中的失效分支。
保留现存桌宠动画、拖拽、碰撞、自动穿透、全屏隐藏、提醒、词库和多窗功能；保留已有可选 Cursor/自定义只读通道。
模型 API 配置及相关密钥不再参与运行；历史会话文件不删除。

## 修改文件说明

以下是本轮快照与最终工作区的逐文件差异，按规范化换行统计；不是相对 Git HEAD，避免把用户已有改动算入本轮。

| 文件 | 增删行数 | 改了什么与原因 |
|---|---|---|
| `.agents/skills/desktop-pet-ui-style/SKILL.md` | 删除 +0/−30 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `.agents/skills/desktop-pet-ui-style/references/visual-system.md` | 删除 +0/−117 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `.agents/skills/qt-ui-review/SKILL.md` | 删除 +0/−24 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `AGENTS.md` | 新增 +201/−0 | 同步纯桌宠功能边界、验收入口与历史文档说明。 |
| `README.md` | 修改 +1/−0 | 同步纯桌宠功能边界、验收入口与历史文档说明。 |
| `docs/ONEDIR_PACKAGING.md` | 修改 +8/−13 | 同步纯桌宠功能边界、验收入口与历史文档说明。 |
| `packaging/pet_entry.py` | 修改 +1/−1 | 移除退役 AI 入口及资源，保持实际构建/验收脚本可运行。 |
| `packaging/pet_entry_no_chat.py` | 删除 +0/−21 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/__main__.py` | 修改 +3/−6 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/app.py` | 修改 +284/−712 | 移除 AI 对话窗口、识屏回调和会话写入器；保留并验证启动、独立设置 watcher、多窗和退出资源收口。 |
| `pet/chat/__init__.py` | 删除 +0/−2 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/ai_settings_page.py` | 删除 +0/−634 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/crop_dialog.py` | 删除 +0/−189 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/geometry.py` | 删除 +0/−61 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/legacy_styles.qss` | 删除 +0/−298 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/legacy_widgets.py` | 删除 +0/−1078 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/models.py` | 删除 +0/−100 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/modern_styles.qss` | 删除 +0/−140 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/pet_link.py` | 删除 +0/−25 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/prompt.py` | 删除 +0/−33 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/providers.py` | 删除 +0/−148 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/service.py` | 删除 +0/−114 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/session_store.py` | 删除 +0/−612 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/settings_dialog.py` | 删除 +0/−451 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/themes.py` | 删除 +0/−297 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/utils.py` | 删除 +0/−58 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/chat/widgets.py` | 删除 +0/−2208 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/config.py` | 修改 +12/−288 | 删除 AI 默认字段、合并和密钥管理；加载与保存清除退役配置，保留现存字段的外部合并。 |
| `pet/config_domains.py` | 删除 +0/−123 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/context_menus/legacy.py` | 修改 +3/−11 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/context_menus/registry.py` | 修改 +4/−15 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/context_menus/shared.py` | 修改 +0/−37 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/dynamic_island.py` | 修改 +7/−30 | 删除内置聊天气泡路由；隐藏桌宠时展开恢复卡片，卡片按钮打开 ChatGPT。 |
| `pet/file_eater.py` | 修改 +0/−4 | 移除文件解读回调，保留喂文件动画与统计，不删除用户文件。 |
| `pet/file_interpret.py` | 删除 +0/−330 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/island_chat.py` | 删除 +0/−119 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/modern_settings_dialog.py` | 修改 +10/−452 | 删除 AI 页面及绑定，设置侧栏调整为六个现存域；删除音频预热空函数。 |
| `pet/multi_window_shared.py` | 修改 +7/−46 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/native/.native-previous-fc7e8ee1281f4932b838eb89ad897487/manifest.json` | 新增 +81/−0 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/platform_win.py` | 修改 +3/−3 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/proactive.py` | 删除 +0/−654 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/proactive_limiter.py` | 删除 +0/−367 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/proactive_memory.py` | 删除 +0/−88 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/quick_chat.py` | 删除 +0/−478 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/settings_file_interpret.py` | 删除 +0/−71 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/settings_interaction.py` | 修改 +1/−1 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/settings_pet_controls.py` | 修改 +1/−3 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/settings_widgets.py` | 修改 +0/−1 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/slot_manager.py` | 修改 +3/−9 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/todo_reminder.py` | 修改 +0/−1 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/vision.py` | 删除 +0/−438 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `pet/window.py` | 修改 +4/−165 | 移除快速聊天、识屏与主动反馈入口；保留动画、拖拽、碰撞、提示气泡、喂文件及全屏处理。 |
| `pet/window_alerts.py` | 修改 +1/−2 | 将自言自语默认词库依赖直接指向 config，去除已移除的间接再导出依赖。 |
| `pet/window_optional_services.py` | 修改 +0/−37 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/window_screen.py` | 修改 +2/−11 | 清理退役 AI 引用和未使用导入，保持现存桌宠调用链。 |
| `pet/windows_foreground.py` | 新增 +111/−0 | 保留独立的 Windows 前台窗口探针，避免删除识屏后损坏全屏隐藏。 |
| `pyproject.toml` | 修改 +0/−14 | 收紧已删除模块的静态检查豁免。 |
| `requirements-dev.txt` | 删除 +0/−5 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `requirements.txt` | 修改 +0/−2 | 移除 AI 专用 keyring 和直接 certifi 声明；语音依赖仍由 edge-tts 引入 certifi。 |
| `scripts/build_linux.sh` | 修改 +4/−11 | 移除退役 AI 入口及资源，保持实际构建/验收脚本可运行。 |
| `scripts/build_macos.sh` | 修改 +4/−11 | 移除退役 AI 入口及资源，保持实际构建/验收脚本可运行。 |
| `scripts/build_onedir.ps1` | 修改 +21/−28 | 统一纯桌宠入口、清理 AI 资源与 keyring，保留语音证书依赖，隔离 APPDATA 并验证原生/Qt/设置窗口。 |
| `scripts/capture_settings_pages.py` | 修改 +5/−32 | 移除退役 AI 入口及资源，保持实际构建/验收脚本可运行。 |
| `scripts/check_bundle_encoding.py` | 修改 +3/−3 | 将失效插件文案检查替换为实际 ChatGPT 中文文案；真实冻结产物由红转绿。 |
| `scripts/manual_ssl_proxy_check.py` | 删除 +0/−88 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `scripts/verify_settings_window.py` | 新增 +53/−0 | 精确检查指定后台进程的 Qt 设置窗口；Hidden 启动时 MainWindowHandle 为零不再造成假失败。 |
| `tests/conftest.py` | 修改 +0/−10 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_agent_link.py` | 修改 +0/−44 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_alert_queue.py` | 修改 +0/−36 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_api_provider_list.py` | 删除 +0/−143 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_architecture.py` | 修改 +0/−21 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_autostart.py` | 修改 +2/−3 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_candidate_release.py` | 修改 +0/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_chat_attachments.py` | 删除 +0/−187 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_chat_service.py` | 删除 +0/−292 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_chat_shared_behavior.py` | 删除 +0/−200 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_chat_subsystem.py` | 删除 +0/−3417 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_chat_themes.py` | 删除 +0/−278 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_click_self_talk_speech.py` | 修改 +0/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_collision_backend.py` | 修改 +0/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_collision_settings.py` | 修改 +2/−2 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_config_domains.py` | 删除 +0/−439 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_config_instance.py` | 修改 +0/−64 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_config_key_migration.py` | 删除 +0/−122 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_config_schema.py` | 修改 +1/−12 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_cursor_visibility.py` | 修改 +3/−4 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_decode_fanout.py` | 修改 +0/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_desktop_pet_features.py` | 修改 +16/−299 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_dynamic_island_revamp.py` | 修改 +4/−24 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_effects_integration.py` | 修改 +1/−7 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_feature_gating.py` | 修改 +3/−81 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_festival.py` | 修改 +2/−2 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_file_eater.py` | 修改 +0/−69 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_file_interpret.py` | 删除 +0/−443 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_first_batch_features.py` | 修改 +0/−22 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_idle_low_fps.py` | 修改 +1/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_island_chat.py` | 删除 +0/−498 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_island_shell_wiring.py` | 删除 +0/−127 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_library_priority_warm.py` | 修改 +0/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_menu_layout.py` | 修改 +65/−129 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_meta_no_gui_probe.py` | 修改 +6/−6 | 使用各用例独有的路径隔离在飞探测，保留 GUI 不探测和后台只探测一次的回归。 |
| `tests/test_persona_template.py` | 修改 +0/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_pet_interaction_locks.py` | 修改 +2/−2 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_proactive.py` | 删除 +0/−1292 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_pure_pet.py` | 修改 +4/−2 | 验证旧 AI 配置迁移清除、Work/Codex 配置保留以及六域设置页面与保存。 |
| `tests/test_requested_regressions.py` | 修改 +30/−306 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_runtime_dependencies.py` | 修改 +0/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_second_batch.py` | 删除 +0/−213 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_self_talk_image_chance.py` | 修改 +1/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_self_talk_voice_precache.py` | 修改 +3/−3 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_session_end_ffmpeg_guard.py` | 修改 +2/−2 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_session_store_async.py` | 删除 +0/−480 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_settings_and_resources.py` | 修改 +19/−19 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_settings_interaction_tabs.py` | 修改 +2/−2 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_settings_process_isolation.py` | 修改 +8/−73 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_single_process_shared.py` | 修改 +4/−107 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_single_process_spawn.py` | 修改 +21/−348 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_slot_and_memory.py` | 修改 +2/−59 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_speech_bubble.py` | 修改 +0/−18 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_stream_capture_compat.py` | 修改 +0/−91 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_todo_reminder.py` | 修改 +1/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_vision.py` | 删除 +0/−223 | 删除退役 AI 功能实现或仅覆盖该功能的测试/构建入口，避免失效依赖。 |
| `tests/test_voice_chime_service.py` | 修改 +15/−15 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_watchdog_settings_page.py` | 修改 +1/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_webm_clip_lifecycle.py` | 修改 +0/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_window_pause.py` | 修改 +0/−32 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |
| `tests/test_window_rendering.py` | 修改 +0/−1 | 移除退役功能断言与桩；更新现存菜单、设置、气泡、配置及生命周期的有效回归。 |

| `docs/INDEX.md` | 修改 +1/−0 | 登记本轮清理、重新打包报告并维护文档入口。 |
| `docs/PR-REPORT-PURE-PET-REPACK-2026-10-03.md` | 新增 +205/−0 | 逐文件变更、性能测量、实机和冻结包验收证据。 |

## 性能分析

环境：Windows 11 x64、Python 3.13.15、PySide6 6.11.2、PyInstaller 6.22.3。
命令：`python scripts/bench_chatgpt_link.py --samples 1000`，真实本机会话目录，4 个活跃日志文件。

| 指标 | 实测 |
|---|---|
| 当前源码 UTF-8 字节数（统一换行） | 2,708,936 → 2,244,207，减少 464,729 |
| 工作状态首次发现 | 5.0409 ms |
| 1000 次稳态轮询平均 / 中位数 | 0.2854 / 0.278 ms |
| 稳态轮询最大值 | 0.553 ms |
| 1000 次轮询 RSS 变化 | +45,056 字节 |
| 冻结目录 / ZIP 大小 | 301.52 / 162.13 MiB |
| 构建瘦身 | 移除 124 项无用 Qt/Pillow 资源，53.03 MiB（现存构建流程） |

轮询在现存后台线程以既定周期运行，本轮未增加轮询频率；读的是本机增量日志，没有新增模型网络请求。
删除的对话/识屏/文件解读路径不再启动其线程、截屏或模型请求；桌宠语音仍保留其既有网络功能。
无新增运行时缓存；已测轮询 RSS 变化见上表，不能据此推断无限运行不增长。
本轮没有同条件的旧包运行时性能测量，因此不宣称运行速度或 RSS 较旧包提升。

## 实机运行记录

1. `python work/live_chatgpt_check.py` 在 Windows 原生 Qt 环境运行 30 秒，读到 1 个真实会话，状态 {'working': 3, 'thinking': 1}；动画请求 ['写代码', '吃Token', '轻快记录']，窗口可见，工作线程在退出时已停止。
2. `windows_app_id()` / `open_chatgpt()`：`installed_desktop_discovered True`、`activation_started True`。当前机器的已安装桌面端通过开始菜单身份启动。
3. 设置六个域完成原生截图：720×600 浅色、1100×760 深色，检查侧栏与滚动内容；当前布局无 AI 页面。
4. 新 exe 启动冒烟通过；`--settings` 在隔离 APPDATA 中创建「桌宠设置」Qt 窗口并持有 `settings.lock`。
5. 后台启动设置窗口时 `MainWindowHandle=0` 的原因经本机枚举确认：窗口存在但按 Hidden 启动不可见；验收改为指定 PID 下精确标题和 Qt 类的检查，产物实际通过 `SETTINGS_QT_WINDOW_OK`。
6. 冻结原生自检 `FROZEN_NATIVE_OK`，ABI 2；Shiboken/QtCore/QtGui/QtWidgets 加载全部通过。
7. 冻结模块审计：1760 个模块，无聊天、识屏、主动识屏、文件解读或 keyring；ChatGPT 联动与所需证书依赖存在。

普通 ChatGPT 聊天生成状态不在本次授权的 Work/Codex 联动范围。Work/Codex 私有日志格式将来可能变化；未声称通过公开桌面状态 API 联动。
未在此次实机运行中人为制造真实任务失败或审批；这些边界由现存确定性回归验证。
自动审批拒绝删除旧原生 DLL 临时备份目录，原因是策略拦截；保留该目录，它不进入当前冻结包。

## 测试与验证

| 检查 | 结果 |
|---|---|
| 新增纯桌宠回归 | 修改前 2 项失败，修改后通过 |
| `python -m pytest -q` | **2178 passed, 7 skipped, 10 warnings**，129.54 秒；警告是既有 QImage 镜像弃用提示 |
| 编码、打包、依赖相关回归 | **48 passed** |
| 打包后报告规范、设置隔离、编码及依赖回归 | **105 passed**，7.23 秒 |
| `ruff check pet tests scripts` | 全部通过 |
| 产品代码额外检查 `ruff check pet --isolated --select F401,F841` | 全部通过，无未使用导入或局部变量 |
| Linux/macOS 构建脚本 `bash -n` | 通过（仅语法检查，未在对应平台构建） |
| 原生 CTest | 1/1 通过 |
| 中文编码、Qt DLL 链、冻结原生、主窗与设置页冒烟 | 全部通过 |
| 语音依赖闭包 | 26 项必要模块全部存在 |
| ZIP CRC 校验 | 1080 项全部通过 |

构建命令：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_onedir.ps1 -PythonExe D:/python/miniconda/envs/py13/python.exe`。
首次后处理识别到编码自检要求失效插件文案；更新自检后用 `-SkipBuild` 复用已重新编译产物，重新执行全部后处理与冒烟，未跳过验证门。

交付：`Desktop-Pet-ChatGPT-2026-10-03.zip`，SHA-256 `d6f2e41e9b7556b453273187e937e67554eb5f45ebe56553c004ff099c970ae1`。
解压完整目录，运行 `dsh-pet-standalone-webm-chat.exe`；文件名保留历史配置身份。当前交付是 Windows x64 便携包。
第三方素材授权声明包含其真实来源名称，保留法律出处，相关旧集成代码已移除。
