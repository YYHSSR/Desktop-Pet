# Personal Edition Phase B1: Update and Built-in Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove product update checks and bundled web shortcuts while preserving application shortcuts and local version metadata.

**Architecture:** Normalize the quick-launch list at the existing config seam; stop offering `default_browser`, whose implementation opens Google. Remove update and bundled-link actions at every menu/tray entry point, then delete the unreachable updater service. Existing custom layouts resolve through `resolve_menu_layout`, which already drops unregistered actions and empty submenus.

**Tech Stack:** Python 3.13, PySide6, pytest, Ruff, JSON menu templates.

**Spec:** [2026-09-27-personal-edition-phase-b-design.md](../specs/2026-09-27-personal-edition-phase-b-design.md)

## Global Constraints



## Review Focus

1. Old quick-launch data contains a renamed `default_browser` entry: remove by kind, not display name (Task 1 test).
2. Old quick-launch data mixes browser and explicit application entries: preserve the application order and paths (Task 1 test).
3. A saved custom menu contains retired actions with alias/icon overrides: omit only retired IDs, preserve retained overrides (Task 2 test).
4. `tools_help` still contains `harness`: do not remove that submenu in B1 (Task 2 test).
5. Startup and tray actions must not invoke the updater or bundled URL opener after retirement (Task 2 test).

---

## File map

| Responsibility | Files |
| --- | --- |
| Quick-launch data and UI | `pet/config.py`, `pet/config_domains.py`, `pet/context_menus/quick_launch.py`, `pet/settings_widgets.py`; tests in `tests/test_config_domains.py`, `tests/test_desktop_pet_features.py` |
| Default/custom/legacy menus | `pet/menu_templates/*.json`, `pet/context_menus/registry.py`, `pet/context_menus/shared.py`, `pet/context_menus/legacy.py`, `pet/menu_layout.py` only if existing resolution fails; tests in `tests/test_menu_layout.py` and `tests/test_desktop_pet_features.py` |
| Update lifecycle and packaging references | `pet/app.py`, `pet/window.py`, `pet/updater.py`, `tests/test_updater.py`; review `scripts/`, `packaging/`, `.github/` for runtime references, without changing public release workflows in this plan |
| Evidence | `docs/PR-REPORT-PERSONAL-PHASE-B1-2026-09-27.md`, `docs/INDEX.md`, `.scratch/personal-edition/HANDOFF.md` |

### Task 1: Remove the implicit browser shortcut

**Interfaces:** `pet.config._clean_quick_launch_apps(value) -> list[dict]` produces only explicit application entries. `QuickLaunchEditor.apps() -> list[dict]` remains the editor output; `launch_quick_app(item: dict) -> bool` opens explicit paths only.

- [ ] Add focused cases in `tests/test_config_domains.py` and `tests/test_desktop_pet_features.py`: `DEFAULT_QUICK_LAUNCH_APPS == []`; a renamed `default_browser` mixed with two path entries becomes exactly those two entries in order; an empty editor still offers adding an application; no “添加默认浏览器” action exists.
- [ ] Run those cases with py13 `-B -m pytest -q -p no:cacheprovider --basetemp E:\CODX\desktop-pet\test-runs\RUN_ID\tmp <test selectors>` and record the expected red failures.
- [ ] Change `pet/config.py` default and cleaner; remove the `default_browser` editor branch in `pet/settings_widgets.py` and the Google opening branch in `pet/context_menus/quick_launch.py`. Keep the existing application launcher and empty-list behavior.
- [ ] Rerun the same cases green, then the related quick-launch/config tests. Record the exact command and counts in the plan ledger.

### Task 2: Retire update and bundled-link paths

**Interfaces:** `MENU_ACTIONS.ids` excludes the four retired IDs; `resolve_menu_layout(raw_layout, *, registered_actions, available_actions)` keeps the retained nodes. Local version reads `pet.__version__` directly.

- [ ] Add red tests in `tests/test_menu_layout.py` and `tests/test_desktop_pet_features.py`: default/legacy/custom menus and tray omit the four IDs/labels; a custom layout with retired IDs plus aliased/icons `harness` and `quick_launch` retains the latter unchanged; `tools_help` remains while `harness` exists; a network sentinel sees zero updater calls during menu construction and app idle/startup.
- [ ] Run focused tests and capture failure before product edits.
- [ ] Remove the four actions from all three menu templates, `registry.py`, `shared.py`, `legacy.py` and `app.py` tray path. Remove `PetWindow.on_check_update`, update bridge/worker/check method in `app.py`, and `pet/updater.py` after searching all runtime imports. Keep `pet.__version__`; remove obsolete updater-specific tests only after the replacement behavior tests are green. Avoid changing public release workflow files here.
- [ ] Rerun focused menu, config, app lifecycle and version checks. Search executable source/packaging for `updater`, retired IDs and built-in URL constants; any remaining runtime reference must be resolved before finishing this task.

### Task 3: Verify and hand off B1

**Interfaces:** B2 starts with update/default-link runtime paths absent and a preserved `harness` entry.

- [ ] Run Ruff on `pet tests scripts`; run the full py13 pytest suite with a new external `--basetemp` and `QT_QPA_PLATFORM=offscreen`. Repeat the affected real Qt/lifecycle timing family three times under load as required by `AGENTS.md`; log command, exit code and counts. Native CTest is not required unless native sources or build logic change.
- [ ] Build a local candidate or record why B1 is being validated only as source pending the cumulative personal build; do not publish. Verify no updater/default URL request occurs in an idle real app, and note the actual executable path/hash if built.
- [ ] Write `docs/PR-REPORT-PERSONAL-PHASE-B1-2026-09-27.md` with 修改文件说明、性能分析、实机运行记录 and limitations; register it in `docs/INDEX.md`, update handoff and verify `tests/test_pr_report_discipline.py`. Without `.git`, use recorded file hashes/line counts instead of fabricated diff numbers.

## Execution handoff

Use the already selected native execution method after the user approves this plan. B2 can begin only after B1's focused and full suite pass; a failing gate is fixed or reported, never silently carried forward. Keep historical source/config backup from phase A intact.
