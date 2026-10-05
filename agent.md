# Desktop-Pet 当前开发说明

更新日期：2026-10-05。适用目录：`E:\CODE\desktop-pet`。当前源码版本：`4.2.1`。

### 托盘自启最新调查（2026-10-05 21:34）

旧进程 PID 8608 的实际日志显示：写入回读 True，但约 4 毫秒后托盘回读 False。
重启原 exe 后，隔离配置和真实配置下均未再次复现；使状态变化的根因尚未确认，
不能仅凭测试通过就宣称此前异常已彻底解决，也不能归因于用户操作或安全软件。

自启写入、配置保存、最后回读、菜单勾选和气泡提示现统一在 TrayController。
移除 PetInstance 中提前发成功提示的第二套处理路径。最后回读与请求不一致时
显示失败提示，禁止继续显示“已开启”。新增保存期间登记消失的回归覆盖。

主回归 89 项、真实桌面 Qt 托盘回归 11 项通过；重建平铺包通过常规构建验收。
另用未经改写入口的最终 exe，在原路径执行四次原生鼠标点击，每次等待 10 秒，
实际 Run 值及可见勾选依次为开启、关闭、开启、关闭。用户实机反馈仍需确认。

`tests/tools/verify_shipped_tray.py` 验证原始成品，不改写 exe、模块或系统注册表路径。
它使用隔离 APPDATA；显式 `--run-key` 允许测试当前成品自己的 Run 值，结束时
恢复该值原来的数据与类型，绝不删除整个 Run 键。按默认托盘布局定位点击并
截图检查勾选；运行期间请勿手动移动鼠标或同时调整自启。

```powershell
& $petPython tests/tools/verify_shipped_tray.py --exe dist-onedir/dsh-pet-standalone-webm-chat.exe --output tests/tmp/shipped-tray --run-key
```

早期冻结入口探针仅可用来辅助定位。其导入顺序、常量覆盖和入口改写可能影响
结果，不应作为正常成品修复有效的唯一证据；以下历史验收记录以本节限定为准。

这份文档记录当前项目的开发约定，供维护者和协助开发的 agent 参考。用户当次明确要求优先于本文。修改前先阅读实际代码和 Git 工作区，区分已有改动、本次改动和历史遗留问题。

## 当前产品方向与边界

- 保持 Pure Pet：透明动画、桌面交互、本地工作状态联动。
- 保留拖拽宠物、弹弓、碰撞、角色切换、气泡、托盘、设置和现有特效。
- **节假日提醒已彻底退役**：不恢复日历服务、调度器、文案库、设置或菜单入口，以及农历/时区专用依赖。配置迁移只保留旧 `festival_` 字段清理。
- **文件投喂功能已彻底退役**：不恢复 `pet/file_eater.py`、窗口拖放处理器、投喂统计、投喂入口或旧测试。拖拽宠物本身是另一项保留功能。
- 不重新引入大模型聊天、文件解读、语音/TTS 或已移除的界面能力，除非用户明确要求。
- 历史 `docs/`、`AGENTS.md`、`CONTEXT.md` 和项目内旧技能文档的删除保持不变。开发说明集中在本文及 README，不批量恢复历史资料。
- 测试采用关键回归覆盖，不为恢复目录数量而恢复全部旧套件。删除功能的测试应验证其确实退役。
- 所有测试文件统一放在 `tests/`：Python 回归在根层，C++ 在 `native/`，打包验收在 `tools/`，性能基准在 `benchmarks/`。`pet/native/diagnostics.py` 是 exe 运行时诊断入口，不能移入测试目录或删除。
- 项目根目录保留 `LICENSE`；素材署名合并在其中。不再生成独立第三方声明文件，必要运行库许可证由 `scripts/collect_runtime_licenses.py` 收集到 `_internal/licenses/`。
- `.github` 已删除，只保留本地开发与打包。不要恢复 GitHub 自动测试或发布配置。

## 架构与主要修改位置

| 模块 | 责任 | 修改时应注意 |
|---|---|---|
| `pet/__main__.py` | 入口及参数分流 | `--settings`、原生自检、卸载清理各自独立；避免无关 GUI 初始化 |
| `pet/app.py` | AppShell 进程服务、PetInstance 每窗容器 | 区分退出一只和全部退出；切换角色不能遗留旧窗口、菜单与线程 |
| `pet/tray_controller.py` | 托盘菜单、状态勾选和菜单生命周期 | 显示勾选读取存活窗口；自启勾选读取系统；失败写入必须回读并恢复正确状态 |
| `pet/window.py` | 绘制、命中、输入、动画与运动编排 | 保留拖拽；不要把昂贵 I/O 放进 GUI 回调；大类新增行为优先提取控制器 |
| `pet/library.py`、`pet/webm_clip.py` | 素材发现、预热、视频解码与进程生命周期 | ffmpeg、线程、缓存和 Qt 对象必须一起收口 |
| `pet/collision_ipc.py` | QThread 内的本地碰撞协调 | QLocalServer/QLocalSocket 属于工作线程，GUI 通过 queued Signal 交互 |
| `pet/native/`、`C++-Python/` | ctypes 接口及 C++ 碰撞内核 | 保持 ABI 版本、布局校验、参考结果一致和打包验证 |
| `pet/config.py` | 配置默认值、清洗、迁移、保存 | 跨进程锁、按修改键合并、原子替换；布尔配置使用 `_bool_or_default` |
| `pet/agent_link.py` | 日志适配、状态聚合、宠物反馈 | 只读事件；限制输入大小；代次作废防止旧线程迟到事件 |
| `pet/modern_settings_dialog.py`、`pet/settings_*.py` | 设置布局与配置回写 | 默认独立设置进程；关闭窗口和保存退出的结果要一致 |
| `pet/session_watcher.py` | Windows 会话结束保护 | 真实 QAbstractNativeEventFilter 接入，先关 ffmpeg 派生闸门再收口 |
| `scripts/` | 构建工具、冻结入口和许可证收集 | 版本标识生成在临时构建目录，不维护重复入口 |
| `tests/` | Python/C++ 测试、验收工具和性能基准 | 分别放在根目录、native/、tools/、benchmarks/ |

## 默认行为与性能事实

- 碰撞默认开启，默认求解器为 Python。
- `PET_COLLISION_BACKEND=native` 强制原生库，失败应显式暴露；`auto` 允许原生不可用时回退 Python。
- 默认多开是独立进程。`experimental_single_process_spawn` 默认关闭；共享解码仅在单进程多窗启用后生效。
- 设置进程隔离默认开启。不要用完整内存快照覆盖另一个进程的新配置。
- 本地联动默认关闭；Codex 会话路径来自 `CODEX_HOME`，否则为 `~/.codex/sessions`。普通云端 Chat 不属于该路径的监听范围。
- 联动轮询约 1.5 秒一次，新会话发现约 15 秒一次，启动跳过历史活动。
- 首帧缓存预算不是应用总内存。测量内存时应计入 ffmpeg 和设置子进程。
- 本机合成基准显示 C++ 在密集碰撞时有收益、稀疏场景可能更慢。不要在缺少真实场景数据时宣称 C++ 总是更快或默认已经加速。

## 本轮修复约定

1. 关机保护使用由 SessionWatcher 强引用的原生过滤器对象；安装失败返回 False 并留下 warning，Qt 信号兜底仍可工作。
2. 支持 Qt 回调提供的 shiboken VoidPtr 消息指针；只解析 Qt 给出的 MSG 内存，不从用户输入构造地址。
3. 会话信号传来的参数不覆盖日志原因标签。重复结束通知保持幂等。
4. 移除文件投喂模块及 AppShell/窗口 mixin 接线。不要为兼容旧投喂实现添加空壳方法。
5. 仅维护本地开发和打包；移除节日提醒、专用依赖及 GitHub 工作流。
6. 清理对已删除开发资料的引用，README 说明实际后端、IPC 与默认开关。
7. 外部配置中的 `"false"` 不得被当成 True 开启联动。

安装路径中的旧可执行程序包含旧代码。源码修复后应重新构建，验证新的产物，不能用旧 exe 的表现判断源码是否生效。历史用户数据中的投喂统计文件属于惰性残留，不应扫描真实用户目录并擅自删除。

## 开发和验证命令

当前这台机器的 Python 不在 PATH；可用环境为：

```powershell
$petPython = 'D:\python\miniconda\envs\py13\python.exe'
$env:PYTHONUTF8 = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
& $petPython -m ruff check pet tests
```

为隔离 Qt/解码线程生命周期，按以下本地分组运行：

```powershell
& $petPython -m pytest -q --ignore=tests/test_webm_reader_lifecycle.py --ignore=tests/test_webm_clip_lifecycle.py --ignore=tests/test_webm_first_frame_lock.py --ignore=tests/test_low_priority_warm_interaction_yield.py
& $petPython -m pytest -q tests/test_webm_reader_lifecycle.py tests/test_webm_clip_lifecycle.py tests/test_webm_first_frame_lock.py
& $petPython -m pytest -q tests/test_low_priority_warm_interaction_yield.py
```

原生库自检需要显式指定 JSON 输出路径：

```powershell
& $petPython -m pet --native-self-test build-native/reports/native-selftest.json
```

本地便携包构建：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_onedir.ps1 -Variant webm-chat -PythonExe $petPython
```

常规构建执行原生编译、PyInstaller、瘦身、编码检查、Qt DLL 链验证、冻结原生自检及桌宠/设置窗口冒烟。无桌面环境可使用 `-SkipGuiSmoke`，但应在报告中明确窗口验收尚未完成。默认产物为 `dist-onedir/dsh-pet-standalone-webm-chat.exe` 和 `dist-onedir/_internal/`。

**所有后续打包固定此平铺结构**：不生成嵌套应用目录、不自动生成 ZIP、不把 README、agent.md 或许可证文档放到 exe 旁。必要许可证位于 `_internal/licenses/`；开发文档只在项目根目录维护。

PyInstaller 的 spec、分析结果与暂存包放在 `build-onedir/`；CMake 编译目录是 `build-native/`。全部验证成功后再替换现有便携包，失败保留旧包。成功默认删除两类构建目录；诊断时可加 `-KeepBuild`。不要删除 `C++-Python/` 或 `pet/native/_bin/`：前者是源码，后者是实际运行的原生库。

`.pytest_cache`、`.ruff_cache`、`__pycache__` 可删除，运行工具时可能重建。`.git`、角色素材和未跟踪的 `SKILL/` 需保留。

验证应匹配修改：

- 会话保护：真实 Qt 注册契约、MSG/VoidPtr 解析、安装失败重试、信号接线和结束后的 ffmpeg 派生禁用。
- 文件投喂移除：模块不可导入、窗口不接受文件拖放、拖拽宠物仍保留；冻结模块表也应没有旧模块。
- 配置：布尔值清洗、旧数据清洗、跨进程修改键合并、槽位隔离。
- 构建：本地构建输入存在，README 相对链接有效，依赖许可证收集正常，最终目录平铺。
- 节日提醒移除：模块不可导入、设置无相关行，默认配置、reload 和并发 save 不再保留旧字段。
- 解码：取消、代次作废、首帧并发、循环结束与 reader/ffmpeg 收口。

## 修改和交付纪律

- 先看 `git status --short`。已有删除和未跟踪 `SKILL/` 不属于可随手清理的内容。
- 只修改本次需要的文件；不要顺带大规模格式化、调整产品开关或恢复废弃功能。
- Windows 递归删除/移动前，检查绝对路径位于指定构建目录；使用 LiteralPath，不拼接跨 shell 删除命令。
- 测试使用临时配置，构建冒烟使用隔离 APPDATA，不写用户真实配置或开机自启项。
- 不为测试执行真实关机/注销。实机验收由用户保存工作后安排；可以向本次创建的测试窗口投递模拟消息。
- 不自动提交、推送、打 tag 或发布；用户请求这些操作后再执行。
- 报告列出改动、实际执行的检查、失败或跳过的检查和产物路径。不要把离屏冒烟写成真实桌面全面验收。

## 后续开发建议

先稳定发布基线，再测量 1/3/10 只宠物的冷启动、CPU、含子进程内存、隐藏状态和长时间动画切换。结构优化优先按输入、动画调度、物理、通知的行为边界逐步提取；每次提取都保留已有可观察行为。角色扩展优先完善 manifest、动画分类、身体/头部框与素材校验。

## 2026-10-05 验证记录

本轮复验：Ruff 通过；关键 Python 回归 135 项通过（主套件 76、解码生命周期 32、低优先级预热交互 27）；C++ CTest 1 项通过。

新平铺包构建成功，瘦身、中文编码、Qt DLL 链、原生库与冻结原生自检通过；桌宠窗口和独立设置窗口在隔离 APPDATA 下启动成功。冻结模块表不含文件投喂、节日提醒、lunar_python 或 tzdata。必要许可证位于 `_internal/licenses/`。

`.github`、独立第三方声明、过时 ZIP/远程发布脚本、便携包重复 README、根目录 spec、构建中间目录及测试/字节码缓存已清理。缓存可能在后续运行工具时重建。此前的嵌套包路径已废弃，以 `dist-onedir/dsh-pet-standalone-webm-chat.exe` 为准。

实际关机/注销、多显示器 DPI 和长时间 CPU/内存观察仍属于后续验收。测试不执行真实系统关机，不写入用户真实配置。本轮不提交或发布 Git 改动。

## 托盘与结构整理（2026-10-05）

- `packaging/` 已移除。冻结入口在 `scripts/pet_entry.py`，版本标识在 `build-onedir/build_variant.py` 临时生成，完整许可证正文在根目录 `DEPENDENCY_LICENSES.md`；不维护安装器脚本。`.git/` 保留版本历史，可清理编辑器索引缓存和未启用的 sample hooks，并执行不裁剪历史的 Git 压缩维护。
- 托盘由 `TrayController` 独立管理。任一宠物可见时显示选项打勾，再点隐藏全部并取消勾选；全部隐藏后再点显示全部。窗口在其他路径隐藏或恢复时也同步状态。
- 开机自启以系统实际状态为准；再次点击关闭后取消勾选，写入失败则恢复真实状态，不仅按点击结果显示。
- 所有菜单勾选通过 QAction 状态驱动绘制，不把符号拼入菜单文案；替换菜单后释放旧 Qt 对象，控制器保留菜单和动作引用。
- 清理无引用的函数、旧转发接口、孤立的旧聊天通知模块和旧会话复制逻辑；配置迁移仍清理已退出功能字段，已有用户文件不擅自删除。
- 删除与当前实现无关的聊天、语音、会话 writer、历史批次及已删除文档引用；保留线程、ABI、Qt 生命周期、迁移和资源回收的必要解释。
- Ruff 不再保留历史规则豁免。新功能的测试验证实际行为，包括托盘勾选绘制、失败写入回读和菜单对象销毁。
- 本轮 Python 回归 142 项通过（主套件 83、解码 32、预热 27），Ruff 通过。平铺包复验完成：C++ CTest、中文编码、Qt DLL 链、原生库和冻结原生自检均通过；桌宠与独立设置窗口启动通过；Windows 平台托盘浅色/深色、开启/关闭状态已检查。测试使用临时配置并模拟系统自启状态，不修改真实开机自启项。

## 测试归档、自启复验与 Git 维护（2026-10-05）

- 测试统一归到 `tests/`，包括 `native/test_core.cpp`、`tools/` 下的构建验收以及 `benchmarks/` 下的性能基准。CMake 和打包脚本已同步更新；运行时原生诊断模块改名为 `pet/native/diagnostics.py`，保留 `--native-self-test` 参数。
- `packaging/` 已移除。入口移到 `scripts/pet_entry.py`；版本标识由构建脚本在临时目录生成；不再维护 Inno Setup 安装器。Qt/PySide 所用的 GPL/LGPL 完整正文合并为根目录 `DEPENDENCY_LICENSES.md`，打包复制到 `_internal/licenses/`，其余依赖许可证继续从实际环境收集。
- 自启点击使用 QAction 当次选中的状态，写入后回读确认；Windows 查询只申请 KEY_QUERY_VALUE 权限，关闭后验证条目已清除，读写异常记录到日志。onedir 自启命令直接执行 exe，不再经 cmd/start。
- 新增独立临时注册表键中的真实 Windows 开关测试，覆盖源码及冻结命令、连续四次鼠标点击、配置同步与实际 ✓ 绘制。测试完成删除该临时键，不触碰用户 Run 登录项。本机未复现用户报告的重复开启，以上调整与新的 exe 已完成验证。
- 本轮 Python 回归 145 项通过（主套件 86、解码 32、预热 27）；Windows 桌面托盘测试 8 项通过。Ruff、C++ CTest、中文编码、Qt DLL 链、原生库、冻结原生自检及桌宠/设置窗口启动检查通过；平铺产物已更新。
- `.git` 执行不裁剪对象、不过期 reflog 的压缩维护，清掉 Cursor 索引缓存及未启用的 `.sample` hooks，体积约 101.3 MiB 降为 82.5 MiB。HEAD、全部分支引用与维护前的工作区状态一致，`git fsck --full` 无完整性错误；四个历史 dangling blobs 保留供恢复。未提交或推送。

## 托盘自启的包内绘制与连续点击修复（2026-10-05）

- 用户在 20:14 新包仍报告没有自启勾选、重复提示开启。此前模拟窗口测试不能作为实机问题已解决的依据。
- 用旧包的 PYZ 和运行库启动完整 AppShell，复现了注册表及 QAction 均已启用、但弹出首帧未绘制自启勾选的情况（标记区域蓝色像素为 0）。托盘原先通过单独的 ModernCheckLayer 和 singleShot(0) 绘制，改为 TrayMenu.paintEvent 在菜单本帧直接绘制；普通上下文菜单仍复用同一绘制函数。
- 开关根据控制器最近同步的系统状态取反，独立于 QAction 点击后传来的 bool；补充“动作勾选丢失仍应关闭”的回归测试。菜单弹出后取得焦点，提示只保留桌宠气泡，取消重复的系统通知。读写及点击结果记录 requested/actual/checked/ok，方便追踪实机状态。
- `tests/tools/verify_frozen_tray.py` 保留打包模块、Qt/原生运行库与完整启动流程，只替换测试入口；通过真实 Qt 托盘 Win32 回调打开菜单，使用 Windows SendInput 点击。测试比对注册表、QAction、配置、气泡及实际截图，不仅检查内部 bool。默认使用独立测试键；显式 `--run-key --in-place` 可验证原 exe 路径和实际 Run 值，先备份后在 finally 恢复，测试期间不得同时启动该 exe。真实配置只读取并复制到隔离 APPDATA。
- 新包在原 exe 路径及实际 Run 值上四次开关通过；每次等 10 秒复验，状态依次 True/False/True/False，气泡依次开启/关闭/开启/关闭，勾选区域蓝色像素依次 94/0/94/0。测试后原启动值恢复，正常 exe 字节与备份一致，未保留测试入口。
- 主回归 88 项、Windows 桌面托盘 10 项通过；Ruff、C++ CTest、冻结原生诊断、Qt DLL 链、中文编码及桌宠/设置窗口启动通过。产物仍为平铺 `dist-onedir/`，exe 旁不增加文档或诊断脚本。
