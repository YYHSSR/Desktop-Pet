# 纯桌宠：移除声音与桌面端启动入口，重排设置并重新打包

日期：2026-10-03。基线：本轮开始时的源码快照 before-silent-pet.zip；工作区原有用户修改保留。
关联：[上一轮纯桌宠清理](PR-REPORT-PURE-PET-REPACK-2026-10-03.md)。

## 核心特性

删除右键菜单、灵动岛卡片和工作提醒里的打开 ChatGPT 入口。玩家自行启动桌面端，桌宠继续只读本机 Work/Codex 会话。删除点击、碰撞、工作提示、报时、朗读的服务、资源、依赖和失效测试；节日与待办保留视觉提醒。

设置收敛为五个侧栏域。桌宠页按外观与气泡、动画与拖拽、多宠与碰撞分成三个页签，显示原先没有入布局的有效控件。锁定位置后拖拽相关项置灰，偏好值保留。节日开关常显，详细选项折叠。

## 修改文件说明

本轮文本源码共 82 个文件：新增 470 行、删除 10962 行。此统计以本轮快照为基线，不计本报告自身和二进制资产；`git diff --numstat` 包含此前用户修改，不用它混算本轮数量。

| 文件 | 增删 | 用途与原因 |
| --- | --- | --- |
| `.agents/skills/desktop-pet-ui-style/references/visual-system.md` | +4 / −2 | 同步五域契约、桌宠页签和有效截图选项。 |
| `README.md` | +4 / −4 | 说明玩家手动打开桌面端与静音互动。 |
| `THIRD_PARTY_NOTICES.md` | +0 / −38 | 移除已删除声音资源的来源与许可条目，保留动画和节日库声明。 |
| `docs/AGENT_LINK_PROTOCOL.md` | +2 / −4 | 移除启动实现说明，保留工作状态映射与有效自定义通道协议。 |
| `docs/INDEX.md` | +2 / −0 | 登记本轮交付证据。 |
| `docs/ONEDIR_PACKAGING.md` | +2 / −3 | 更新纯静音构建依赖和验证流程。 |
| `pet/agent_link.py` | +3 / −49 | 删除工作提示音和启动桌面端按钮；保留状态聚合、审批提示及忽略操作。 |
| `pet/app.py` | +3 / −214 | 删除声音服务生命周期、预热和窗口回调；保留节日气泡服务及应用退出顺序。 |
| `pet/chatgpt_desktop.py` | +1 / −71 | 仅保留本机工作会话目录解析，删除启动/激活应用实现。 |
| `pet/click_sound.py` | +0 / −945 | 删除已退休声音功能的实现、资源生成或测试。 |
| `pet/click_talk_dialog.py` | +0 / −107 | 删除只服务于已移除声音功能的实现/验证；点击绑定编辑器没有可达入口，实际点击气泡覆盖保留。 |
| `pet/collision_client.py` | +1 / −5 | 删除声音回调，保留物理冲量与命中视觉反馈。 |
| `pet/config.py` | +3 / −110 | 删除所有声音默认值与白名单，清理旧配置，保持其他偏好和并发保存。 |
| `pet/context_menus/icons.py` | +0 / −12 | 删除已无使用入口的扬声器图标。 |
| `pet/context_menus/registry.py` | +1 / −15 | 删除报时动作注册，保留节日视觉提醒注册。 |
| `pet/context_menus/shared.py` | +0 / −3 | 删除右键菜单启动 ChatGPT 动作。 |
| `pet/dynamic_island.py` | +2 / −8 | 卡片保留桌宠显隐和设置两项，删除第三按钮与启动信号。 |
| `pet/festival.py` | +2 / −27 | 改用通用文案/时间校验，删除声音配置与过时说明。 |
| `pet/festival_quotes_cn.py` | +1 / −1 | 文案库仍用于节日气泡，仅移除已失效的播报描述。 |
| `pet/festival_quotes_west.py` | +1 / −1 | 文案库仍用于节日气泡，仅移除已失效的播报描述。 |
| `pet/festival_service.py` | +3 / −68 | 提醒仅显示气泡；删除音频通道和报时让位逻辑，保留按分钟去重。 |
| `pet/festival_settings.py` | +11 / −47 | 删除播报选项，按钮改名立即预览，避免描述不存在的声音功能。 |
| `pet/island_collision.py` | +5 / −9 | 删除声音反馈；抛掷、冲量、挤压与岛弹跳继续工作。 |
| `pet/modern_settings_dialog.py` | +64 / −254 | 五个侧栏域和三个桌宠页签；有效控件入布局，锁定位置禁用拖拽，删除不可达命令。 |
| `pet/reminder_values.py` | +53 / −0 | 从删除的报时模块提取仍被节日提醒使用的布尔、时间、文案校验。 |
| `pet/self_talk_voice.py` | +0 / −256 | 删除已退休声音功能的实现、资源生成或测试。 |
| `pet/settings_interaction.py` | +1 / −21 | 点击反馈和随机自言自语采用竖排卡片，清理过时描述。 |
| `pet/settings_pet_controls.py` | +8 / −73 | 增加可操作的大小与工作状态开关，删除声音控件和未显示按钮。 |
| `pet/settings_standalone.py` | +10 / −124 | 独立设置宿主仅承担节日预览与位置避让，删除声音通道。 |
| `pet/settings_widgets.py` | +0 / −87 | 删除声音资源选择器与语音侧栏域。 |
| `pet/sound_winmm.py` | +0 / −709 | 删除已退休声音功能的实现、资源生成或测试。 |
| `pet/voice_chime.py` | +0 / −491 | 删除已退休声音功能的实现、资源生成或测试。 |
| `pet/voice_chime_quotes.py` | +0 / −96 | 删除已退休声音功能的实现、资源生成或测试。 |
| `pet/voice_chime_service.py` | +0 / −835 | 删除已退休声音功能的实现、资源生成或测试。 |
| `pet/voice_chime_settings.py` | +0 / −239 | 删除已退休声音功能的实现、资源生成或测试。 |
| `pet/window.py` | +0 / −48 | 删除点击和碰撞播放、音量与声音缓存属性；保留动画和拖拽行为。 |
| `pet/window_alerts.py` | +1 / −38 | 点击与周期气泡仅显示文本/图片，删除朗读及无人消费的文本记录字段。 |
| `requirements.txt` | +0 / −1 | 删除在线语音合成依赖。 |
| `scripts/build_linux.sh` | +7 / −3 | 排除声音依赖和资源收集，随产物复制许可说明，防止开发环境依赖混入。 |
| `scripts/build_macos.sh` | +7 / −5 | 排除声音依赖和资源收集，随产物复制许可说明，防止开发环境依赖混入。 |
| `scripts/build_onedir.ps1` | +6 / −5 | 排除声音依赖和资源收集，随产物复制许可说明，防止开发环境依赖混入。 |
| `scripts/capture_settings_pages.py` | +19 / −13 | 捕获五个域和三个桌宠页签，删除声音控件访问和失效图片目录。 |
| `scripts/check_bundle_encoding.py` | +2 / −2 | 中文编码断言改用当前菜单与设置字面量。 |
| `scripts/gen_agent_sounds.py` | +0 / −96 | 删除已退休声音功能的实现、资源生成或测试。 |
| `scripts/make_click_sound.py` | +0 / −54 | 删除已退休声音功能的实现、资源生成或测试。 |
| `scripts/slim_bundle.py` | +3 / −9 | 必需清单移除 Qt 音频绑定、插件及其视频 DLL；保留独立 ffmpeg 动画解码。 |
| `scripts/verify_bundle_tts.py` | +0 / −257 | 删除已退休声音功能的实现、资源生成或测试。 |
| `tests/conftest.py` | +1 / −83 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_agent_link.py` | +6 / −83 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_agent_multi_session.py` | +0 / −1 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_chatgpt_desktop.py` | +1 / −38 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_click_self_talk.py` | +84 / −0 | 保留真实点击入口与周期气泡独立性的有效回归，替代朗读测试。 |
| `tests/test_click_self_talk_speech.py` | +0 / −275 | 删除已退休声音功能的实现、资源生成或测试。 |
| `tests/test_click_sound.py` | +0 / −612 | 删除已退休声音功能的实现、资源生成或测试。 |
| `tests/test_collision_settings.py` | +0 / −30 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_collision_window.py` | +4 / −27 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_config_schema.py` | +10 / −32 | 更新有效配置快照；数值安全和并发保存改用存续字段。 |
| `tests/test_config_sound.py` | +0 / −160 | 删除已退休声音功能的实现、资源生成或测试。 |
| `tests/test_desktop_pet_features.py` | +3 / −7 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_dynamic_island_revamp.py` | +2 / −4 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_effects_integration.py` | +0 / −2 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_feature_gating.py` | +0 / −1 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_festival.py` | +17 / −91 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_island_collision.py` | +0 / −7 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_island_remote_wall.py` | +0 / −1 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_menu_layout.py` | +9 / −298 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_pet_interaction_locks.py` | +0 / −17 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_pure_pet.py` | +1 / −1 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_requested_regressions.py` | +0 / −21 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_self_talk_voice_precache.py` | +0 / −273 | 删除已退休声音功能的实现、资源生成或测试。 |
| `tests/test_settings_and_resources.py` | +0 / −178 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_settings_interaction_tabs.py` | +4 / −16 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_settings_process_isolation.py` | +0 / −4 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_silent_pet.py` | +83 / −0 | 公开窗口/菜单回归：旧声音配置清理、无启动入口、布局保存与锁定依赖。 |
| `tests/test_single_process_shared.py` | +2 / −8 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_single_process_spawn.py` | +2 / −43 | 删除退休声音/启动/不可达控件断言和空夹具；保留本文件现有行为回归并更新五域契约。 |
| `tests/test_slot_and_memory.py` | +9 / −9 | 把继承/存档回归中的退休音量字段换成仍有效的动画间隔，保持真实持久化覆盖。 |
| `tests/test_verify_bundle_tts.py` | +0 / −114 | 删除已退休声音功能的实现、资源生成或测试。 |
| `tests/test_voice_chime.py` | +0 / −943 | 删除已退休声音功能的实现、资源生成或测试。 |
| `tests/test_voice_chime_edge_voice.py` | +0 / −237 | 删除已退休声音功能的实现、资源生成或测试。 |
| `tests/test_voice_chime_service.py` | +0 / −1053 | 删除已退休声音功能的实现、资源生成或测试。 |
| `tests/test_winmm_sound.py` | +0 / −834 | 删除已退休声音功能的实现、资源生成或测试。 |

删除二进制资源：`assets/sounds/` 共 6 个音频文件、`assets/chat/` 共 9 张旧聊天图片。资源备份位于交付目录外的 work，未进入项目运行路径和新包。既有稳定构建与旧 native DLL 备份保持原状，未打入新包。


## 性能分析

Windows、Python 3.13.15、PySide6 6.11.2。真实本机会话目录：4 个文件；首次扫描 3.651 ms。200 次无新增内容轮询：平均 0.303 ms，最大 1.043 ms。该采样期间读到了真实工作事件，桌宠有 95 个动作可用。

联动使用既有文件监听线程，不增加线程、网络请求或会话写操作。声音合成、下载、缓存与声卡访问路径已移除。设置重排发生在打开窗口时，关闭时仍由原有保存路径落盘。执行 `D:/python/miniconda/envs/py13/python.exe E:/CODX/2026-10-03/shen/work/silent_settings_bench.py`，Windows 原生 Qt，64 次构造/销毁、1 次预热后采样 63 次：中位数 206.932 ms，均值 320.857 ms，最大 484.564 ms。这是打开设置窗口的成本，不在动画帧路径执行；构造沿用原有开机自启读取和本地配置访问。

RSS 第 16/32/64 次分别为 83.277/83.836/83.598 MiB；后 32 次变化 -0.238 MiB，未观察到该采样区间持续增长。启动至最终累计增加 4.762 MiB，包含 Qt 缓存预热；没有把这一短期采样当成长期无泄漏证明。

上一包 162.13 MiB，新包 129.79 MiB，减少 32.34 MiB（约 19.9%）。移除的是声音依赖、资源与冻结模块，动画解码仍使用 imageio-ffmpeg。

## 实机运行记录

执行 live_silent_check.py，Windows 原生 Qt 窗口可见；30 秒内收到 working=5、thinking=1，1 个真实会话，请求动作：写代码、吃Token、轻快记录。结束输出 worker_stopped True。

执行 scripts/capture_settings_pages.py，宽度 720/1100，浅色与深色，共 32 张原生截图；检查桌宠三个页签与自动化入口，未发现横向裁切。Windows 缩放 125%，720 px 窗口截图为 900 px 宽，滚动区可达。锁定位置后的置灰与恢复由公开设置窗口测试验证。

Mac/Linux 构建脚本同步移除声音收集项，但本机仅能验证 Windows，未宣称其他平台的原生运行结果。

## 测试与验证

新四项回归在本轮基线全部失败，分别揭示残留声音键、菜单启动入口、旧侧栏和灵动岛第三按钮；当前全部通过。锁定位置依赖回归先红后绿。

第一轮完整回归：1860 passed、6 skipped、11 warnings，129.58 秒。最终完整回归：1861 passed、6 skipped、11 warnings，125.46 秒。打包/编码/布局/交付证据集中检查另有 63 passed（2.00 秒）。跳过的是平台相关用例；警告来自既有 Qt 图像镜像 API 的弃用提示。

产品模块引用审计：所有保留 Python 模块均有其他生产模块或入口引用。ruff（含产品 F401/F841 独立检查）通过。未把静态引用审计描述成对每一行代码用途的绝对证明。

## 打包结果

命令：`powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build_onedir.ps1 -PythonExe D:/python/miniconda/envs/py13/python.exe`。

- 原生碰撞 CTest：1/1 passed。ABI=2，build_id=`collision-core/2.0+99648e8ce8d66563-GNU16.2.0-Release`。
- 编码检查 PASS；Shiboken/QtCore/QtGui/QtWidgets DLL 链通过。
- 原生主窗口运行 10 秒通过；独立设置窗口运行 10 秒，精确 PID 的 Win32 Qt 标题检查返回 `SETTINGS_QT_WINDOW_OK`。
- 939 个文件，解压体积 230.99 MiB；冻结 PYZ 共 339 个模块。
- 冻结模块无 pet 的音频/朗读/聊天/识屏/主动感知模块，无 edge_tts、aiofiles、aiohttp、certifi、keyring、PySide6.QtMultimedia；包内无音频文件和 QtMultimedia 文件。
- 递归检查 pet 字节码的名称，无 `open_chatgpt`、`open_chatgpt_from_pet`、`windows_app_id`、`open_chatgpt_requested`。
- ZIP CRC 通过，附使用说明、项目许可和第三方声明。

文件：`Desktop-Pet-Silent-2026-10-03.zip`，129.79 MiB。
SHA-256：`dc5682327174cbe23b94c412848a638c5eae0d6561eada334bfc78c97ccba24c`。

## 设置预览

[720 px 浅色：动画与拖拽](screenshots/silent-pet-2026-10-03/light-720-movement.png) · [1100 px 深色：多宠与碰撞](screenshots/silent-pet-2026-10-03/dark-1100-companions.png)。GitHub 附两张代表截图；本地交付目录的 Settings-Preview 保留四种窗口/配色组合的全部 32 张截图。

实机工作监测、性能、构建、测试、资源和包内审计的原始日志保存在 work。

## GitHub 推送整理

本次提交汇总此前连续清理和联动改动，直接推送现有 main 分支。生成的构建目录、可执行程序、ZIP 和原生 DLL 事务备份由 .gitignore 排除；交付包继续保存在本地 outputs。

- `.gitignore`：增加 `/pet/native/.native-previous-*/`，保留本地备份并排除提交。
- `.github/workflows/build-linux.yml`、`build-macos.yml`：删除失效桥接插件的成功提示，与当前资源收集项一致。
- `.github/workflows/build-windows.yml`：删除构建器未声明的 `-SkipZip` 参数，同步命令快照，避免手动构建立即失败。
- 本报告和 `docs/screenshots/silent-pet-2026-10-03/`：补充推送前验证，加入两张实际设置截图，确保 GitHub 预览链接可用。

推送前最终验证（Windows、Python 3.13.15、PySide6 6.11.2）：

- `python -m ruff check pet scripts tests`：All checks passed。
- `QT_QPA_PLATFORM=offscreen python -m pytest -q`：1861 passed、6 skipped、10 warnings，141.69 秒。
- 20 个逐核负载进程，三轮起始 CPU 采样均为 100.0%；每轮执行 agent_link_threads、codex_monitor、chatgpt_desktop、collision_ipc、single_process_shared、single_process_spawn、webm_clip_lifecycle 七个测试族。三轮均为 136 passed、1 skipped，pytest 用时分别 12.57 / 12.23 / 12.19 秒；负载进程全部停止。复跑脚本和日志保存在本地 work。
- 工作流 YAML 解析与 Linux/macOS 构建脚本 Bash 语法检查通过。此项不代表在其他平台运行了构建。
- 暂存区逐文件审计：无新增生成二进制、原生备份或命中的凭据模式；`git diff --cached --check` 通过。
