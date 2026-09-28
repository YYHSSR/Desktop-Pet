# 个人版 B2：余额与本轮消耗功能退役

实施依据：[设计](superpowers/specs/2026-09-27-personal-edition-phase-b-design.md)、[B2 计划](superpowers/plans/2026-09-27-personal-edition-phase-b2.md)及[B1 报告](PR-REPORT-PERSONAL-PHASE-B1-2026-09-27.md)。实施与最终验证跨 2026-09-27—28。本源码快照没有 `.git`；以下增删行数是相对只读 Phase A 归档 `E:\CODX\desktop-pet\baselines\phase-a-2026-09-27-20260927-142027-5d23e13e\source.zip` 的**累计 B1+B2 逐行比较**，不是 Git diff，也不能直接相加为 B2 独立改动。B1 独立文件见其报告。比较原始清单：`E:\CODX\desktop-pet\t\b2-numstat.txt`。

## 修改文件说明

| 文件 | 累计增删 | 改动与原因 |
| --- | ---: | --- |
| `pet/config.py` | +18/-26 | 旧消耗、余额七个键在构造、显式重载及保存时失效；旧灵动岛余额模式迁移为时间模式。 |
| `pet/catalog.py` | +2/-2 | 明确历史余额动画仅留作普通动画资源。 |
| `pet/context_menus/registry.py` | +6/-48 | 注销余额、本轮消耗动作及图标和标签。 |
| `pet/context_menus/shared.py` | +2/-42 | 删除余额查询菜单回调。 |
| `pet/context_menus/legacy.py` | +1/-6 | 旧版菜单同步去掉退役入口。 |
| `pet/menu_templates/modern-default-v1.json` | +1/-7 | 默认树去掉余额与消耗节点。 |
| `pet/menu_templates/modern.json` | +1/-1 | 同步旧模板节点。 |
| `pet/modern_settings_dialog.py` | +22/-58 | 删除退役行、搜索文字和保存接线；设置保存时保留历史自定义余额台词数据。 |
| `pet/settings_pet_controls.py` | +0/-32 | 移除余额档位编辑控件及选项。 |
| `pet/settings_interaction.py` | +0/-10 | 移除点击查余额设置行。 |
| `pet/app.py` | +10/-363 | 断开托盘查询、定时刷新、网络 worker、缓存和灵动岛余额桥接。 |
| `pet/window.py` | +2/-8 | 移除点击查余额的窗口回调和过时说明。 |
| `pet/dynamic_island.py` | +15/-110 | 删除余额卡片和峰谷定时器；保留时间、最近消息、通用动效和快捷按钮。 |
| `pet/agent_link.py` | +5/-121 | 删除本轮消耗差额查询及后台 worker；保留 Cursor/Agent 完成信号。 |
| `pet/agent_cost.py` | +0/-138 | 删除已无运行时调用的消耗模块。 |
| `pet/balance.py` | +0/-308 | 删除已无运行时调用的余额查询模块。 |
| `pet/persona_phrases.py` | +1/-2 | 从新台词词表的公共事件中移除余额查询。 |
| `pet/persona_template.py` | +2/-10 | 导出模板不再宣传不可触发的余额事件。 |
| `pet/persona_presets/legacy.json` | +0/-10 | 删除旧余额内置台词。 |
| `pet/persona_presets/whale_maid.json` | +0/-10 | 同步删除旧余额内置台词。 |
| `pet/report_gates.py` | +0/-1 | 删除旧余额事件到汇报门的映射。 |
| `pet/window_alerts.py` | +2/-2 | 删除余额提醒特殊抑制规则。 |

| 测试文件 | 累计增删 | 覆盖 |
| --- | ---: | --- |
| `tests/test_config_domains.py` | +81/-1 | 七个旧键、两种旧岛模式、显式重载与保存幂等。 |
| `tests/test_config_schema.py` | +24/-11 | 退役配置不可再由设置 API 写回。 |
| `tests/test_config_instance.py` | +9/-9 | 多实例配置不复活旧岛档位键。 |
| `tests/test_desktop_pet_features.py` | +33/-95 | 旧菜单与窗口替身更新为实际退役行为。 |
| `tests/test_menu_layout.py` | +61/-12 | 默认/自定义菜单裁剪，保留 `harness`、别名和图标；删除旧回调替身。 |
| `tests/test_settings_interaction_tabs.py` | +11/-1 | 控件和设置搜索无余额/消耗入口。 |
| `tests/test_settings_and_resources.py` | +18/-2 | 旧用户自定义余额台词在普通设置保存后原样保留。 |
| `tests/test_island_shell_wiring.py` | +11/-49 | 展开岛不写余额缓存或启动查询。 |
| `tests/test_dynamic_island_revamp.py` | +1/-3 | 删除旧卡片字段断言并更新信号说明，保留通用岛行为。 |
| `tests/test_island_content_cache.py` | +0/-21 | 删除旧余额内容缓存用例。 |
| `tests/test_agent_link.py` | +23/-94 | 老配置不创建消耗 worker，Cursor 完成保留。 |
| `tests/test_first_batch_features.py` | +13/-52 | 旧余额/消耗预期替换为退役行为。 |
| `tests/test_click_self_talk_speech.py` | +0/-2 | 删除旧点击余额替身字段。 |
| `tests/test_feature_gating.py` | +0/-1 | 删除旧余额定时器替身。 |
| `tests/test_requested_regressions.py` | +0/-1 | 删除旧余额定时器替身。 |
| `tests/test_persona_presets.py` | +11/-11 | 公共桥接事件继续覆盖自定义台词回退。 |
| `tests/test_persona_template.py` | +4/-6 | 模板事件与实际呈递点对齐。 |
| `tests/test_persona_settings.py` | +1/-1 | 更新非 Agent 台词说明。 |
| `tests/test_report_gates.py` | +6/-1 | 余额事件不再映射汇报门。 |
| `tests/test_alert_queue.py` | +1/-1 | 更新旧提醒说明。 |
| `tests/test_agent_cost.py` | +0/-179 | 删除退役模块专用测试。 |
| `tests/test_balance.py` | +0/-255 | 删除退役模块专用测试。 |
| `tests/test_dynamic_island_balance_tier_time.py` | +0/-107 | 删除退役档位专用测试。 |

其他 B1 专属文件与测试已在 B1 报告逐项说明。`pet/native/_bin/manifest.json` 是本机构建生成的 staging 清单，未作为 B2 业务源码修改。历史用户配置、`balance_cache.json` 和资源包中的余额动画均未清理；这些数据留待后续批次决定去向。

## 性能分析

环境：Windows 11、Python 3.13.15/PySide6；本机累计 B1+B2 `webm-chat` onedir 候选。一次性测量脚本在隔离的 `%APPDATA%` 中写入旧余额开关和缓存哨兵，启动 EXE；启动 7 秒后再采样 8 秒。最终原始结果 `E:\CODX\desktop-pet\t\b2host-final-smoke.json`：空闲 8 秒 CPU 增量为 0.00 CPU 秒/秒（进程计数器精度内），工作集 119.26 MiB，私有内存 81.01 MiB，期间分别变化 +0.39/−0.16 MiB；线程从 23 降到 20；采样末进程 TCP 连接数 0；余额缓存 SHA-256 不变。该结果是**单次短时、隐藏窗口空闲**的绝对测量，没有改前同条件基线，不据此声称整体加速或长期无泄漏。独立设置进程运行 7 秒、11 个线程。

余额刷新、点击查询、消耗差额的触发频率现为零；本批未增加常驻定时器、网络或磁盘路径。旧缓存文件不会因岛展开而重写（隔离实机与 Qt 测试均检查）。通用聊天、Cursor 和时间显示仍按原路径运行，不能从本次 8 秒空闲采样推断它们的活动期性能。受影响时序族在与打包负载并行期间连跑三次，每次 `82 passed`，耗时 5.11、5.10、5.16 秒。

## 实机运行记录

最终候选：`E:\CODX\desktop-pet\deliveries\personal-b1-b2-2026-09-28\dsh-pet-standalone-webm-chat\dsh-pet-standalone-webm-chat.exe`，SHA-256 `2cf19fc013e0a226a308bcbbd3464e51b6b8e05aa99f78dbbbd86d1d6a3e3151`；同目录便携 ZIP 为 175,245,926 字节，SHA-256 `790bb1701c949439d1db42274c40c6cbd43696efde586f03cc5816f144d45a34`。源码先复制到外部隔离目录，再由 `scripts/build_onedir.ps1 -Variant webm-chat -SkipZip -SkipGuiSmoke` 构建，未覆盖仓库已有包，也未发布。构建日志 `E:\CODX\desktop-pet\t\b2build-delivery.log` 记录原生 CTest、编码自检、Qt DLL 链、`NATIVE_BUNDLE_OK` 与 `FROZEN_NATIVE_OK`；脚本自动 GUI 冒烟被跳过，改为下列独立配置实机试跑。

最终 EXE 使用旧 `agent_cost_enabled=true`、`click_show_balance=true`、`balance_refresh_minutes=1`、岛 `balance_tier` 模式和已有 `balance_cache.json` 的隔离配置：主程序存活 15 秒；独立 `--settings` 进程存活 7 秒并持有 `settings.lock`；缓存内容未变。Windows 原生 Qt 平台对设置页做了 800 px 明/暗主题与 720 px 窄宽度截图，路径 `E:\CODX\desktop-pet\t\b2ui`；人工核对互动页、桌面组件页无遮挡或旧余额选项。设置搜索“余额”返回零个结果；默认、旧版、自定义菜单的退役动作与 `harness` 保留由真实 QMenu/Qt 测试覆盖。未用此试跑声称 Cursor 完成、托盘点击和隐藏岛交互已在人工实机逐项操作；Cursor 保留由自动化测试覆盖，待有实际会话时可追加验收。

## 测试与限制

- 先红后绿：旧配置、菜单、岛展开、Agent 消耗 worker、设置搜索、历史台词保留和汇报门均观察到针对性失败，再实现修正。
- Ruff：`python -m ruff check pet tests scripts` 通过。用户要求停止继续测试前，最终完整测试已结束：`2992 passed, 11 skipped, 260 warnings in 190.34s`，原始日志 `E:\CODX\desktop-pet\t\b2finalverified\out.log`；跳过项和弃用警告不算通过。受影响时序族三次各 `82 passed`。
- 原生代码未改；候选构建脚本执行的 CTest 已通过。macOS/Linux GUI 未在本机执行，不外推为通过。Windows 原生 Qt 截图属于源码设置页，候选 EXE 则完成隔离配置启动、锁和空闲采样；没有自动化工具可从隐藏候选窗口读取完整视觉状态。ChatGPT 客户端真实状态适配仍按 Phase A 结论关闭，未作为本批验收项。
- 用户随后要求停止继续测试并清理临时脚本。六个一次性 B2 编辑/验证脚本已经删除；自动审批机制以 `blocked by policy` 拒绝递归删除外部构建暂存副本和中间测试目录，故这些目录仍在 `E:\CODX\desktop-pet`，不属于交付包。

## 风险与回滚

旧余额和消耗配置加载后失效，下一次正常保存才从新配置中清除；旧用户自定义台词和缓存文件保留。自定义菜单里的退役 ID 在解析时跳过，其余节点顺序与别名保留。若需回退，先退出候选进程，以只读 Phase A 归档和 B1/B2 报告按文件恢复源码，再做完整测试；不要用回退脚本覆盖现有用户配置。无 `.git`、提交或 PR 可引用。后续批次 C 才处理 DSH/Harness、Claude、OpenCode；本批保留 `harness` 与通用聊天。未上传或发布候选包。
