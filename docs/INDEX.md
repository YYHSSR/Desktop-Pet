# 文档索引

本文件是 `docs/` 与仓库根级文档的**唯一入口索引**。目的是按 Wikipedia 式的方式组织知识：每个文档一行，写明「它是什么」和「什么时候该读它」，读者可以顺着索引直接跳到相关条目，不必通读整个目录才知道功能模块在哪里。

怎么用：

1. **不知道从哪开始** → 先读根级入口表，再按领域找到对应分组。
2. **要改某块代码但不确定影响面** → 直接在本文搜索关键词（如 `ffmpeg`、`菜单`、`设置`、`ggml`），命中的行的「何时必读」就是判断依据。
3. **「何时必读」优先沿用 `AGENTS.md` 的 "Context pointers" 口径**（那是最权威的现行约定）；该节没有覆盖的文档，按文档正文自身标注的用途如实概括。

## 新文档入场规则

本节是规则的**出处**；任何新增文档都必须遵守：

1. **任何新文档必须在本文登记一行**，否则视为未定义的孤儿文档（审查时应作为缺陷提出）。
2. **新文档必须与相关文档互链**：正文中至少一处指向它所补充或取代的既有文档（用仓库相对路径），并同步更新本索引中那些文档行的「何时必读」。
3. **取代旧文档时**，先在本索引的「疑似过时/重复文档」小节登记旧文档与新文档的关系，再考虑是否删除；在删除前不得让两个文档同时作为权威描述存在。
4. **有明确生效范围的文档，标题或首段必须写清基线**（分支 / 版本 / 日期 / 实测用例数）；只描述"当时的快照"的文档必须自带「历史快照」警示（参见 `HANDOVER_2026-09.md` 的写法）。
5. **「何时必读」写触发条件，不写文档摘要**：写成"改 X 之前必读"，不要写成"介绍了 X"。

---

## 根级入口

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`../README.md`](../README.md) | 面向用户与贡献者的主说明：功能、安装、构建、更新日志与踩坑。 | 第一次接触项目；查用户可见行为、发布形态、上游同步状态。 |
| [`../AGENTS.md`](../AGENTS.md) | 工程指南：项目结构、变更纪律、CI 成本纪律、"Context pointers" 触发表、agent skills 入口。 | 提交任何代码之前；尤其改动碰撞选举、ffmpeg 派生、打包、菜单、设置、PR 合并前，先查 "Context pointers"。 |
| [`../CONTEXT.md`](../CONTEXT.md) | 领域术语表（Shared UX Contract / Settings System / Menu Action Model / Report Gate / Session-End Spawn Freeze 等）与禁用说法。 | 命名新概念、写设计文档、或需要确认"这个词在本项目里到底指什么"时；提案与既有术语冲突时必须先读。 |
| [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) | 第三方素材与组件的授权声明。 | 新增/替换动画素材、图标、字体或第三方库时。 |

---

## C++ / Python collision stage

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`../C++-Python/构建说明/项目重构说明.md`](../C++-Python/构建说明/项目重构说明.md) | 混合架构目标、迁移边界、ABI、性能与发布验收路线。 | 改碰撞原生后端、图像或解码迁移前必读；当前实测进度另见下行。 |
| [`../C++-Python/构建说明/README.md`](../C++-Python/构建说明/README.md) | 历次审查整改状态与最新复审入口。 | 评估候选包是否可发布时先读，并对照 2026-09-26 复审。 |
| [`../C++-Python/构建说明/项目整改复审与后续改进建议-2026-09-26.md`](../C++-Python/构建说明/项目整改复审与后续改进建议-2026-09-26.md) | R01–R11 复核、发布产物绑定、候选入口和基准场景改进。 | 接续本轮整改、引用圆链/静态墙性能数据或准备正式发布前必读。 |
| [`../C++-Python/构建说明/候选包索引-2026-09-26.md`](../C++-Python/构建说明/候选包索引-2026-09-26.md) | 2026-09-26 本地新旧候选包的准确路径、摘要和状态。 | 下载本地整改候选或核对旧包与新包身份前必读。 |
| [`COLLISION-NATIVE-BASELINE-2026-09-24.md`](COLLISION-NATIVE-BASELINE-2026-09-24.md) | 首批原生碰撞实现的行为与端到端性能基线。 | 选择默认后端、评估性能收益或发布原生 DLL 前必读。 |
| [`superpowers/plans/2026-09-24-collision-native.md`](superpowers/plans/2026-09-24-collision-native.md) | 首批实施任务与验收约束。 | 接续 P0–P3 的未完验收或审查本批实现范围时必读。 |
| [`superpowers/plans/2026-09-24-remediation.md`](superpowers/plans/2026-09-24-remediation.md) | 审查建议 R01–R11 的整改任务与验证步骤。 | 复核本次整改范围或接续未完成的干净机验收时必读。 |
| [`superpowers/plans/2026-09-26-candidate-promotion.md`](superpowers/plans/2026-09-26-candidate-promotion.md) | 候选晋级、完整收据和性能场景修正的实施计划。 | 接续 2026-09-26 复审 F01–F04 的实施或验证时必读。 |
| [`superpowers/specs/2026-09-27-personal-edition-phase-a-design.md`](superpowers/specs/2026-09-27-personal-edition-phase-a-design.md) | 个人版首批源码/配置基线与 Windows ChatGPT 状态来源验证设计。 | 创建状态探针或迁移个人版配置前必读，并对照 9/27 改造指导。 |
| [`superpowers/specs/2026-09-27-personal-edition-phase-b-design.md`](superpowers/specs/2026-09-27-personal-edition-phase-b-design.md) | 个人版第二批更新、默认网址与消费余额功能退役设计；已确认。 | 调整菜单、设置、配置迁移或后台余额/更新任务前必读。 |
| [`superpowers/plans/2026-09-27-personal-edition-phase-b1.md`](superpowers/plans/2026-09-27-personal-edition-phase-b1.md) | 第二批 B1：退役更新检查、内置网址与固定 Google 浏览器快捷项的步骤；待审阅。 | 实施 B1 前核对测试、旧配置迁移和实机验收。 |
| [`superpowers/plans/2026-09-27-personal-edition-phase-b2.md`](superpowers/plans/2026-09-27-personal-edition-phase-b2.md) | 第二批 B2：退役消费、余额和后台任务并保留 Cursor 的步骤；待审阅。 | B1 通过后实施 B2 前核对配置、生命周期和打包门禁。 |
| [`superpowers/plans/2026-09-27-personal-edition-phase-a.md`](superpowers/plans/2026-09-27-personal-edition-phase-a.md) | 个人版首批基线备份、Chat/Work 状态探针与证据交付步骤。 | 执行首批改造前必读，并核对对应设计与本机能力。 |
| [`../C++-Python/构建说明/候选晋级流程专项审查-2026-09-26-第二轮.md`](../C++-Python/构建说明/候选晋级流程专项审查-2026-09-26-第二轮.md) | 候选晋级第二轮检查及代码精简清单：清单契约、旧包 ABI、迁移位置、草稿恢复与删除阻碍。 | 清理重复/旧代码、移除 Python 回退或 JS 桥接前必读；第二轮交付状态另见最新交付复审。 |
| [`../C++-Python/构建说明/第二轮整改交付复审与剩余问题-2026-09-26.md`](../C++-Python/构建说明/第二轮整改交付复审与剩余问题-2026-09-26.md) | 第二轮交付复审、候选索引实测及 T01–T03 剩余问题。 | 回溯 T01–T03 缺陷时必读；修复后当前状态见最新整体复审。 |
| [`../C++-Python/构建说明/项目整体复审与清理记录-2026-09-26.md`](../C++-Python/构建说明/项目整体复审与清理记录-2026-09-26.md) | 最新 T01–T03 复核、338 个缓存文件清理结果及剩余目录限制。 | 继续清理项目缓存与构建产物前必读；当前构建问题见 9/27 复审。 |
| [`../C++-Python/构建说明/项目复审与构建缓存问题-2026-09-27.md`](../C++-Python/构建说明/项目复审与构建缓存问题-2026-09-27.md) | 9/27 复审：保留文件一致、测试复验与旧 CMake 缓存路径问题。 | 迁移后重新构建原生核心或判断当前验收状态时必读。 |
| [`../C++-Python/构建说明/个人版功能裁剪与ChatGPT状态联动改造指导-2026-09-27.md`](../C++-Python/构建说明/个人版功能裁剪与ChatGPT状态联动改造指导-2026-09-27.md) | 个人版功能退役、快捷网址、Windows ChatGPT Chat/Work 状态适配、图标和测试产物整理方案。 | 实施个人版菜单、联动或 E:\CODE/E:\CODX 目录整理前必读。 |

---

## 构建与发布

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`ONEDIR_PACKAGING.md`](ONEDIR_PACKAGING.md) | onedir 打包流水线：绿色版 zip + Inno Setup 安装包，目标是运行期零解压、不产生 `_MEI` 缓存。 | **改 PyInstaller spec、打包资源、或平台构建脚本（`scripts/build_onedir.ps1` / `build_macos.sh` / `build_linux.sh`）时必读**（AGENTS.md 口径）。 |
| [`STABLE_BUILDS.md`](STABLE_BUILDS.md) | 稳定版构建冻结记录：受保护文件名、构建隔离规则、防止误覆盖稳定版产物。 | **改发布/构建工作流时必读**（AGENTS.md 口径）。注意其冻结对象是 onefile 时代的 `dist/*.exe`，现行发布形态已是 onedir（见文末过时清单）。 |
| [`BUILD-CI-FAILURE-NOTES-2026-08.md`](BUILD-CI-FAILURE-NOTES-2026-08.md) | 三平台打包/CI 反复踩坑与最终解法汇总（持续更新）：脚本统一入口、资源漏收集、依赖只在叶子模块导入导致整族用例红等。 | CI 连续两轮红、或遇到"本机红 CI 绿"的依赖类假红时；动手重试之前先查这里是否已有同类记录。 |
| [`ACCEPTANCE_TESTS.md`](ACCEPTANCE_TESTS.md) | 验收测试文件清单：设置窗口、ChatGPT 状态联动、Qt 生命周期/全量三条验收路径的精确命令与当前实测基线。 | 提 PR 前跑验收、或需要确认"这个改动该跑哪几个测试文件"时；改动测试边界后必须同步更新本文基线数字。 |
| [`RELEASE-v4.2.0.md`](RELEASE-v4.2.0.md) | v4.1.0 → v4.2.0 的完整功能与修复汇总（含全部合入 PR 与各平台产物清单）。 | 写发布说明、回答"这个功能从哪个版本开始有"、或判断某行为是哪个 PR 引入时；**v4.2.0 之后的变更改看 [`RELEASE-v4.2.1.md`](RELEASE-v4.2.1.md)**。 |
| [`RELEASE-v4.2.1.md`](RELEASE-v4.2.1.md) | **v4.2.0 → v4.2.1 的发布稿（2026-09-23 已发布）**：57 个已合并 PR / 192 个提交的完整汇总（含 #181 歌词代理修复、#182 流畅度与岛墙批次）。文件分两段：`## 📦 下载` 至 `## 🙏 致谢` 是**发布正文**，`RELEASE-BODY-END` 注释之后的**发布前测试清单**（勾选式）、**视频预演脚本**（逐段分镜）与维护者清单**只在仓库内使用、不随 Release 发布**。 | **准备发布、跑人工验收、或录制演示视频时必读**；改版本号、打 tag、换 Release 正文（用文件头那行命令生成 body.md，别整份贴）、或需要"这一版到底该验哪些行为"的清单时。 |

---

## 渲染、解码与窗口结构

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`WINDOW_PY_SPLIT_GUIDE.md`](WINDOW_PY_SPLIT_GUIDE.md) | `pet/window.py`（`PetWindow`）的演进指南：功能驱动的拆分流程、控制器边界与架构红线。 | **给 `window.py` 加功能前必读**（README 口径）；凡新功能预计超过约 100 行、或需改 3 个以上同域方法、或行数预算告警时，先按本文拆控制器。 |
| [`QT-LIFECYCLE-FULL-SUITE-STABILIZATION-2026-09.md`](QT-LIFECYCLE-FULL-SUITE-STABILIZATION-2026-09.md) | Qt 生命周期与全量套件稳定性收口记录：Windows/offscreen 下原生崩溃（0xC0000005 / 0xC0000374）的归属分析与 QObject owner 清理方案。 | 全量套件出现随机原生崩溃、或改动 `PetWindow.closeEvent()`、`PetSpeechBubble` owner 清理、菜单执行 seam、后台资源 teardown 时。 |

> 与 ffmpeg 派生、预热调度、Windows 关机/注销路径相关的权威档案是 issue #111（见下方「专项 issue 档案与事故复盘」分组），因为改这几处代码同时牵涉渲染生命周期与会话拆除时序。

---

## 交互、菜单与设置

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md`](CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md) | 右键菜单图标调研与双模板（`modern-default-v1`）重构记录，含菜单布局树的顺序/显隐/别名/图标覆盖规则与 2026-09 生命周期收口补充。 | **改右键菜单结构、样式、交互或平台行为时必读**（AGENTS.md 口径）。 |
| [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) | Settings System 的变更门禁：一条设置能否进入设置页的准入条件、以及变更的准出证据要求。 | **新增、移动、重命名、删除或改变任何持久设置、以及修改设置页布局/保存语义/平台可见性/依赖关系之前必读**（AGENTS.md 口径）。 |
| [`SETTINGS-INFORMATION-ARCHITECTURE-2026-08-27.md`](SETTINGS-INFORMATION-ARCHITECTURE-2026-08-27.md) | 设置页信息架构重组记录：按用户任务划分的页面归属表、渐进显示与禁用规则、视觉密度。 | 决定某个新设置该放哪一页/哪一组；确认"同一概念不得跨页重复"的现行归属时。 |
| [`SETTINGS-REDESIGN-Q4-CLASSIFICATION-RESEARCH.md`](SETTINGS-REDESIGN-Q4-CLASSIFICATION-RESEARCH.md) | Q4 调研：侧栏分类（7 个稳定能力域）的跨平台 IA 结论与第一方 HIG 出处。 | 为"要不要新增一级侧栏页"找判断依据与先例出处时。 |
| [`SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md`](SETTINGS-REDESIGN-Q6-Q7-DOMAIN-LAYOUT-DECISION.md) | Q6/Q7 讨论稿：能力域划分规则、布局系统、UI skill 评估，含菜单树兜底优先级链。 | 讨论能力域边界、菜单树降级/回退语义时；注意本文自标"讨论稿，不作为实现规范"。 |
| [`SETTINGS-REDESIGN-IMPLEMENTATION-LOG.md`](SETTINGS-REDESIGN-IMPLEMENTATION-LOG.md) | 设置与菜单重构的实现及踩坑记录：菜单动作注册表、菜单编辑器、七个能力域、草稿写回语义。 | 需要了解菜单/设置重构的**实际实现结构**与其断点续作位置（`.scratch/settings-redesign/HANDOFF.md`）时。 |
| [`SETTINGS-REDESIGN-UI-ACCEPTANCE.md`](SETTINGS-REDESIGN-UI-ACCEPTANCE.md) | 设置页逐页 UI 验收记录：窗口矩阵（尺寸×明暗）与最终保留的截图证据清单。 | 修改设置页视觉后需要对照既有验收矩阵重跑、或需要定位合理截图证据路径时。 |
| [`SETTINGS-REPORT-PROBABILITY-2026-09-10.md`](SETTINGS-REPORT-PROBABILITY-2026-09-10.md) | 事件汇报概率门（`report_gates`）的设置变更记录：8 个门的准入契约（setting_id / domain / 搜索别名）与准出证据。 | 增删/调整汇报概率门、或按 `SETTINGS-CHANGE-GATES.md` 需要一份设置变更契约的书写范例时。 |
| [`BUGFIX-AND-FEATURES-2026-08-24.md`](BUGFIX-AND-FEATURES-2026-08-24.md) | 一次性开发记录：气泡显示不抢输入焦点、EXE 图标裁剪、右键菜单「生小肥鱼」独立进程启动、菜单图标补齐。 | 改窗口激活/焦点策略（`WS_EX_NOACTIVATE` 类问题）、图标生成（`scripts/make_icon.py`）或子进程启动路径时。 |

---

## 聊天、语音与内容功能

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`CHAT-BACKGROUND-DISPLAY-2026-08-27.md`](CHAT-BACKGROUND-DISPLAY-2026-08-27.md) | AI 对话背景显示调整记录：两套窗口各自的背景图片/不透明度/填充模式，以及消息卡片可读性方案。 | 改对话窗口背景、`cover`/`contain`/`stretch` 语义、或消息区 QSS（`message-bubble` vs `message-surface`、`QScrollArea` 调色板）时。 |
| [`ISSUE-EDGE-TTS-VOICE-DEPRECATION-2026-09-22.md`](ISSUE-EDGE-TTS-VOICE-DEPRECATION-2026-09-22.md) | 事故档案：edge 合成「没声音」的两条根因（微软下架音色 + 连发偶发空音频）与对策（音色表兜底、重试、非空缓存判定）。 | **改语音报时的合成/缓存路径、或再遇到「配置了却没声音」时必读**；它记录了 `NoAudioReceived` 为什么不等于网络问题的判断链。 |

---

## Agent 与 ChatGPT 工作状态联动

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`AGENT_LINK_PROTOCOL.md`](AGENT_LINK_PROTOCOL.md) | 多 Agent 联动统一事件协议与扩展指南：本地文件事件总线、六态词汇、第三方 Agent 接入与新增内置 Agent 的步骤。 | 接入新 Agent、改事件归一（`normalize_event_state`）或六态词汇时；面向集成方的对外协议口径以本文为准。 |
| [`PET-STATE-MACHINE-AND-REPETITION-2026-09-02.md`](PET-STATE-MACHINE-AND-REPETITION-2026-09-02.md) | Pet 状态机与重复检查说明：状态聚合与分析检测器的独立处理链与两个重复检测器的区别。 | 改状态、动画切换、提醒或风险判断时；尤其要避免把"重复检查"和"状态机"当成同一个东西。 |

---

## 台词、人格与预设数据

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`PERSONA-PHRASES-PRESET-STORAGE-2026-09-08.md`](PERSONA-PHRASES-PRESET-STORAGE-2026-09-08.md) | 台词预设的存储与加载架构：内置预设（数据文件）/ 用户台词（config）/ 便携模板（运行时生成）三类内容的归属与路由。 | **改台词预设文件 `pet/persona_presets/*.json`、短语加载 `persona_phrases.py`、或表达风格语义（`dialogue_mode` / `dialogue_phrases`）之前必读**（AGENTS.md 口径）。 |
| [`PERSONA-TEMPLATE-FIELD-ALIGNMENT-2026-09-05.md`](PERSONA-TEMPLATE-FIELD-ALIGNMENT-2026-09-05.md) | 台词模板变量名契约：代码 kwargs ↔ 模板 `{占位符}` 的逐 key 对照表（由 `pet/persona_template.py` 常量自动生成）。 | 新增/重命名模板变量、或改事件可用变量集合时；必须先改代码常量再重新生成本文，否则 `test_persona_template.py` 的 AST 双向校验会红。 |

---

## 主动识屏与感知

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`PROACTIVE_SCREEN_PLAN.md`](PROACTIVE_SCREEN_PLAN.md) | 主动识屏与多 Agent 感知的已验证设计方案 v1：低功耗、多开友好、默认关闭，逐条技术依据与出处。 | 追溯识屏机制（白名单、dHash 变化检测、软流控、负坐标多屏裁剪）的**设计依据与出处**时。 |

---

## 专项 issue 档案与事故复盘

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`ISSUE-111-WINDOWS-SESSION-END-FFMPEG-2026-09-12.md`](ISSUE-111-WINDOWS-SESSION-END-FFMPEG-2026-09-12.md) | issue #111 专项档案：Windows 关机/注销弹 `0xc0000142` 的根因（会话拆除期派生进程）与「会话结束冻结」闸门设计。 | **改 ffmpeg 派生（`webm_clip` 的 reader / 首帧 / meta / exe 探测）、预热调度、或任何在 Windows 关机/注销时运行的东西（`session_watcher`、`match_shutdown`、`AppShell._on_session_end`）时必读**（AGENTS.md 口径）。 |
| [`PR-MERGE-LESSONS-2026-09-12.md`](PR-MERGE-LESSONS-2026-09-12.md) | PR 合并三则教训：叠放 PR 在 squash 父 PR 后必然冲突、预算/红线只在两 PR 组合时才破、时序测试 flake 纪律。 | **合并 PR 之前必读**（AGENTS.md 口径）。 |
| [`NETWORK-PROXY-AND-VPN-2026-09-22.md`](NETWORK-PROXY-AND-VPN-2026-09-22.md) | 代理/VPN 影响面清单：歌词取词（代理下 20~41s 超时）、edge-tts 语音、更新检查（jsdelivr 只有代理能通）、余额/识屏/对话（用户自配端点）、localhost 类（本地 TTS / Agent 联动）各自该不该走代理，附 30 秒探针与推荐分流配置。 | **改任何联网功能，或用户报「某功能昨天还好好的 / 歌词没了 / 语音不出声 / 更新检查失败」时必读**（系统代理与 VPN 是一等嫌疑）；也用于回答"桌宠为什么不自己绕过代理"。 |

> 注：`AGENTS.md` 的 "Context pointers" 还指向 `docs/ISSUE-42-POSIX-COLLISION-IPC-2026-08-31.md`（碰撞选举 / QLocal IPC / 协调者锁），但该文件在当前工作树中不存在。改动碰撞选举、QLocal IPC 或协调者锁之前，需要先确认该文档是被删除、改名还是从未入库——本索引无法为它登记有效条目。

---

## PR 报告存档

- [PR-REPORT-SILENT-PET-2026-10-03.md](PR-REPORT-SILENT-PET-2026-10-03.md)：移除声音与启动入口、设置页重排和重新打包的验证证据。

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`PR-REPORT-PURE-PET-REPACK-2026-10-03.md`](PR-REPORT-PURE-PET-REPACK-2026-10-03.md) | 纯桌宠 AI 模块与失效测试清理、Work/Codex 实机联动和重新打包验收。 | 核对本轮裁剪、构建依赖或运行新便携包前必读。 |
| [`PR-REPORT-CHATGPT-LINK-2026-10-03.md`](PR-REPORT-CHATGPT-LINK-2026-10-03.md) | 本轮旧集成清理、Work/Codex 联动、逐文件增量与实机验证。 | 修改本机工作状态读取、桌面端启动或核对本轮清理结果前必读。 |
| [`PR-REPORT-COLLISION-REMEDIATION-2026-09-24.md`](PR-REPORT-COLLISION-REMEDIATION-2026-09-24.md) | 原生碰撞 R01–R11 整改、候选包来源与本机验证记录。 | 继续原生后端开发、复核 ABI/依赖闭包，或准备干净 Windows 发布验收前必读。 |
| [`PR-REPORT-CANDIDATE-PROMOTION-2026-09-26.md`](PR-REPORT-CANDIDATE-PROMOTION-2026-09-26.md) | F01–F04 后续整改、候选收据与基准重测证据。 | 晋级 Windows 发布、核对新基准结果或追查未完成外部验收时必读。 |
| [`PR-REPORT-CANDIDATE-SECOND-REVIEW-2026-09-26.md`](PR-REPORT-CANDIDATE-SECOND-REVIEW-2026-09-26.md) | S01–S05 整改及 T01–T03 后续补强：运行时清单、候选身份、草稿占位附件、输入与资源门禁。 | 首跑候选 CI、重试草稿晋级或审查当前候选身份前必读。 |
| [`PR-REPORT-PERSONAL-PHASE-A-2026-09-27.md`](PR-REPORT-PERSONAL-PHASE-A-2026-09-27.md) | 个人版首批源码/配置基线与 ChatGPT 状态探针的实机证据及未验收项。 | 接续个人版批次 B 或设计 Chat/Work 状态适配前必读。 |
| [`PR-REPORT-PERSONAL-PHASE-B1-2026-09-27.md`](PR-REPORT-PERSONAL-PHASE-B1-2026-09-27.md) | 个人版更新和内置网址入口退役的变更、性能与本机测试记录。 | 接续 B2 余额和成本裁剪前必读。 |
| [`PR-REPORT-PERSONAL-PHASE-B2-2026-09-27.md`](PR-REPORT-PERSONAL-PHASE-B2-2026-09-27.md) | 个人版余额与本轮消耗退役、累计候选包身份及 Windows 实机验证记录。 | 接续批次 C 或复核个人版候选时必读。 |
| [`PR-REPORT-ISLAND-HIDDEN-CHAT-DEADLOCK-2026-09-23.md`](PR-REPORT-ISLAND-HIDDEN-CHAT-DEADLOCK-2026-09-23.md) | 纯桌宠版岛隐藏死锁修复：无聊天构建 hidden_chat 单击路由回退展开卡片（岛能力开关 + 设置页开关按构建变体隐藏）。 | 改灵动岛单击路由 / hidden_chat 设置 / 打包变体（无 pet.chat）行为时。 |
| [`PR-REPORT-TEMPLATE.md`](PR-REPORT-TEMPLATE.md) | PR 报告模板：三份交付证据（修改文件说明 / 性能分析 / 实机运行记录）的逐节骨架与判定标准。 | **开新 PR 写报告前必读并整份复制**；2026-09-22 起三份证据是硬要求（`AGENTS.md` Delivery evidence discipline），由 `tests/test_pr_report_discipline.py` 机器化校验。 |
| [`PR-REPORT-PR76-2026-09-10.md`](PR-REPORT-PR76-2026-09-10.md) | PR76 批次的完整报告：事件汇报概率门 + Persona 模板升级 + 全链路错误语义统一（46 文件，+3004/−917）。 | 追溯 PR76 批次改了什么、以及概率门/persona 模板/错误语义三条线的组合动机时。 |
| [`PR-REPORT-GATES-2026-09-10.md`](PR-REPORT-GATES-2026-09-10.md) | 汇报概率门专项 PR 报告：8 个门表、判决语义（`roll < probability`）、可注入 rng 的测试考量、提交点自检。 | 调整汇报概率门、或需要"为什么未知事件不抽稀/边界取小于"这类判决语义依据时。 |
| [`PR-REPORT-VOICE-CHIME-2026-09-15.md`](PR-REPORT-VOICE-CHIME-2026-09-15.md) | 语音报时（voice_chime）PR 报告：六种调度模式、20s tick 判定与槽位盖戳幂等、edge-tts 合成与缓存、设置页接入。 | 改语音报时调度/合成/播放、或需要复用其"纯逻辑零 Qt 依赖可测"结构时；也要改共用音频通道的第三方（节日语音 / 点击台词朗读）时。 |
| [`PR-REPORT-FESTIVAL-REMINDER-2026-09-16.md`](PR-REPORT-FESTIVAL-REMINDER-2026-09-16.md) | 节日提醒（festival_reminder）PR 报告：46 个日子、314 条节日文案、提醒时机二选一、与语音报时共用音频通道且报时让位。 | 改节日数据/文案/提醒时机，或调整与语音报时的让位规则时。 |
| [`PR-REPORT-SELF-TALK-PRECACHE-2026-09-20.md`](PR-REPORT-SELF-TALK-PRECACHE-2026-09-20.md) | 点击台词朗读 + 本机语音预缓存（`self_talk_speak_enabled` / `self_talk_voice_precache_enabled`）：复用报时音频通道、后台补齐、缓存命名契约与 0 字节残file 判定。 | 改点击朗读/预缓存触发点、台词语音缓存命名或残file 判定、或调整 `_chime_wanted` 的通道存在性条件时。 |
| [`PR-REPORT-SELF-TALK-IMAGE-CHANCE-2026-09-20.md`](PR-REPORT-SELF-TALK-IMAGE-CHANCE-2026-09-20.md) | 自言自语「配图概率」（`self_talk_image_chance`，默认 30）：把"文本+图片等权随机"（实测出图 82.8%）改成先掷骰子再在池内等权选。 | 改 `show_random_self_talk` 的抽签逻辑、或需要"为什么默认值从等权变成 30%"的依据与回滚口径时。 |
| [`PR-REPORT-SETTINGS-INTERACTION-TABS-2026-09-22.md`](PR-REPORT-SETTINGS-INTERACTION-TABS-2026-09-22.md) | 「互动」域设置页分页 PR 报告：页内任务标签（点击与音效 / 自言自语）+ 整域抽成 `pet/settings_interaction.py`（对话框净减 94 行、预算首次因拆分下调）；含"功能不丢"的机器化断言与三档宽度截图。 | 改互动域的行/分组/标签、把某个域也改成分页、或调整 `scripts/capture_settings_pages.py` 的截图入口时。 |
| [`PR-REPORT-LOCAL-WIP-BATCH-2026-09-22.md`](PR-REPORT-LOCAL-WIP-BATCH-2026-09-22.md) | 本地 WIP 批次 PR 报告：交付证据纪律（三份证据 + 机器化校验）、`build_onedir.ps1` 的 Qt 绑定排他（不修则构建被 PyInstaller 中止）、产物 TTS 自检脚本（真产物假红 → 修掉）、`character_head_box()` 与 shenshen 头部框数据。 | 改 `scripts/build_onedir.ps1` 的排除清单、`scripts/verify_bundle_tts.py` 的闭包判定、`pet/catalog.py` 的 `body_box`/`head_box` 取值，或要写新的 PR 报告（含三个必备章节的实例）时。 |
| [`PR-REPORT-ISLAND-RESHOW-NOCHAT-2026-09-23.md`](PR-REPORT-ISLAND-RESHOW-NOCHAT-2026-09-23.md) | 纯桌宠版「桌宠隐藏后单击灵动岛无反应」的发布后补丁报告（`1c3a59c`）：岛发 `chat_requested` → 无 Chat 变体的 `_show_island_chat` 可用性闸门静默返回，整次点击被吞；改为无对话能力时直接「显示桌宠」。 | 改灵动岛单击路由 / `_chat_from_island` / 隐藏态交互面 / 无 Chat 变体的可用性闸门时；或再遇「点了没反应」类反馈要先看这条链路（岛 → AppShell → 闸门）时。 |
| [`PR-REPORT-PERF-ISLAND-CONSOLIDATED-2026-09-23.md`](PR-REPORT-PERF-ISLAND-CONSOLIDATED-2026-09-23.md) | 流畅度/解码减负 + 岛远端硬墙 + 音效缓存 + 设置收口的 PR 报告：走路帧间补点（位置交付 28.6Hz→~160Hz）、碰撞 >50ms 卡顿 133→3、子宠进程补挂远端硬墙、零拷贝消融的诚实记录（崩溃案机理=绘制重入，未结案）。 | 改 `movement.move_anim_tick`/走路位移、webm 冷路径/首帧缓存/meta 后台化、岛碰撞远端模式与静态成员发布、音效候选缓存、或「多开」设置项时；排查 Qt6Gui 绘制重入崩溃时也要读（含消融对比与取证指针）。 |
| [`PR-REPORT-DESKTOP-AGENT-LINK-2026-09-29.md`](PR-REPORT-DESKTOP-AGENT-LINK-2026-09-29.md) | 桌面端软件联动（Codex 桌面端原生监控 + F08 多会话聚合 + F09 隐藏持续采集）交付报告：支持矩阵、微秒级延迟分析、交错与迟到回合实机验证。 | 查阅桌面端联动机制、Codex 轨迹尾读、多会话交错聚合与隐藏采集实现时。 |

---

## 交接、阶段快照与变更汇总

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`DEV-HANDOVER.md`](DEV-HANDOVER.md) | 开发交接文档：本地运行、改配置、加功能、跑测试、重新打包的全流程，面向接手「语音报时」定制分支的开发者。 | 新人上手或需要一份"从零到跑起来"的完整流程时；它是三份交接文档中基线最新的一份（2026-09-16）。 |
| [`HANDOVER_2026-09.md`](HANDOVER_2026-09.md) | perf/stage-1 性能+结构线的交付手册（自带历史快照警示，含后续批次更正）。 | 追溯 perf/stage-1 那条线做了什么时；**正文数值已被后续批次更新**，实际以代码与 `_plan/current/` 档案为准。 |
| [`CHANGELOG-DEV-SINCE-v4.1.0-2026-09-09.md`](CHANGELOG-DEV-SINCE-v4.1.0-2026-09-09.md) | 自 v4.1.0 以来开发版变更汇总：按合入顺序的主线演进表、性能线/结构线细节，含"实现后被回滚/取代"的口径说明。 | 需要逐 PR 粒度的开发期变更脉络、或核对"某功能是否真的上线"（第六节列了被取代项）时。 |

---

## 调研与设计稿（尚未进入实现）

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|

---

## agent 工作约定（`docs/agents/`）

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [`agents/domain.md`](agents/domain.md) | 单上下文仓库的领域文档约定：先读根 `CONTEXT.md`，再读相关 ADR，术语保持一致，与 ADR 冲突的方案要显式标注。 | 探索一个陌生领域、或提出可能与既有决策冲突的方案之前。 |
| [`agents/issue-tracker.md`](agents/issue-tracker.md) | Local Markdown issue tracker 约定：feature/spec/ticket 的目录结构与状态行格式。 | 创建或读取 issue、spec、ticket 时（`.scratch/<feature-slug>/`）。 |
| [`agents/triage-labels.md`](agents/triage-labels.md) | 五个标准 triage 状态的映射表与含义。 | 给 issue 打标签、或需要把外部角色名映射到本仓库状态名时。 |
| [`agents/handoff.md`](agents/handoff.md) | 工作交接约定：`.scratch/<feature-slug>/HANDOFF.md` 的必备字段与续作时的校验步骤。 | 跨任务/跨上下文窗口续作未完成工作时；开工前先读 handoff 并核对 `git status`。 |

---

## 疑似过时/重复文档

通读全部 `docs/*.md` 后的发现如下。判定口径：**描述内容与现状差距悬殊、且已被更新的文档取代**（过时）；或**两份文档覆盖同一主题且读者无法判断以谁为准**（重复）。本小节只登记，不构成删除建议——处置需由维护者决定。

### 疑似过时



### 疑似重复
