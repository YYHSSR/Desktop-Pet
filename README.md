# 鲸鱼娘 · Desktop-Pet

<div align="center">

✨ **一款基于 PySide6 + WebM 透明动画的高性能、低占用桌面交互宠物** ✨

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC_BY--NC_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-green.svg)](https://www.microsoft.com/)
[![Framework](https://img.shields.io/badge/Framework-PySide6-41CD52.svg)](https://www.qt.io/)

</div>

---

## 📖 项目简介

**Desktop-Pet** 是一款面向 Windows 平台打造的轻量、丝滑、高度自拟物化交互的桌面宠物系统。

本项目聚焦于提供最纯粹的陪伴与桌面互动体验（Pure Pet 模式），剥离了繁复庞杂的大模型对话交互，以极低 CPU 与内存占用常驻系统，配合底层 C++ 物理加速引擎与流水线透明视频流解码，带来如丝般顺滑的动作表现和桌面物理弹射反馈。

> [!IMPORTANT]
> **商业限制声明**：本项目遵循 **CC BY-NC 4.0（知识共享 署名-非商业性使用 4.0 国际许可协议）**。允许个人自由使用、学习研究、修改与分享，**严禁任何形式的商业用途、付费出售、捆绑变现或营利性分发**！

---

## 🌟 核心特性

- 🎬 **透明无缝 WebM 动效引擎**：采用原生无黑边 Alpha 透明通道视频驱动，配合 LRU 帧缓存与流水线首帧预热，动作衔接丝滑自然。
- ⚡ **底层物理碰撞与弹射互动**：
  - 支持鼠标抓取、拖拽弹射甩飞、撞墙弹性反弹；
  - 基于 C++ 核心 (`pet_core.dll`) 与共享内存原子锁物理模拟，支持多开桌宠之间真实弹性碰撞。
- 🔗 **ChatGPT Work/Codex 联动**：只读本机工作会话状态，切换工作、等待与完成动作并提示；ChatGPT 桌面端由玩家自行打开。参见 [联动说明](docs/AGENT_LINK_PROTOCOL.md)。
- 🎯 **纯净专注（Pure Pet）**：零多余 AI 依赖，不拉起庞大臃肿的模型调用，开箱即用，资源极简。
- ⚙️ **现代化独立设置面板**：
  - 独立进程隔离设计，设置调节与桌宠渲染互不干扰；
  - 调整动作间隔、弹射力度、物理碰撞参数、自言自语词库与 ChatGPT 工作状态联动。
- 🎨 **桌宠右键菜单**：
  - 头像首行「厉害了我的鲸 · 请点击」，点击播放回应动画并弹出随机卡通图片气泡，避免连续重复；
  - 动作集一键直达、角色快速切换、应用快捷启动坞（Quick Launch）。
- 🐾 **鲸鱼娘托盘**：角色头像图标，显示／隐藏所有桌宠、鼠标穿透、开机自启、退出；自启读取系统状态并显示勾选，操作后给出反馈。
- 🚀 **绿色免安装单目录**：构建脚本支持开箱即用的便携式单目录产物，随拷随用，不写死注册表。

---

## 🛠️ 快速开始

### 1. 环境准备

推荐使用 Python 3.10 ~ 3.13 虚拟环境：

```bash
# 克隆仓库
git clone https://github.com/YYHSSR/Desktop-Pet.git
cd Desktop-Pet

# 安装依赖
pip install -r requirements.txt
```

若需执行开发者测试或调试：
```bash
pip install -r requirements-dev.txt
```

### 2. 运行桌宠

直接通过模块方式启动主程序：

```bash
python -m pet
```

独立打开设置面板：
```bash
python -m pet --settings
```

---

## 🎮 操作指南

### ChatGPT 桌面端工作联动

右键桌宠 → **桌宠设置 → 自动化与联动 → ChatGPT Work/Codex**，即可开启
工作动作、思考动作、工具执行气泡和完成提醒；默认关闭。
请先自行打开 ChatGPT 桌面端，再启动 Work/Codex 工作会话。

联动只读本地 Work/Codex 会话文件，不需要 API Key。普通 Chat 和云端会话不在
监听范围内。默认读取 `~/.codex/sessions`，也支持 `CODEX_HOME`。
本机日志格式可能随桌面端版本变化；详细范围与协议见
[桌面联动协议](docs/AGENT_LINK_PROTOCOL.md)。

| 操作手势 | 触发交互 | 说明 |
| :--- | :--- | :--- |
| **鼠标左键单击** | 角色互动动作 | 随机播放点击动作并触发互动气泡 |
| **鼠标左键长按拖拽** | 移动桌宠位置 | 拖拽至屏幕任意位置 |
| **快速甩拽并松开** | 物理弹射 | 具有动量与阻尼加速度的甩飞弹射效果 |
| **鼠标右键单击** | 上下文主菜单 | 打开功能菜单（角色切换、动作播放、设置等） |
| **鼠标滚轮** | 缩放大小 | 便捷调整桌宠显示比例 |

大小、播放速率、置顶、拖动物理等快捷操作集中在右键菜单中；系统操作集中在托盘中，设置页不重复这些选项。气泡、文案、碰撞及联动的详细参数仍可在设置中调整。

---

## 📦 打包构建 (单目录绿色版)

项目内置经过深度优化的单目录构建脚本，可自动执行依赖瘦身、无死锁原生库链接与启动冒烟测试：

```powershell
# 在 Windows PowerShell 下执行
powershell -ExecutionPolicy Bypass -File scripts\build_onedir.ps1 -Variant webm-chat
```

构建完成后产物位于：
`dist-onedir\dsh-pet-standalone-webm-chat\`
双击文件夹内的 `dsh-pet-standalone-webm-chat.exe` 即可直接免安装运行。

---

## 📁 目录结构概览

```text
desktop-pet/
├── assets/                 # 桌宠人物动画素材 (WebM/预设)
├── pet/                    # Python 核心业务逻辑
│   ├── app.py             # 应用程序宿主与生命周期调度
│   ├── window.py          # 桌宠透明窗口与手势交互
│   ├── modern_settings_dialog.py # 现代设置对话框
│   ├── native/            # C++ 物理碰撞底层动态库
│   └── ...
├── C++-Python/             # 碰撞内核 C++ 源代码
├── packaging/              # 打包规范、资源清单与 Slim 规则
├── scripts/                # 构建、本地打包与测试脚本
├── tests/                  # Pytest 自动化测试套件
├── docs/                   # 架构设计与性能优化复盘文档
├── LICENSE                 # CC BY-NC 4.0 非商业开源许可协议
└── README.md               # 项目主说明文档
```

`docs/` 和 README 不参与应用启动，也不会进入便携包。删除 README 会移除 GitHub 首页说明；删除 `docs/` 会让 README、`AGENTS.md` 等文档链接失效，并使依赖文档的开发规范测试失败。保留 `LICENSE`、`THIRD_PARTY_NOTICES.md`、角色素材和 `C++-Python/` 原生源码。

---

## 📄 开源许可证与协议 (License)

本项目采用 **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)** 许可证。

- **允许**：个人学习、交流研究、私人使用及非商业性二次演绎修改。
- **禁止**：**严禁任何形式的商业用途！** 包括但不限于通过本作品获利、有偿转售、打包变现、广告盈利或商业软件集成。
- 详情请查阅项目中的 [LICENSE](LICENSE) 文件。
