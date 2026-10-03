# 验收测试文件清单

验收按当前测试文件的实际边界执行；旧插件桥接及其 Node 测试已退役。

## 设置窗口验收

现代设置窗口的测试已按功能拆分：

- `tests/test_settings_and_resources.py`：现代设置窗口基本控件与配置 round-trip；
- `tests/test_collision_settings.py`：现代设置窗口碰撞控件、持久化和运行时同步；
- `tests/test_settings_subslot_autostart.py`：子槽位下现代设置窗口的开机自启行为；
- `tests/test_desktop_pet_features.py`：现代设置侧栏、页面归属、表达风格及依赖控件；
- `tests/test_settings_event_gating.py`：设置窗口打开时的事件/提醒拦截边界。

验收命令（每个路径都由 pytest 收集并执行）：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q `
  tests/test_settings_and_resources.py `
  tests/test_collision_settings.py `
  tests/test_settings_subslot_autostart.py `
  tests/test_desktop_pet_features.py `
  tests/test_settings_event_gating.py
```

## ChatGPT Work/Codex 联动验收

验证本机 rollout 的会话身份、增量读取、并发聚合、等待输入、启停和桌面端启动：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_chatgpt_desktop.py tests/test_codex_monitor.py tests/test_cursor_monitor.py tests/test_agent_multi_session.py tests/test_agent_link.py tests/test_agent_link_threads.py
```

2026-10-03 的完整验证与已知基线失败见
[`PR-REPORT-CHATGPT-LINK-2026-10-03.md`](PR-REPORT-CHATGPT-LINK-2026-10-03.md)。

## Qt 生命周期与最终全量验收

Windows/offscreen 的最终验证必须分两步执行，避免高并发跨进程压力测试掩盖普通
Qt 生命周期问题：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q -k "not decode_fanout"
python -m pytest -q tests/test_decode_fanout.py tests/test_decode_fanout_integration.py
```

第一步应先完整结束且无 native abort；第二步只能在第一步通过后运行。下列数字为历史基线，当前结果见上方交付报告：

- 主套件：`1895 passed, 8 skipped, 2 deselected`（2 deselected = 本机两个已知环境假红：高刷屏 drag 节流钟差、collision 真时钟竞态）；
- 解码扇出族（原跨进程 shm broker 已被进程内 fan-out 取代）：`29 passed`。

生命周期重点覆盖 `PetWindow.closeEvent()` 的幂等关闭、外置
`PetSpeechBubble` 的 owner 清理、右键菜单执行 seam、AgentLink/WebM/session
后台资源 teardown。详细说明见
[`QT-LIFECYCLE-FULL-SUITE-STABILIZATION-2026-09.md`](QT-LIFECYCLE-FULL-SUITE-STABILIZATION-2026-09.md).
