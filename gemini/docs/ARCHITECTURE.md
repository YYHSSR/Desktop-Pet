# Gemini 星光陪伴架构

Gemini 使用与 ChatGPT 相同的 Qt 事件循环、固定透明画布和公共流式动画引擎，但不继承 ChatGPT 的 Codex 业务界面。交互采用与 Gpt 同类的浅色紧凑卡片，内容围绕人物动作和本机用量统计展开。

## 启动链路

```text
app/main.py → share.desktop.companion_app.run(Companion)
app/companion.py → Companion(CompanionApp)        # 与 Claude 共用的行为基类
               ├── sprite.GeminiSprite(SpriteWindow) → 环境星光
               │     └── share.pet_engine.stream_player.StreamPlayer ×2（接管交叠时）
               ├── share.pet_engine.character_pack.CharacterPack
               ├── card.CompanionCard（首帧之后构建）→ 动作 / 设置 / 额度；主卡片显示今日 Token
               │     └── share.desktop.card_kit → SettingsPanel、TodayTokens
               ├── companion_state.ActionDirector → 接管、排队与完成提醒优先级
               ├── local_store.LocalStore → 设置、记录、诊断日志
               ├── desktop_integration → 开机启动、全屏让位
               └── QSystemTrayIcon + QLocalServer → 找回与单实例
```

Gemini 专属的行为在 `companion.py`：状态点喵喵回应、放下后蹦一下、环境星光开关；其他行为与 Claude 共用应用基类。

`share/` 不反向导入角色代码。`app/` 使用扁平导入，启动入口加入工作区根路径；冻结程序从 `_MEIPASS` 读取资源。原始视频处理依赖位于可选的 `share/asset_tools/`，不进入运行包。

## 动画与交互

人物固定在方形原生窗口内，通过透明像素测试让空白位置不阻挡桌面。Windows 物理坐标经 HWND 客户区转换，兼顾高 DPI。渲染使用公共六帧队列和精确帧时钟；取消解码不在 GUI 线程等待。

默认循环为 `idle`（平常）。其他动作按清单注册；随机动作只在空闲时启动，人物拖拽期间暂停随机触发。手动选择的新动作默认立即接管，两段动画交叠 0.32 秒（先叠上新姿势、再淡去旧残留）；单击与双击分别处理，拖拽不会误触单击，锁定位置时只响应点击。

面板与人物独立定位，优先放在人物旁边并限制在当前屏幕可用区。面板保持稳定画布；小屏幕使用内部滚动，避免控件被裁切。

## 素材分层

- `assets/character/manifest.json`：14 段原始 WebP 清单。拖拽已换成新片段，原来的被拎起来仍在互动分类。
- `assets/character/playback/`：13 段透明、对齐的 512 × 512 动画及处理回执（“日常”和“星星魔法”不在播放包里）。
- `assets/character/character.json`：运行时的动作标签、循环属性、时长、帧数与校验值。
- `build/asset-previews/`：深色背景上的透明处理预览。

`tools/prepare_assets.py` 从原片清单取材，验证原片校验值，移除连通到边界的中性浅背景，并处理外侧发卷的封闭白色空洞。每段使用固定变换，避免逐帧重新对齐造成抖动；待机选取近似姿势并制作短循环接缝。原片镜头裁切无法重建，因此“星星魔法”未纳入播放包，庆祝采用完整全身的“接住星星”。

## 数据边界

设置和 Token 缓存保存在 `%LOCALAPPDATA%\GeminiDesktopPet`，不再创建或读取专注记录。单实例名称独立于其他角色。

额度来自 Antigravity 的本机缓存：`app/antigravity_link.py` 只读打开 `state.vscdb`，用一个极小的 protobuf 解码器取出套餐与各模型 `quotaInfo`（剩余比例、重置时间），邮箱与令牌不被读取。“打开 Gemini”仅交给默认浏览器。

## 验证和打包

`tools/check.py` 使用隔离用户目录和 Qt 离屏环境，覆盖动作优先级、拖拽/双击分流、专注计时、设置隔离、角色资源边界及透明处理；完整素材检查核对校验值和所有动画帧。Windows 原生启动及冻结程序可用 `--smoke-test --state-dir <目录> --capture-dir <目录>` 生成截图和启动结果。

`tools/build.py --onefile` 打包为 `dist/GeminiPet.exe`，只收集已选播放资源和运行依赖。角色原片、素材处理依赖、用户配置、日志及账户资料不收集。

## 紧凑卡片和参考姿势

`card.CompanionCard` 默认显示概要、图标工具栏及双区卡片。额度用共用的 `share.desktop.quota.QuotaSnapshot` 表示，未连接时为空；卡片的专注、动作、设置、额度与星星记录页在同一窗口内切换。

`ActionDirector` 分开保存最近一次手动请求和优先的完成提醒，避免手动选择切掉未收尾的动作。流式播放器交接时先保持新动作的参考帧，结束交接后再推进其时钟。

基础素材的共同参考帧位于待机起点。离线过渡先把人物的中心、脚底和身高配准，再补间身体细节；游离粒子保留位置并独立渐隐。完成后的入口与收尾都回到同一参考姿势，资源检查会核对编码后的首尾差异。`sprite.GeminiSprite` 单独绘制连续环境星光，不重置闪烁时钟。

## 与 Gpt 一致的卡片表面

角色卡片继承 `share.desktop.card_surface.CompanionCardSurface`。默认 268 × 188，扩展编辑区最大 560 × 600，并按显示器可用区域收窄。额度只使用真实快照，缺失值为“—”。

每次导航只准备起点与终点两张图像，原生窗口在过渡期间保持联合画布不变；每帧只绘制圆角裁剪、背景和缓存图像。打开、展开、收缩、收起使用与 Gpt 相同的公共动效曲线和时长，快速导航保留最近一次请求。缩小时由独立透明画面覆盖原生 backing store 交接。

设置面板由 `share.desktop.settings_panel` 提供。编辑、恢复默认和切页都只修改草稿；应用后再发出设置变更，外部设置更新会保留尚未应用的草稿并提示冲突。退出设置不会丢弃草稿。网页入口只留在卡片工具栏，右键菜单移除。

卡片顶部仅保留刷新、网页、设置；日报入口和日报页面已移除。底栏 `TodayTokens` 显示本机当天用量，点击切换 `Dashboard` 的小时曲线。三个角色的右键菜单结构集中在 `share/desktop/context_menu.py`。
