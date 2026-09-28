# Collision native review remediation plan

**Authority:** [R01–R11 review](../../../C++-Python/构建说明/项目完成情况审查与优化整改建议-2026-09-24.md). The review distinguishes proven defects from risks and missing environment acceptance. Preserve the Python default and reference solver. Implementation evidence is in the [delivery report](../../PR-REPORT-COLLISION-REMEDIATION-2026-09-24.md).

**Workspace constraint at planning time:** This source snapshot had no `.git` or root `AGENTS.md`. The authentic `AGENTS.md` was subsequently restored from the matching upstream candidate; `.git` remains absent. Do not overwrite the prior candidate zip. Keep scratch in `E:\CODE\2026-09-24\li\work` and user-facing evidence in `E:\CODE\2026-09-24\li\outputs`.

## Task 1 — R01 Release native gate

- Replace `assert` tests with explicit checks whose calls survive `NDEBUG`.
- Add invalid ABI, null pointer, circle range, pair index, capacity and error-buffer cases.
- Build Release, inject one wrong expectation in a temporary copy, prove CTest fails, restore, then prove it passes.

## Task 2 — R03 frozen executable self-test

- Add an argument path in the frozen entry that skips GUI and writes structured JSON to a chosen file, using only bundled code and the default bundled DLL path.
- Cover forced native success, forced native with missing/incompatible DLL, and auto fallback in isolated extracted copies. Report ABI/build/call count and exit code.
- Retain existing source-side checks as preliminary checks. Verify no developer Python, source tree or `PET_CORE_DLL` is used by frozen self-test.

## Task 3 — R04/R09 native dependency provenance

- Stage a complete dependency closure in a temporary build-only directory; generate a manifest with names, hashes, architecture, direct imports and toolchain package versions.
- Replace `_bin` only after all checks succeed; package only manifest entries. Test stale DLL and missing dependency paths.
- Record exact Python, MSYS2 and build inputs for each candidate zip, and audit conda extension dependencies rather than trusting an unversioned fixed list.

## Task 4 — R05 auto fallback and hot-path resolution

- Cache default DLL path; cache auto load failures with an explicit reset on path/config change. Forced native still fails.
- Prove repeated missing-DLL calls do not reattempt each tick and live mode/path changes work. Rebench fixed costs.

## Task 5 — R06/R07 ABI contract

- Define finite numeric, integer/count and iteration limits in the public contract. Reject invalid input before writes; preserve existing nonpositive-mass semantics.
- Validate Python integers before ctypes conversion. Expose/check offsets or a layout fingerprint, and replace the constant build ID with reproducible build provenance.
- Test malformed native inputs, output sentinels, ABI and layout mismatches.

## Task 6 — R08/R10 differential and benchmark evidence

- Extend multi-tick, circles, history, static, mass, 10/30 member and ID ordering tests. Fix parity differences demonstrated by tests.
- Rename ambiguous first-call timing or use fresh processes; preserve raw samples, metadata, pack/solve/unpack detail and backend order controls.

## Task 7 — R02/R11 documentation and acceptance

- Locate an authentic Git source and `AGENTS.md` if available; never synthesize them. Run the CI command unchanged only when the complete source exists; otherwise document the exact blocked test and provenance gap.
- Repair moved local documentation links, path/unit statements and add a current status index. Validate local links.
- Rebuild and test the frozen package; record desktop and clean-Windows acceptance separately. Do not mark clean-machine tests passed without that environment.

## Final verification

- Fresh Release CTest with negative-control evidence, Python/native targeted suites, full pytest, Ruff, package build, frozen self-test, zip integrity and hash.
- Compare each review item R01–R11 to evidence, report remaining external-state gates explicitly.
