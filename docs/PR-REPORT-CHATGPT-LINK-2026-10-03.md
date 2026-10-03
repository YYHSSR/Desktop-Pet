# 旧集成清理与 ChatGPT 工作状态联动（2026-10-03）

项目：`E:/CODE/desktop-pet`。Git HEAD：`9933cd9`；分支：`main`。
本轮以开始工作时的源码快照为增量基线，原工作区已有大量未提交改动；这些原有改动继续保留。
用户确认目标为 **Work/Codex 工作状态联动，并可打开 ChatGPT 桌面端**。

## 核心变化

- 删除三类退役产品的专用集成、DSH 插件桥接、Node/pnpm 安装与启动器、审批回写/控制端点以及对应测试、CI 和打包收集步骤。
- 右键桌宠 → Agent 联动 → **ChatGPT 工作状态（Work / Codex）** 启用只读监听；**打开 ChatGPT 桌面端** 激活本机安装应用。
- 按会话和回合聚合 working / thinking / attention / error / idle，处理并发、迟到完成、停用清理与重新启用。完成提醒等待 800 毫秒稳定；中断使用中性反馈。
- 大工具输出不会逐个 64 KiB 片段延迟状态读取；单文件每轮最多读取 1 MiB，单行上限 64 KiB，最多追踪 50 个近期文件，已结束状态历史限制 256 条。
- 沿用 `agent_link.codex` 配置键；清理旧来源与 `pnpm_bin`，防止磁盘合并复活退役字段，同时保留用户自定义来源及通用 API 配置。

完整支持边界和事件映射见 [桌面联动协议](AGENT_LINK_PROTOCOL.md)，验收入口见 [验收测试清单](ACCEPTANCE_TESTS.md)。

## 修改文件说明

下表为本轮相对开始时源码快照的逐文件增量，共 120 个已有/新增实现、测试与说明文件，另新增本报告。
增删行按逐行比较统计，忽略 LF/CRLF 差异。新测试的前 5 个红测早于源码备份创建，表中按整个新文件统计。
末尾另附 `git diff --numstat` 原始结果；那份 Git HEAD 差异包含用户进入本轮前的修改，不能等同于本轮工作量。

| 文件 | 本轮增删行 | 改动及原因 |
|---|---:|---|
| `.github/workflows/build-linux.yml` | +1 / −3 | 移除旧插件源码收集、Node 契约门禁或桥接 bundle 校验。 |
| `.github/workflows/build-macos.yml` | +1 / −3 | 移除旧插件源码收集、Node 契约门禁或桥接 bundle 校验。 |
| `.github/workflows/pr-test.yml` | +0 / −14 | 移除旧插件源码收集、Node 契约门禁或桥接 bundle 校验。 |
| `README.md` | +11 / −0 | 补充用户可执行的 ChatGPT 联动开关、无需 API Key 和支持范围说明。 |
| `SKIll/En-SKILL.md` | +1 / −1 | 示例改为通用 AI 工具，移除退役产品提及。 |
| `docs/ACCEPTANCE_TESTS.md` | +8 / −19 | 替换失效的 Node 桥接验收为现存工作状态用例；明确旧数字为历史基线。 |
| `docs/AGENT_LINK_PROTOCOL.md` | +50 / −148 | 重写只读 Work/Codex 联动、真实本机路径、私有格式限制、菜单启动和自定义协议。 |
| `docs/BUGFIX-AND-FEATURES-2026-08-24.md` | +3 / −7 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/CHANGELOG-DEV-SINCE-v4.1.0-2026-09-09.md` | +3 / −43 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/CHAT-BACKGROUND-DISPLAY-2026-08-27.md` | +2 / −8 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md` | +8 / −98 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/DEV-HANDOVER.md` | +0 / −1 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/DSH-BRIDGE-PET-EVENT-CONTRACT-2026-09-02.md` | +0 / −371 | 删除专属于退役插件、启动器或其协议的研究文档。 |
| `docs/DSH-HUMAN-REQUEST-RESEARCH-2026-09-02.md` | +0 / −170 | 删除专属于退役插件、启动器或其协议的研究文档。 |
| `docs/DSH-REQUEST-EVENT-CATALOG.md` | +0 / −59 | 删除专属于退役插件、启动器或其协议的研究文档。 |
| `docs/HANDOVER_2026-09.md` | +1 / −9 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/INDEX.md` | +6 / −20 | 移除已删除文档入口，更新联动索引并登记本报告。 |
| `docs/ISSUE-111-WINDOWS-SESSION-END-FFMPEG-2026-09-12.md` | +0 / −1 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/NETWORK-PROXY-AND-VPN-2026-09-22.md` | +1 / −11 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/OPEN-SOURCE-HARNESS-RISK-RESEARCH.md` | +0 / −78 | 删除专属于退役插件、启动器或其协议的研究文档。 |
| `docs/PET-STATE-MACHINE-AND-REPETITION-2026-09-02.md` | +0 / −1 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/PHASE3_PROCESS_PLUGIN_RESEARCH.md` | +0 / −268 | 删除专属于退役插件、启动器或其协议的研究文档。 |
| `docs/PR-MERGE-LESSONS-2026-09-12.md` | +1 / −3 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/PR-REPORT-GATES-2026-09-10.md` | +1 / −10 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/PR-REPORT-PERSONAL-PHASE-A-2026-09-27.md` | +1 / −4 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/PR-REPORT-PERSONAL-PHASE-B2-2026-09-27.md` | +0 / −2 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/PR-REPORT-PR76-2026-09-10.md` | +2 / −9 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/PROACTIVE_SCREEN_PLAN.md` | +1 / −10 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/RELEASE-v4.2.0.md` | +3 / −32 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/SETTINGS-INFORMATION-ARCHITECTURE-2026-08-27.md` | +0 / −5 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/SETTINGS-REDESIGN-Q4-CLASSIFICATION-RESEARCH.md` | +1 / −4 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md` | +3 / −34 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/SETTINGS-REPORT-PROBABILITY-2026-09-10.md` | +0 / −1 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/UPSTREAM-INTEGRATION-2026-08-26.md` | +0 / −51 | 删除专属于退役插件、启动器或其协议的研究文档。 |
| `docs/superpowers/plans/2026-09-27-personal-edition-phase-b1.md` | +1 / −6 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/superpowers/plans/2026-09-27-personal-edition-phase-b2.md` | +1 / −5 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `docs/superpowers/specs/2026-09-27-personal-edition-phase-b-design.md` | +5 / −5 | 删除旧集成相关描述、失效文件链接或品牌示例；保留其他章节。 |
| `integrations/dsh-pet-bridge/cordis.patch.yml` | +0 / −4 | 删除专属于退役插件桥接、启动器或 Node 运行时的实现文件。 |
| `integrations/dsh-pet-bridge/index.js` | +0 / −1795 | 删除专属于退役插件桥接、启动器或 Node 运行时的实现文件。 |
| `integrations/dsh-pet-bridge/package.json` | +0 / −21 | 删除专属于退役插件桥接、启动器或 Node 运行时的实现文件。 |
| `integrations/dsh-pet-bridge/verify_import.mjs` | +0 / −82 | 删除专属于退役插件桥接、启动器或 Node 运行时的实现文件。 |
| `pet/agent_event_normalizer.py` | +1 / −1 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pet/agent_link.py` | +276 / −2050 | 删除旧安装、回写和控制层；补足 Work/Codex 会话与回合身份、增量追踪、停用清理、提醒聚合和历史容量限制。 |
| `pet/app.py` | +3 / −3 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pet/behavior_detector.py` | +4 / −4 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pet/chat/modern_styles.qss` | +2 / −2 | 将品牌专用侧栏样式名改为 chat-sidebar，并同步样式与测试。 |
| `pet/chat/settings_dialog.py` | +1 / −1 | 将品牌专用侧栏样式名改为 chat-sidebar，并同步样式与测试。 |
| `pet/chat/themes.py` | +1 / −1 | 将品牌专用侧栏样式名改为 chat-sidebar，并同步样式与测试。 |
| `pet/chat/widgets.py` | +2 / −2 | 将品牌专用侧栏样式名改为 chat-sidebar，并同步样式与测试。 |
| `pet/chatgpt_desktop.py` | +78 / −0 | 新增 CODEX_HOME 定位和已安装 ChatGPT 桌面端发现、启动及失败反馈。 |
| `pet/config.py` | +37 / −14 | 来源开关白名单迁移；清除旧启动器字段，防止磁盘配置合并重新引入退役字段，保留外部更新与通用 API 配置。 |
| `pet/context_menus/icons.py` | +0 / −3 | 删除退役启动器专用矢量图标。 |
| `pet/context_menus/shared.py` | +6 / −1 | 将工作状态入口命名为 ChatGPT Work/Codex；增加打开桌面端菜单动作。 |
| `pet/dsh_control.py` | +0 / −113 | 删除专属于退役插件桥接、启动器或 Node 运行时的实现文件。 |
| `pet/dsh_responder.py` | +0 / −57 | 删除专属于退役插件桥接、启动器或 Node 运行时的实现文件。 |
| `pet/dsh_state.py` | +0 / −449 | 删除专属于退役插件桥接、启动器或 Node 运行时的实现文件。 |
| `pet/dynamic_island.py` | +2 / −2 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pet/exploration_watchdog.py` | +2 / −5 | 删除旧控制队列专用分类分支；保留通用事件检测。 |
| `pet/exploration_watchdog_settings.py` | +2 / −2 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pet/harness_launcher.py` | +0 / −882 | 删除专属于退役插件桥接、启动器或 Node 运行时的实现文件。 |
| `pet/modern_settings_dialog.py` | +0 / −5 | 删除退役安装器路径的控件绑定。 |
| `pet/multi_window_shared.py` | +2 / −2 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pet/node_runtime.py` | +0 / −453 | 删除专属于退役插件桥接、启动器或 Node 运行时的实现文件。 |
| `pet/persona_phrases.py` | +0 / −3 | 删除退役安装、卸载和回写的角色台词、事件描述及预设。 |
| `pet/persona_presets/legacy.json` | +0 / −30 | 删除退役安装、卸载和回写的角色台词、事件描述及预设。 |
| `pet/persona_presets/whale_maid.json` | +0 / −30 | 删除退役安装、卸载和回写的角色台词、事件描述及预设。 |
| `pet/persona_template.py` | +2 / −24 | 删除退役安装、卸载和回写的角色台词、事件描述及预设。 |
| `pet/report_gates.py` | +1 / −2 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pet/settings_widgets.py` | +0 / −1 | 移除清理后多余文件尾空行或残留旧品牌注释。 |
| `pet/speech_bubble.py` | +2 / −2 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pet/stuck_detector.py` | +3 / −3 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pet/win_job.py` | +1 / −1 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pet/window.py` | +2 / −2 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pet/window_alerts.py` | +2 / −2 | 清理退役来源的说明/示例，现存通用交互与检测继续使用。 |
| `pyproject.toml` | +0 / −1 | 移除退役 Node 桥接测试工具记录。 |
| `scripts/bench_chatgpt_link.py` | +58 / −0 | 新增可复现的真实本机会话轮询、冷发现和 RSS 测量脚本。 |
| `scripts/build_linux.sh` | +1 / −5 | 移除旧插件源码收集、Node 契约门禁或桥接 bundle 校验。 |
| `scripts/build_macos.sh` | +1 / −5 | 移除旧插件源码收集、Node 契约门禁或桥接 bundle 校验。 |
| `scripts/fix_bridge_bundle.py` | +0 / −138 | 删除专属于退役插件桥接、启动器或 Node 运行时的实现文件。 |
| `scripts/package_collision_candidate.py` | +1 / −1 | 候选源码清单移除已删除的 integrations 目录。 |
| `tests/conftest.py` | +1 / −23 | 移除不存在的监视器启动拦截及 Node/安装器资源清理。 |
| `tests/test_agent_link.py` | +226 / −1021 | 删除退役安装与响应协议测试；改为工作状态、所属应用入口和只读提醒的有效断言。 |
| `tests/test_agent_link_dep_specs.py` | +0 / −526 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_agent_link_threads.py` | +10 / −46 | 删除退役安装线程测试；保留现存监视器线程生命周期覆盖。 |
| `tests/test_bridge_hardfailure.js` | +0 / −145 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_bridge_interaction_dedup.js` | +0 / −74 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_bridge_manifest.js` | +0 / −26 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_bridge_question_callid.js` | +0 / −101 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_bridge_retry.js` | +0 / −88 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_bridge_root_control.js` | +0 / −123 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_bridge_user_action_guard.js` | +0 / −59 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_chat_subsystem.py` | +8 / −8 | 测试来源和示例改为 Codex 或通用值，保持原功能断言。 |
| `tests/test_chat_themes.py` | +1 / −1 | 将品牌专用侧栏样式名改为 chat-sidebar，并同步样式与测试。 |
| `tests/test_chatgpt_desktop.py` | +168 / −0 | 新增 11 项回归：身份、并发、配置目录、等待输入、启动、停用、大输出排空和历史容量。 |
| `tests/test_config_domains.py` | +10 / −10 | 外部配置合并测试改用现存字段，确保迁移不破坏外部修改。 |
| `tests/test_config_instance.py` | +0 / −1 | 移除清理后多余文件尾空行或残留旧品牌注释。 |
| `tests/test_config_key_migration.py` | +4 / −4 | 测试来源和示例改为 Codex 或通用值，保持原功能断言。 |
| `tests/test_config_schema.py` | +0 / −1 | 配置 schema 删除退役 pnpm_bin。 |
| `tests/test_desktop_pet_features.py` | +12 / −38 | 删除退役设置页断言，加入三类旧产品文案不得重新进入运行代码的扫描。 |
| `tests/test_dsh_control_client.py` | +0 / −92 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_dsh_state.py` | +0 / −370 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_file_interpret.py` | +0 / −1 | 移除清理后多余文件尾空行或残留旧品牌注释。 |
| `tests/test_fix_bridge_bundle.py` | +0 / −81 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_harness_launcher.py` | +0 / −327 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_harness_lifecycle.py` | +0 / −590 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_idle_low_fps.py` | +8 / −8 | 测试来源和示例改为 Codex 或通用值，保持原功能断言。 |
| `tests/test_menu_layout.py` | +2 / −2 | 测试来源和示例改为 Codex 或通用值，保持原功能断言。 |
| `tests/test_meta_round2_optimizations.py` | +0 / −2 | 移除清理后多余文件尾空行或残留旧品牌注释。 |
| `tests/test_persona_settings.py` | +9 / −9 | 角色词库专属来源改为保留的 Codex/通用事件。 |
| `tests/test_persona_template.py` | +0 / −14 | 删除已不存在的桥接模板事件断言。 |
| `tests/test_pet_interaction_locks.py` | +2 / −2 | 测试来源和示例改为 Codex 或通用值，保持原功能断言。 |
| `tests/test_proactive.py` | +4 / −11 | 移除退役来源配置和安装器 mock；保持联动忙碌抑制主动反馈验证。 |
| `tests/test_settings_and_resources.py` | +14 / −15 | 测试来源和示例改为 Codex 或通用值，保持原功能断言。 |
| `tests/test_settings_process_isolation.py` | +7 / −7 | 测试来源和示例改为 Codex 或通用值，保持原功能断言。 |
| `tests/test_single_process_shared.py` | +6 / −6 | 测试来源和示例改为 Codex 或通用值，保持原功能断言。 |
| `tests/test_uninstall_cleanup.py` | +0 / −23 | 删除专供旧插件卸载的多实例授权判断测试。 |
| `tests/test_vision.py` | +16 / −16 | 测试来源和示例改为 Codex 或通用值，保持原功能断言。 |
| `tests/test_voice_chime_service.py` | +0 / −1 | 测试来源和示例改为 Codex 或通用值，保持原功能断言。 |
| `tests/test_watchdog_control_wiring.py` | +0 / −562 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `tests/test_windows_node_env.py` | +0 / −790 | 删除专属于退役桥接、启动器或 Node 环境的测试文件。 |
| `docs/PR-REPORT-CHATGPT-LINK-2026-10-03.md` | 新增整份报告 | 登记逐文件增量、性能实测、实机证据和已知限制。 |

## 性能分析

实测环境：Windows、Python 3.13.15、PySide6 6.11.2、psutil 7.2.2；真实本机会话目录中跟踪 1 个近期 rollout。
修改前后各测量 2,000 次轮询；先预热 20 次并在 RSS 测量前后执行 GC。两次独立进程顺序运行，此数据用于估计成本，不构成严格的长期性能保证。

可复现命令（修改前源码来自启动时快照，assets 链接回项目已有素材）：

```powershell
& D:/python/miniconda/envs/py13/python.exe scripts/bench_chatgpt_link.py --samples 2000 --source-root E:/CODX/2026-10-03/shen/work/baseline
& D:/python/miniconda/envs/py13/python.exe scripts/bench_chatgpt_link.py --samples 2000
```

| 指标 | 修改前 | 修改后 |
|---|---:|---:|
| 首次发现 | 1.7865 ms | 2.8122 ms |
| 稳态平均 | 0.1098 ms | 0.0822 ms |
| 稳态中位数 | 0.104 ms | 0.078 ms |
| 稳态最大 | 1.0175 ms | 0.6012 ms |
| RSS 测量开始/结束 | 47448064 / 47525888 B | 43040768 / 43118592 B |
| 2,000 次轮询 RSS 增量 | 77824 B | 77824 B |

稳态绝对耗时约 0.082 ms/次，单次样本较旧实现减少约 0.028 ms；首次发现因补读会话/回合元数据增加约 1.026 ms。
后台轮询间隔 1.5 秒，目录发现间隔 15 秒。读取新增日志需文件 stat/open/read；无新增网络请求，默认关闭时无此来源轮询线程。
启用每个来源使用现存监视器 worker 模型；单进程多窗共享模式继续只运行一份共享监视器。
缓存容量已受文件数、单行、单轮读取和已结束会话数限制；两次测量的 RSS 增量均为 76 KiB，启动 RSS 差异存在进程波动，不据此宣称固定内存节省。
开始菜单应用发现的现场耗时为 **575.82 ms**，只在点击打开菜单动作时运行一次隐藏 PowerShell 子进程，随后由 Explorer 激活应用。

## 实机运行记录

本机开始菜单实际结果：`Name=ChatGPT`，`AppID=OpenAI.Codex_2p2nqsd0c76g0!App`；安装包版本为 `26.930.3930.0`。
执行 `pet.chatgpt_desktop.open_chatgpt()` 返回 `True`，并成功调用系统激活入口打开桌面端。

实际以 Windows 原生 Qt 平台启动桌宠，使用临时桌宠配置读取真实 `.codex/sessions`；没有向 ChatGPT 会话目录写入模拟记录。
采样 30 秒期间得到两个 `working` 状态事件、1 个真实会话，携带非空 session/turn 身份；调用原 `PetWindow.request_animation`，动作请求为 **写代码**。
该采样窗口没有收到完成或思考事件，因此这些分支的验证来自回归测试，不把模拟测试描述成实际桌面端观察。

现场输出摘要：

```text
native_gui_started
live_state working session_present True turn_present True
live_state working session_present True turn_present True
native_visible=True active_worker=True tracked_files=1
manager_states={"codex":"working"} animation_requests=["写代码"]
cold_discovery_ms=4.088 steady_poll_samples=200
steady_poll_mean_ms=0.151 steady_poll_max_ms=0.43
worker_stopped True
```

已查看右键联动菜单和实际桌宠截图，并检查自动化与联动设置页：720×760 浅色及 1100×760 深色，未发现裁切或无法访问的入口。
缺失桌面应用时的气泡反馈、启停、多会话、大输出和历史容量分支由针对性测试验证；本机已安装应用，未卸载真实应用来制造缺失条件。
macOS 启动分支未在真实 macOS 机器上验证，Linux 返回无法启动的明确结果。

## 测试与验证

新回归先失败后修复：会话身份/回合继承、菜单启动、启用后新建 rollout、停用忙碌清理、400 KB 工具输出后的状态读取、300 条完成历史上限。
相关集成回归曾得到 `412 passed`；最后增加大输出及容量回归后，聚焦工作状态族得到 `130 passed`。
最终代码冻结后的全量结果和静态检查见下方最终记录。

| 检查 | 最终结果 |
|---|---|
| `python -m ruff check pet tests scripts/bench_chatgpt_link.py` | 全部通过。 |
| `python -m pytest -q`（Windows / QT_QPA_PLATFORM=offscreen） | **2607 passed, 10 skipped, 3 failed, 13 warnings in 154.07s**；失败均为下表原有问题。 |
| 工作状态与文档纪律聚焦：`test_chatgpt_desktop / test_codex_monitor / test_cursor_monitor / test_agent_multi_session / test_agent_link / test_agent_link_threads / test_pr_report_discipline` | **189 passed in 2.82s**。 |
| `git diff --check` | 通过（只有仓库 LF/CRLF 提示，无空白错误）。 |
| 三类旧产品全文检索（运行源码、测试、脚本、CI、README、项目技能） | 零匹配；全仓库只剩素材来源声明的两处。 |

完整日志与截图已交付至 `E:/CODX/2026-10-03/shen/outputs`。


三项完整套件失败在修改前源码快照中逐项复现，断言相同：

| 用例 | 修改前已有问题 |
|---|---|
| `test_file_eater.py::test_petinstance_build_window_wires_file_eater` | 纯净模式不安装可选 file interpreter，旧测试仍期望安装次数为 1。 |
| `test_island_chat.py::test_pause_agent_link_for_hide_decision` | 原实现隐藏后保留后台监听，旧测试期望调用 pause。 |
| `test_requested_regressions.py::test_settings_dialog_position_avoids_pet_window` | offscreen 800×600 环境下设置窗口 sizeHint 为 720，位置断言仍发生重叠。 |

修改前隔离复现结果：`3 failed, 1 passed in 1.20s`，同时包含 Qt GUI 探针用例。
未修改这些无关产品行为或删掉失败断言来制造全绿。未推送，推送前仍需解决完整测试门禁并执行要求的三轮高负载时序复跑。

## 已知限制与回滚

工作状态来自本机 rollout 内部格式，并非官方公开稳定 API。普通 Chat 对话及云端任务不在监听范围；同目录中的 Codex CLI 任务也会被感知。
启动前历史状态不会回放，故启用时正在运行但没有继续写事件的任务要等待后续事件才会显示状态；新会话发现最长约 15 秒。
超过单行 64 KiB 的复杂记录会被跳过，积压超过 1 MiB 时分轮读取。格式升级需更新适配器。
保留现存两项鸭子音效的第三方素材来源声明，故 `THIRD_PARTY_NOTICES.md` 有两处旧产品来源文字；它们不参与任何模型或代理集成。
Git 历史和已有生成的旧安装包/可执行文件未重写；源码与打包输入已清理，运行已有旧 exe 仍需重新构建。
本轮没有修改用户实际 ChatGPT 配置/会话，没有迁移桌宠现用档案；联动开关仍默认关闭。
回滚可从 `E:/CODX/2026-10-03/shen/work/desktop-pet-before-cleanup.zip` 恢复选定源码，保留原用户未提交改动；不要对整个工作区执行硬重置。

## Git HEAD 差异附录

下列是本轮涉及的已追踪文件的 `git diff --numstat`，**含工作开始前的修改**。新增未追踪文件不出现在此输出，已在上表登记。

```text
1	3	.github/workflows/build-linux.yml
1	3	.github/workflows/build-macos.yml
0	14	.github/workflows/pr-test.yml
12	1	README.md
1	1	SKIll/En-SKILL.md
8	19	docs/ACCEPTANCE_TESTS.md
60	160	docs/AGENT_LINK_PROTOCOL.md
3	7	docs/BUGFIX-AND-FEATURES-2026-08-24.md
5	45	docs/CHANGELOG-DEV-SINCE-v4.1.0-2026-09-09.md
2	8	docs/CHAT-BACKGROUND-DISPLAY-2026-08-27.md
9	99	docs/CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md
0	1	docs/DEV-HANDOVER.md
0	371	docs/DSH-BRIDGE-PET-EVENT-CONTRACT-2026-09-02.md
0	170	docs/DSH-HUMAN-REQUEST-RESEARCH-2026-09-02.md
0	59	docs/DSH-REQUEST-EVENT-CATALOG.md
1	9	docs/HANDOVER_2026-09.md
8	39	docs/INDEX.md
0	1	docs/ISSUE-111-WINDOWS-SESSION-END-FFMPEG-2026-09-12.md
3	18	docs/NETWORK-PROXY-AND-VPN-2026-09-22.md
0	78	docs/OPEN-SOURCE-HARNESS-RISK-RESEARCH.md
0	1	docs/PET-STATE-MACHINE-AND-REPETITION-2026-09-02.md
0	268	docs/PHASE3_PROCESS_PLUGIN_RESEARCH.md
1	3	docs/PR-MERGE-LESSONS-2026-09-12.md
1	10	docs/PR-REPORT-GATES-2026-09-10.md
1	4	docs/PR-REPORT-PERSONAL-PHASE-A-2026-09-27.md
0	2	docs/PR-REPORT-PERSONAL-PHASE-B2-2026-09-27.md
2	9	docs/PR-REPORT-PR76-2026-09-10.md
1	10	docs/PROACTIVE_SCREEN_PLAN.md
3	33	docs/RELEASE-v4.2.0.md
0	5	docs/SETTINGS-INFORMATION-ARCHITECTURE-2026-08-27.md
4	7	docs/SETTINGS-REDESIGN-Q4-CLASSIFICATION-RESEARCH.md
3	34	docs/SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md
0	1	docs/SETTINGS-REPORT-PROBABILITY-2026-09-10.md
0	51	docs/UPSTREAM-INTEGRATION-2026-08-26.md
1	6	docs/superpowers/plans/2026-09-27-personal-edition-phase-b1.md
1	5	docs/superpowers/plans/2026-09-27-personal-edition-phase-b2.md
5	5	docs/superpowers/specs/2026-09-27-personal-edition-phase-b-design.md
0	4	integrations/dsh-pet-bridge/cordis.patch.yml
0	1795	integrations/dsh-pet-bridge/index.js
0	21	integrations/dsh-pet-bridge/package.json
0	82	integrations/dsh-pet-bridge/verify_import.mjs
3	3	pet/agent_event_normalizer.py
504	2456	pet/agent_link.py
10	93	pet/app.py
4	4	pet/behavior_detector.py
2	2	pet/chat/modern_styles.qss
1	1	pet/chat/settings_dialog.py
1	1	pet/chat/themes.py
3	6	pet/chat/widgets.py
212	132	pet/config.py
22	7	pet/context_menus/icons.py
9	290	pet/context_menus/shared.py
0	113	pet/dsh_control.py
0	57	pet/dsh_responder.py
0	449	pet/dsh_state.py
2	2	pet/dynamic_island.py
2	5	pet/exploration_watchdog.py
2	2	pet/exploration_watchdog_settings.py
0	882	pet/harness_launcher.py
69	66	pet/modern_settings_dialog.py
2	2	pet/multi_window_shared.py
0	453	pet/node_runtime.py
1	4	pet/persona_phrases.py
60	40	pet/persona_presets/legacy.json
0	30	pet/persona_presets/whale_maid.json
3	25	pet/persona_template.py
1	2	pet/report_gates.py
206	1	pet/settings_widgets.py
2	2	pet/speech_bubble.py
3	3	pet/stuck_detector.py
1	1	pet/win_job.py
26	79	pet/window.py
2	81	pet/window_alerts.py
2	8	pyproject.toml
1	5	scripts/build_linux.sh
1	5	scripts/build_macos.sh
0	138	scripts/fix_bridge_bundle.py
2	2	scripts/package_collision_candidate.py
1	40	tests/conftest.py
244	2037	tests/test_agent_link.py
0	526	tests/test_agent_link_dep_specs.py
11	79	tests/test_agent_link_threads.py
0	145	tests/test_bridge_hardfailure.js
0	74	tests/test_bridge_interaction_dedup.js
0	26	tests/test_bridge_manifest.js
0	101	tests/test_bridge_question_callid.js
0	88	tests/test_bridge_retry.js
0	123	tests/test_bridge_root_control.js
0	59	tests/test_bridge_user_action_guard.js
8	8	tests/test_chat_subsystem.py
1	1	tests/test_chat_themes.py
15	11	tests/test_config_domains.py
61	3	tests/test_config_instance.py
4	4	tests/test_config_key_migration.py
5	165	tests/test_config_schema.py
49	118	tests/test_desktop_pet_features.py
0	92	tests/test_dsh_control_client.py
0	370	tests/test_dsh_state.py
12	0	tests/test_file_interpret.py
0	81	tests/test_fix_bridge_bundle.py
0	327	tests/test_harness_launcher.py
0	590	tests/test_harness_lifecycle.py
8	8	tests/test_idle_low_fps.py
39	167	tests/test_menu_layout.py
54	0	tests/test_meta_round2_optimizations.py
9	9	tests/test_persona_settings.py
0	14	tests/test_persona_template.py
4	96	tests/test_pet_interaction_locks.py
10	31	tests/test_proactive.py
14	21	tests/test_settings_and_resources.py
8	9	tests/test_settings_process_isolation.py
6	6	tests/test_single_process_shared.py
6	114	tests/test_uninstall_cleanup.py
16	16	tests/test_vision.py
0	1	tests/test_voice_chime_service.py
0	562	tests/test_watchdog_control_wiring.py
0	790	tests/test_windows_node_env.py
```
