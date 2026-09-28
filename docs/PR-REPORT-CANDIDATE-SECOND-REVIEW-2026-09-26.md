# 候选晋级第二轮整改交付报告（2026-09-26）

关联：[第二轮审查](../C++-Python/构建说明/候选晋级流程专项审查-2026-09-26-第二轮.md)、[候选包索引](../C++-Python/构建说明/候选包索引-2026-09-26.md)。当前目录无 `.git`，此报告记录本地文件整改，不声称已形成 PR、远端 CI run 或正式发布。

## 一、核心特性

1. **S01 构建阻断**：构建脚本在普通 Python 环境写入明确的 `provider=standard, applicable=false` 清单；Conda 环境继续收集 DLL 闭包并写 `provider=conda, applicable=true`。候选汇总依据构建 Python 的 `sys.prefix/Library/bin` 检查来源，拒绝缺失、错标或 DLL 摘要不符；收据覆盖两包内运行时清单。
2. **S02/S03 候选身份**：迁移后的整改 zip 位于 `E:\CODX\2026-09-24\li\outputs`，旧 zip 位于本项目 `dist-onedir`。两者字节与 SHA-256 已复算；直接读取各 zip 内 DLL 的 `pet_core_abi_version` 导出指令，分别为 ABI 2 与 ABI 1。历史收据保留原路径，索引新增迁移说明。
3. **S04 草稿恢复**：晋级按 tag 串行；Release 身份写入草稿正文。重跑只恢复同 tag、同 run、同 artifact、同收据哈希和提交的未公开草稿。已有附件先下载验摘要，只补缺失项；公开版、异候选及附件不符均失败。
4. **S05 验收记录**：两变体各要求至少 5 分钟运行、全进程树 CPU/内存数字、无持续增长的人工判定、退出后零残留进程及证据路径。这些字段是晋级门禁；实机数据仍待实际填写。

## 二、修改文件说明

当前项目缺 `.git`，且没有整改前同目录快照，无法可信给出本轮 `git diff --numstat`；因此不把上游累计补丁的增删行数冒充本轮差异。新增文件的行数可直接统计，既有文件按实际改动逐项说明。没有删除文件或覆盖旧候选包。

| 文件 | 改动与原因 |
| --- | --- |
| `scripts/candidate_release.py` | 增加标准/Conda 运行时清单校验、包内清单摘要绑定及资源验收字段，消除普通 Python 构建中断和自由文本漏验。 |
| `scripts/collect_conda_runtime.py` | 将清单升为 schema 2 并明确 Conda 来源。 |
| `scripts/build_onedir.ps1` | 普通 Python 分支也生成清单，使两个环境都可进入候选汇总。 |
| `scripts/promote_candidate.py`（新增，+82/−0 行） | 封装草稿身份与已有附件摘要判定，供晋级工作流执行。 |
| `.github/workflows/promote-windows-release.yml` | 分页查找包含草稿的 Release、绑定身份、串行化并受控补传缺失附件。 |
| `tests/test_candidate_release.py` | 红绿回归覆盖普通 Python、Conda 清单缺失/错标/篡改以及资源验收。 |
| `tests/test_collect_conda_runtime.py` | 验证实际收集器生成的 schema 2 清单可被候选汇总器读取。 |
| `tests/test_promote_candidate.py`（新增，+47/−0 行） | 模拟同候选草稿、异候选/公开版、部分附件和摘要不符。 |
| `C++-Python/构建说明/候选包索引-2026-09-26.md`、`README.md` | 修复可访问路径及旧包 ABI 标注；说明历史收据位置。 |
| `docs/INDEX.md`、本文（新增） | 登记本轮改动、证据与剩余验收。 |
| `.gitignore` | 忽略可重建的 Ruff 缓存，避免后续建立 Git 基线时误收入。 |

## 三、性能分析

在本机 Windows、Python 3.13.15 上，对一个临时标准环境清单连续验证 1000 次用时 **127.59 ms**，即每次约 **0.128 ms**；对同候选草稿身份判定 1000 次用时 **2.98 ms**，即每次约 **0.003 ms**。测量使用 `time.perf_counter()` 包住 1000 次函数调用；第一项包含本地 JSON 文件读取和目录检查，第二项纯内存。该路径仅在构建/晋级时触发，不在桌宠逐帧或每 tick 路径触发；稳态产品调用次数新增 **0**。标准清单新增一个约百字节的磁盘文件和候选归档条目；Conda 验证逐个读取已收集的 DLL 求 SHA-256，耗时随依赖总字节增长。晋级新增 GitHub API 读取、附件下载和校验，频率为每次人工晋级一次；未添加产品运行期系统线程或常驻缓存。远端真实构建/晋级耗时与峰值内存尚无实跑数字，不能以本地函数测量替代。

## 四、实机运行记录

- 回归先在缺少新函数时出现 **3 failed**；草稿测试先因模块缺失在收集期失败；资源验收测试先出现 **1 failed**。对应实现后，定向 `tests/test_candidate_release.py tests/test_promote_candidate.py tests/test_collect_conda_runtime.py` 为 **10 passed**。
- 在 `QT_QPA_PLATFORM=offscreen`、MSYS2 UCRT runtime 可见的本机环境执行全量 `python -m pytest -q --basetemp E:\CODE\pf2full`：**2971 passed、11 skipped**，189.29 秒。之后仅收紧资源字段的整数类型、补收集器契约断言及加入本文；受影响的收据、收集器、草稿与报告纪律定向复验 **37 passed**。
- `ruff` 检查修改的 Python 文件：**All checks passed!**；两个 Windows workflow 均经 PyYAML 解析，分别识别 2 和 1 个 job。
- 命令行小型端到端演练：`runtime-standard --bundle` 实际写出 `provider=standard`；`promote_candidate.py preflight` 首次输出 `release_state=create`，对同候选草稿再次执行输出 `release_state=resume`。这不涉及真实 GitHub Release。
- 本机复算整改 zip：170,566,410 字节，SHA-256 `c369757a707063ee69c5acaa64a4df85418cc37374c772cd6d73fda44e2acb3f`。旧 zip：170,472,903 字节，SHA-256 `377368865e782f32d64ecb1ceb73d889eee5f0b7f09a6f9454e2eaab03788e41`。收据仍在迁移后目录，SHA-256 `2a4ffbc3312a020fc478e8d72c1bd450c5eacecdfa8db6376420962ef43b09d4`。
- 未重打真实安装包：当前目录无 `.git`，本机找不到 `ISCC.exe`；没有可写的项目 GitHub 仓库、候选 run/artifact 或人工验收记录，不能在本机完成远端 CI 与 Release 晋级。旧包和历史收据字节未改动。

### 首次真实验收所需记录

人工记录须绑定同一候选 run、commit、四个附件摘要；每个变体附 `desktop_checks` 与 `resource_checks`。后者字段：`duration_minutes`（至少 5）、`process_tree_cpu_percent_p95`、`process_tree_memory_mb_start`、`process_tree_memory_mb_end`、`residual_processes`（0）、`no_sustained_growth`（true）、`evidence`（日志/截图路径）。资源数字和人工判定必须来自真实桌面测试，不可用本地假包回归结果填写。首次远端 CI 成功后还须归档候选收据、独立 runner JSON 自检、两种安装/桌面/后端/退出结果与公开附件复下载摘要。

### 精简清单处理边界

第二轮审查第 10 节是后续整改建议。本轮仅将可重建的 `.ruff_cache/` 加入忽略规则。`package_collision_candidate.py` 当前仍覆盖无 Git 的本地打包方式；Python 碰撞回退、旧聊天样式、JS 桥接及两变体入口都有现用调用方。本轮保留这些路径及构建输出，未根据文件名或扩展名批量删除。后续清理先建立可恢复的 Git 基线，逐项迁移调用与验收，再处理重复产物。

## 五、交付复审 T01–T03 后续补强（2026-09-26）

关联：[第二轮整改交付复审与剩余问题](../C++-Python/构建说明/第二轮整改交付复审与剩余问题-2026-09-26.md)。本节追加在原交付记录之后，保留前述测试和功能判断的历史时点。

### 修改文件说明

本地仍无 `.git`，无法提供可信的本轮 `git diff --numstat`。本次仅修改下列已有文件，无源码或产物删除：

| 文件 | 改动与原因 |
| --- | --- |
| `scripts/promote_candidate.py` | 对收据 SHA-256 严格验证；恢复前重新读取指定草稿，校验身份与原候选字节；按状态区分完整附件和 `starter` 空占位，先验证完整附件，再仅删除受控占位并补传缺失文件。 |
| `.github/workflows/promote-windows-release.yml` | 把人工哈希经环境变量传给 Bash 和 Python；草稿恢复交给可测试的顺序执行器，避免直接在 shell 源码中插入输入。 |
| `scripts/candidate_release.py` | 验收入口验证收据哈希格式；资源值要求有限数字，拒绝布尔值与无法转换的巨大整数；机器和证据字段要求非空文本。 |
| `tests/test_promote_candidate.py` | 覆盖异常哈希文本、同候选空占位、重复或错误元数据、完整附件摘要错误、公开草稿拒绝，以及 API/CLI 替身的下载→删除→补传顺序。 |
| `tests/test_candidate_release.py` | 对四个资源测量字段逐项覆盖 Infinity、NaN、溢出指数、巨大整数、布尔值和缺失值。 |
| `C++-Python/构建说明/README.md`、`docs/INDEX.md`、本文 | 更新复审入口与本次证据；保留审查原文和历史测试记录。 |

### 性能分析

本机 Windows、Python 3.13.15，`time.perf_counter()` 测得有限数判定 100000 次 **14.92 ms**（约 0.000149 ms/次），两个附件的状态分类 10000 次 **8.01 ms**（约 0.000801 ms/次）。这两条路径只在人工晋级时执行，不进入桌宠运行期；稳态调用新增 **0**。恢复草稿多读取一次 GitHub Release 元数据，只在重试时发生；对 `starter` 的删除和补传仅在上传失败遗留占位时发生。已有附件下载与 SHA-256 验证仍随附件总字节数增长。本轮没有新增产品运行期网络调用、系统线程或常驻内存。真实 GitHub 往返耗时尚未测量，不能用本地函数数字估计。

### 实机运行记录与剩余边界

- 改动前，新回归先出现 **11 failed**，包含空占位无法恢复、非法哈希被接受及无限资源值通过；新增巨大整数用例再出现 **4 failed**。修复后定向收据、草稿、Conda 清单和报告纪律共 **81 passed**；Ruff 与工作流 YAML/Bash 语法检查通过。
- 在本机 `QT_QPA_PLATFORM=offscreen`、MSYS2 UCRT runtime 可见环境，以 `D:\python\miniconda\envs\py13\python.exe -B -m pytest -q --basetemp E:\CODE\pf3full` 执行全量：**3016 passed、11 skipped**，202.56 秒。全量启动后新增的空草稿边界测试另在上述 81 项定向复验中通过。
- 用隔离替身运行 `recover` 命令入口，观察顺序为读取 Release → 下载完整附件 → 删除 ID 123 的 `starter` → 上传原候选文件；完整附件摘要错误时仅发生下载，不执行删除或补传。没有使用真实发布凭据。
- GitHub 官方[Release asset API](https://docs.github.com/en/rest/releases/assets#upload-a-release-asset)说明 502 上传失败可能留下 `starter` 空附件，允许删除；本实现将删除范围限定为身份相符的草稿中、预期名称且 `state=starter,size=0` 的附件。
- 当前项目仍无 `.git`，本机无 `ISCC.exe`。真实 Windows 候选 CI、GitHub 草稿恢复、GUI/安装卸载和长期资源采样尚待实际运行。此次未修改两份历史 zip 或收据，也未执行清理清单 C01–C11 的源码删除。
