# Desktop-Pet

Windows 桌面白龙助手，使用 Python 和 PySide6 实现。

主要功能：

- 显示 Codex 会话状态、上下文压缩和任务完成提醒，点击会话名打开对应对话。
- 展示本机账户额度、重置倒计时、Token 用量图表和每日统计。
- 支持人物动画、拖动、独立卡片、角色导入，以及内置轻量/高清两种画质的离线切换。
- 状态卡片在点击人物、任务完成或从托盘打开时出现，空闲一段时间后自动收起；卡片顶部的浏览器按钮打开 ChatGPT 或自定义网页。
- 提供登录启动、随 Codex 启动、托盘找回、连接诊断。
- 支持视频全屏临时取消置顶；未读完成提醒优先，自动动作保持静音。

## 目录

```text
desktop-pet/
├── app/                 # 桌宠、界面、Codex 联动和数据服务
│   ├── fonts/           # 字体及许可证
│   ├── licenses/        # 第三方组件与素材的许可声明
│   └── sounds/          # 音效及许可声明
├── assets/character/    # 角色素材清单和播放资源
├── docs/                # 开发说明与架构
├── tests/               # 自动化回归测试
│   └── manual/          # 需要桌面和完整素材的验收脚本
├── tools/               # 构建、素材导入和验证工具
├── requirements.txt     # 固定的开发和运行依赖
├── LICENSE              # 项目许可证（CC BY-NC 4.0）
└── NOTICE.md            # 依赖与素材许可说明
```

缓存与检查结果写入 `build/`，独立程序写入 `dist/`。文件夹统一使用英文命名，界面与说明保留中文。

## 运行

使用 Windows x64 和 Python 3.13。项目不自带虚拟环境，直接使用本机 py13 解释器安装依赖并运行（下文 `python` 均指该解释器）：

```powershell
& 'E:\minconda\envs\py13\python.exe' -m pip install -r requirements.txt
python tools/import_assets.py --source "D:\materials"
python app/enhanced.py
```

角色资源位于 `assets/character/`，构建还可复用 `build/materials/light/` 中已校验的轻量资源。仓库中只包含素材清单，不包含角色播放文件；运行前需先导入素材：`--source` 需要指向含 `素材清单.json` 及其引用的播放文件、循环接缝的目录。检查素材是否齐全：

```powershell
python tools/import_assets.py --check
```

账户额度与会话联动需要在本机安装并登录 Codex。设置与统计保存在 `%LOCALAPPDATA%\BailongEnhanced`，与源码目录分离。

## 检查与构建

```powershell
python tools/check.py
python tools/build.py
```

默认检查不需要外部动画文件。构建需要轻量资源和通过校验的高清资源（可用 `--hd-source` 指定），输出为单文件 `dist/DesktopPet.exe`（约 1.6 GB，其中高清素材约 1 GB、轻量素材约 0.6 GB，运行库约 0.1 GB），包含运行库、两套角色画质、字体与音效，可直接运行，不联网下载任何素材；轻量素材在首次启动、高清素材在首次切换时校验后缓存到 `%LOCALAPPDATA%\BailongEnhanced\materials`，之后不再重复解压。项目没有软件更新、安装升级或回退入口。

更多说明见 [开发指南](docs/DEVELOPMENT.md) 和 [架构说明](docs/ARCHITECTURE.md)。

## 许可证

本项目原创的源代码与文档采用 [知识共享 署名-非商业性使用 4.0 国际许可协议（CC BY-NC 4.0）](https://creativecommons.org/licenses/by-nc/4.0/deed.zh-hans) 授权，全文见 [LICENSE](LICENSE)：

- 允许：复制、分发、修改、二次创作，以及基于本项目发布衍生作品。
- 要求：注明原作者与出处、附上许可协议链接，并说明是否做了修改。
- 禁止：任何商业性使用，包括出售本项目或其衍生作品、将其用于付费产品或服务。

第三方依赖、字体、音效和角色素材不在此许可范围内，分别适用其原有许可，详见 [NOTICE.md](NOTICE.md)。
