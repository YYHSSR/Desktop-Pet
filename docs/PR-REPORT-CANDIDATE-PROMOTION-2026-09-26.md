# 候选晋级与性能基准修正交付报告（2026-09-26）

范围：[2026-09-26 复审 F01–F05](../C++-Python/构建说明/项目整改复审与后续改进建议-2026-09-26.md)、[实施计划](superpowers/plans/2026-09-26-candidate-promotion.md)与[候选包索引](../C++-Python/构建说明/候选包索引-2026-09-26.md)。本地项目目录没有 `.git`；用户提供的公开上游是第三方仓库。本轮修改本地源码与文档，重建暂存的原生 DLL 并重测基准；不推送、不创建 Release。

## 一、整改结果

| 项 | 当前实现 | 证据边界 |
| --- | --- | --- |
| F01 | 独立 `promote-windows-release.yml` 读取成功的原候选 run/artifact，检查 tag 提交、工作流身份、artifact 是否过期、收据摘要与人工验收 JSON；四个附件先写入草稿 Release，重新下载并逐个比对哈希后才公开，禁止已有 Release 覆盖。 | 工作流经本地语法解析与校验器测试；远端尚未执行。 |
| F02 | 构建前对完整 Git 跟踪树取 SHA-256，并记录提交、Python 包、MSYS2 包、编译器/Inno 版本、语言文件哈希和构建命令。每个变体还保存生成的 `build_variant.py` 与 PyInstaller spec 摘要；构建结束检查受控源码未变。两个包嵌入 manifest，收据覆盖两 zip、两 installer、包内 exe/native DLL/manifest 和生成输入；独立 runner 先核对收据再自检。 | 本地用临时 Git 仓库与小型假包验证机制；实际 CI 构建尚未执行。 |
| F03 | 构建说明首屏与独立索引明确当前本地整改包的路径、字节、SHA-256 和待验收状态，旧 `dist-onedir` zip 标为历史；未来 CI 候选使用 `run-<id>` 独立目录。 | 两个本地 zip 摘要已复算。 |
| F04 | 基准圆链使用成员世界坐标；静态体设置 `FLAG_STATIC`；JSON 标 `fixture_version: 2`，旧数据保留。 | 定向测试与 5 轮×100 次重测已运行，见下节。 |
| 11.3 | 增加 Python/native 各自独立推进的 100 tick 轨迹对照，检查碰撞对、历史和位置/速度累积差异。 | 本机定向测试 1 passed；原有逐 tick Python 主导对照仍保留。 |
| 11.2 | 原生 build ID 输入摘要加入私有头、生成模板、CMake 文件和生效的 C++ 编译标志。 | 修改私有头后重新配置会生成不同 build ID；本机 Release 重建与 CTest 通过。 |
| F05 | 独立 runner 与人工桌面/长时资源验收流程继续保留，晋级记录要求每个变体的便携、安装/卸载、GUI、Python/native、正常退出和配置保留结果。 | 尚无远端 run、真实桌面人工记录，不标记发布完成。 |

人工验收 JSON 的最小结构：`candidate_run_id`、`commit`、`artifacts`（四个文件名到各自 SHA-256）、`desktop_checks`（`webm-chat` 和 `webm` 两项，各含 `portable`、`installer_install`、`installer_uninstall`、`gui`、`python`、`native`、`normal_exit`、`config_retained` 的布尔结果）、`machine`、`evidence`。其中 `evidence` 写日志或截图记录位置；实际填写和签认须由完成验收的人进行。发布输入还需收据 SHA-256 与原 run/artifact ID。

```json
{
  "candidate_run_id": 123456,
  "commit": "<tag commit SHA-1>",
  "artifacts": {
    "dsh-pet-standalone-webm-chat-portable.zip": "<SHA-256>",
    "dsh-pet-standalone-webm-chat-setup.exe": "<SHA-256>",
    "dsh-pet-standalone-webm-portable.zip": "<SHA-256>",
    "dsh-pet-standalone-webm-setup.exe": "<SHA-256>"
  },
  "desktop_checks": {
    "webm-chat": {"portable": true, "installer_install": true, "installer_uninstall": true, "gui": true, "python": true, "native": true, "normal_exit": true, "config_retained": true},
    "webm": {"portable": true, "installer_install": true, "installer_uninstall": true, "gui": true, "python": true, "native": true, "normal_exit": true, "config_retained": true}
  },
  "machine": "<Windows version / display / no Conda or MSYS2>",
  "evidence": "<test log and screenshots location, run duration and process tree notes>"
}
```

## 二、修改文件说明

当前快照无 `.git`，不能把本轮净改动冒充 `git diff --numstat`。新增文件逐个列出；既有文件描述实际本轮编辑，行数可在有本地 Git 基线的完整项目中精确统计。

为了便于接手，已在独立的上游对照工作树按公开提交 `5a2025111de915413635b096e7091e3db9a0193b` 生成**逐文件累计增删行数**。完整补丁 `E:\CODE\2026-09-24\li\outputs\collision-candidate-promotion-against-5a20251-2026-09-26-final.patch` 和 numstat `E:\CODE\2026-09-24\li\outputs\collision-candidate-promotion-numstat-2026-09-26.txt` 在独立、干净的上游稀疏检出中通过 `git apply --check`。复审原文本身由另一轮只读审查新增，不能算本轮实现；这些累计差异也包含 9 月 24 日的先前整改，**不是本次对话的净修改量**。未对第三方上游创建提交。

| 文件 | 改动与原因 |
| --- | --- |
| `scripts/candidate_release.py`（新增） | 预建输入快照、构建后漂移检查、双变体收据、zip 内部哈希及桌面验收校验。 |
| `tests/test_candidate_release.py`（新增） | 验证源漂移、脏工作树、产物缺失/篡改、验收提交与变体缺失、完整小型候选归档。 |
| `.github/workflows/build-windows.yml` | 只构建候选，两个变体跳过默认覆盖式 zip，接入快照/收据/测试报告/独立 runner；加 Release 原生测试负控。 |
| `.github/workflows/promote-windows-release.yml`（新增） | 只从既有成功 run 下载指定 artifact 晋级，草稿附件复核后发布；不重新安装依赖或构建。 |
| `scripts/bench_collision_backends.py`、`tests/test_bench_collision_backends.py`（测试新增） | 修正圆链世界坐标和静态标志，固定场景预期并记录 fixture 版本。 |
| `tests/test_collision_native.py` | 增加两套状态分别推进的 100 tick 轨迹对照，补足已有单步参考检查。 |
| `C++-Python/CMakeLists.txt`、`tests/test_collision_build_id.py`（测试新增） | 扩大构建 ID 的受控输入范围，并验证私有头修改确实改变 ID。 |
| `C++-Python/构建说明/README.md`、`候选包索引-2026-09-26.md`（索引新增） | 防止默认旧 zip 被误作整改候选。 |
| `docs/INDEX.md`、`docs/PR-REPORT-COLLISION-REMEDIATION-2026-09-24.md`、`docs/superpowers/plans/2026-09-26-candidate-promotion.md`（计划新增） | 登记入口，给历史圆链数据加限制说明，并记录本轮实现步骤。 |

## 三、性能分析

环境：本机 Windows，Python 3.13.15，最终重建的原生 DLL SHA-256 `89f93b9dce2ff556e89063b95d56253ed007b18458ad2141da70268e26d7367e`，build ID `collision-core/2.0+99648e8ce8d66563-GNU16.2.0-Release`。命令：`D:\python\miniconda\envs\py13\python.exe scripts/bench_collision_backends.py --rounds 5 --samples 100 --output E:\CODE\2026-09-24\li\outputs\collision-benchmark-fixture-v2-buildid-2026-09-26.json`；15 个场景、每种后端各 500 次交错采样。最终 JSON SHA-256 为 `a158dc974bda8c5f90c25a4d5d532fb1616a10f15270c200db47d4d70e3f5014`。先前同日 v2 首测 `collision-benchmark-fixture-v2-2026-09-26.json` 也保留，使用旧 DLL；下表使用最终重建数据。旧 `collision-benchmark-2026-09-24.json` 未覆盖，其 circles/static 属 fixture v1。两次测量不同日，耗时差异同时含机器状态变化，不作严格加速比归因。

| 场景/成员 | 旧碰撞对→新碰撞对 | 旧 Python/native 中位 µs | 新 Python/native 中位 µs |
| --- | ---: | ---: | ---: |
| circles / 3 | 3→3 | 141.5 / 49.55 | 125.95 / 48.7 |
| circles / 10 | 39→31 | 1636.0 / 303.9 | 1257.55 / 282.0 |
| circles / 30 | 330→189 | 13143.35 / 3026.25 | 7748.1 / 2636.5 |
| static / 3 | 3→3 | 87.3 / 41.8 | 90.1 / 42.65 |
| static / 10 | 39→39 | 903.25 / 273.95 | 892.15 / 271.0 |
| static / 30 | 284→284 | 6636.95 / 2875.65 | 6502.65 / 2830.95 |

几何 sanity check：旧圆链 3 成员的前 3 个接触点全为 `(0,0)`；修正后依次为 `(9,0)`、`(18,0)`、`(27,0)`。静态场景的碰撞对和接触点不变，但首成员现在确实进入静态体恢复系数分支。稀疏/稠密 fixture 未修改。Python 继续作为默认后端。

构建收据只在 CI 打包时扫描磁盘、查询包版本与制作归档；生产每 tick 路径没有新增调用、网络、系统线程或持久内存。哈希按 1 MiB 流式读取，installer 复制使用流式 `copyfile`；两份 WebM 包各增加一次 zip 生成和 CRC 校验，远端真实耗时与峰值内存尚未测量。基准修正只影响测试脚本，不改变应用运行期性能。

## 四、实机运行记录

- 本机测试以 `D:\python\miniconda\envs\py13\python.exe` 执行。先观察圆链与静态旗标测试分别失败，再修正后 `tests/test_bench_collision_backends.py` **2 passed**。
- 收据测试先因模块缺失失败，再经实现后运行 `tests/test_candidate_release.py` **5 passed**；其中使用临时 Git 仓库和假 exe/DLL/installer，验证生成输入被篡改会失败，不能代替真正打包。
- 原生独立轨迹 `tests/test_collision_native.py::test_native_and_python_independent_trajectories_do_not_drift`：**1 passed**，分别推进两套状态 100 tick。
- 构建 ID 集成测试先复现私有头变化但 ID 不变；修正后 `tests/test_collision_build_id.py` **1 passed**。随后执行 `scripts/build_native.ps1 -UcrtBin E:\msys2\ucrt64\bin`，Release CMake 编译与 CTest 1/1 通过，新 DLL 已暂存到源码 `_bin`。现有本地 zip 保持旧字节，未静默重打。
- `python -m ruff check scripts/candidate_release.py scripts/bench_collision_backends.py tests/test_candidate_release.py tests/test_bench_collision_backends.py`：通过。Windows 工作流与晋级工作流使用隔离目录中的 PyYAML 解析：两个文件分别有 2、1 个 job，语法通过。
- `QT_QPA_PLATFORM=offscreen` 下首次全量执行 `D:\python\miniconda\envs\py13\python.exe -m pytest -q --basetemp E:\CODE\2026-09-24\li\work\pytest-followup-temp`：**2962 passed、11 skipped**，200.88 秒。随后加入 build ID 与轨迹测试并重建原生 DLL。第二次使用更长的 `pytest-followup-final-temp` 临时路径：**1 failed、2966 passed、11 skipped**，唯一失败为既有 `test_image_directory_picker_opens_right_drawer_with_three_column_masonry` 在 Windows 过长路径上写入长文件名时 `FileNotFoundError`，与本轮代码路径无关。改用已确认位于工作区且原先不存在的短路径 `E:\CODE\pf0926b` 重跑最终全量：**2967 passed、11 skipped**，180.30 秒。
- 原生 Release 测试：`PET_CORE_TEST_INJECT_FAILURE=1` 时 CTest 1/1 失败、退出码 8；清除后 1/1 通过、退出码 0。本轮没有重新打真实安装包或启动 GUI。真正的远端 CI/无开发工具 Windows 桌面仍需执行并记录 run URL、artifact ID、收据与验收 JSON，不能由本地测试推断通过。

**交付状态：** F01–F04 本地代码与文档已实现并进入验证；F05 和首次远端候选晋级实跑待完成。原 2026-09-24 本地候选仍可用于整改功能复核，但不含本轮新 CI 脚本的构建收据，正式发布必须由新流程生成候选。
