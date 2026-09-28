# Collision Native Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first collision-computation stage of `C++-Python/项目重构说明.md` while preserving the current Python behavior and a safe fallback.

**Architecture:** Keep Python responsible for IDs, IPC, GUI and events. Pack one collision tick into fixed C ABI arrays; C++20 computes pair detection, impulses and iterative separation. Select `python`, `native`, or `auto` through one Python backend facade. The existing Python solver remains the reference.

**Tech Stack:** Python 3.13, PySide6, ctypes, C++20, UCRT64 CMake/Ninja/CTest, pytest, Ruff.

**Spec:** [项目重构说明](../../../C++-Python/项目重构说明.md)

## Global Constraints

- Do not link Qt, embed Python or pass C++/Qt objects across the ABI.
- Preserve pair ordering, static and infinite mass rules, flags, overlap history, swept contacts and degenerate geometry.
- Forced native mode must fail when loading or ABI checks fail. Auto mode may fall back with a diagnostic.
- Native CI must prove the C++ path actually ran.
- Keep generated binaries out of source control; build in `build-native/ucrt64-release`.

## Review Focus

- Empty arrays and output capacity edges must return defined status without writing past buffers.
- Coincident centers and circle chains must agree with the Python reference.
- Swept contacts and ignored pairs must preserve event ordering.
- Repeated calls must not retain native state or leak native allocations.
- Frozen bundles must load from their own package directory without the developer PATH.

## Tasks

### Task 1: P0 baseline and dependency restoration

- [x] Record Python 3.13 import, focused tests and full-suite baseline.
- [x] Restore curated runtime and development dependency lists from imports and CI.
- [x] Add Python 3.13 to the existing CI test matrix.

### Task 2: P1 stable backend interface

- [x] Write tests for Python facade parity, backend selection and strict native failure.
- [x] Extract the existing solver under a reference name without changing its algorithm.
- [x] Route the application call through the backend facade.

### Task 3: P2 C ABI and native solver

- [x] Write CTest cases for ABI, empty input, capacity errors and representative collisions.
- [x] Add fixed-layout C ABI and C++20 batch solver with exception containment.
- [x] Add ctypes loader with structure-size and ABI checks and explicit signatures.
- [x] Add Python/native differential tests for geometry, flags, history, swept and randomized cases.
- [x] Add a build script and required native CI job.

### Task 4: Performance and release integration

- [x] Benchmark end-to-end Python and native calls for 1, 3, 10 and 30 members, cold and warm.
- [x] Keep Python as default if measured native gains do not exceed noise.
- [x] Add audited DLL and transitive runtime collection to onedir packaging.
- [x] Run applicable verification, record remaining desktop and clean-machine checks.
