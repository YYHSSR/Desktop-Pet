# 个人版 B1：更新与内置网址入口退役

日期：2026-09-27。范围和验收依据见[设计](superpowers/specs/2026-09-27-personal-edition-phase-b-design.md)与[B1 计划](superpowers/plans/2026-09-27-personal-edition-phase-b1.md)。本地源码没有 `.git`，下列增删行数按 9 月 27 日首批归档的 `source.zip` 与 B1 结束时文件逐行比对，不是 Git diff。原始备份仍在 `E:\CODX\desktop-pet\baselines\phase-a-2026-09-27-20260927-142027-5d23e13e\source.zip`。

## 修改文件说明

| 文件 | 相对归档增删 | 改动与原因 |
| --- | ---: | --- |
| `pet/config.py` | +2/-6 | 快捷启动默认值改为空，按 `kind` 清除旧浏览器条目。 |
| `pet/context_menus/quick_launch.py` | +11/-13 | 仅启动显式配置的应用路径，不再打开固定 Google 地址。 |
| `pet/settings_widgets.py` | +12/-24 | 移除添加默认浏览器的选择，保留空列表添加应用的入口。 |
| `pet/menu_templates/modern-default-v1.json` | +1/-5 | 默认菜单移除更新和内置网页动作。 |
| `pet/menu_templates/modern.json` | +1/-1 | 同步菜单模板。 |
| `pet/context_menus/registry.py` | +2/-38 | 注销四个退役动作及其 URL 构造。 |
| `pet/context_menus/shared.py` | +2/-14 | 清除内置网页常量和启动器。 |
| `pet/context_menus/legacy.py` | +1/-4 | 旧版手工菜单移除网页入口。 |
| `pet/app.py` | +0/-62 | 清除更新桥接、线程、回调和托盘入口。 |
| `pet/window.py` | +0/-1 | 清除窗口的更新回调。 |
| `pet/context_menu.py` | +1/-1 | 资源缺失时的回退菜单也不恢复内置链接。 |
| `pet/__init__.py` | +1/-1 | 更新过时注释，保留本地版本号。 |
| `pet/updater.py` | +0/-103 | 删除无调用的更新查询模块。 |
| `tests/test_updater.py` | +0/-108 | 删除退役功能专用断言；两项配置用例迁至配置测试。 |
| `tests/test_config_domains.py` | +16/-0 | 覆盖改名浏览器条目与显式应用路径的迁移。 |
| `tests/test_config_schema.py` | +20/-0 | 保留非更新配置回归。 |
| `tests/test_desktop_pet_features.py` | +33/-92 | 验证空快捷列表、菜单和固定网址入口退役。 |
| `tests/test_menu_layout.py` | +40/-5 | 验证默认、自定义和资源回退菜单，并保留别名与图标。 |
| `tests/test_pet_interaction_locks.py` | +4/-0 | 验证托盘不再提供更新动作。 |

菜单仍保留 `harness`；余额和消耗的裁剪进入 B2。原有用户配置与历史文件未直接修改。

## 性能分析

Windows 11、Python 3.13，本机单进程计时：`_clean_quick_launch_apps` 输入含两条显式应用和一条旧浏览器，10,000 次共 8.749 ms，均值 0.00087 ms/次；`load_default_menu_layout` 1,000 次共 95.252 ms，均值 0.09525 ms/次。这是本轮绝对成本，没有可比的改前测量，不据此宣称加速。B1 移除更新查询线程与固定网址启动路径；没有新增持久线程、定时器、网络或磁盘写入路径。真实应用的空闲 CPU、内存及线程数留待 B2 累积候选包测量。

## 实机运行记录

在本机 Windows 11 的 Python 3.13 环境执行源码测试。相关配置、菜单、窗口族 `236 passed in 25.35s`；完整测试 `3017 passed, 11 skipped, 261 warnings in 257.23s`，日志位于 `E:\CODX\desktop-pet\t\66001e5b\pytest.log`。新增资源回退菜单用例在全量运行启动之后单独通过，因此 B2 结束还须重新跑全量。受影响菜单生命周期族三次并发负载复跑，各 `76 passed`，分别为 13.09、13.21、13.47 秒；Ruff 对 `pet tests scripts` 检查通过。红灯阶段先观察到旧浏览器和菜单退役断言失败，再修改实现复跑为绿。

本批没有单独生成 EXE：B1、B2 连续开发，统一在 B2 生成候选包以避免重复构建。因此没有把真实空闲应用的网络请求计数、CPU、内存和线程数写成已验证；此项是 B2 交付门槛。自动化网络边界断言验证了菜单路径不启动退役网址和更新器。旧版发布工作流未改，原生代码未改，未运行 CTest。没有发布或覆盖用户配置。

## 测试与限制

完整测试存在既有弃用警告和跳过项；本报告记录数量，不将其计为通过。Windows 路径长度使原先较长的 pytest 临时路径在图片长文件名测试上失败；改用 `E:\CODX\desktop-pet\t` 下的短路径后全量通过。开发文档中的品牌引用不属于产品文案检查对象，该检查现覆盖产品源码、测试与 README；如日后将 `docs/` 用作产品直接展示内容，需扩展检查范围。

## 风险与回滚

删除了旧快捷列表中的 `kind=default_browser`；用户显式配置的应用路径和顺序仍保留。菜单自定义布局中的退役 ID 在解析时被忽略，其余别名和图标保留。若需回滚，先停止新进程，再从上方只读源码归档逐文件恢复 B1 文件并运行全量测试；不自动回滚或覆盖现存用户配置。缺少 `.git`，没有提交或 PR 链接可引用。
