# Desktop-Pet 桌面宠物 (Pure Pet 纯净版)

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
- 🎯 **纯净专注（Pure Pet）**：零多余 AI 依赖，不拉起庞大臃肿的模型调用，开箱即用，资源极简。
- ⚙️ **现代化独立设置面板**：
  - 独立进程隔离设计，设置调节与桌宠渲染互不干扰；
  - 支持调整桌宠大小、动作间隔、弹射力度、物理碰撞参数、自言自语词库、多角色切换等丰富功能。
- 🎨 **高度可定制右键菜单**：
  - 全新现代毛玻璃扁平风格菜单；
  - 动作集一键直达、角色快速切换、应用快捷启动坞（Quick Launch）。
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

| 操作手势 | 触发交互 | 说明 |
| :--- | :--- | :--- |
| **鼠标左键单击** | 角色互动动作 | 随机播放点击动作并触发互动气泡与音效 |
| **鼠标左键长按拖拽** | 移动桌宠位置 | 拖拽至屏幕任意位置 |
| **快速甩拽并松开** | 物理弹射 | 具有动量与阻尼加速度的甩飞弹射效果 |
| **鼠标右键单击** | 上下文主菜单 | 打开功能菜单（角色切换、动作播放、设置等） |
| **鼠标滚轮** | 缩放大小 | 便捷调整桌宠显示比例 |

---

## 📦 打包构建 (单目录绿色版)

项目内置经过深度优化的单目录构建脚本，可自动执行依赖瘦身、无死锁原生库链接与启动冒烟测试：

```powershell
# 在 Windows PowerShell 下执行
powershell -ExecutionPolicy Bypass -File scripts\build_onedir.ps1 -Variant webm-chat -SkipZip
```

构建完成后产物位于：
`dist-onedir\dsh-pet-standalone-webm-chat\`
双击文件夹内的 `dsh-pet-standalone-webm-chat.exe` 即可直接免安装运行。

---

## 📁 目录结构概览

```text
desktop-pet/
├── assets/                 # 桌宠人物动画素材 (WebM/音效/预设)
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

---

## 📄 开源许可证与协议 (License)

本项目采用 **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)** 许可证。

- **允许**：个人学习、交流研究、私人使用及非商业性二次演绎修改。
- **禁止**：**严禁任何形式的商业用途！** 包括但不限于通过本作品获利、有偿转售、打包变现、广告盈利或商业软件集成。
- 详情请查阅项目中的 [LICENSE](LICENSE) 文件。
