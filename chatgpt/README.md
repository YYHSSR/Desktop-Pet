# ChatGpt 桌宠

ChatGpt Windows 桌面助手，使用 Python 和 PySide6 实现。

此目录由原 `Codex/` 迁入，是三个 AI 娘中已完成的 ChatGPT 角色，保留现有 Codex 联动。公共组件位于同级 `../share/`，所有命令从本目录 `chatgpt/` 执行。

主要功能：

- 显示 Codex 会话状态、上下文压缩和任务完成提醒，点击会话名打开对应对话。
- 展示本机账户额度、重置倒计时、Token 用量图表和今日统计。
- 支持人物动画、拖动、独立卡片，使用原尺寸 512px 内置动画。
- 状态卡片在点击人物、任务完成或从托盘打开时出现，空闲一段时间后自动收起；卡片顶部的浏览器按钮打开 ChatGPT 或自定义网页。
- 提供登录启动、随 Codex 启动、托盘找回、连接诊断。
- 支持视频全屏临时取消置顶；未读完成提醒优先，自动动作保持静音。

## 目录

```text
chatgpt/
├── app/                 # 桌宠、界面、Codex 联动和数据服务
├── assets/character/    # 角色素材清单和播放资源
├── docs/                # 开发说明与架构
├── tests/               # 自动化回归测试
│   └── manual/          # 需要桌面和完整素材的验收脚本
├── tools/               # 构建、素材导入和验证工具
├── requirements.txt     # 固定的开发和运行依赖
└── LICENSE              # 项目许可证（CC BY-NC 4.0）
```

`requirements.txt` 引用 `../share/requirements.txt`，运行与构建应保留整个工作区。

缓存与检查结果写入 `build/`，独立程序写入 `dist/`。文件夹统一使用英文命名，界面与说明保留中文。

## 运行

使用 Windows x64 和 Python 3.13。项目不自带虚拟环境，直接使用本机 py13 解释器安装依赖并运行（下文 `python` 均指该解释器）：

```powershell
& 'E:\minconda\envs\py13\python.exe' -m pip install -r requirements.txt
python tools/import_assets.py --source "D:\materials"
python app/main.py
```

角色资源位于 `assets/character/`，构建直接校验并使用当前 512px 播放文件。仓库已包含完整角色动画，克隆后即可运行；更换素材时用 `--source` 指向含 `manifest.json` 及其引用的播放文件、循环接缝的目录。检查素材是否齐全：

```powershell
python tools/import_assets.py --check
```

账户额度与会话联动需要在本机安装并登录 Codex。设置与统计保存在 `%LOCALAPPDATA%\BailongEnhanced`，与源码目录分离。

## 检查与构建

```powershell
python tools/check.py
python tools/build.py
```

默认检查不需要外部动画文件。构建直接使用当前 512px 原尺寸播放包，输出文件夹版 `dist/ChatGpt/ChatGpt.exe`，不再提供画质切换或内置放大材质。请保留完整 `ChatGpt` 文件夹。首次运行时校验并缓存内置动画；已有旧版高清偏好自动回到当前素材，不读取旧高清缓存。需要单文件时可使用 `--onefile`。

更多说明见 [开发指南](docs/DEVELOPMENT.md) 和 [架构说明](docs/ARCHITECTURE.md)。

## 许可证

本项目的源代码、文档和角色动画素材采用 [知识共享 署名-非商业性使用 4.0 国际许可协议（CC BY-NC 4.0）](https://creativecommons.org/licenses/by-nc/4.0/deed.zh-hans) 授权，全文见 [LICENSE](LICENSE)：

- 允许：复制、分发、修改、二次创作，以及基于本项目发布衍生作品。
- 要求：注明原作者与出处、附上许可协议链接，并说明是否做了修改。
- 禁止：任何商业性使用，包括出售本项目或其衍生作品、将其用于付费产品或服务。

第三方依赖和字体不在此许可范围内，分别适用其原有许可（见 `assets/licenses/` 和 `../share/assets/fonts/OFL.txt`）。

## 布局与兼容

三个角色统一使用 `app/`、`assets/`、`docs/`、`tests/`、`tools/`、`build/`、`dist/`。ChatGpt 的标准入口为 `app/main.py`，原 `enhanced.py` 仍可启动。音效与角色专属第三方许可在 `assets/sounds/` 和 `assets/licenses/`；共用字体与 OFL 原文在 `../share/assets/fonts/`。

名称已改为 ChatGpt。已有 `%LOCALAPPDATA%\BailongEnhanced`、单实例名称和启动同步标识保持兼容，避免丢失设置和统计。历史高清包的完整性描述保持原样，内置角色的界面名称由程序统一显示为 ChatGpt。

卡片顶部操作为刷新、网页、展开/设置；原第二个“Token 日报”图标及日报窗口已移除。今日 Token 底栏和主卡片的用量图表保留。三个角色的右键菜单结构统一由 `share/desktop/context_menu.py` 提供。

当前新角色已接入 22 段原片，共同姿势衔接、拖动期间播放和各动作权重见 [动画安排](docs/ANIMATIONS.md)。重新处理素材运行 `python tools/prepare_character.py`；该步骤更新本地播放资源，不打包程序。设置页仅保留常规 / 动作，置顶和移动开关仅在右键菜单保留。

主卡片默认仅并排展示 5h 剩余与周剩余，不再展示右侧重置大倒计时。今日 Token 底栏保留，点击切换完整宽度的小时图，使用“额度”返回。

展开状态页只保留任务、额度卡片和今日 Token，不再重复展示下方“额度 / Token”详情区域。角色右键与托盘退出共用完整关闭流程，先隐藏托盘和窗口，再异步等待后台线程结束。

设置中的角色管理页及导入、转换、预览、素材检查入口已移除；手动播放动作仍从右键“角色动作”进入。常规与动作页仅保留标题和必要控件。
