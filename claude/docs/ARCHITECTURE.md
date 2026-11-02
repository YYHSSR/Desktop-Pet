# Claude 角色实现

角色目录与 ChatGPT、Gemini 保持一致：`app`、`assets`、`docs`、`tests`、`tools`、`build`、`dist`。

## 模块

| 模块 | 职责 |
| --- | --- |
| `app/main.py` | 入口：把 `Companion` 交给共用的 `share.desktop.companion_app.run()` |
| `app/companion.py` | `CompanionApp` 子类：卡片、图标、今日 Token 统计来源和角色动作 |
| `app/model.py` | Claude 的设置表（沿用共用表）、内置的随机动作 / 行走 / 单击双击回应权重、时段招呼 |
| `app/claude_link.py` | 读取 Claude 桌面端本机的 `plan-usage-history.json`，转成 5 小时 / 本周额度快照 |
| `app/card.py` | Gpt 同款紧凑卡片：工具栏、七个页面、草稿设置、书签与读书记录 |
| `app/ornaments.py` | 绘制件与配色：火花、墨水进度线、书页堆、书签丝带、图标按钮 |
| `app/messages.py` | 角色固定回应与彩蛋台词 |

共用层：`share/desktop/companion_app.py`（与 Gemini 共用的全部桌宠行为与入口）、`share/desktop/card_kit.py`（分段设置、7 天柱状图）、`share/desktop/local_store.py`（本机文件）、`share/desktop/desktop_integration.py`（开机启动、全屏检测）、`share/desktop/companion_state.py`（设置表、动作排队与接管）、`share/desktop/sprite_window.py` 与 `share/pet_engine`（透明窗口、拖动命中、固定画布、六帧有界解码队列、离屏停止和恢复）、`share/asset_tools`（离线素材处理，不进入运行包）。角色不导入其他角色的 `app/`。

## 启动顺序

1. 解析参数、安装崩溃日志、创建 `QApplication`、单实例检查。
2. `Companion` 读取设置与素材清单，**先显示人物并播放首帧**，再建立托盘与定时器。
3. 事件循环开始后约 60 ms 构建卡片（首次文字排版会加载系统字体库，约 0.4 秒）；在此之前若用户点击人物，卡片会立即同步构建。
4. 冒烟测试把 `launched` / `first_frame` / `card_ready` 时间戳写进 `smoke-result.json`，`tools/bench_startup.py` 据此测速。

其他启动优化：共享层只在离屏平台额外注册雅黑字体；`stream_player` 直接注册 WebP 插件，避免 Pillow 首次打开时导入全部格式插件（约 50 ms）。默认文件夹版打包免去单文件版每次约 2 秒的解包。

## 运行时约定

- 独立存储目录 `%LOCALAPPDATA%\ClaudeDesktopPet`；单实例通信名 `claude-reading-local`。测试使用独立目录与带路径摘要的通信名。
- 手动动作默认立即接管（`ActionDirector.request(interrupt=True)` + `SpriteWindow.play(takeover=True)`），两段动画都在动地交叠 0.25 秒；自然播完的动作直接切换，自动动作在待机循环接缝处切入；关闭“立即切换”后恢复为收尾后播放、只保留最后一次选择。拖动期间停止推进动画，释放后继续当前动作。自动活动不会打断互动；角色没有任何声音。
- 卡片只在可见时刷新计时文字；静止时不运行卡片环境动效定时器。彩蛋场景的 33 ms 定时器只在约 11 秒的场景中运行，结束即隐藏。
- 全屏让位：每秒检查一次前台窗口，若其他程序铺满人物所在显示器就隐藏人物（解码随之停止），结束后恢复；从托盘“找回”会对当前全屏程序破例。
- 未捕获异常写入 `diagnostics.log`（256 KB 轮换），窗口版程序不会因为没有控制台而静默丢失错误。新接入的显示器同样监听可用区域变化。

原片按 `manifest.json` 校验。基础透明缓存位于 `build/animation-base`；最终素材位于 `assets/character/playback`。运行清单记录源片、处理配方、帧数、持续时间、SHA-256、共同参考姿势和首尾差异。排除的夜景原片在清单里单独记录。

检查入口 `tools/check.py` 使用临时用户目录与 Qt 离屏测试；打包后的 `--smoke-test --state-dir <目录> --capture-dir <目录>` 可验证真实独立包的启动、流式播放和界面截图。

## 与 Gpt 一致的卡片表面

角色卡片继承 `share.desktop.card_surface.CompanionCardSurface`。默认 268 × 188，扩展编辑区最大 560 × 600，并按显示器可用区域收窄。额度只使用真实快照，缺失值为“—”。

每次导航只准备起点与终点两张图像，原生窗口在过渡期间保持联合画布不变；每帧只绘制圆角裁剪、背景和缓存图像。打开、展开、收缩、收起使用与 Gpt 相同的公共动效曲线和时长，快速导航保留最近一次请求。缩小时由独立透明画面覆盖原生 backing store 交接。

设置面板由 `share.desktop.settings_panel` 提供。编辑、恢复默认和切页都只修改草稿；应用后再发出设置变更，外部设置更新会保留尚未应用的草稿并提示冲突。退出设置不会丢弃草稿。网页入口只留在卡片工具栏，右键菜单移除。

卡片顶部仅保留刷新、网页、设置；日报入口和日报页面已移除。底栏 `TodayTokens` 显示本机当天用量，点击切换 `Dashboard` 的小时曲线。三个角色的右键菜单结构集中在 `share/desktop/context_menu.py`。

主卡片由 `share.desktop.quota_dashboard.QuotaDashboard` 提供两张额度卡，取消右侧动作/专注面板；底栏切换今日小时图。新 Claude 拖拽使用角色元数据指定的有效起点与循环文件；该能力仅在存在对应元数据时启用，其他角色播放包不变。
