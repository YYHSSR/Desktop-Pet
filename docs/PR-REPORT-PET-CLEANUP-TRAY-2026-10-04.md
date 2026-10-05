# 桌宠精简、气泡与托盘交付记录（2026-10-04）

本轮只保留本地修改，没有提交或推送 GitHub。应用继续以桌宠与本机 ChatGPT Work/Codex 工作状态为主；用户自行打开 ChatGPT。
此报告补充 [设置变更门禁](SETTINGS-CHANGE-GATES.md)、[打包流程](ONEDIR_PACKAGING.md) 与 [此前纯净版报告](PR-REPORT-PURE-PET-REPACK-2026-10-03.md)。

## 修改文件说明

- 移除省电模式的配置、控件、帧发布/解码节流、共享节流仲裁；移除灵动岛窗口、静态碰撞/IPC通道、隐藏反馈以及相关测试。
- 移除菜单编排、旧模板/主题、彩蛋弹窗与飞行彩蛋；固定右键菜单。托盘仅有显示/隐藏全部桌宠、鼠标穿透、开机自启、退出。
- 右键负责大小、速度、置顶、移动与拖动物理等快捷操作；设置只负责详细偏好。通过并发配置回归确认保存设置不会覆盖其它入口修改。
- 气泡锚定角色主体，间距8逻辑像素，字体14逻辑像素；按字体实测行高避免裁切；思考气泡尾巴随边缘换位镜像。
- 补充36条自言自语短句；默认过程文案不依赖可缺失的步骤/会话字段，自定义步骤文案缺失编号时显示“当前步骤”。仅原始默认词库自动替换，用户自定义保留。
- 联动开关前移，长台词、概率和文案模板折叠；菜单设置只保留快捷应用、快捷网址、外观。资源路径解析拆到asset_paths，设置/点击台词测试按用途重命名。
- 重复通用SKIll指南先归档仓库外再删除；空的旧integrations目录移除。保留角色媒体、自言自语图片、原生源码、许可证与项目技能。
- 构建临时目录、生成spec与Python/测试/检查缓存共14处（24.85 MiB）移到仓库外的work/2026-10-04/recoverable-build-cache，项目内不保留这些可重新生成的文件。删除命令被环境策略拦截，采用可恢复的移出方式完成清理。

下面增删行以开始前的source-baseline.zip为基线；不在该快照内的文件以HEAD为基线。已有未提交的构建/监视器/验证脚本改动继续保留，不把它们当成本轮新增。重命名按删除+新增列示。

| 文件 | 新增行 | 删除行 | 修改与原因 |
|---|---:|---:|---|
| `.agents/skills/desktop-pet-ui-style/references/visual-system.md` | 10 | 0 | 记录新的入口归属、折叠策略、气泡字体及距离规则。 |
| `C++-Python/src/collision.cpp` | 1 | 5 | 删除原生静态岛弹床分支，保持与Python桌宠求解一致，并重建DLL。 |
| `CONTEXT.md` | 10 | 16 | 同步单一偏好归属和固定菜单模型，避免后续开发恢复已删除功能。 |
| `README.md` | 8 | 3 | 更新真实的联动入口、托盘归属、目录用途及删除文档的后果。 |
| `SKIll/Agent-Code/SKILL.md` | 0 | 49 | 删除未被当前工程引用的重复通用指南；先归档到仓库外，保留.agents中的项目技能。 |
| `SKIll/Agent-Code/references/debugging.md` | 0 | 44 | 删除未被当前工程引用的重复通用指南；先归档到仓库外，保留.agents中的项目技能。 |
| `SKIll/Agent-Code/references/design.md` | 0 | 42 | 删除未被当前工程引用的重复通用指南；先归档到仓库外，保留.agents中的项目技能。 |
| `SKIll/Agent-Code/references/implementation.md` | 0 | 42 | 删除未被当前工程引用的重复通用指南；先归档到仓库外，保留.agents中的项目技能。 |
| `SKIll/Agent-Code/references/planning.md` | 0 | 42 | 删除未被当前工程引用的重复通用指南；先归档到仓库外，保留.agents中的项目技能。 |
| `SKIll/Agent-Code/references/verification.md` | 0 | 47 | 删除未被当前工程引用的重复通用指南；先归档到仓库外，保留.agents中的项目技能。 |
| `SKIll/En-SKILL.md` | 0 | 145 | 删除未被当前工程引用的重复通用指南；先归档到仓库外，保留.agents中的项目技能。 |
| `docs/INDEX.md` | 1 | 9 | 移除失效导入、注释或接口说明，保持现有有效调用和样式。 |
| `pet/__main__.py` | 1 | 3 | 移除失效导入、注释或接口说明，保持现有有效调用和样式。 |
| `pet/agent_link.py` | 2 | 20 | 移除闲置活跃锚点与隐藏岛反馈分支，继续处理本机会话和工作状态；保留开始前用户的监视器修订。 |
| `pet/app.py` | 60 | 322 | 托盘收拢为四项系统操作，移除岛和隐藏气泡转发，保留多桌宠生命周期及预热。 |
| `pet/asset_paths.py` | 13 | 0 | 从退役彩蛋模块提取仍被自言自语图片使用的资源路径解析。 |
| `pet/collision.py` | 12 | 33 | 移除灵动岛静态成员标记与特殊弹床恢复系数，保留桌宠碰撞求解。 |
| `pet/collision_client.py` | 2 | 38 | 删除岛几何和阈值/彩蛋分支，保持真实桌宠碰撞预测及冲量处理。 |
| `pet/collision_ipc.py` | 7 | 94 | 删除静态成员第二通道；状态归属握手登记的桌宠，保留IPC选举、快照和求解。 |
| `pet/config.py` | 7 | 186 | 加载短句资源；清除退役配置并迁移原始默认词库，保留用户自定义内容及其它入口的设置。 |
| `pet/context_menu.py` | 21 | 91 | 只读取固定菜单树并按能力过滤动作，删除菜单模板切换与自定义编排入口。 |
| `pet/context_menus/__init__.py` | 1 | 6 | 移除失效导入、注释或接口说明，保持现有有效调用和样式。 |
| `pet/context_menus/fun_entry.py` | 0 | 229 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/context_menus/icons.py` | 0 | 37 | 删除菜单编排专用的文件图标渲染，保留快捷应用的图片校验及语义矢量图标。 |
| `pet/context_menus/legacy.py` | 0 | 64 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/context_menus/menu_styles/__init__.py` | 1 | 2 | 移除失效导入、注释或接口说明，保持现有有效调用和样式。 |
| `pet/context_menus/menu_styles/common.py` | 0 | 3 | 停止派发已退役的旧菜单主题，保留通用布局及子菜单字体继承。 |
| `pet/context_menus/menu_styles/legacy.py` | 0 | 13 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/context_menus/modern.py` | 0 | 21 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/context_menus/registry.py` | 19 | 183 | 固定动作登记；删除别名、任意图标、草稿和退役动作渲染分支。 |
| `pet/context_menus/shared.py` | 0 | 100 | 删除移至托盘的系统选项及退役入口，保留动画、角色、大小等快捷操作。 |
| `pet/decode_fanout.py` | 7 | 112 | 移除省电专用的解码节流仲裁；保留共享解码、订阅、交接和安全收口。 |
| `pet/dynamic_island.py` | 0 | 1269 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/edge_probe.py` | 0 | 3 | 移除碰撞飞行彩蛋激活，保留探头碰撞退出与恢复行为。 |
| `pet/fun_image_popup.py` | 0 | 262 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/island_collision.py` | 0 | 653 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/menu_layout.py` | 0 | 363 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/menu_templates/legacy.json` | 0 | 14 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/menu_templates/modern-default-v1.json` | 109 | 27 | 固定实用菜单树；删除彩蛋、系统选项重复入口、联动快捷开关及隐藏无用项。 |
| `pet/menu_templates/modern.json` | 0 | 15 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/modern_settings_dialog.py` | 14 | 336 | 移除重复及退役控件；联动开关前移，长文案配置折叠，保存时不覆盖菜单/托盘所有的偏好。 |
| `pet/multi_window_shared.py` | 0 | 6 | 共享代理删除省电活跃锚点转发，保留状态和提醒分发。 |
| `pet/native/_bin/manifest.json` | 1 | 1 | 更新原生构建的校验清单和SHA，确保分发DLL与源码一致。 |
| `pet/native/_bin/pet_core.dll` | 二进制 | 二进制 | 删除岛分支后重建原生碰撞DLL，随包验证ABI和构建标识。 |
| `pet/persona_phrases.py` | 3 | 0 | 缺少步骤号时将空白“第 步”改为完整的“当前步骤”；保留未知字段兼容契约。 |
| `pet/persona_presets/legacy.json` | 37 | 74 | 改写简短状态/过程/完成提醒，内置文案仅依赖可靠名称，避免空步骤与会话残壳。 |
| `pet/persona_presets/self_talk.json` | 38 | 0 | 新增36条简短陪伴词库，采用口语表达并避免缺失字段。 |
| `pet/persona_presets/whale_maid.json` | 38 | 30 | 改写简短状态/过程/完成提醒，内置文案仅依赖可靠名称，避免空步骤与会话残壳。 |
| `pet/settings_interaction.py` | 1 | 1 | 移除失效导入、注释或接口说明，保持现有有效调用和样式。 |
| `pet/settings_menu_layout_editor.py` | 0 | 801 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/settings_pet_controls.py` | 0 | 95 | 删除重复和退役控件及其控制器，保留有效气泡、动作、碰撞、联动参数。 |
| `pet/settings_widgets.py` | 0 | 1 | 移除失效导入、注释或接口说明，保持现有有效调用和样式。 |
| `pet/slot_manager.py` | 2 | 11 | 落种清除退役配置；保留继承大小、用户定制保护及窗口位置。 |
| `pet/speech_bubble.py` | 25 | 76 | 字体改为14px；限制行数于实际可绘制高度，尾巴随边缘换位镜像，清除歌词专用布局。 |
| `pet/speech_bubble_text.py` | 2 | 3 | 统一14px正文与8px定位间距，改善短提示的距离和清晰度。 |
| `pet/throw_egg.py` | 0 | 99 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `pet/webm_clip.py` | 14 | 86 | 移除省电解码节流及其队列分支，保留有界丢帧、源帧号、循环和ffmpeg回收。 |
| `pet/window.py` | 11 | 229 | 删除省电、菜单切换与彩蛋钩子，保留逐帧呈现和预测预热，减少失效分支。 |
| `pet/window_alerts.py` | 0 | 27 | 移除隐藏气泡改道岛的接口；保留提醒队列与交互决策。 |
| `pet/window_optional_services.py` | 3 | 19 | 移除飞行彩蛋控制器的装配和旋转钩子，保留边缘探头、回旋与工作联动。 |
| `pet/window_placement.py` | 7 | 14 | 气泡锚定稳定角色主体并计入贴边绘制偏移，避免动画特效扩大间距。 |
| `scripts/bench_collision_backends.py` | 5 | 5 | 将岛静态基准改成实际可用的拖拽无限质量桌宠场景。 |
| `scripts/capture_settings_pages.py` | 1 | 59 | 删除退役控件和编辑器截图步骤，继续覆盖有效设置域和标签。 |
| `tests/test_agent_link.py` | 6 | 74 | 校验agent / link的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_alert_queue.py` | 1 | 18 | 校验alert / queue的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_autostart.py` | 0 | 25 | 校验autostart的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_bubble_text_scale.py` | 3 | 3 | 校验bubble / text / scale的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_click_talk_bindings.py` | 33 | 0 | 校验click / talk / bindings的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_collision_backend.py` | 4 | 4 | 校验collision / backend的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_collision_ipc.py` | 0 | 58 | 校验collision / ipc的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_collision_native.py` | 2 | 2 | 校验collision / native的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_collision_window.py` | 5 | 44 | 校验collision / window的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_config_schema.py` | 0 | 7 | 校验config / schema的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_decode_fanout.py` | 0 | 41 | 校验decode / fanout的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_desktop_pet_features.py` | 5 | 625 | 校验desktop / pet / features的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_dynamic_island_revamp.py` | 0 | 697 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `tests/test_effects_integration.py` | 3 | 16 | 校验effects / integration的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_first_batch_features.py` | 0 | 100 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `tests/test_idle_low_fps.py` | 0 | 999 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `tests/test_island_collision.py` | 0 | 598 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `tests/test_island_content_cache.py` | 0 | 127 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `tests/test_island_remote_wall.py` | 0 | 471 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `tests/test_menu_layout.py` | 0 | 2173 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `tests/test_perfstats.py` | 0 | 23 | 校验perfstats的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_pet_interaction_locks.py` | 2 | 4 | 校验pet / interaction / locks的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_pet_surface_cleanup.py` | 44 | 6 | 校验pet / surface / cleanup的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_predictive_prewarm.py` | 0 | 19 | 校验predictive / prewarm的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_requested_regressions.py` | 13 | 261 | 校验requested / regressions的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_settings_and_resources.py` | 0 | 3 | 校验settings / and / resources的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_settings_interaction_tabs.py` | 1 | 1 | 校验settings / interaction / tabs的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_settings_ui.py` | 623 | 0 | 校验settings / ui的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_silent_pet.py` | 6 | 29 | 校验silent / pet的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_single_process_shared.py` | 11 | 90 | 校验single / process / shared的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_single_process_spawn.py` | 0 | 50 | 校验single / process / spawn的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_slot_and_memory.py` | 0 | 8 | 校验slot / and / memory的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_speech_bubble.py` | 0 | 42 | 校验speech / bubble的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_throw_egg.py` | 0 | 296 | 删除已退役功能的实现、资源或测试，避免无入口代码继续保留。 |
| `tests/test_throw_flight_anim.py` | 0 | 3 | 校验throw / flight / anim的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_webm_clip_loop.py` | 0 | 52 | 校验webm / clip / loop的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |
| `tests/test_window_broker_wiring.py` | 0 | 6 | 校验window / broker / wiring的有效行为；删去退役路径的断言或替身，保留配置、窗口及生命周期覆盖。 |

## 性能分析

实测环境：Windows 11，Python 3.13 / PySide6 6.11.2，原生windows Qt平台，主角色scale=0.5；本机联动开启。没有原始版本同机A/B，因此不宣称CPU或内存提升比例。

| 路径 | 样本 | 实测 |
|---|---:|---|
| 气泡主体锚点计算 | 2000次，perf_counter_ns | 中位 5.7 μs；P95 6.9 μs |
| 真实桌宠+联动进程 | 30.379秒 | 平均CPU 1.08%，结束RSS 107.31 MiB |
| RSS采样 | 120次，250ms间隔 | 峰值 116.93 MiB |
| 便携产物 | 937文件 | 230.86 MiB；ZIP 129.63 MiB |

气泡锚点在显示/跟随桌宠时按矩形计算；尾巴镜像及字体测量只随布局和位置更新，不增加定时器。删除省电后可见桌宠按用户播放速率呈现，隐藏仍暂停播放；这是预期行为，不能把删除省电称为降低播放CPU。托盘复用既有对象，不新增线程；弹出菜单时读取开机自启系统状态，复选框同步由QSignalBlocker防止误写。只有用户点击开机自启才写系统配置。本次实测未改写实际自启动项。

无新增网络请求。保留现有本地会话尾读与碰撞线程。新增36条静态短句在启动时读取一次；没有无限增长缓存。上述RSS峰值来自短样本，不能代替长时间泄漏验证；托盘重建和多窗收口由既有真实Qt测试覆盖。

## 实机运行记录

- 原生Qt截图命令：`D:/python/miniconda/envs/py13/python.exe scripts/capture_settings_pages.py <输出目录> --width 720 --height 700 --menu-details --interaction-details`；1100×760加`--dark`。截图覆盖5域、桌宠3标签、菜单3标签，窄屏无横向裁切；ChatGPT开关处于联动页首屏。
- 原生窗口复验脚本在`E:/CODX/2026-10-03/shen/work/2026-10-04/native_ui_live_review.py`：运行30.379秒，系统托盘可用，4个真实本机会话尾读器，工作忙碌聚合为True；不记录会话内容。截图展示居中与贴顶两种位置的普通/思考气泡及托盘。
- 常规气泡位于主体上方，矩形间距8；贴顶思考气泡换到右侧，尾巴转向桌宠。14px字体实测行高18，三行54px小于67px可用高度。
- 宿主验证为Windows原生Qt；未把macOS或Linux伪平台单测宣称为实机验证。
- 构建命令：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_onedir.ps1 -Variant webm-chat -PythonExe D:/python/miniconda/envs/py13/python.exe`。
- 构建输出：原生CTest 1/1通过；Qt Runtime validation OK；中文编码PASS；DLL chain ALL OK；NATIVE_BUNDLE_OK / FROZEN_NATIVE_OK；PET_QT_WINDOW_OK；SETTINGS_QT_WINDOW_OK。
- 使用Start-Process取得构建验证子进程的真实退出码：0；再次执行-SkipBuild时原生DLL、桌宠和设置窗口检查全部通过。
- PyInstaller嵌入模块检查：不含灵动岛、静态岛碰撞、彩蛋弹窗/飞行彩蛋、菜单编辑器/旧模板主题或QtMultimedia；新词库资源存在；无wav/mp3文件；LICENSE与THIRD_PARTY_NOTICES均在包中。ZIP CRC检查通过。
- ZIP：`E:/CODX/2026-10-03/shen/outputs/2026-10-04/Desktop-Pet-2026-10-04.zip`。
- ZIP SHA256：`0ec35f293f498a8f8f200843edb5d0e54d2224251657fd7d95d424657800a409`。
- EXE SHA256：`81908f57603981cbf5432c859025ab1e89f3e13af321e0e81ab3a43cb03267cd`。

本机证据位于`E:/CODX/2026-10-03/shen/outputs/2026-10-04/`（ui-final-720-light、ui-final-1100-dark、pet-bubble-*.png、tray-menu.png、native-ui-metrics-live.json、package-verification.json）。构建与测试原始日志在同级工作目录的work/2026-10-04，均不进入源码仓库。

## 测试与验证

- 首批9项公共行为回归：修改前8失败/1通过，修改后9通过；补充缺失步骤字段、字体行高、尾巴换位后共12项通过。
- 最终全量：1649 passed、6 skipped、10 warnings，112.88秒；跳过为平台/环境约束，警告为既有Qt接口弃用。Ruff通过，git diff --check通过。
- 真实Qt测试覆盖单托盘切换全部本地桌宠、鼠标穿透状态同步、配置并发保存、预测预热、动画呈现、碰撞IPC及原生Python一致性。
- 中间一次全量进程在Qt事件循环里出现访问冲突；相关测试族单独通过，随后完整全量运行均完成并通过。日志保留，不把这次异常隐藏为通过记录。

## 删除docs及README的后果

应用入口和当前打包不读取docs或根README，删除它们通常不会影响桌宠和本地联动运行。README删除会让GitHub首页缺少使用/构建说明；整套docs删除会使README、AGENTS和工程链接失效，文档纪律测试缺少模板/规范/索引而失败，并失去构建与架构记录。本轮只回答影响，没有删除整套docs或根README；保留许可证、第三方声明、原生源码和角色资源。以后删历史文档，应同步修复索引及仍引用它的规范/测试。

词库采用原创短句改写，[抖音精选中的流行口语表达](https://jingxuan.douyin.com/m/video/7615195132844918947)作为参考；没有声称它们全部是当前排行榜词条。
