# Codex 使用的共享组件

此目录当前仅由 `Codex/` 调用，不包含其他角色的模型、素材、桌面界面或状态服务。

| 模块 | 职责 | 调用方 |
| --- | --- | --- |
| `pet_engine/stream_player.py` | 六帧后台解码队列、累积帧时钟、异步取消及动态采样尺寸 | `Codex/app/stream_player.py` |
| `pet_engine/decode_runtime.py` | 解码线程生命周期与统计单例 | `Codex/app/decode_runtime.py`、共享播放器 |
| `pet_engine/loop_cache.py` | 有界无损循环缓存 | `Codex/app/loop_cache.py`、共享播放器 |
| `pet_engine/packaging.py` | Conda 原生 DLL 收集与构建环境 | `Codex/tools/build.py` |

前三项由 Codex 原实现提取，原扁平模块路径保留为兼容入口，并使用相同模块对象，保持补丁测试和统计单例的行为。Codex 的卡片、账户额度、日报和平台连接仍在 `Codex/app/`。

源码及构建均需完整保留根目录下的 `Codex/` 和 `shared/`。共享实现沿用项目 CC BY-NC 4.0 授权，见根目录 `LICENSE`。
