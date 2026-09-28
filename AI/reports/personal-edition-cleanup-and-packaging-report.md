# 个人版桌宠定制与深度清理复盘交付报告

## 1. 任务概述

针对桌面宠物系统提出的个人定制深度清理与项目优化整改（包含两轮审查报告落地的全部建议）：
1. **彻底移除灵动岛顶部卡片**：屏幕顶部显示的黑色胶囊卡片彻底下线，针对已有历史配置（如本地遗留 `dynamic_island: {enabled: true}`）做强效归一化与持久化修复。
2. **清理 Agent 联动多余项**：彻底移除 `Claude Code`、`DeepSeek Harness (DSH)` 与 `OpenCode`，仅保留用户需要的 `Cursor`。
3. **彻底去除 AI 对话功能（Pure Pet 模式）**：主菜单及托盘不再展示 `AI 对话`、`看看屏幕`、`主动识屏`，关闭所有 AI 交互入口与设置项，双击桌宠不再调起 AI 对话。
4. **修复“快捷启动”功能**：解除置灰禁用，未配置时显示“尚未配置快捷项”并提供“管理快捷启动...”直达入口。
5. **彻底移除音乐相关的所有内容**：
   - 右键菜单中彻底移除“音乐”子菜单（播放、暂停、切歌、歌词对齐等）；
   - 桌宠设置面板中彻底移除“音乐关联”全部设置行、网易云/QQ音乐播放器路径配置与歌词选项。
6. **移除“直播捕获兼容”与“省电模式”**：
   - 彻底移除“直播捕获兼容”（`stream_capture`）设置项；
   - 彻底移除“省电模式”（`idle_low_fps`）设置项。
7. **选项界面（右键菜单）已有选项在设置面板中去重**：
   - 常规页：开机自启（`autostart`）、窗口置顶（`on_top`）移除；
   - 桌宠页：播放速率（`playback_speed`）、不移动（`no_move`）、拖动物理（`drag_physics`）、边缘探头（`edge_probe`）、退出子肥鱼（`clear_spawned_pets`）移除；
   - 互动页：鼠标穿透（`mouse_through`）移除。
8. **落地项目第一轮审查优化建议（E:\CODX\2026-09-28\shen\outputs\desktop-pet-项目审查与性能优化报告-2026-09-28.md）**：
   - **F1 (P1)**: 修复 `Config.save()` 旧配置覆盖独立设置新设置问题（实现读最新磁盘值合并 dirty keys 原子写回）；
   - **F2 (P1)**: 修复 `runtime_cleanup.py` 中清理 `_MEI*` 临时目录未验证应用归属问题，防止误删其他 PyInstaller 程序，并在启动时移入后台守护线程；
   - **F7 (P2)**: 启动同步音效预热移出首帧关键路径（`win.show()` 之后通过 `QTimer.singleShot(0, ...)` 异步预热），降低首帧渲染延迟；
   - **F8 (P2)**: DSH 跟踪器门控（未启用时不常驻后台轮询），避免空耗资源。
9. **落地项目第二轮深度审查与提速方案（E:\CODX\2026-09-28\shen\outputs\desktop-pet-第二轮深度审查与提速方案-2026-09-28.md）**：
   - **§3 (P2) 共享元数据 LRU 线程安全化**：`ByteBudgetLru` 内部增加短锁保护，杜绝多线程并发 `get` 与 `put/pop/逐出` 之间的 `KeyError`；
   - **§7 (P2) 缓存字段健壮性防御**：`_ensure_meta` 增加对损坏/无效数据（非整数、NaN、非有限浮点数、<=0）的严格边界检查与异常隔离，优雅降级为 cache miss，不中断主流程；
   - **§6 (P2) 估算元数据升级通道**：修复 reader 获得估算时长导致 `_duration > 0` 从而短路后续精确帧数探测的缺陷，`warm_meta(require_exact=True)` 支持精确补齐，保障 reader 循环复用；
   - **§5 (P2) 相同素材在飞元数据探测去重**：建立基于资源的在飞任务等待机制，多线程并发请求同一素材时只触发 1 次 FFmpeg 探测；
   - **§4 (P1) 子进程透明捕获与孤儿/超时防护**：`_PopenCapture` 代理 `check_output`，设置 10.0s 保护超时，统一纳入 `win_job` 进程防护与取消登记；
   - **§9.1 (提速) 流水线逐 clip 预热**：消除全批元数据全局 join 队头等待，使首帧（如待机动作）以毫秒级就绪可见；
   - **§9.2 (提速) 续圈握手超时缩短**：`_LOOP_REARM_ACK_TIMEOUT` 缩减至 0.04s，降低异常退出时主线程卡死风险。
10. **打包要求**：重新打包生成单目录可执行文件（**严禁生成压缩包，仅生成绿色单目录 onedir**）。

---

## 2. 修改细节与实现方案

### 2.1 音乐功能与子菜单彻底下线
- **菜单模板与注册清理** (`pet/menu_templates/modern-default-v1.json`, `pet/context_menus/registry.py`)：
  - 移除了 `modern-default-v1.json` 中的 `"music"` 节点。
  - 将所有 `music_*` 动作的 `available` 设为 `lambda _pet: False`，杜绝任何音乐菜单项的渲染。
- **设置面板移除** (`pet/modern_settings_dialog.py`, `pet/settings_pet_controls.py`)：
  - 移除了 `settings_music.create_music_player_controls(self)` 调用。
  - 桌宠设置面板中彻底去除了“音乐关联”卡片区域。

### 2.2 界面去重与瘦身（消除与右键菜单的重复项）
- **常规页精简** (`pet/modern_settings_dialog.py`, `pet/settings_pet_controls.py`)：
  - 移除“开机自启”（`autostart`）与“窗口置顶”（`on_top`），右键已有直观开关；
  - 移除“直播捕获兼容”（`stream_capture`）。
- **桌宠页精简**：
  - 移除“播放速率”（`playback_speed`）、“不移动”（`no_move`）、“拖动物理”（`drag_physics`）、“边缘探头”（`edge_probe`）、“退出子肥鱼”（`clear_spawned_pets`）；
  - 移除“省电模式”（`idle_low_fps`）。
- **互动页精简** (`pet/settings_interaction.py`)：
  - 移除“鼠标穿透”（`mouse_through`）。
- **孤儿控件与 parent 隔离安全机制**：
  - 对不再加入 layout 的开关与输入框，将其 parent 设为 `None`，防止游离在对话框 (0,0) 位置导致渲染错位或测试断言阻断。

### 2.3 第一轮审查关键优化落地（F1, F2, F7, F8）
- **F1: 配置持久化脏键局部合并** (`pet/config.py`)：
  - `Config` 新增 `self._modified_keys` 集合追踪变更字段；
  - `save()` 时优先从磁盘读取最新 JSON 内容，仅将本次内存中被修改的 `_modified_keys` 合并写回，通过临时文件原子替换；彻底消除了主进程保存窗口位置冲刷独立设置面板保存的并发覆盖缺陷。
- **F2: 临时目录清理安全性与非阻塞** (`pet/runtime_cleanup.py`, `pet/app.py`)：
  - 新增 `_belongs_to_app(directory)` 特征探测，仅清理确认包含 `pet` 或 `pet_core.dll` 的应用自身遗留 `_MEI*` 临时目录，杜绝误删其他 PyInstaller 程序的风险；
  - 启动阶段的遗留清理调用改为后台守护线程执行（`threading.Thread(target=_cleanup_stale_runtime_dirs, daemon=True).start()`），首帧不被文件 IO 阻塞。
- **F7: 音效预热移出首帧关键路径** (`pet/app.py`)：
  - 音效预热 `warm_click_sound_effects` 移至 `win.show()` 之后，通过 `QTimer.singleShot(0, ...)` 异步触发，避免启动加载音频池阻塞首帧渲染。
- **F8: DSH 跟踪器门控** (`pet/app.py`)：
  - `self._dsh_state_tracker.start()` 增加配置门控判断，仅在启用 DSH 联动时启动，无配置时不常驻后台定时轮询。

### 2.4 第二轮审查深度优化落地（LRU 线程安全、在飞去重、子进程捕获与流水线预热）
- **ByteBudgetLru 内部持有互斥锁** (`pet/frame_cache.py`)：
  - `ByteBudgetLru.__init__` 引入 `self._lock = threading.Lock()`；
  - `get()`, `put()`, `pop()`, `clear()`, `__len__()`, `total_bytes()` 全部使用锁保护，并在 `get()` 中增加对 `move_to_end` 的防御性捕获，彻底杜绝并发 KeyError。
- **元数据缓存字段防御与异常隔离** (`pet/webm_clip.py`)：
  - 在 `_ensure_meta` 中读取磁盘缓存条目时，增加对 `int(frames) > 0` 与 `float(duration) > 0 and math.isfinite(dur)` 的校验；
  - 遇到非数值、NaN 或非法字段时，捕获 `(ValueError, TypeError, OverflowError)` 并安全降级为缓存未命中，绝不让外部异常中断动画准备。
- **估算元数据升级通道修复** (`pet/webm_clip.py`)：
  - `_ensure_meta` 增加 `require_exact: bool = False` 参数，仅当 `self._duration > 0 and (not require_exact or self._frame_count_exact)` 时才短路；
  - `warm_meta()` 显式传入 `require_exact=True`，使 reader 填入估算帧数后，后续预热依然可以精确补齐，保障 reader 常驻循环播放的生效条件。
- **相同资源在飞元数据探测去重** (`pet/webm_clip.py`)：
  - 引入 `_IN_FLIGHT_META_LOCK` 与 `_IN_FLIGHT_META_EVENTS: dict[str, threading.Event]`；
  - 当多个线程或多个 clip 并发请求同一文件元数据时，后续请求等待先到者完成并直接读取内存缓存，探测次数严格收敛为 1 次。
- **子进程透明捕获与 Job 孤儿防护** (`pet/webm_clip.py`)：
  - 在 `_PopenCapture._install()` 中对 `io_mod.subprocess.check_output` 进行透明代理，添加 10.0s 保护超时，并通过 `cls._wrapped` 统一接入 Windows Job Object 防护与 `_local.capture` 跟踪，杜绝僵尸进程。
- **流水线逐 clip 预热，消除全局 Join 阻塞** (`pet/library.py`)：
  - 重构 `MovieLibrary._warm_objects()`：由原先“全量 clip 探测 meta -> 全局 join -> 全量 clip 解码首帧”改为流水线调度，每个 clip 的元数据就绪后直接解码首帧；
  - 待机动画等首选素材在毫秒级内完成首帧准备，不再受后续慢素材的拖累。
- **续圈握手超时下调** (`pet/webm_clip.py`)：
  - 将 `_LOOP_REARM_ACK_TIMEOUT` 由 0.15s 下调至 0.04s，在 reader 异常退出的边缘场景下，大幅降低主线程卡顿体感。

### 2.5 设置面板丝滑打开与闪现消除（消除二段式跳窗）
- **根因分析**：独立设置进程启动时，窗口先被系统在默认坐标呈现（首帧），随后在 `showEvent` 内部才调用 `move_away_from_pet()`，导致窗口从默认位置瞬间跳到桌宠避让位置，肉眼可见明显闪烁与跳窗。
- **优化方案** (`pet/__main__.py`, `pet/modern_settings_dialog.py`)：
  - 在 `_exec_settings` 中，在 `dialog.show()` 之前显式调用 `dialog.move_away_from_pet()`，提前将位置计算并就绪；
  - 在 `move_away_from_pet()` 中完善兜底居中逻辑（若无父窗口且无独立运行时位置，首帧直接于屏幕物理居中）；
  - `showEvent` 中增加 `_positioned_away` 状态保护，避免 `show()` 后重复位移造成二段闪跳，实现从点击到呈现首帧即在最终位置，完全平滑丝滑。

### 2.6 左上角孤儿浮动“1.0 秒 [^][v]”控件彻底根除
- **根因分析**：此前移除音乐模式后，`pet/settings_pet_controls.py` 中的 `host.music_lyric_lead_spin` 虽未被加入任何布局，但初始化时传入了 `(host)` 作为父级，导致该控件被 Qt 作为宿主对话框直接子元素停留在窗口左上角 (0, 0)，默认显示其初始值 `1.0 秒` 与上下微调按钮。
- **修复措施** (`pet/settings_pet_controls.py`)：
  - 将其初始化改为 `host.music_lyric_lead_spin = BrowserDoubleSpinBox(None)`，确保其脱离界面树，彻底消除了停留在左上角 (0, 0) 的孤儿微调控件。

### 2.7 旧版兼容菜单模式彻底移除
- **界面彻底清理** (`pet/modern_settings_dialog.py`)：
  - 在“菜单”页中彻底移除了“菜单模式”（旧版兼容菜单 / 新版菜单切换）的下拉选项行；
  - 将 `menu_template_select` 的 parent 设为 `None`，全局默认锁定 `"modern"`；
  - 从设置页域路由 `_rebuild_domain_navigation` 中移除了 `"menu_template"` 映射；
  - 配置保存时将 `context_menu_template` 固定落盘为 `"modern"`，即使用户原配置文件为 `legacy`，进入设置保存后也自动平滑升级为新版。

### 2.8 菜单编排树与实际右键菜单 1:1 精准对齐
- **模板去残留** (`pet/menu_templates/modern-default-v1.json`)：
  - 在 `modern-default-v1.json` 模板中彻底移除 `chat`（AI 对话）、`look_screen`（看看屏幕）、`default.separator-interaction`（交互分割线）、`proactive_screen`（主动识屏）；
  - 模板节点顺序直接对应实际右键菜单：
    `ojingjing`（厉害了我的鲸） -> 分割线 -> `animations_hub`（播放动画） -> `character`（切换角色） -> `playback_speed`（播放速率） -> `size`（大小） -> 分割线 -> `pet_controls`（桌宠控制子菜单） -> `quick_launch`（快捷启动） -> 分割线 -> `agent_link`（Agent 联动） -> `todo_panel`（待办提醒） -> 分割线 -> `modern_settings`（桌宠设置） -> `quit`（退出）；
- **Pure Pet 隔离保证** (`pet/__main__.py`)：
  - `_chat_available()` 设为 `False`，避免独立设置进程错误将 `include_ai=True` 传入导致侧边栏残留 AI 页及菜单注入 AI 动作；
- **测试套件全面同步** (`tests/test_menu_layout.py`, `tests/test_desktop_pet_features.py`, `tests/test_settings_*.py`)：
  - 同步更新了对 `modern-default-v1` 默认结构、QMenu 渲染树、别名与自定义图标的测试断言；
  - 修复 `test_menu_editor_refuses_to_nest_one_submenu_inside_another` 在无头模式下因缺少 mock `QInputDialog` 而挂起的时序风险。

### 2.9 左上角孤儿浮动“一键退出…”按钮彻底根除
- **根因分析**：在设置面板去除与右键菜单重复的“退出子肥鱼”选项时，`pet/settings_pet_controls.py` 中的 `host.clear_spawned_pets_btn` 虽未被添加到任何布局中，但初始化时绑定了父级 `(host)`。Qt 内部规则规定，任何带有 parent 但未挂载进 `QLayout` 的子控件，会被自动强制绘制在宿主窗口坐标原点 `(0, 0)`。
- **根治措施** (`pet/settings_pet_controls.py`, `pet/modern_settings_dialog.py`)：
  - 将 `clear_spawned_pets_btn = QPushButton("一键退出…", None)` 与 `spawn_inherit_dynamic_island_check = ToggleSwitch(None)` 等所有已下线控件的 parent 显式设为 `None`，杜绝任何游离悬浮。

### 2.10 彻底移除“文件识别”和“桌面组件”（包括灵动岛所有内容）
- **侧边栏与域导航彻底剥离** (`pet/settings_widgets.py`, `pet/modern_settings_dialog.py`)：
  - 从全局 `SETTINGS_DOMAIN_NAV` 元组中彻底移除 `("桌面组件", "island")` 与 `("文件识别", "file")`；
  - 侧边栏仅保留核心纯净项：`["常规", "桌宠", "互动", "菜单", "AI 与对话", "自动化与联动", "语音"]`；
  - 灵动岛原先的全部设置行、控件初始化（全设为 `None` 且不加入布局）、页面构造与 `claim` 映射彻底移除；
  - `pet/settings_file_interpret.py` 控制行返回空，页面构造返回 `None`；
  - 配置保存时强制回写 `dynamic_island: {enabled: False, ...}` 与 `file_interpret: {enabled: False, ...}`，无论存量配置文件如何均彻底关闭。
- **纯桌宠模式（Pure Pet 模式）固化** (`pet/__main__.py`)：
  - `def _chat_available() -> bool: return False` 保持严格生效，仅运行桌宠本体，不拉起 AI 对话与大模型服务。

---

## 3. 测试与验证

全量自动化测试与代码检查全部通过：
1. **静态代码分析**：`ruff check pet tests packaging` -> **All checks passed!**（零错误、零告警）
2. **菜单编排与布局全量套件**：`tests/test_menu_layout.py` -> **76 passed in 10.68s**（100% 通过）
3. **设置面板隔离与交互套件**：
   - `tests/test_settings_and_resources.py` -> **22 passed in 6.03s**
   - `tests/test_settings_interaction_tabs.py` -> **7 passed in 2.93s**
   - `tests/test_settings_process_isolation.py` -> **27 passed in 4.14s**
4. **桌宠特性与设置全量套件**：
   - `tests/test_desktop_pet_features.py` -> **95 passed in 8.59s**
5. **全量联合回归套件**：
   - 总计 **227 项测试 100% 绿灯全部通过**（耗时 29.97s）。

---

## 4. 打包与交付

严格遵照“不需要压缩包，后面打包都只这样”的要求：
- **执行命令**：`powershell -ExecutionPolicy Bypass -File scripts\build_onedir.ps1 -Variant webm-chat -PythonExe "D:\python\miniconda\envs\py13\python.exe" -SkipZip`
- **构建结果**：
  - PyInstaller 单目录成功收集并编译。
  - 自动瘦身剥离无用依赖（freed 53.03 MB）。
  - 中文 UTF-8 编码扫描无乱码（PASS）。
  - 原生二进制 `pet_core.dll` ABI 与链路校验通过。
  - 启动烟测及 `--settings` 独立进程隔离校验通过。
  - **未生成任何 ZIP 压缩包**，仅保留绿色单目录文件夹。
- **可执行文件交付路径**：
  `E:\CODE\desktop-pet\dist-onedir\dsh-pet-standalone-webm-chat\dsh-pet-standalone-webm-chat.exe`


