# 桌宠项目交接说明（2026-10-31）

给在 Claude Code 中继续本项目的会话：先读本文件、根目录 `README.md`、`En-SKILL.md`，再动手。

## 环境约定
- Python 一律用 `E:\minconda\envs\py13\python.exe`（缺依赖时按 `share/requirements.txt` 用同解释器 `-m pip` 安装）。
- 辅助文档放 `AI/docs/`，临时日志与中间产物放 `AI/temp/`，交付前清理 `AI/temp/` 中本次产生的临时文件。
- 只做与任务相关的最小修改；删除非临时文件前需用户确认。

## 已完成
- **Gemini**（`gemini/`）：新版陪伴卡片——顶部猫耳（弹出回弹、悬停抖动、点击播放喵喵）、呼吸的四角星 ✦、按时段变化的猫咪招呼语、五星专注进度、底栏"星星罐"（按 ISO 周累计，7 颗连成双子座，记录在 `focus.json` 的 `week`/`week_stars`）、摇尾巴、闲置爪印；蓝紫星光配色。动效共用 40 ms 定时器，仅在卡片可见时运行。卡片主体仍为 288×224，上方多 13 px 透明边（`CompanionCard.EAR`）。
- **共用引擎**：`share/desktop/sprite_window.py` 的命中测试图像改为按需转换（不再每帧 `toImage()`）；`stream_player.py` 的 `math` 导入移到顶部。
- **ChatGPT**：显示名与产物统一改为 ChatGpt（`dist/ChatGpt.exe`），数据目录 `%LOCALAPPDATA%\BailongEnhanced` 与单实例名保持不变。
- 验证：Gemini 36 项测试、12 段动画逐帧检查通过；ChatGpt 30 个模块 254 项测试通过；`gemini/dist/GeminiPet.exe`（onefile）与 `chatgpt/dist/ChatGpt.exe` 已构建，GeminiPet.exe 打包冒烟测试通过。
- 待用户处理：旧的 `chatgpt/dist/Gpt.exe` 尚未删除（等用户确认新版无误）；指向 Gpt.exe 的快捷方式需改为 ChatGpt.exe。

## 常用命令
```powershell
$PY = 'E:\minconda\envs\py13\python.exe'
cd E:\CODE\desktop-pet\gemini;  & $PY tools\check.py;  & $PY tools\build.py --onefile
cd E:\CODE\desktop-pet\chatgpt; & $PY tools\check.py;  & $PY tools\build.py
# 卡片截图：
& $PY app\main.py --smoke-test --no-tray --state-dir ..\AI\temp\preview-state --capture-dir ..\AI\temp\preview
```

## Claude 娘（`claude/`，2026-10-31 完成重构）
- 在原有实现上重构：`main.py` 入口 / `companion.py` 调度 / `card.py` 卡片 / `ornaments.py` 绘制件 / `impostor.py` 彩蛋，说明见 `claude/docs/ARCHITECTURE.md`（第二轮后存储与调度已移到 `share/`）。
- 卡片：暖橘 + 米白纸页、右上角书签丝带（摆动，拉一下打开随记）、衬线招呼语与计时、墨水进度线、底栏“今日读了 N 页”；专注完成交替播放赠花 / 灵光一闪。
- 彩蛋：连点三下火花（或随机活动中 4%、冷却 45 分钟），DeepSeek 小鲸鱼假扮 Claude 娘被识破。
- 启动：先显示人物后构建卡片；默认文件夹版打包并剔除约 49 MB 无用 Qt 组件。首帧约 0.28 s（旧单文件版约 2.4 s），测速用 `tools/bench_startup.py`。
- 共享层两处小改动（Gemini 36 项测试复核通过）：`typography.register_font` 仅在 offscreen 平台注册雅黑；`stream_player` 直接导入 WebP 插件。
- 验证：Claude 46 项测试 + 9 段动画校验通过；`dist/ClaudePet/ClaudePet.exe` 冒烟（含彩蛋与截图）通过。
- 待用户处理：旧单文件 `claude/dist/ClaudePet.exe` 已过时，确认后可删除；快捷方式改指 `dist/ClaudePet/ClaudePet.exe`。重构前源码备份在 `AI/temp/claude-before-refactor/`，确认无误后可删。

## 第二轮：Claude + Gemini 共用行为层（2026-10-31，未打包）
- `share/desktop/` 新增 `companion_app.py`（两角色共用的全部桌宠行为与 `run()` 入口）、`card_kit.py`（分段设置面板、7 天柱状图）、`local_store.py`、`desktop_integration.py`（开机启动 VBS、前台全屏检测）；`companion_state.py` 改为可扩展设置表 + `FocusLedger`（62 天逐日记录，兼容旧单日格式与 Gemini 周星）。两角色的 `app/companion.py` 只剩各自特色。
- 动作：手动选择默认立即接管（`instant_switch`），旧播放器只消耗已解码帧，0.32 s “先叠新、再淡旧”交叠，人物轮廓不透明；专注完成与彩蛋庆祝只排队。原 Plus 合成在缩放绘制下 alpha 不相加，已弃用。
- 设置（两角色同构，分常规 / 动作 / 角色）：开机启动、全屏让位、锁定位置、卡片停留、网页地址、立即切换、播放速度、单击 / 双击动作、称呼、每日目标，以及角色专属开关；每页可恢复默认。新增“读书记录 / 星星记录”页。
- 性能：人物窗口独立 96 MB 循环缓存（单项 64 MB），待机第二遍起从内存回放，闲置 CPU 约 28% → 约 5%（125% 缩放实测）；Gemini 改为先显示人物后建卡片（源码首帧约 0.37 s，冒烟总时长 3.54 s → 3.28 s），卡片外形路径缓存，动效与爪印全关时定时器停止。
- 验证：Claude 60 项、Gemini 41 项测试 + 素材校验通过；ChatGpt 254 项复核通过。两角色源码冒烟与各页截图正常；本轮未重新打包 exe。
- 本轮改动前的备份：`AI/temp/before-round2/`。

## 第三轮：平台额度联动、动作权重、清理与打包（2026-10-31）
- Claude ↔ Claude 桌面端：`claude/app/claude_link.py` 只读桌面端本机 `plan-usage-history.json`（Store 版在 `%LOCALAPPDATA%\Claude-Data\claude_*\`），样本字段 `fh`/`sd` 为 5 小时 / 本周已用百分比，无重置时间。
- Gemini ↔ Antigravity：`gemini/app/antigravity_link.py` 只读 `%APPDATA%\Antigravity IDE\User\globalStorage\state.vscdb` 的 `antigravityUnifiedStateSync.userStatus`（base64 包着 base64 的 protobuf），解出套餐与各模型 `quotaInfo{remainingFraction, resetTime}`；不读邮箱与 oauthToken。
- 共用：`share/desktop/quota.py`（快照 + 每分钟轮询，仅变化时通知）；卡片“额度”页取代原平台占位页，底栏在已连接时显示额度小圆环；刷新时庆祝、用到 80% 时提醒（先播动作再说话）；设置 · 角色可关闭读取。
- 动作：`ActionPicker.pick(pool, weight=)` 支持基础权重；Claude / Gemini 在 `model.py` 定义随机权重与时段倍率（完成动作权重 0），ChatGpt 在 `desktop.py` 的 `VARIANT_WEIGHTS`。Gemini 移除“日常 quiet”（与待机雷同且偏淡），播放包 11 段。
- 清理：退出项改为“退出 Claude / 退出 Gemini”；删除 `gemini/app/panel.py`、`claude/tools/accept_package.py`、两角色空的 `assets/sounds`、`assets/licenses` 与多余 `.gitkeep`；Qt 精简表移到 `share/pet_engine/packaging.py` 供两角色构建共用；旧单文件 exe 与旧备份已删除。

## 第四轮：菜单对齐与角色卡片配色（2026-10-31，未打包）
- 菜单：Claude / Gemini 右键与托盘第一项改为“查看状态”，移除专注时光、专注记录、偏好设置、找回人物（`recentre` 一并删除）；退出项统一为“退出Claude / 退出Gemini”。
- 卡片：布局保持 Gpt 同款不变，`share/desktop/card_surface.py` 新增 `Theme` 与 `style_sheet()`，原硬编码梅紫色改为主题字段；纸面由卡片的 `paint_surface()` 绘制，可用 `surface_hot/surface_pressed` 响应点击。
  - Claude：米白纸页 + 赤陶墨色，衬线标题与数字，状态点换成橙色火花，标题栏空隙挂一条书签丝带（点击打开书签随记），进度条为墨水渐变。
  - Gemini：蓝紫星光，渐变描边与主按钮，状态点换成渐变四角星，标题栏空隙三颗淡星。
- 验证：Claude 77 项、Gemini 46 项测试 + 素材校验通过；两角色源码截图检查正常。exe 尚未重新打包。

## 第五轮：置顶、重置倒计时与 Token 日报（2026-10-31，未打包）
- 置顶：右键 / 托盘移除“保持置顶”，与 ChatGpt 一样只在设置（“始终置顶（人物与卡片）”）和卡片导航条里切换。
- 重置倒计时：`share/desktop/quota.py` 的 `reset_text` 改为倒计时（“约1小时05分后重置”），`Meter.estimated` 标记推算值；卡片可见时每 30 秒刷新。Claude 的 `claude_link.py` 依据 `plan-usage-history.json` 的用量变化链式推算 5 小时 / 本周窗口（区间超过窗口 1/4 时不显示）。
- 日报：`share/desktop/token_report.py`（增量缓存 `token_cache.json`、后台线程、概览 / 模型两页）；Claude 读 `~/.claude/projects/**/*.jsonl`（按 message.id 去重、半行留待下次），Gemini 读 `~/.gemini/antigravity[-ide]/conversations/*.db` 的 `gen_metadata`（字段 1+2 输入、5 缓存、3 输出，时间取 last_step_index 对应步骤）。卡片工具栏“记录”图标改为日报，专注记录从底栏“7天 ›”进入。因为两者都能做出真正的 Token 日报，备选的“书签随记留言 / 猫女心声”未实现。
- 验证：Claude 81 项、Gemini 47 项测试通过；两角色源码冒烟 quota_connected、tokens_ready 均为 True。

## 第六轮：移除书签随记、动作衔接与三角色打包（2026-10-31）
- 移除 Claude 书签随记（页面、菜单、设置入口、`LocalStore.note`）；丝带保留为装饰。用户已有的 `note.txt` 未删除。
- 新素材：Claude「送出花朵」v2 第 101 帧后镜头推近，截到第 116 帧、持花停留 3 秒；Gemini「跳一跳」v2 全身完整，直接使用。
- 衔接：`share/asset_tools/pose_bridge.py` 的颜色溶解只占桥接中段一半（身体变形仍贯穿全程），重影从 4~5 帧降到 1~2 帧；`animation_pack.prepare_bridges` 在两端 12 帧内挑最接近待机的切点，并按姿势差自动定桥长（进入 9~18 帧、退出 12~22 帧，粒子类至少 22）。Gemini 的 `prepare_transitions.py` 改用共用实现。ChatGpt 各动作首尾与待机逐像素一致，无需重做。
- 节奏：`ActionPicker` 带权重时不再屏蔽半个池子（小池子会逼出稀有动作），改为“不连播 + 近两次降权 + 久未出现最多 2 倍”；每个动作结束后至少休息随机间隔的 35%。
- ChatGpt 启动：默认改为文件夹版 `dist/ChatGpt/ChatGpt.exe`，两档素材仍内嵌在 exe（`embedded_assets` 对文件夹版同样适用），免去每次解包 Python/Qt；`--onefile` 保留单文件。实测单文件版首个窗口约 2.0 s，源码约 1.0 s。
