# Desktop-Pet

角色动画使用 Git LFS 保存。克隆前安装 Git LFS，执行 `git lfs install`；克隆后执行 `git lfs pull`，再运行或打包桌宠。普通 GitHub 源码 ZIP 不保证包含实际动画文件。

三个角色的托盘使用当前角色图片生成头像，悬停仅显示 `ChatGpt`、`Claude` 或 `Gemini`。

ChatGPT、Claude、Gemini 三个 AI 娘桌宠的工作区，统一采用 Python、PySide6 和共用动画引擎。

| 角色目录 | 当前状态 | 素材 |
| --- | --- | --- |
| `chatgpt/` | ChatGpt 桌宠，由原 `Codex/` 迁入；保留 Codex 会话、额度、Token 图表和桌面交互 | 原有 WebP 动画及校验清单 |
| `claude/` | 书页陪伴桌宠：Gpt 同款卡片、角色动作、今日 Token 统计、Claude 桌面端额度联动（含重置倒计时） | 9 段原始 WebP，选用 9 段透明播放动画 |
| `gemini/` | 星光陪伴桌宠：Gpt 同款卡片、角色动作、今日 Token 统计、Antigravity 模型额度联动 | 14 段原始 WebP，选用 12 段透明播放动画 |
| `share/` | 共用动画引擎、桌面基础组件和依赖清单 | 不放角色专属素材 |

## 目录约定

```text
desktop-pet/
├── chatgpt/                 # 已完成角色，也是后续实现的架构参考
├── claude/                  # 暖橙色书页陪伴桌宠
├── gemini/                  # 独立的蓝紫星光桌宠
├── share/
│   ├── pet_engine/          # 播放、持续动作、解码、缓存、动作选择、打包环境
│   ├── desktop/             # 动效曲线、Windows 坐标转换、工作线程退出
│   └── requirements.txt     # 共用的固定依赖
├── .github/                # 检查与问题模板
└── LICENSE
```

三个角色采用同样的目录分工：

```text
<character>/
├── app/                    # 角色入口、界面、平台适配与配置
├── assets/character/       # 角色播放素材、素材清单及校验信息
│   └── 原分类目录/         # 用户提供的 WebP 与 manifest.json
├── docs/                   # 角色开发和架构说明
├── tests/                  # 角色回归测试
├── tools/                  # 角色素材处理、检查和构建入口
└── requirements.txt        # 引用 ../share/requirements.txt
```

Claude 的 10 段与 Gemini 的 14 段原始 WebP 保留在各自的分类目录，`manifest.json` 记录原始文件校验。两者处理后的透明动画另放 `playback/`，运行时读取 `character.json`；原始素材清单与运行时动作清单用途不同。

角色通过 `share/` 复用公共实现，不相互导入对方的 `app/`。ChatGPT 原扁平模块路径保留为兼容入口，共用相同模块对象和解码统计单例。平台连接、额度、日报及业务界面仍归各角色；后续可参考 ChatGPT 的分层接入各自的平台。

## 运行 ChatGpt 桌宠

Windows x64、Python 3.13，从仓库根目录执行：

```powershell
cd chatgpt
python -m pip install -r requirements.txt
python app/main.py
```

ChatGPT 已采用你改名后的 `manifest.json` 和分类素材路径，旧角色包的中文清单名保持兼容。账户联动仍需本机安装并登录 Codex。配置与统计继续使用 `%LOCALAPPDATA%\BailongEnhanced`，单实例通信名称保持兼容。原来指向 `Codex/` 的手动启动命令和外部快捷方式应改用 `chatgpt/`。

## 检查与构建

Gemini 的运行、动作选择与检查见 [Gemini 使用说明](gemini/README.md)。其入口为 `gemini/app/main.py`，用户配置与本机 Token 缓存保存在 `%LOCALAPPDATA%\GeminiDesktopPet`，与 ChatGPT 隔离。整个工作区只有根目录的一份 `.git/`。

从 `chatgpt/` 执行：

```powershell
python tools/check.py
python tools/import_assets.py --check
python tools/build.py
```

构建需要通过校验的高清素材。源码运行、测试及打包需要同级 `share/`，请保留整个工作区。说明见 [ChatGPT 桌宠](chatgpt/README.md)、[开发指南](chatgpt/docs/DEVELOPMENT.md)、[公共层](share/README.md)。

源码、文档与已有角色动画沿用 [CC BY-NC 4.0](LICENSE)，第三方依赖、字体按原有许可证使用。

## 统一角色布局

`chatgpt/`（名称 ChatGpt）、`claude/` 和 `gemini/` 保持相同的一级布局：`app`、`assets`、`docs`、`tests`、`tools`、`build`、`dist`，并保留各自的 README、LICENSE 和 requirements。三者的入口统一为 `app/main.py`，启动脚本为 `run.ps1`。Claude 的运行、动作与日报说明见 [Claude 桌宠](claude/README.md)，用户数据保存在 `%LOCALAPPDATA%\ClaudeDesktopPet`。

字体仅在 `share/assets/fonts/` 保存一份；运行包分别收集到自己的 `assets/fonts/`。构建缓存留在各角色 `build/`，当前程序在 `dist/`：ChatGpt 为文件夹版 `ChatGpt/ChatGpt.exe`（仅内嵌当前 512px 原尺寸播放包），Claude 为文件夹版 `ClaudePet/ClaudePet.exe`（免解包，约 0.3 秒出现），Gemini 为文件夹版 `GeminiPet/GeminiPet.exe`。


三者的设置统一为“常规 / 动作”，顶部仅“状态 / 设置”，手动动作从右键“角色动作”进入。统一打包与验证入口为 `share/tools/package_all.py`；当前程序保存在各角色 `dist/`，旧程序、旧材质和临时预览统一归档在根目录 `build/archive/`。当前验证记录保存在各角色 `build/checks/`。
