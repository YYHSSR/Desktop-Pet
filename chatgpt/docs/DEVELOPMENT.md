# 开发指南

## 共享工作区

本角色位于 `desktop-pet/chatgpt/`，由原 `Codex/` 迁入。动画播放器、解码、缓存、持续动作和动作选择位于工作区的 `share/pet_engine/`；通用动效曲线、坐标转换和线程退出位于 `share/desktop/`。`app/` 下原模块保持同一模块对象的兼容导入入口。源码运行、测试与打包需要保留整个工作区，构建脚本已加入工作区根目录的模块搜索路径。

## 环境

目标平台为 Windows x64，使用 Python 3.13。项目不自带虚拟环境，本机直接使用 py13 解释器（`E:\minconda\envs\py13\python.exe`），本角色的 `requirements.txt` 引用 `../share/requirements.txt`；所有命令从 `chatgpt/` 执行，下文的 `python` 均指该解释器。

```powershell
& 'E:\minconda\envs\py13\python.exe' -m pip install -r requirements.txt
```

## 素材与启动

`assets/character/` 保存角色素材。The active character uses three original MP4 clips: idle, move-left, and move-right. The old WebP pack is retained for reference and excluded from the active manifest.实际播放使用 `playbackFile`，缺失时才使用 `file`。干净源码若只有清单，需要先导入实际播放文件。

```powershell
python tools/import_assets.py --source "D:\materials"
python tools/import_assets.py --check
python app/main.py
```

导入工具接受直接素材目录或包含素材子目录的旧程序目录，只导入播放文件和清单。导入前检查所有文件与路径边界，不读取账户或统计数据。

素材清单与资源目录的完整性描述参与 SHA-256 校验；资源格式、编码配方及 Codex 外部协议中的标记不代表应用发布编号，不应随意改写。目录中的历史资源地址仅作为数据契约保留，程序不再联网获取素材。

`tools/import_assets.py --check` 检查播放资源是否齐全，缺少时给出导入提示；源码启动入口为 `app/main.py`，启动本身不做素材预检。

程序使用当前用户的真实配置。自动测试为每个测试进程隔离 `LOCALAPPDATA`、`APPDATA` 和 `CODEX_HOME`，并设置 Qt 离屏模式。手动实验也应隔离数据，避免修改日常使用的数据。

## 自动检查

```powershell
python -m compileall -q app tools tests ../share
python tools/check.py
python tools/check.py test_material_store test_quota_summary_data
python tools/check.py --suite all
```

默认 `core` 集合不依赖外部角色动画，覆盖数据解析、动画时钟、状态调度、图形逻辑、资源校验、启动监听和应用结构。`all` 包含依赖完整素材的历史回归，资源不齐时会失败；它不等同于真实桌面验收。

每个模块在独立进程运行，超时会终止该进程及其子进程。结果与日志保存在 `build/checks/`。GitHub Actions 使用相同入口。

真实全屏播放、系统缩放和原生窗口交接需要完整资源与实际桌面操作。

## 独立程序

```powershell
python tools/build.py
```

构建直接验证 `assets/character/` 的 512px 播放包与 `app/material_catalog.json`，只内嵌这一份资源。默认输出 `dist/ChatGpt/ChatGpt.exe`，分发时保留完整程序文件夹。可用 `--output <目录>` 改变输出目录，或用 `--onefile` 生成单文件版。无需高清源或画质切换，旧高清偏好会回到当前原尺寸素材。

首次启动时按完整性清单校验并缓存内置素材，之后凭大小与修改时间回执复用。`tools/prepare_character.py` 更新当前播放文件及校验清单，不再生成 720px 放大副本。所有原始 WebP 均保留。

退出时先隐藏角色、独立卡片和托盘，发出后台任务取消信号；线程结束后关闭事件循环。关闭设置后也必须能从两个菜单退出，回归覆盖在 `tests/test_exit_and_single_pack.py`。`--material-probe <结果.json>` 可验证打包后的简化设置、单份素材及托盘退出。

## 修改边界

- 生产代码放 `app/`，测试放 `tests/`，工具放 `tools/`。
- 字体和许可放在原资源目录，不混入历史说明或发布记录。
- 用户数据、数据库、日志、密钥、构建缓存和可执行文件不提交到源码。
- 角色不发出任何声音；保持人物比例和完整收尾；完成提醒优先于全屏让位。
- 解码取消不得在 GUI 线程等待，动画时钟与业务时钟分开使用。
- 不重新加入软件更新、应用发布编号、作者介绍或更新日志。

## 素材命名兼容

`manifest.json` 是源码及新导入角色包的标准文件名，读取时优先使用它；旧角色包和既有内嵌资源仍支持中文旧名。同一目录同时存在两者时，以英文名为准。

单纯重命名素材目录或文件后，运行 `python tools/sync_material_catalog.py` 同步原尺寸资源的路径与内容标识。该工具先确认所有动画的字节数及 SHA-256 未变，再重算轻量目录。使用 `--check` 只检查一致性，不写文件。动画内容变化时应使用素材构建工具重新生成校验数据。

## 当前角色素材处理

For the current character, update the three MP4 files and run `python tools/prepare_mp4_character.py`, followed by `python tools/check.py test_mp4_matte test_mp4_character`. Originals remain unchanged. Legacy WebP reconstruction is not used while these MP4 sources are present.

## MP4 character preparation

The current built-in character has only three active actions: `idle`, `move-left`, and `move-right`. Source MP4 files stay under `assets/character/MP4/` with their supplied names. Processed files are isolated in `assets/character/playback-mp4/`; older classified WebP files remain untouched and are not bundled.

Run `python tools/prepare_mp4_character.py` to regenerate this pack. The canonical `prepare_character.py` entry also dispatches to the MP4 pipeline when MP4 sources are present. The supplied videos are 480 x 480 at 24 fps. Their native pixels are centered on a 512px transparent canvas without enlargement or per-frame registration.

`tools/mp4_matte.py` removes only border-connected neutral white backdrop and selected enclosed outer negative spaces, preserving pale fabric and central highlights inside drawn outlines. Opaque source RGB remains exact. No inpainting, hidden-colour reconstruction, or optical-flow texture borrowing is used. Every source frame is retained. Short additional whole-frame dissolves connect the supplied poses to the common idle anchor; all clips have identical first and last RGBA frames.

The right-click action menu exposes the three actions. A selected directional walk moves the window when there is room, or previews in place while locked. Dragging uses idle until a dedicated drag clip is supplied. Missing work, quota, and celebration gestures do not enable old assets; Codex data and completion reminders remain available.

Run `python tools/check.py test_mp4_matte test_mp4_character test_exit_and_single_pack` plus the default core suite. `build/mp4-rebuild/verification.json` records source hashes, frame counts, exact opaque-pixel preservation, endpoint preparation, and lossless output verification. Legacy full-pack artwork checks in `test_new_character` are skipped for this explicitly limited pack.

The 12-second idle loop uses a bounded 160 MB cache with a 128 MB entry limit. Runtime decoding is capped at the native 512px canvas; Qt scales the displayed result for larger windows.
