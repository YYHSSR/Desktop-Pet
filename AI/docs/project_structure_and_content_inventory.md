# 桌面宠物项目（Desktop Pet）工程结构与全量内容整理

> **说明**：本文档遵循 `SKIll/En-SKILL.md` 规范收录于 `AI/docs/`，去除临时版本号与历史发布标签，以架构和模块职责为导向，全面梳理当前工程的文件组织、核心子系统、模块分工与交互边界。

---

## 1. 项目定位与核心技术栈

本项目是一个基于 **Python 3 + PySide6 (Qt for Python)** 开发的高性能桌面宠物独立应用程序，并辅以 **C++ 原生加速核心** 与 **Node.js 扩展桥接**：
- **GUI 与主逻辑**：Python + PySide6（透明置顶无边框窗口、右键可编排菜单、现代卡片式设置面板、灵动岛、气泡对话框）。
- **动效与多媒体**：基于 ffmpeg 的 WebM/透明视频帧级扇出解码、同角色多窗口共享解码器、WinMM 音频播放、Edge TTS 离线/在线语音报时。
- **性能核心**：C++ 编写的碰撞检测与物理计算原生库（`C++-Python/`），通过 C-API 与 Python ctypes 绑定加速高频碰撞计算。
- **多开与进程协调**：基于操作系统内核文件锁（Windows/POSIX）与 `QLocalServer/QLocalSocket` 本地 IPC 通信，支持单进程多窗口与多进程协同。
- **扩展与联动**：内置独立 AI 会话窗口、桌面智能识屏、Agent 任务状态联动（Cursor / ChatGPT 等）及 DSH 协议桥接。

---

## 2. 顶级目录结构总览

```text
e:/CODE/desktop-pet/
├── pet/                 # Python 核心业务逻辑包（108 个核心文件，包含 UI、服务、IPC、配置等）
│   ├── chat/            # 独立 AI 对话窗口与模型服务提供层
│   ├── context_menus/   # 模块化上下文菜单（现代右键菜单、快捷启动、图标体系）
│   ├── menu_templates/  # 菜单布局 JSON 模板（默认配置与编排定义）
│   ├── native/          # C++ 原生动态库加载器与自检机制
│   └── persona_presets/ # 桌宠人设台词预设库（内置台词与语气表达）
├── assets/              # 运行期静态多媒体资源库（动效、角色、音频、界面图元）
│   ├── characters/      # 角色核心包（动画分镜、清单与贴图边缘定义）
│   ├── big_blue_fat_fish/# 角色模型扩展包
│   ├── chat/            # 聊天气泡背景、角色头像等
│   └── sounds/          # 交互提示音、点击音效
├── C++-Python/          # C++ 碰撞检测与原生计算核心源码及构建配置
│   ├── src/             # C++ 核心源文件与 C-API 接口
│   ├── include/         # 头文件定义
│   └── 构建说明/        # 架构重构备忘、审查记录与自检说明
├── integrations/        # 外部框架或平台的桥接插件（如 dsh-pet-bridge）
├── packaging/           # 打包分发定义（PyInstaller 规格、Inno Setup 脚本、打包入口）
├── scripts/             # 工程与运维脚本（自动化构建、页面截图、测试、依赖提取）
├── tests/               # 完整自动化测试套件（160+ 个测试文件，涵盖逻辑、UI、架构守卫）
├── docs/                # 项目架构文档、决策记录（ADR）、系统说明与演进索引
├── SKIll/               # 工程治理与开发标准（环境规范、产出治理、Agent 研发工作流）
│   ├── En-SKILL.md      # 工具链路径、AI 产出统一收纳目录与 Walkthrough 报告规范
│   └── Agent-Code/      # 通用 Agent 研发流程指导及参考手册
├── .agents/             # IDE 智能体专用扩展技能
│   └── skills/          # PySide6 UI 规范与代码走查技能
└── AI/                  # 【AI 治理根目录】所有由 AI 生成的文档、报告与临时产物
    ├── docs/            # 技术实现计划与架构设计方案（如本文档）
    ├── reports/         # 任务总结报告 (Walkthrough)
    ├── markdown/        # MarkItDown / MinerU 转换产物
    ├── extractions/     # 结构化数据抽取
    └── temp/            # 临时过渡文件与缓存（交付前清理）
```

---

## 3. 核心子系统与文件清单详解 (`pet/`)

### 3.1 核心入口与应用生命周期
- `__main__.py`：程序主入口，解析启动参数，初始化单例保护与错误钩子。
- `app.py` (`PetApp`)：全局应用控制器，管理配置生命周期、角色热重载、托盘图标、全局快捷键、IPC 启动以及后台服务的装配。
- `window.py` (`PetWindow`)：桌面宠核心交互窗口（保持预算控制在 4648 行以内），管理宠物拖拽、物理运动、贴边停靠、动画触发、点击反馈与各扩展组件桥接。
- `window_placement.py` / `window_screen.py`：多显示器 DPI 适配、工作区尺寸感应、窗口边缘吸附与边界夹持。
- `session_watcher.py`：操作系统注销与关机事件监听，激活会话冻结闸门（防止注销期唤醒子进程导致崩溃）。
- `runtime_cleanup.py` / `uninstall_cleanup.py`：运行时临时资源释放与清理。

### 3.2 动效与视频流解码引擎
- `webm_clip.py`：基于 ffmpeg 的 WebM/透明视频帧级读取器，支持精确首帧提取、循环播放与帧缓存。
- `decode_fanout.py`：**共享解码扇出核心**。多个窗口若处于同一角色状态，只需驱动单条 ffmpeg 解码管线，通过扇出广播给各窗口，显著降低系统资源消耗。
- `library.py` (`MovieLibrary`)：动画素材资源编目与加载，按角色 ID 索引所有动作视频。
- `catalog.py`：角色配置元数据解析（`character_body_box` 身体碰撞盒定位与边缘检测）。
- `frame_cache.py` / `predictive_prewarm.py`：帧缓冲管理与动画预测性预热机制。

### 3.3 多开协调与物理碰撞系统
- `collision_ipc.py` (`CollisionIpcSession`)：多实例 IPC 门面，GUI 线程安全接口，底层通过独立 QThread 驱动工作线程。
- `collision.py` / `physics.py`：纯 Python 实现的刚体碰撞与物理反弹算法（严格隔离 PySide6，保证纯逻辑独立性）。
- `collision_codec.py`：进程间坐标与速度状态序列化/反序列化编解码器。
- `slot_manager.py` / `multi_window_shared.py`：多实例插槽管理（`config-slot-N.json`），分离独立窗口配置与共享进程配置。
- `island_collision.py`：桌宠与灵动岛之间的硬墙碰撞检测。

### 3.4 原生 C++ 加速层 (`pet/native/` 与 `C++-Python/`)
- `pet/native/loader.py`：原生 DLL 动态链接库定位、构建 ID 校验、ABI 匹配检查与加载。
- `pet/native/collision_backend.py`：提供统一碰撞计算抽象，优先路由至 C++ 原生库，原生缺失时无缝回退到纯 Python 实现。
- `C++-Python/src/collision.cpp`：C++ 高性能碰撞检测实现。
- `C++-Python/src/c_api.cpp`：导出 C 风格接口，供 Python `ctypes` 高效调用。

### 3.5 菜单编排与交互体系
- `pet/context_menus/registry.py`：上下文菜单动作语义注册中心，解耦菜单显示与实际业务逻辑。
- `pet/context_menus/modern.py`：现代化右键多级菜单呈现层，支持主题自适应矢量图标。
- `pet/context_menus/icons.py`：调色板感知的矢量图标渲染。
- `pet/context_menus/quick_launch.py`：快捷启动子菜单逻辑（支持用户自定义外部应用快速拉起）。
- `pet/menu_layout.py`：菜单布局树模型，支持持久化用户菜单排序、隐藏与别名自定义。
- `pet/menu_templates/modern-default-v1.json`：默认菜单布局标准模板。

### 3.6 设置系统与持久化配置
- `pet/modern_settings_dialog.py` (`ModernSettingsDialog`)：现代设置主面板（控制在 2347 行预算内），提供分类侧边栏与卡片式交互。
- `pet/config.py` (`Config`)：核心配置管理，处理读写、版本迁移、默认值回退、插槽隔离与变更信号广播。
- `pet/config_domains.py`：定义设置项所属的持久化领域（Appearance, Interaction, Audio, Proactive 等）。
- `pet/settings_widgets.py`：通用设置 UI 控件库（开关、滑块、下拉选择、颜色选择器）。
- `pet/settings_theme_qss.py`：现代化暗色/亮色 QSS 样式表引擎。
- `pet/settings_menu_layout_editor.py`：直观拖拽可视化的菜单项编排编辑器。
- `pet/settings_pet_controls.py` / `pet/settings_interaction.py`：交互与控制专项设置组件。

### 3.7 AI 对话与扩展集成 (`pet/chat/` 与 `agent_link.py`)
- `pet/chat/service.py`：AI 聊天核心调度服务，管理会话历史、上下文与模型交互。
- `pet/chat/providers.py`：大语言模型提供商适配层（OpenAI 兼容接口、本地/远端端点）。
- `pet/chat/widgets.py`：现代流式气泡聊天窗口。
- `pet/chat/crop_dialog.py`：桌宠聊天背景图裁切与取景器。
- `pet/agent_link.py`：外部编程 Agent 联动核心（监测外部 Agent 工作状态如 Cursor / ChatGPT，驱动桌宠做出工作、成功、报错动效）。
- `integrations/dsh-pet-bridge/`：DSH 平台生态的 Node.js 桥接扩展。

### 3.8 桌面扩展与日常互动功能
- `speech_bubble.py` / `speech_bubble_text.py`：高保真自适应桌面台词气泡，支持字体度量自适应折行与大小调整。
- `dynamic_island.py`：桌面灵动岛交互胶囊，展示系统状态、快捷按钮、通用动效与最近消息。
- `voice_chime.py` / `voice_chime_service.py`：语音报时服务，支持整点报时、台词语音合成与发音缓存。
- `music_lyric.py` / `music_lyric_controller.py`：系统音乐播放感知与歌词同步显示控制器。
- `todo_panel.py` / `todo_reminder.py`：桌面待办清单面板与定时提醒服务。
- `festival.py` / `festival_service.py`：节日提醒与专属节日祝福语轮播。
- `edge_probe.py` / `golden_spin.py` / `throw_egg.py`：边缘探头、黄金回旋、投掷彩蛋等趣味互动。
- `behavior_detector.py` / `stuck_detector.py`：用户闲置检测与鼠标拖动防卡死机制。

---

## 4. 资源、构建与自动化体系

### 4.1 静态资源 (`assets/`)
- `assets/characters/shenshen/`：主打角色资源包（包含不同动作的透明 WebM 视频切片及坐标 manifest 配置文件）。
- `assets/big_blue_fat_fish/`：大蓝胖头鱼独立角色资源包。
- `assets/chat/`：内置 AI 聊天主题气泡底图与默认头像。
- `assets/sounds/`：点击音、状态提示音的 WAV 音频资源。

### 4.2 构建与打包 (`packaging/` & `scripts/`)
- `packaging/dsh-pet.iss`：Inno Setup Windows 安装包打包脚本。
- `packaging/pet_entry.py` / `pet_entry_no_chat.py`：PyInstaller 冻结打包执行入口。
- `dsh-pet-standalone-webm-chat.spec`：PyInstaller 单文件/单目录打包规格规范。
- `scripts/build_onedir.ps1`：Windows onedir 便携版打包自动化脚本。
- `scripts/build_native.ps1`：MSYS2 MinGW64 原生 C++ 动态库编译脚本。
- `scripts/capture_settings_pages.py`：自动化截取各设置页面的视觉验收脚本。
- `scripts/audit_warm_cache.py` / `bench_*.py`：性能基准与解码吞吐压测脚本。

---

## 5. 质量保证与测试套件 (`tests/`)

测试套件包含 160 余个自动化测试文件，是项目稳定重构的最坚实防线：
- **架构红线测试** (`tests/test_architecture.py`)：校验模块导入边界（纯逻辑禁止依赖 Qt）与关键文件行数预算（`window.py` 与 `modern_settings_dialog.py`）。
- **配置与迁移测试** (`tests/test_config_*.py`)：验证新增/修改配置的默认值回退、多实例隔离以及版本迁移。
- **IPC 与多开测试** (`tests/test_collision_*.py`)：测试多进程选举、文件锁竞争、状态同步与断开重连。
- **渲染与动效测试** (`tests/test_decode_fanout.py`, `tests/test_webm_clip.py`)：验证 ffmpeg 解码生命周期与内存稳定性。
- **交付纪律校验** (`tests/test_pr_report_discipline.py`)：强制校验工程交付报告的四个必备章节与索引登记。

---

## 6. 治理规范与 Skill 体系协同

当前工作区存在紧密的规则约束与方法论指引：
1. **[SKIll/En-SKILL.md](file:///e:/CODE/desktop-pet/SKIll/En-SKILL.md)**：
   - 规定本机运行工具链（Python 13、MSYS2 MinGW64、Node.js）。
   - 确立 `AI/` 目录分类收纳红线（`AI/docs/`、`AI/reports/` 等），防止产物散落在项目根目录。
   - 确立 MarkItDown / MinerU 文档转换标准及 Walkthrough 任务总结报告生成规范。
2. **[SKIll/Agent-Code/SKILL.md](file:///e:/CODE/desktop-pet/SKIll/Agent-Code/SKILL.md)**：
   - 规范 Agent 在设计（`design.md`）、规划（`planning.md`）、实现（`implementation.md`）、调试（`debugging.md`）和验收（`verification.md`）全流程中的行为边界。
3. **[AGENTS.md](file:///e:/CODE/desktop-pet/AGENTS.md)**：
   - PR 三份证据硬要求（修改说明、受影响路径实测数据、本机真实运行输出）。
   - CI 零容忍与时序测试禁止固定 sleep 纪律。
