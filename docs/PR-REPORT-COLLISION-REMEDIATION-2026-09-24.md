# 碰撞原生审查整改交付报告（2026-09-24）

范围：[审查建议 R01–R11](../C++-Python/构建说明/项目完成情况审查与优化整改建议-2026-09-24.md)及[当前状态索引](../C++-Python/构建说明/README.md)。本地目录没有 `.git`；用户给出的[上游仓库](https://github.com/MerZlin/dsh-pet-indesktop)中提交 `5a2025111de915413635b096e7091e3db9a0193b` 的六个关键文件与改动前快照逐字节一致，无法据此证明整个本地树的提交身份。根 `AGENTS.md`、`.gitignore`、`README.md`、`CONTEXT.md` 从该提交恢复；没有伪造 Git 历史。

## 一、整改结果

| 项 | 实施与直接证据 |
| --- | --- |
| R01 | Release 测试使用显式 CHECK；错误注入下 CTest 退出 8，正常退出 0。 |
| R02 | 恢复真实 `AGENTS.md`，不排除规范测试运行全量套件。 |
| R03 | 冻结 exe 无 GUI JSON 自检证明 ABI 2、构建 ID 和 1 次真实 native 调用；缺失与错误 DLL 非零退出，auto 回退到 Python。解压副本复测通过。 |
| R04 | 原生 DLL 递归依赖闭包以独立候选目录暂存，哈希、架构、导入、pacman 版本写入 manifest；验证后替换。旧 DLL 与缺失依赖负例通过。 |
| R05 | 默认 DLL 路径与 auto 失败路径缓存；动态路径变化与显式重试有测试。 |
| R06 | ABI v2 明确有限数值、正质量、数组/迭代边界；Python 在 ctypes 收窄前验证整数；非法输入不写有效输出。 |
| R07 | ctypes 校验结构尺寸、对齐和 78 个字段偏移；构建 ID 包含源码哈希、编译器与 Release 配置。 |
| R08 | 5 轮×100 次交错顺序测 15 个拓扑，保存全部原始调用耗时、p95/p99、CPU、DLL 哈希及构建 ID；首调用明确指单进程的场景首次调用。 |
| R09 | Conda 运行库由顶层 `.pyd` 导入及传递闭包收集，当前环境收集 10 个 DLL，逐个记录哈希并替换旧字节。候选包嵌入构建输入 manifest；完整 Git 来源仍缺。 |
| R10 | 加入多 tick、圆形链、静态体、30 成员和前缀 ID 差分；修复近似并列圆接触点及 pair 排序。 |
| R11 | 修复搬迁后的文档链接、便携包位置和 MiB 单位；建立当前状态页。 |

## 二、修改文件说明

本地快照仍无 `.git`，无法计算它自身的提交差异。已在独立目录克隆真实上游 Git 历史，检出上述候选提交，并将本轮相关文件复制进去计算 `git diff --numstat`。下表是 **9 月 24 日文件相对上游候选提交**的取样，非本轮净改动；其中上游缺失的文件显示为全文件新增。9 月 26 日完整逐文件数字以交付目录的 `upstream-git-numstat-2026-09-26.txt` 为准；早期 Python 对照快照另存为 `upstream-numstat.json`。

| 文件 | 上游比较 +/− | 改动与原因 |
| --- | ---: | --- |
| `C++-Python/CMakeLists.txt`、`include/pet_core.h`、`src/pet_build_id.h.in` | +119/−0 | 生成源码关联构建 ID；公开 ABI v2、边界与布局接口。 |
| `C++-Python/src/c_api.cpp`、`src/collision.cpp`、`tests/test_core.cpp` | +596/−0 | C 边界验证、确定性接触点、有效的 Release 断言及负例。 |
| `pet/native/loader.py`、`collision_backend.py`、`selftest.py` | +413/−0 | 绑定布局验证、热路径缓存、失败回退与机器可读自检。 |
| `packaging/pet_entry.py`、`pet_entry_no_chat.py`、`pet/__main__.py` | +13/−0 | 在 GUI 导入前分流冻结自检参数。 |
| `scripts/build_native.ps1`、`build_onedir.ps1` | +195/−21 | 原生依赖事务式暂存、按 manifest 打包、递归 Conda 收集、冻结 exe 验证；修正 PowerShell `$entry` 被 manifest 循环覆盖。 |
| `scripts/verify_frozen_native.py`、`collect_conda_runtime.py`、`package_collision_candidate.py`、`bench_collision_backends.py` | +391/−0 | 隔离运行自检、依赖闭包、候选包收据和原始性能数据。 |
| `tests/test_collision_backend.py`、`test_collision_native.py`、`test_collision_native_contract.py`、`test_native_selftest.py`、`test_collect_conda_runtime.py` | +404/−0 | 失败缓存、时序/排序/圆链差分、ABI 负例及暂存替换测试。 |
| `requirements-dev.txt`、`.github/workflows/build-windows.yml`、`.gitignore` | +26/−3 | 声明 pefile 构建依赖、CI 安装开发依赖并忽略生成目录。 |
| `docs/INDEX.md`、`C++-Python/构建说明/*`、`docs/superpowers/plans/2026-09-24-remediation.md` | +584/−0 | 索引、规格搬迁链接、历史/现状区分与整改计划。 |
| `README.md`、`CONTEXT.md`、`AGENTS.md` | 上游字节相同 | 从匹配候选提交恢复快照缺失的原始文档。 |

## 三、性能分析

> 历史快照：本节圆链和“静态墙”场景使用 fixture v1。圆链世界坐标与成员中心不一致，静态体未设置 `FLAG_STATIC`。修正后的 2026-09-26 数据与解释见[候选晋级与基准修正报告](PR-REPORT-CANDIDATE-PROMOTION-2026-09-26.md)；本节原始数字保留作历史证据。

方法：Windows 11、Python 3.13.15、Intel Family 6 Model 183；`python scripts/bench_collision_backends.py --rounds 5 --samples 100 --output ...`。每个拓扑交替 Python/native 顺序，测公开求解调用（包括 marshal、DLL 求解和解包）。原始 JSON 位于交付目录 `collision-benchmark-2026-09-24.json`，DLL SHA-256 为 `fcfe44b0c4cbd244b8f802261f806f27c7d546d736eebb85654149e6e927a796`。

| 30 成员拓扑 | Python 中位/p95 µs | Native 中位/p95 µs | Native/Python 中位 |
| --- | ---: | ---: | ---: |
| 稀疏 | 401.6 / 432.1 | 1919.25 / 2069.88 | 4.779 |
| 稠密 | 6386.9 / 6763.22 | 2783.25 / 2989.57 | 0.436 |
| 圆链 | 13143.35 / 13931.33 | 3026.25 / 3297.57 | 0.230 |
| 静态墙 | 6636.95 / 7101.27 | 2875.65 / 3187.56 | 0.433 |

1 成员稀疏为 Python 3.3 µs、native 12.9 µs；3 成员稀疏为 8.6 / 29.0 µs。默认继续使用 Python。auto 失败缓存减少重复 DLL 预检，正常 native 每次仍经 ctypes 加载器缓存与批量打包；没有增加每 tick 磁盘扫描、网络请求或新线程。新 Conda 依赖扫描、哈希和源文件哈希仅在构建时运行。此微基准没有测 GUI 帧率、整机 CPU、内存增长、电源状态和背景负载，也没有分离打包/求解/解包成本；这些不作为实际帧率收益的证据。

## 四、实机运行记录

- 本机 `python -m pytest -q --basetemp ...`：**2954 passed, 11 skipped**，180.74 秒，未 deselect。之后聚焦 49 个测试通过；Ruff `check pet tests` 及新增构建脚本通过。
- Release `ctest --test-dir build-native/ucrt64-release --output-on-failure --no-tests=error`：1/1 通过；设置 `PET_CORE_TEST_INJECT_FAILURE=1` 后 1/1 失败、退出 8；取消后再通过。原始输出在交付目录。
- `build_onedir.ps1 -Variant webm-chat -PythonExe D:\python\miniconda\envs\py13\python.exe -UcrtBin E:\msys2\ucrt64\bin -SkipZip -SkipGuiSmoke`：PyInstaller、Qt/Shiboken、中文编码、原生依赖与冻结 exe 自检通过。初次执行暴露 `$entry` 变量复用导致 PyInstaller 入参错误，修正后完整重建通过。
- 候选 zip 含 1128 文件，170566410 字节，CRC 全检通过，SHA-256 `c369757a707063ee69c5acaa64a4df85418cc37374c772cd6d73fda44e2acb3f`。解压到独立工作目录后，在仅 Windows 系统 PATH 和隔离 APPDATA/LOCALAPPDATA/TEMP 下，自检输出 `FROZEN_NATIVE_OK`、ABI 2、1 次 native 调用。包内有 `build-input-manifest.json`、原生与 Conda 依赖 manifest；外部 `candidate-receipt-2026-09-24.json` 记录 zip 哈希。
- 已用链接检查器核对本目录和 `docs/INDEX.md` 的本地链接，0 条缺失。

**尚未完成的外部验收：** 未取得无 Conda、MSYS2、源码的干净 Windows 环境；未在本轮验证真实桌面交互、正常退出、配置保留及长时间全进程树资源。构建时 `-SkipGuiSmoke`，因此当前候选包只可供下一轮人工/干净机验收，不标记正式发布。目录缺 `.git`，未创建分支或 PR；提交/树来源需要完整仓库或原始快照才能证实。

## 2026-09-26 来源补证

Git 网络现已可用。在独立目录克隆[上游仓库](https://github.com/MerZlin/dsh-pet-indesktop)，检出 `5a2025111de915413635b096e7091e3db9a0193b`，将本轮相关文件复制进该检出，并用 `git add -N -- .`、`git diff --numstat` 记录逐文件差异。交付目录的 `collision-remediation-against-5a20251.patch` 已通过针对干净上游检出的 `git apply --check` 与修改后检出的 `git apply --reverse --check`。这个比较证明这些文件相对公开提交的内容变化；它**不能证明**本地项目快照原本就是该完整 Git 树，也不代表已经向上游提交或创建 PR。项目原目录继续保持不变。

同日复查七份当前文档，本地链接缺失数为 0；新增整改计划已登记到 `docs/INDEX.md` 并回链本报告。候选包 SHA-256 复算仍与交付收据一致，Ruff 和报告纪律测试保持通过。

## 2026-09-26 独立 Windows runner 门禁

`build-windows.yml` 新增 `clean-portable-native` 作业：全新 Windows runner 只下载构建作业上传的便携 zip 与 `verify_portable_native.ps1`，不检出源码、不安装 Conda 或 MSYS2；脚本解压两种 WebM 包，隔离 PATH/用户配置/临时目录，核对包内 DLL、真实 native 调用、缺失/错误 DLL 失败和 auto 回退。tag 推送现在只构建候选包；正式 Release 需在 tag 上手动运行工作流、勾选已完成干净 Windows 桌面验收，并等待构建与独立 runner 门禁通过。脚本已在本机对本轮候选 zip 实跑，输出 `PORTABLE_NATIVE_OK`；远端 CI 尚未运行，因此不把该门禁记为通过，也不以它代替真实桌面交互验收。

> 历史流程说明：上段“手动运行同一工作流并勾选验收”是当时的方案，现已由[2026-09-26 候选晋级流程](PR-REPORT-CANDIDATE-PROMOTION-2026-09-26.md)取代。新流程从已验收 run 下载原 artifact，不重新构建；远端执行仍待完成。
