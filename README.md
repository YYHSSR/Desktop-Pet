# Desktop-Pet

ChatGPT、Claude、Gemini 三个 Windows 桌宠，使用 Python 3.13、PySide6 和共享流式动画引擎。角色保持独立的程序入口、素材和用户配置。

| 角色 | 当前动画 | 本机数据联动 | 打包程序 |
| --- | --- | --- | --- |
| [ChatGpt](chatgpt/README.md) | 23 段 MP4：待机、左右移动、19 个互动动作和拖拽 | Codex 会话、额度、今日 Token 和完成提醒 | `chatgpt/dist/ChatGpt/ChatGpt.exe` |
| [Claude](claude/README.md) | 12 段 MP4：待机、书页互动、左右移动和拖拽 | Claude 桌面端额度、Claude Code 今日 Token | `claude/dist/ClaudePet/ClaudePet.exe` |
| [Gemini](gemini/README.md) | 14 段 MP4：待机、猫猫互动、左右移动和拖拽 | Antigravity 模型额度、今日 Token | `gemini/dist/GeminiPet/GeminiPet.exe` |

## 获取源码和素材

原始 MP4 和透明 WebP 播放素材使用 Git LFS。克隆前安装 Git LFS，再执行：

```powershell
git lfs install
git clone https://github.com/YYHSSR/Desktop-Pet.git
cd Desktop-Pet
git lfs pull
```

从 GitHub 下载的普通源码 ZIP 不保证包含完整 LFS 素材。完整运行文件夹保存在本机各角色的 `dist/`，分发时需要保留整个程序文件夹。

## 安装和运行

从仓库根目录执行：

```powershell
python -m pip install -r share/requirements.txt
python gemini/app/main.py
```

其他角色使用 `chatgpt/app/main.py` 或 `claude/app/main.py`，也可从角色目录运行 `run.ps1`。三个角色都需要同级 `share/`。

## 角色交互

单击人物打开卡片，右键选择角色动作、桌面操作或设置。短拖拽会完成动作后复原；持续按住则停在复原前的姿势，松手后继续复原。ChatGPT 支持按住触发，Claude 和 Gemini 通过按住并移动触发；快速单击不会触发拖拽。

Claude 和 Gemini 使用原生窗口置顶及层级恢复，普通最大化软件窗口不会触发全屏隐藏；截图浮层结束后会重新检查实际遮挡顺序。窗口置顶、人物显示、自主移动等偏好可在桌面菜单中调整。

## 检查和打包

```powershell
python chatgpt/tools/check.py
python chatgpt/tools/check.py test_mp4_matte test_mp4_character test_mp4_drag test_exit_and_single_pack
python claude/tools/check.py
python gemini/tools/check.py
```

在角色目录运行 `python tools/build.py` 生成该角色的文件夹版程序。也可运行 `python share/tools/package_all.py --activate`，按顺序构建、验证并替换三个程序；替换前会归档旧程序。

## 重新处理素材

```powershell
python -m pip install -r share/requirements-assets.txt
python chatgpt/tools/prepare_character.py
python claude/tools/prepare_assets.py
python gemini/tools/prepare_assets.py
```

各角色以自己的 `MP4/待机.mp4` 首帧为基准，生成 `assets/character/playback-mp4/`，并更新素材清单和校验信息。原始 MP4 保持不变。素材处理不会补绘原片画面边界之外的内容。

## 目录和用户数据

```text
<role>/app/                  角色界面、交互和本机数据读取
<role>/assets/character/MP4/  原始视频
<role>/assets/character/playback-mp4/  透明播放素材
<role>/tools/                素材处理、检查、构建
<role>/tests/                回归测试
<role>/docs/                 角色说明
share/                      共享播放器、桌面组件、字体和依赖
```

构建缓存和验证输出保存在 `build/`，当前程序保存在 `dist/`，均不提交到 Git。用户设置、对话、日志、数据库和凭据也不提交。ChatGPT 使用 `%LOCALAPPDATA%/BailongEnhanced`，Claude 使用 `%LOCALAPPDATA%/ClaudeDesktopPet`，Gemini 使用 `%LOCALAPPDATA%/GeminiDesktopPet`。

源码、文档与角色动画沿用 [CC BY-NC 4.0](LICENSE)，第三方依赖和字体按各自许可证使用。共享实现见 [share/README.md](share/README.md)。
