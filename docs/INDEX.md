# 文档索引

当前基线：2026-10-04，静音鲸鱼娘与ChatGPT Work/Codex工作联动。

## 新文档入场规则

新增文档必须在此登记并与相关文档互链。说明适用的当前版本与何时读取；替代旧文档时记录关系，避免重复权威说明。

## 根级入口

| 文档 | 用途 | 何时必读 |
|---|---|---|
| [README](../README.md) | 使用、构建与入口说明 | 安装、运行或准备打包时。 |
| [AGENTS](../AGENTS.md) | 工程和验证纪律 | 修改项目之前。 |
| [CONTEXT](../CONTEXT.md) | UI与模块协作契约 | 修改设置、菜单或生命周期之前。 |
| [第三方声明](../THIRD_PARTY_NOTICES.md) | 素材和运行库许可 | 重新分发之前。 |

## 开发指南与PR报告存档

| 文档 | 一句话内容 | 何时必读 |
|---|---|---|
| [AGENT_LINK_PROTOCOL.md](AGENT_LINK_PROTOCOL.md) | 本机会话日志、状态映射和有界增量读取 | 修改ChatGPT/Codex或自定义通道之前。 |
| [COLLISION-NATIVE-BASELINE-2026-09-24.md](COLLISION-NATIVE-BASELINE-2026-09-24.md) | 原生碰撞、Python一致性与构建证据 | 修改碰撞求解、IPC或原生DLL之前。 |
| [CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md](CONTEXT-MENU-RESEARCH-AND-REFACTOR-2026-08-25.md) | 菜单图标尺寸及Qt菜单生命周期；首段标注当前固定菜单 | 修改菜单几何、图标、子菜单或事件循环之前。 |
| [DEV-HANDOVER.md](DEV-HANDOVER.md) | 当前运行、入口归属、线程收口和交付纪律 | 首次接手工程或准备交付时。 |
| [ISSUE-111-WINDOWS-SESSION-END-FFMPEG-2026-09-12.md](ISSUE-111-WINDOWS-SESSION-END-FFMPEG-2026-09-12.md) | Windows关机/注销时ffmpeg进程回收 | 修改播放器进程或会话结束处理之前。 |
| [ONEDIR_PACKAGING.md](ONEDIR_PACKAGING.md) | 当前Windows便携目录、资源与验收步骤 | 构建和交付便携版之前。 |
| [PERSONA-PHRASES-PRESET-STORAGE-2026-09-08.md](PERSONA-PHRASES-PRESET-STORAGE-2026-09-08.md) | 台词预设加载、覆盖和保存规则 | 修改台词资源或导入导出之前。 |
| [PERSONA-TEMPLATE-FIELD-ALIGNMENT-2026-09-05.md](PERSONA-TEMPLATE-FIELD-ALIGNMENT-2026-09-05.md) | 事件字段与文案占位符语义 | 修改联动字段或自定义文案渲染之前。 |
| [PET-STATE-MACHINE-AND-REPETITION-2026-09-02.md](PET-STATE-MACHINE-AND-REPETITION-2026-09-02.md) | 桌宠动作状态机及联动重复控制 | 修改动作选择和行为检测之前。 |
| [PR-MERGE-LESSONS-2026-09-12.md](PR-MERGE-LESSONS-2026-09-12.md) | 配置、时序与合并回归经验 | 合并多人改动或处理时序失败之前。 |
| [PR-REPORT-PET-CLEANUP-TRAY-2026-10-04.md](PR-REPORT-PET-CLEANUP-TRAY-2026-10-04.md) | 上一轮功能精简、气泡和托盘的真实验证 | 追溯退役功能、气泡锚点或第一版托盘时。 |
| [PR-REPORT-PURE-PET-REPACK-2026-10-03.md](PR-REPORT-PURE-PET-REPACK-2026-10-03.md) | 静音桌宠与工作联动的构建基线 | 追溯纯净版范围和原始打包结果时。 |
| [PR-REPORT-TEMPLATE.md](PR-REPORT-TEMPLATE.md) | 修改文件说明、性能分析与实机运行记录模板 | 创建行为变更交付报告时。 |
| [QT-LIFECYCLE-FULL-SUITE-STABILIZATION-2026-09.md](QT-LIFECYCLE-FULL-SUITE-STABILIZATION-2026-09.md) | Qt对象、线程与测试退出期收口 | 诊断Qt生命周期和事件循环崩溃之前。 |
| [SETTINGS-CHANGE-GATES.md](SETTINGS-CHANGE-GATES.md) | 设置默认值、迁移、保存、响应布局和平台门禁 | 改动持久设置或控件之前。 |
| [SETTINGS-REDESIGN-UI-ACCEPTANCE.md](SETTINGS-REDESIGN-UI-ACCEPTANCE.md) | 设置界面的布局与可访问性验收记录 | 复核布局退化、文字裁切或焦点问题时。 |
| [SETTINGS-REPORT-PROBABILITY-2026-09-10.md](SETTINGS-REPORT-PROBABILITY-2026-09-10.md) | 联动事件气泡的概率门语义 | 修改事件概率或覆盖策略之前。 |
| [STABLE_BUILDS.md](STABLE_BUILDS.md) | 历史onefile产物保护规则 | 修改构建输出名或分发目录之前。 |
| [WINDOW_PY_SPLIT_GUIDE.md](WINDOW_PY_SPLIT_GUIDE.md) | PetWindow职责与拆分边界 | 整理窗口实现或跨模块状态之前。 |
| [PR-REPORT-WHALE-TRAY-FEEDBACK-2026-10-04.md](PR-REPORT-WHALE-TRAY-FEEDBACK-2026-10-04.md) | 鲸鱼娘托盘反馈、回应首行、内置检测及本轮打包推送证据 | 追溯本轮自启修复、菜单回应或文档清理时。 |

## Agent工作规范

| 文档 | 用途 |
|---|---|
| [问题追踪](agents/issue-tracker.md) | 本地问题目录与规范。 |
| [领域文档](agents/domain.md) | CONTEXT和ADR组织规则。 |
| [交接](agents/handoff.md) | 未完成工作的断点记录。 |
| [分诊](agents/triage-labels.md) | 本地问题状态。 |

## 历史材料精简

本轮删除43份旧聊天、声音、识屏、灵动岛说明，以及重复的旧计划和历史报告；当前功能以README、CONTEXT、DEV-HANDOVER和上述报告为准。旧材料先保存在仓库外before-feedback.zip，同时仍可从Git历史恢复。许可证、第三方声明、有效构建指南、Qt生命周期和碰撞约束保留。
