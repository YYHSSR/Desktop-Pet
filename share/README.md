# 三个角色的公共组件

`chatgpt/`、`claude/`、`gemini/` 共用的实现放在此处。三个角色均有独立应用与素材包。

| 模块 | 职责 |
| --- | --- |
| `pet_engine/stream_player.py` | 后台解码队列、累积帧时钟、异步取消及动态尺寸 |
| `pet_engine/decode_runtime.py` | 解码线程生命周期与统计单例 |
| `pet_engine/loop_cache.py` | 有界无损循环缓存 |
| `pet_engine/sustained_player.py` | 入场、循环体、接缝和收尾的持续动作播放 |
| `pet_engine/sustained_assets.py` | 持续动作的清单校验及路径解析 |
| `pet_engine/action_picker.py` | 带历史记忆的随机动作选择与间隔 |
| `pet_engine/packaging.py` | Conda 原生 DLL 收集与构建环境 |
| `pet_engine/character_pack.py` | 新角色的动作清单、路径边界与资源完整性检查 |
| `desktop/sprite_window.py` | 通用透明人物画布、流式播放、拖拽 / 锁定、缩放、播放速度、动作接管交叠与原生透明命中 |
| `desktop/companion_state.py` | Claude 与 Gemini 共用的设置表（可按角色扩展）和动作队列（保留旧记录解析工具） |
| `desktop/companion_app.py` | Claude 与 Gemini 共用的桌宠行为：先显示人物再建卡片、托盘与菜单、动作调度、全屏让位、开机启动、统一入口 `run()` |
| `desktop/card_kit.py` | 卡片公共组件：当前页尺寸栈、额度条、7 天柱状图及设置兼容入口 |
| `desktop/card_surface.py` | Gpt 同款紧凑额度卡片、工具栏、固定画布快照导航、原生缩小交接 |
| `desktop/token_widgets.py` | 今日 Token 底栏与本机日期取值 |
| `desktop/context_menu.py` | 三个角色共用的右键与托盘菜单结构 |
| `desktop/settings_panel.py` | 标签页设置草稿、应用 / 放弃 / 本页默认、外部修改同步和 Ctrl+S |
| `desktop/local_store.py` | 单个角色的设置与诊断日志（旧专注记录接口仅兼容保留）（原子写入、日志轮换） |
| `desktop/desktop_integration.py` | Windows 启动文件夹自启动、前台全屏检测、按程序名判断是否在运行 |
| `desktop/token_report.py` | 本机 Token 增量缓存、后台读取与小时曲线；角色提供只读数据源 |
| `desktop/quota.py` | 只读额度快照（`QuotaSnapshot` / `Meter`）与按需轮询的 `QuotaWatcher`；各角色提供自己的读取器 |
| `asset_tools/animation_pack.py` | 离线透明动画编排、人物对齐、循环和共同姿势衔接 |
| `desktop/spring_motion.py` | 卡片展开、收缩与消失的动效曲线 |
| `desktop/native_coordinates.py` | Windows 原生坐标到 Qt 客户区的转换 |
| `desktop/worker_lifecycle.py` | 等后台工作线程结束后关闭窗口，不阻塞 GUI |

这些组件不依赖任一角色的 `app/`、账户数据或素材路径。`requirements.txt` 保存统一的运行和构建依赖，三个角色各自的依赖文件引用它，角色专属依赖可追加到各自文件。

`asset_tools/white_background.py` 是离线的浅色背景动画处理工具，保持白色服装内部和分离的彩色星光。它针对当前提供的平面浅色背景素材，不是通用人物分割模型；无法重建原片已被裁切的人物。工具依赖单列于 `requirements-assets.txt`，不会进入桌宠运行包。

## 导入与边界

从工作区根目录可直接导入：

```python
from share.pet_engine.stream_player import StreamPlayer
from share.pet_engine.sustained_player import SustainedPlayback
from share.pet_engine.action_picker import ActionPicker
from share.desktop.spring_motion import container_progress
```

从角色脚本启动时，应像 `chatgpt/app/stream_player.py` 一样把工作区根目录加入 Python 模块搜索路径；冻结构建由角色构建入口加入该路径，并通过静态导入收集公共模块。

ChatGPT 原有扁平模块通过 `sys.modules` 指向相同的公共模块对象，保持统计单例、缓存和测试补丁目标一致。不要在各角色目录复制公共实现。

各平台的读取方式由角色提供（Claude 读桌面端用量记录，Gemini 读 Antigravity 缓存，ChatGpt 读 Codex），共用层只负责快照、轮询、卡片展示和角色反应。随机动作的基础权重由角色决定，`ActionPicker.pick(pool, weight=...)` 再叠加“久未出现更可能”的历史权重。复用更多 UI 时，先移除其平台和角色依赖，再提取到此处。Claude、Gemini 的用户数据目录、单实例名称和打包输出分别隔离，避免相互冲突。

运行及构建时需保留整个工作区。公共代码沿用根目录 [LICENSE](../LICENSE) 的授权。

## 字体和动作衔接

`assets/fonts/` 保存共用的 Chakra Petch 字体与 OFL 许可证。`desktop/typography.py` 为三个角色提供同一个注册入口及中文字体回退；角色构建脚本把共用字体收集到冻结资源的 `assets/fonts/`。

`asset_tools/pose_bridge.py` 是离线短过渡工具。它先配准人物身体位置和比例，再做小范围光流补间；游离星光独立渐隐，不跟随身体光流扭曲。运行时无需 OpenCV 或 NumPy。

`desktop/sprite_window.py` 在静态待机交接期间暂停新动作的时钟，之后再播放完整入场。人为选择新动作时则“接管”：旧播放器只消耗已解码的帧并淡出，新动作同时开始，0.32 秒内先让新姿势叠上、再让旧姿势的残留淡去，交叠处始终不透明。人物窗口使用独立的 96 MB 循环缓存（单项 64 MB），常见缩放下待机循环第二遍起从内存回放，闲置 CPU 从约 28% 降到约 5%；ChatGpt 仍用引擎默认缓存。角色专属的环境特效由角色子类绘制，避免把 Gemini 星光加入 Gpt 或 Claude。

`desktop/quota_dashboard.py` 提供额度优先的 Claude/Gemini 主面板：Claude 为 5h/周两格，Gemini 为两组四格。缺失窗口保持未知，多个模型不混成平均额度；只展示组内最低剩余比例。今日 Token 仍可切换小时曲线。


## 统一设置与打包

三个角色的设置均为“常规 / 动作”，顶部只保留“状态 / 设置”。Claude、Gemini 共用 `desktop/settings_panel.py` 的草稿与高级参数组件，并保留各自配色和真实数据源。

从工作区根目录执行 `python share/tools/package_all.py`，依次构建三者并验证资源、启动与设置界面。结果暂存于各角色的 `build/package-output/`，日志和截图位于 `build/checks/`。退出已运行的桌宠后执行 `python share/tools/package_all.py --activate-only`，将通过验证的程序放入各角色 `dist/`；旧程序集中归档到根目录 `build/archive/`。

源码、原始素材、当前播放资源与用户配置保持独立。过期构建和预览只归档，不混入 `app/` 或 `assets/`。
