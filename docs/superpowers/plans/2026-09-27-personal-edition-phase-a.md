# Personal Edition Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a restorable source/config baseline and an evidence-backed Chat/Work status capability matrix.

**Architecture:** Keep one-time backup and observation tools under `E:\CODX\desktop-pet\experiments`, separate from source and private backup files. Observe only the selected Windows ChatGPT window, then classify manually triggered trials. No product adapter is added in this phase.

**Tech Stack:** py13 Python, PowerShell 5.1 built-in Windows UI Automation, JSON, ZIP, SHA-256.

**Spec:** [2026-09-27-personal-edition-phase-a-design.md](../specs/2026-09-27-personal-edition-phase-a-design.md)

## Global Constraints

- Do not modify product code, ChatGPT, external hooks, or user configuration; do not send messages from the probe.
- Keep prompts, replies, credentials, query strings and raw UIA labels out of logs and reports.
- Use `E:\CODE\desktop-pet` as source and `E:\CODX\desktop-pet` for new artifacts. Do not move `tests/` or delete historical test trees.
- Bind by installed package, PID and window ownership; validate Chat and Work separately. Ambiguous endings remain `unknown`.
- No `.git` exists locally. Use archive hashes, and do not claim commits or upstream provenance.
- Use a fresh run ID: local `yyyyMMdd-HHmmss` plus eight lowercase UUID hex digits.

## Review Focus

1. Reparse point in a scanned tree: skip without following it (Task 1 fixture).
2. File changes during copy: fail verification (Task 1 fixture).
3. Existing output with different content: refuse overwrite (Task 1 fixture).
4. UIA label containing private text: output no raw label (Task 2 self-test).
5. Mode switch or window loss: never infer completion (Task 3 trial check).

---

### Task 1: Restorable baseline

**Files:** Create `E:\CODX\desktop-pet\experiments\phase-a-baseline\snapshot.py` and `test_snapshot.py`; output `E:\CODX\desktop-pet\baselines\phase-a-2026-09-27-RUN_ID\` with source ZIP, app-config copies and redacted `manifest.json`.

**Interface:** `snapshot.py --project-root PATH --appdata-root PATH --output-root PATH`; manifest records relative path, bytes and SHA-256 for each file, ZIP hash, skipped reparse points and final verification. Config input is limited to `config.json`/`config-*.json` in this app's `dsh-pet-standalone*` directories.

- [ ] Write fixture tests for the first three Review Focus cases, ZIP-member hash validation and exclusion of a sample secret from the manifest. Run `D:\python\miniconda\envs\py13\python.exe -B -m unittest discover -s E:\CODX\desktop-pet\experiments\phase-a-baseline -p test_snapshot.py -v`; confirm red before implementation.
- [ ] Implement the CLI: include root files and `.github`, `.agents`, `pet`, `tests`, `scripts`, `C++-Python`, `packaging`, `integrations`, `assets`, `docs`; skip Git, caches, `.scratch`, build/dist and prior review archives. Reject changed inputs and conflicting targets. Restrict backup ACL to this Windows user before copying config bytes.
- [ ] Rerun fixtures green; snapshot the real project and `%APPDATA%`. Reopen all copies and the ZIP to check every hash. Verify the 9/26 baseline separately, without overwriting it.

### Task 2: Narrow ChatGPT observer

**Files:** Create `E:\CODX\desktop-pet\experiments\chatgpt-windows-state-probe\inspect.ps1` and `README.md`; output `observations-RUN_ID.jsonl` in that directory.

**Interface:** `inspect.ps1 -Mode Chat|Work -OutputPath PATH -DurationSeconds INT`; `-SelfTest` checks redaction. Each record contains UTC time, package/version, PID, window identifier and allowlisted control-state signatures. Never output a raw UIA `Name` or document text.

- [ ] Load `UIAutomationClient`/`UIAutomationTypes`, identify the installed `OpenAI.Codex_*` package, its `ChatGPT.exe` PIDs and owned windows; record failures without guessing from title alone.
- [ ] Implement bounded observation of the selected window's controls. Use only type, AutomationId, class, enabled/offscreen state and allowlisted button booleans; emit typed `unavailable` on access failure and stop cleanly.
- [ ] Run `-SelfTest` with a synthetic private label, then a short idle capture. Check JSONL parses, omits the marker and raw labels, and leaves no observer process. Record idle CPU/memory and detection latency or a specific measurement limitation.

### Task 3: Real-mode trials

**Files:** Create `E:\CODX\desktop-pet\experiments\chatgpt-windows-state-probe\trial-runbook.md` and `capability-matrix.json`.

**Interface:** Each trial links mode, scenario and timestamp range to observation IDs. Matrix verdicts are `verified`, `unknown`, `unavailable` or `not_run` for start, complete, fail, cancel, disconnect and background visibility, separately for Chat and Work.

- [ ] Write the runbook: 10 normal start/end trials per mode, plus cancel, error, wait for input/approval, switch, minimize/restore, close and disconnect. The operator triggers actions; the probe only watches.
- [ ] Capture real trials with fresh run IDs. Record unreachable scenarios as `not_run` with reason; collect timing and resource numbers with conditions.
- [ ] Classify traces: only a repeatable distinct terminal signal qualifies as completion; timeout, wait, switch and closure remain unknown/disconnected. Verify every `verified` verdict links to evidence and per-mode counts are accurate.

### Task 4: Evidence and handoff

**Files:** Create `docs/PR-REPORT-PERSONAL-PHASE-A-2026-09-27.md`; update `docs/INDEX.md` and `.scratch/personal-edition/HANDOFF.md`.

- [ ] Recheck the ZIP, config copies, manifest and matrix. Record actual counts and any failure.
- [ ] Write the report using `docs/PR-REPORT-TEMPLATE.md`: file changes, measured observer overhead, real-host results, privacy/ACL check and remaining limitations. State clearly that product integration is not yet implemented.
- [ ] Register the report in the index and save the next breakpoint in the handoff. Run py13 `-B -m pytest -q -p no:cacheprovider --basetemp E:\CODX\desktop-pet\test-runs\RUN_ID\tmp tests/test_pr_report_discipline.py` with `PYTHONDONTWRITEBYTECODE=1`; record real output.

## Handoff

Use verified host capabilities to design the later product adapter. Menu cleanup may continue even if state access is unavailable. No Git commit is possible until a trustworthy local Git baseline exists.
