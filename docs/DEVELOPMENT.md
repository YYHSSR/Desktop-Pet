# 开发指南

## 环境

目标平台为 Windows x64，使用 Python 3.13。项目不自带虚拟环境，本机直接使用 py13 解释器（`E:\minconda\envs\py13\python.exe`），依赖列于根目录 `requirements.txt`；所有命令从项目根目录执行，下文的 `python` 均指该解释器。

```powershell
& 'E:\minconda\envs\py13\python.exe' -m pip install -r requirements.txt
```

## 素材与启动

`assets/character/` 保存角色素材。清单引用 25 个逻辑动作和 6 段循环接缝。实际播放使用 `playbackFile`，缺失时才使用 `file`。干净源码若只有清单，需要先导入实际播放文件。

```powershell
python tools/import_assets.py --source "D:\materials"
python tools/import_assets.py --check
python app/enhanced.py
```

导入工具接受直接素材目录或包含素材子目录的旧程序目录，只导入播放文件和清单。导入前检查所有文件与路径边界，不读取账户或统计数据。

素材清单与资源目录的完整性描述参与 SHA-256 校验；资源格式、编码配方及 Codex 外部协议中的标记不代表应用发布编号，不应随意改写。目录中的历史资源地址仅作为数据契约保留，程序不再联网获取素材。

`tools/import_assets.py --check` 检查播放资源是否齐全，缺少时给出导入提示；源码启动入口为 `app/enhanced.py`，启动本身不做素材预检。

程序使用当前用户的真实配置。自动测试为每个测试进程隔离 `LOCALAPPDATA`、`APPDATA` 和 `CODEX_HOME`，并设置 Qt 离屏模式。手动实验也应隔离数据，避免修改日常使用的数据。

## 自动检查

```powershell
python -m compileall -q app tools tests
python tools/check.py
python tools/check.py test_material_store test_quota_summary_data
python tools/check.py --suite all
```

默认 `core` 集合不依赖外部角色动画，覆盖数据解析、动画时钟、状态调度、图形逻辑、资源校验、启动监听和应用结构。`all` 包含依赖完整素材的历史回归，资源不齐时会失败；它不等同于真实桌面验收。

每个模块在独立进程运行，超时会终止该进程及其子进程。结果与日志保存在 `build/checks/`。GitHub Actions 使用相同入口。

`tests/manual/` 保存实际桌面验收脚本，使用模块方式启动：

```powershell
python -m tests.manual.qa_desktop
```

真实全屏播放、系统缩放和原生窗口交接需要完整资源与实际桌面操作。

## 独立程序

```powershell
python tools/build.py
```

工具优先验证并复用 `build/materials/light/` 中的轻量资源；缓存缺失时可从已匹配清单的轻量源复制，或从高清源生成。高清资源按 `--hd-source <目录>`、`build/materials/hd/`、`assets/character/`、`%LOCALAPPDATA%\BailongEnhanced\materials\hd\<id>` 的顺序查找，必须通过高清校验清单。随后使用 PyInstaller 生成单文件 `dist/DesktopPet.exe`（约 1.6 GB），内含运行库、字体、音效、轻量与高清两套资源及许可证。不创建安装器、不注册安装目录，也不改变正在运行的程序。可用 `--output <目录>` 指定输出位置。

冻结程序从运行时资源目录读取字体与音效，配置和诊断仍写入独立用户目录，支持从任意当前工作目录启动。`--onedir` 仅用于开发排查。

为加快启动，单文件构建会裁掉未使用的 Qt/PIL 组件（软件 OpenGL、Quick/QML、PDF、虚拟键盘、翻译、AVIF），并把两套角色素材放在 PyInstaller 归档之外的程序内嵌区（`app/embedded_assets.py`），避免每次启动都解压到临时目录。轻量素材在首次启动、高清素材在首次切换时按 `material_catalog.json` 的 SHA-256 校验后解包到 `%LOCALAPPDATA%\BailongEnhanced\materials\<画质>\<id>`，之后凭大小与修改时间回执直接复用；回执失效会重新解包，旧版本缓存会被清理。画质切换完全离线，源码运行时没有内置高清，只能使用轻量素材。

`tools/asset_pack.py` 校验并无损优化源动画；`tools/build_materials.py` 生成轻量资源及其校验描述。资源构建需要完整高清源文件。

## 修改边界

- 生产代码放 `app/`，测试放 `tests/`，工具放 `tools/`。
- 字体和许可放在原资源目录，不混入历史说明或发布记录。
- 用户数据、数据库、日志、密钥、构建缓存和可执行文件不提交到源码。
- 保持自动动作静音、人物比例和完整收尾；完成提醒优先于全屏让位。
- 解码取消不得在 GUI 线程等待，动画时钟与业务时钟分开使用。
- 不重新加入软件更新、应用发布编号、作者介绍或更新日志。
