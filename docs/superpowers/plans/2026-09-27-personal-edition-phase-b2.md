# Personal Edition Phase B2: Cost and Balance Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove cost and balance UI, persistence and background work without disrupting generic chat, Cursor or the remaining island features.

**Architecture:** Migrate old config at load/save, then remove menu/settings paths, then disconnect AppShell, Agent link and dynamic-island producers before deleting their dedicated modules. Use existing public config, menu and Qt seams for red-green tests; preserve historical user files until the later cleanup batch.

**Tech Stack:** Python 3.13, PySide6, pytest, Ruff, JSON config/menu templates.

**Spec:** [2026-09-27-personal-edition-phase-b-design.md](../specs/2026-09-27-personal-edition-phase-b-design.md)

## Global Constraints



## Review Focus

1. Legacy `agent_cost_enabled=true` and nonzero refresh minutes: loading must not start a query or timer (Tasks 1 and 3 tests).
2. Legacy `dynamic_island.info_mode=balance_tier|balance`: both normalize to `time`, while all other island fields stay unchanged (Task 1 test).
3. Saved custom menu with retired `agent_cost`/`balance` and a retained aliased action: prune only retired nodes (Task 2 test).
4. Cursor completion after cost tracker removal: still emits its ordinary completion path with no balance HTTP request (Task 4 test).
5. Multiple app instances exit with no balance worker/timer leak; cached `balance_cache.json` is left untouched (Task 3 test).

---

## File map

| Responsibility | Files |
| --- | --- |
| Config normalization and settings | `pet/config.py`, `pet/config_domains.py`, `pet/modern_settings_dialog.py`, `pet/settings_pet_controls.py`, `pet/settings_interaction.py`, `pet/settings_widgets.py` only if its shared UI changes; `tests/test_config_schema.py`, `tests/test_config_domains.py`, `tests/test_settings_interaction_tabs.py` |
| Menus and window callbacks | `pet/menu_templates/*.json`, `pet/context_menus/registry.py`, `pet/context_menus/shared.py`, `pet/context_menus/legacy.py`, `pet/window.py`, `pet/app.py`; `tests/test_menu_layout.py`, `tests/test_desktop_pet_features.py` |
| App/Agent/island lifecycle | `pet/app.py`, `pet/agent_link.py`, `pet/dynamic_island.py`, `pet/window_alerts.py` if event mapping is obsolete, `pet/agent_cost.py`, `pet/balance.py`; `tests/test_agent_link.py`, `tests/test_island_shell_wiring.py`, `tests/test_dynamic_island_revamp.py` |
| Dedicated removed-feature tests | `tests/test_agent_cost.py`, `tests/test_balance.py`, `tests/test_dynamic_island_balance_tier_time.py`, plus narrow tests in shared files; replace them with behavioral retirement tests before deleting obsolete assertions |
| Evidence | `docs/PR-REPORT-PERSONAL-PHASE-B2-2026-09-27.md`, `docs/INDEX.md`, `.scratch/personal-edition/HANDOFF.md` |

### Task 1: Make legacy settings inert

**Interfaces:** `Config` load/reload/save returns data without retired top-level keys; `_clean_dynamic_island_data(value) -> dict` maps the two retired modes to `time` and retains unrelated fields. `Config.set()` cannot reactivate a retired key.

- [ ] Add red cases in `tests/test_config_schema.py` and `tests/test_config_domains.py`: old config with all seven retired keys (including `true`, invalid text and nonzero minutes) loads without activating them; saving and reloading is idempotent; both old island modes become `time`; ordinary island options, chat Provider secrets and application shortcuts are unchanged.
- [ ] Run only those cases with a fresh external `--basetemp`; record the red result.
- [ ] Remove retired defaults, reload whitelist entries and normalizer branches in `pet/config.py`; delete obsolete domain fields if present. Normalize old island modes to `time` and drop retired top-level keys from in-memory data before normal save. Ensure `Config.set()` cannot persist a retired key, while unrelated unknown keys retain the existing policy.
- [ ] Rerun focused config tests green and related settings persistence tests.

### Task 2: Remove menu and settings UI

**Interfaces:** `MENU_ACTIONS.ids` excludes `agent_cost` and `balance`; all menu variants and settings search omit their controls. `tools_help` remains while `harness` exists.

- [ ] Add red QMenu/settings cases in `tests/test_menu_layout.py`, `tests/test_desktop_pet_features.py` and `tests/test_settings_interaction_tabs.py`: default, legacy, custom and tray menus omit cost/balance; retained alias/icon and order survive; settings search has no cost/balance rows; saving unrelated click interactions does not recreate retired keys.
- [ ] Run focused cases and capture red output.
- [ ] Remove the two IDs from three menu templates, `registry.py`, `shared.py`, `legacy.py` and `app.py` tray path. Remove corresponding controls, rows, search metadata and save wiring from `modern_settings_dialog.py`, `settings_pet_controls.py` and `settings_interaction.py`. Preserve the retained `harness` menu action.
- [ ] Rerun focused menu/settings cases green; inspect actual light/dark menu and settings at standard and narrow widths, keyboard focus and disabled states. Record screenshots only when a new candidate is running.

### Task 3: Disconnect app and island balance work

**Interfaces:** `AppShell` has no balance timer, balance network worker or balance cache writer. `PetWindow` has no balance callback/click action. `DynamicIsland` still renders time and generic events but no balance card/mode.

- [ ] Add red tests in `tests/test_island_shell_wiring.py`, `tests/test_dynamic_island_revamp.py` and a window interaction test: startup with old true refresh settings and island expansion make zero balance HTTP calls, create no `pet-balance*` thread/timer, do not touch an existing `balance_cache.json`; closing two instances leaves no balance worker; time/generic island behavior remains.
- [ ] Run focused cases red. Use a blocked network sentinel instead of a real endpoint; use Qt event synchronization rather than fixed sleeps.
- [ ] Remove `_apply_balance_timer`, balance bridge/cache/worker and quiet/explicit query paths from `pet/app.py`; remove `on_show_balance` and click branch from `pet/window.py`; remove balance-only island text, card and peak-timer paths from `pet/dynamic_island.py`. Keep generic event and time paths.
- [ ] Rerun focused lifecycle/island tests green, including process-exit coverage. Record idle CPU/memory and thread counts before/after with conditions for the report.

### Task 4: Remove Agent cost queries and dedicated modules

**Interfaces:** Existing Agent/Cursor start and completion signals keep their non-cost behavior; no remaining runtime module imports `pet.balance` or `pet.agent_cost`.

- [ ] Add red cases in `tests/test_agent_link.py` and `tests/test_agent_link_threads.py`: Cursor and retained Agent completion paths still report completion but never request a balance baseline/final amount; cancellation/error is not converted to completion; the cost worker is absent after close.
- [ ] Run focused cases red, then remove cost tracker connections and queries in `pet/agent_link.py` while keeping its common protocol and Cursor logic. Remove zero-call `pet/agent_cost.py` and `pet/balance.py`, associated tests, stale imports and packaging entries only after searching all executable references.
- [ ] Rerun Agent, Cursor, island and app lifecycle families green. Verify no runtime path imports the removed modules or writes balance cache; historical docs and `balance_cache.json` are left intact.

### Task 5: Verify and hand off B2

**Interfaces:** Batch C receives no cost/balance dependency and a still-working Cursor/generic chat path.

- [ ] Run Ruff on `pet tests scripts`, full py13 pytest with `QT_QPA_PLATFORM=offscreen` and a new external `--basetemp`, and the affected real Qt/Agent timing family three times under load. Run native CTest only if native/build code changed. Do not treat an unrun platform as passed.
- [ ] Build a new local personal candidate, record absolute EXE path/hash, exit old instances and run it. Check menu, settings search, tray, island, Cursor, idle threads/CPU/memory and no retired network request; keep release workflows untouched and do not publish.
- [ ] Write `docs/PR-REPORT-PERSONAL-PHASE-B2-2026-09-27.md` with per-file changes, measured performance, real-host behavior, explicit limitations and rollback. Register in `docs/INDEX.md`, update handoff, and run `tests/test_pr_report_discipline.py`. Use archived baseline/file hashes rather than Git claims.

## Execution handoff

Use the already selected native execution method after user approval. Each task needs a visible red-green cycle and a reviewable result. Stop the removal sequence if a preserved consumer still depends on a proposed deletion; resolve that dependency before deleting the module.
