# Collision native stage: baseline and validation (2026-09-24)

This records the first collision stage in [项目重构说明](../C++-Python/项目重构说明.md). The Python solver remains the default. Set `PET_COLLISION_BACKEND=native` to require the C++ DLL or `auto` to try it and fall back on load/ABI failure.

## Scope

- `solve_multi_body_collision_python` is the unchanged reference implementation.
- The C++20 DLL handles pair geometry, impulse calculation, swept contacts and iterative separation in one batch. Python owns IDs, overlap history serialization, IPC, GUI and event dispatch.
- The C ABI uses fixed-width fields, caller-owned buffers, explicit capacities, status codes, ABI version and structure-size checks. The DLL exports no C++ or Qt objects.
- `scripts/build_native.ps1` builds, runs CTest and stages only the audited runtime DLL closure. `scripts/build_onedir.ps1` collects those DLLs explicitly and verifies the packaged ABI before GUI smoke tests.

## Test baseline and behavior

- Before changes, Python 3.13.15 ran `tests/test_physics.py tests/test_collision.py`: **46 passed**.
- First full run: **2916 passed, 11 skipped, 4 failed**. Two failures came from the then-missing `requirements.txt` and now pass. One test requires a missing root `AGENTS.md`; this checkout has no `.git` metadata to recover it. One image picker test hit a Windows long-path error under the default pytest temporary directory; using a shorter `--basetemp` resolved it.
- Earlier full run with a short temporary path and the parametrized documentation test deselected: **2926 passed, 11 skipped, 2 deselected** in 179.08 seconds. Only the `AGENTS.md` case actually lacks its source file; the `DEV-HANDOVER.md` case can run. After stabilizing the drag-coalescing test's synthetic window origin, the final full run deselecting only the missing-file case: **2929 passed, 10 skipped, 1 deselected** in 210.03 seconds.
- Final forced-native collision/physics/window/IPC suite: **149 passed, 1 skipped**; CTest **1/1 passed**. The native differential tests require actual native calls in this mode.
- `python -m ruff check pet tests` passed. `import pet.app` passed with the specified py13 interpreter.

## Performance analysis

Command: `D:\python\miniconda\envs\py13\python.exe -m scripts.bench_collision_backends --rounds 3 --samples 30`. Environment: Windows 11, Python 3.13.15, UCRT64 GCC 16.2.0 Release DLL, one process. Times are median microseconds per public `collision.solve_multi_body_collision` call, including backend selection and ctypes packing/call/unpacking. Each scenario uses 3 rounds of 30 calls; cold calls are recorded separately by the script. The first set uses separated bodies, the second has dense overlaps.

| Members | Separated Python/native (µs) | Dense Python/native (µs) |
| ---: | ---: | ---: |
| 1 | 3.00 / 98.80 | 3.00 / 97.05 |
| 3 | 6.60 / 108.50 | 75.00 / 121.60 |
| 10 | 44.85 / 199.30 | 877.50 / 308.55 |
| 30 | 404.75 / 1640.20 | 6412.70 / 2484.00 |

The native backend helps dense 10/30-member scenes, but loses for the common small and separated cases. It stays opt-in. Calls perform no disk or network access after DLL loading and create no worker thread; the DLL does allocate temporary vectors per call. Memory growth and whole-process CPU should still be measured during a real desktop session before changing the default.

## Release and desktop limits

The staged DLL directly imports `libgcc_s_seh-1.dll` and `libstdc++-6.dll`; recursive audit also collects `libwinpthread-1.dll`. The source package loader uses its own `_bin` directory. The `webm-chat` PyInstaller onedir build completed with Python 3.13 and the UCRT64 native build. Bundle checks passed for Qt (Shiboken, QtCore, QtGui, QtWidgets), Chinese resource encoding, native ABI/collision, and the TTS module set (25 required, 1702 frozen). The package includes the four native DLLs and eight audited conda Python extension dependencies. Qt and native ABI checks also passed in a child process with PATH limited to `C:\Windows\System32;C:\Windows`. With that restricted PATH and isolated APPDATA/LOCALAPPDATA/TEMP, the packaged GUI executable remained running for a 10-second hidden startup smoke, then was stopped. A portable zip was produced; SHA-256 is `377368865E782F32D64ECB1CEB73D889EEE5F0B7F09A6F9454E2EAAB03788E41`, and an archive listing confirmed the executable and key native/runtime DLLs. PyInstaller's analysis still reports the conda DLLs as unresolved at analysis time; the packaging script copies and checks them after collection.

A clean Windows machine without MSYS2/conda, GUI interactions, and long-running memory checks remain unverified here. The PATH-restricted checks are useful evidence but do not replace clean-machine or interactive desktop tests. No performance or compatibility claim is made for those environments.

The checkout contains no `.git` directory, so no source commit can be verified or created. Restore the original Git repository before treating this as a releasable branch.
