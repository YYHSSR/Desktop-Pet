# 项目架构

程序由 Qt 事件循环驱动，人物播放、Codex 数据采集和卡片展示相互协作。耗时的解码、网络请求与日志扫描在后台执行，界面负责接收结果和局部重绘。

## 启动链路

```text
app/enhanced.py → DesktopPet
                  ├── StreamPlayer / SustainedPlayback → 人物动画
                  ├── CompactBubble → 状态卡片和日报
                  ├── ActivityThread → Codex 会话状态与用量
                  ├── QuotaWorker → 账户额度
                  ├── MaterialController → 资源校验与画质切换
                  └── VideoYield → 全屏检测与置顶协调
```

`pet.py` 提供人物基础渲染与输入；`enhanced.py` 添加 Codex 状态、统计及生命周期；`desktop.py` 整合完整桌面交互。三者形成现有继承链，应用模块维持扁平导入，便于源码启动和 PyInstaller 收集。

## 模块分工

| 范围 | 主要模块 |
| --- | --- |
| 桌宠和设置 | `pet`、`enhanced`、`desktop`、`desktop_core`、`desktop_settings`、`settings_draft` |
| 动画和状态动作 | `stream_player`、`decode_runtime`、`loop_cache`、`sustained_player`、`continuous_work`、`status_reactions` |
| 卡片与窗口过渡 | `compact_bubble`、`surface_morph`、`panel_transition`、`linked_report_motion`、`card_motion` |
| Codex 数据与会话 | `codex_connection`、`codex_live_status`、`conversation_roster`、`session_read_state`、`completion_ledger`、`quota` |
| Token 与日报 | `token_calendar`、`token_analytics`、`token_charts`、`daily_report` |
| 角色资源 | `desktop_services`、`material_store`、`material_controller`、`embedded_assets` |
| 系统集成 | `codex_startup`、`autostart`、`video_fullscreen`、`firefox_video`、`video_yield` |

## 数据与存储

- 源码及固定资源位于项目目录。
- 角色播放文件位于 `assets/character/`；轻量生成缓存位于 `build/materials/`。
- 用户设置、统计和资源缓存位于 `%LOCALAPPDATA%\BailongEnhanced`。
- 会话与额度读取本机 Codex 数据；失联或解析失败保留有效旧数据，不当作零值或已读。
- 本地用量仅覆盖可读取的本机日志，不代表其他设备或所有服务的消耗。

## 后台与界面

动画通过有界队列提交帧，取消只发送停止信号，不在 GUI 线程等待解码线程。人物使用固定画布，卡片过渡复用布局和缓存，避免每帧修改原生窗口大小。

人物显示时状态卡片默认隐藏：点击人物、任务完成、托盘或设置入口会显示卡片，并按 `card_hide_delay` 计时自动收起；指针停留、详情展开、日报或编辑页打开时延后收起。只显示卡片时卡片常驻。Codex 数据目录与 CLI 只通过自动识别或 `BAILONG_CODEX_HOME`、`BAILONG_CODEX` 环境变量指定。

Codex 完成消息进入未读提醒账本；实际查看或手动确认后移除。视频全屏可临时取消置顶，但不能压过未读完成提醒；用户手动关闭的置顶不会自动打开。
