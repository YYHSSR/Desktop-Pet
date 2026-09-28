# 个人版首批执行记录：基线完成，ChatGPT 状态来源未验收

日期：2026-09-27。工程：`E:\CODE\desktop-pet`。本报告对应[首批设计](superpowers/specs/2026-09-27-personal-edition-phase-a-design.md)与[实施计划](superpowers/plans/2026-09-27-personal-edition-phase-a.md)，细化[个人版改造指导](../C++-Python/构建说明/个人版功能裁剪与ChatGPT状态联动改造指导-2026-09-27.md)的批次 A。当前目录没有 `.git`，下述“文件增删”由本轮操作记录和文件行数核算，不冒充 `git diff --numstat`。

## 一、结果

已建立当前源码与两份应用配置的独立备份，并完成逐文件摘要、ZIP CRC 和私有 ACL 核验。已制作只读 Windows UI Automation 探针，在本机合并 ChatGPT 客户端完成一轮操作者确认的 Chat 试验。通用 Stop 控件在该轮结束前后反复出现，**不能作为当前 Chat 会话的完成信号**。Work 真实场景尚未执行；两种模式的状态联动均未验收，本轮没有把探针接入桌宠产品。

## 二、修改文件说明

| 文件 | 本轮增删 | 原因 |
| --- | ---: | --- |
| `docs/superpowers/specs/2026-09-27-personal-edition-phase-a-design.md` | 新增 +45/−0 | 固定备份、隐私和状态能力边界。 |
| `docs/superpowers/plans/2026-09-27-personal-edition-phase-a.md` | 新增 +72/−0 | 把批次 A 拆成可核验的任务。 |
| `C++-Python/构建说明/个人版功能裁剪与ChatGPT状态联动改造指导-2026-09-27.md` | +2/−0 | 互链首批设计。 |
| `docs/INDEX.md` | +3/−0 | 登记设计、计划和本报告。 |
| `docs/PR-REPORT-PERSONAL-PHASE-A-2026-09-27.md` | 新增 +59/−0 | 记录实际结果和未验收项。 |
| `.scratch/personal-edition/HANDOFF.md` | 新增 +9/−0 | 保留下一批准确断点。 |

外置产物：`E:\CODX\desktop-pet\experiments\phase-a-baseline` 新增备份工具 215 行、验证用例 109 行；`experiments\chatgpt-windows-state-probe` 新增只读观察器 170 行、自检 27 行、说明 11 行、试验记录表和能力矩阵。它们不属于产品运行代码。没有删除文件、修改用户配置、安装插件或启动新版本桌宠。

## 三、基线与实现要点

新基线位于 `E:\CODX\desktop-pet\baselines\phase-a-2026-09-27-20260927-142027-5d23e13e`：源码 ZIP 86,233,888 字节，710 个成员，SHA-256 `fe6238c373197305e4e02e9f221d599a4844ac71be8d9dcb43040448337414b9`；两份配置仅为 `dsh-pet-standalone-webm-chat/config.json` 和 `dsh-pet-standalone-webm/config.json`。710 个 ZIP 成员和两份配置的 SHA-256 独立复核均无差异，ZIP CRC 正常。备份目录及配置副本继承仅当前 Windows 用户可访问的 ACL；清单只含路径、大小和摘要，不含配置正文。

9 月 26 日历史源码基线仍在原位，ZIP SHA-256 与原记录 `1d82265260b1bb38ded020b6d5dbf627ee1c14c25b0e53fd57c28622f3b57ee2` 一致。本轮没有覆盖或搬迁它。探针只在内存比对允许列表中的按钮名称，输出结构计数和布尔签名，不存原始控件名称或聊天正文。

## 四、性能分析

环境：Windows 11、PowerShell 5.1、py13 Python，客户端包 `OpenAI.Codex_26.917.6896.0_x64__2p2nqsd0c76g0`。一次备份命令耗时 3.46 秒，处理 710 个源码文件和 2 个配置文件。短时观察运行 5.7 秒、8 次扫描，单次 149–212 毫秒，包装 PowerShell 进程累计 CPU 增量 0.094 秒、结束时工作集 114.88 MiB；正式 Chat 观察运行 90 秒、100 条记录，扫描中位数 158.11 毫秒、范围 54.47–307.20 毫秒，JSONL 为 39,066 字节。数字来自本机单次试验，不外推长期稳定性。

桌宠稳态开销变化为 **0**：尚未接入产品。探针活动时用 UIA 查询窗口，每次扫描产生系统调用和短暂 CPU/内存成本；没有新增网络请求、持久线程或产品缓存。备份阶段读写磁盘，结束后不常驻。事件到界面的延迟尚不可测，因为没有可靠事件和产品适配器。

## 五、实机运行记录

- 备份工具先看到缺少实现的失败用例，再实现并复跑；独立复核发现根目录链接和枚举错误边界后，补失败用例并修正：6 项通过，符号链接因 Windows 缺少创建权限跳过 1 项；junction 回归实际通过。独立复核结果为 `zip_count=710`、`source_bad=0`、`config_bad=0`、`zip_sha_match=True`。原始备份仍有效，工具的新增保护适用于未来重跑。
- PowerShell 探针自检通过，合成私密标签未进入 JSONL。首次浅层探针只见 13–15 个控件；扩大深度后见 387 个控件，说明原深度遗漏大量控件，但控件数量本身不证明到达对话正文区域。后来增加屏幕外按钮过滤；复核后又将节点/深度截断和不可用元素标为 `partial`，将缺失信号设为未知，自检通过。旧观察文件仍按旧探针解释。
- 操作者确认普通 Chat 完成一轮消息，并提供 `C:\Users\zf\Pictures\Screenshots\屏幕截图 2026-09-27 143518.png`（SHA-256 `64bb8d040b4cb62fa0b8bf4e38585fb1f786d9211503e48bf83f665aae378286`）。同轮探针 `observations-20260927-143404-0f1da4d6.jsonl` 记录 Stop 信号多次消失又出现；截图显示回复完成后，信号又于 UTC 06:35:19 变 true。故本轮算 1 次执行、0 次可靠终态识别。外部 `E:\CODX\desktop-pet\experiments\chatgpt-windows-state-probe\capability-matrix.json` 保留 `unknown/not_run`，没有误报通过。
- 当前客户端是否有可附着既有 Chat/Work 会话的正式状态订阅接口仍未证实。[OpenAI 插件迁移指南](https://developers.openai.com/plugins/guides/submit-claude-plugin)说明普通 Chat 不能依赖 Codex hooks；[Agents API 概览](https://developers.openai.com/api/docs/guides/agents-api/overview)描述的是通过该 API 创建和管理的会话。这些文档不能证明本机既有客户端会话可供第三方订阅。

## 六、测试与验证

| 门 | 实际命令或检查 | 结果 |
| --- | --- | --- |
| 备份工具用例 | py13 `-B -m unittest discover -s E:\CODX\desktop-pet\experiments\phase-a-baseline -p test_snapshot.py -v` | 6 passed，1 skipped；跳过的是需特权创建的符号链接，junction 用例通过。 |
| 探针隐私与窗口层级 | `E:\CODX\desktop-pet\experiments\chatgpt-windows-state-probe\test_inspect.ps1` | `self-test passed`。 |
| 归档与清单 | 独立重开 ZIP、逐成员和配置副本计算 SHA-256 | 710/710 源文件、2/2 配置通过。 |
| 报告纪律 | py13 `-B -m pytest -q -p no:cacheprovider --basetemp E:\CODX\desktop-pet\test-runs\20260927-144100-23341212\tmp tests/test_pr_report_discipline.py` | 29 passed in 0.58s。 |
| 产品全量测试/新 EXE | 未运行 | 本批没有产品代码变更或新构建；不得写成交付验收通过。 |

## 七、已知限制与后续

Chat 仅执行 1 次真实试验，Work 0 次；达到“稳定支持”所需的各 10 次正常场景和错误/取消/多会话场景未执行。当前 UIA Stop 布尔值存在明显跨状态干扰，继续重复相同探针不会使它成为可信完成事件。本轮提早停止重复试验，保留能力矩阵为未知；若后续取得会话专属且可区分终态的正式事件源，再恢复完整矩阵验证。

下一批可独立推进菜单、消费/余额、更新入口退役；必须保持旧配置可恢复、保留 Cursor 和通用聊天数据。不要用本探针布尔值直接触发完成动画。本地无 Git，无法出具提交差异；9/27 备份和文件摘要是本轮恢复依据。旧构建目录和 `E:\CODE` 根下临时测试树仍未清理。

## 八、风险与回滚

本批没有改变桌宠运行行为。若需撤销文档或外部实验脚本，可依据上述 9/27 ZIP 与清单恢复源码；两份配置副本用于后续迁移前比对，不能自动覆盖用户此后改动。原始备份和诊断证据保留原位，清理前需逐文件核对。
