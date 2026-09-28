# Candidate promotion and benchmark correction implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task. Steps use checkbox syntax.

**Goal:** Make Windows releases promote exactly the tested candidate bytes, record complete build inputs and output hashes, identify the current local candidate, and correct misleading benchmark fixtures.

**Architecture:** A prebuild source and tool snapshot is checked again after both WebM builds. One receipt records both zips, both installers, both executables and native DLLs. The clean runner validates it, and a separate manual workflow verifies a digest-bound desktop acceptance record before publishing the downloaded artifacts unchanged. Benchmark geometry is corrected and historic data stays intact.

**Tech Stack:** Python 3.13, PowerShell, GitHub Actions, PyInstaller, CMake, pytest.

**Spec:** [2026-09-26 review](../../../C++-Python/构建说明/项目整改复审与后续改进建议-2026-09-26.md).

## Global constraints

- Keep Python as the default collision backend.
- Preserve old candidate archives and historic benchmark JSON.
- Do not publish to the third-party upstream repository.
- Treat remote CI and real desktop acceptance as pending until executed and recorded.

## Review focus

- Wrong candidate run or tag commit must fail promotion.
- Expired or absent artifact must fail promotion.
- Any changed or missing zip/setup digest must fail receipt or acceptance validation.
- A source file changed during build must fail finalization.
- Circle geometry and static flags must match the advertised benchmark topology.

---

### Task 1: Benchmark fixtures and evidence

**Files:** `scripts/bench_collision_backends.py`, `tests/test_bench_collision_backends.py`, new benchmark result and report.

- [x] Write fixture tests for world-coordinate circles, static flag, expected contact geometry; run and observe failures.
- [x] Correct fixture construction, label output with fixture version, and report contact sanity results; run focused tests.
- [x] Keep the 2026-09-24 JSON unchanged; run corrected measurements and report old/new limitations and timings.

### Task 2: Build and release receipts

**Files:** new `scripts/candidate_release.py`, `tests/test_candidate_release.py`, `.github/workflows/build-windows.yml`.

- [x] Write failing tests for pre/post source drift, complete output hashes and missing/tampered variant rejection.
- [x] Implement snapshot, finalize and verify commands; validate two zip/setup variants and embedded manifests.
- [x] Make CI snapshot before native/app builds, build with `-SkipZip`, finalize one unique candidate artifact, and verify it in the clean runner.

### Task 3: Immutable promotion

**Files:** new `.github/workflows/promote-windows-release.yml`, `scripts/candidate_release.py`, `tests/test_candidate_release.py`.

- [x] Write failing acceptance tests for wrong run/commit, missing variant, changed hash and invalid desktop result.
- [x] Implement acceptance validation; promotion checks successful original run, workflow identity, commit, artifact ID and expiration, then downloads and hashes the original files.
- [x] Publish exactly the four verified attachments with no rebuild; test validator and workflow structure locally.

### Task 4: Candidate entry and closeout

**Files:** `C++-Python/构建说明/README.md`, new candidate index, `docs/INDEX.md`, new PR report.

- [x] Recheck old and current archive digests and document ID, path, size, ABI, status and replacement relation.
- [x] Record commands, benchmark results, changed files, local runtime evidence and external acceptance still pending.
- [x] Run Ruff, full pytest and applicable native checks; review diffs without claiming remote execution.

Remote candidate build, clean runner, human desktop acceptance and actual promotion remain pending external execution. Completed checkboxes above mean local implementation and verification only.
