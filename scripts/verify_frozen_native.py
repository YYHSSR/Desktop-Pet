"""Exercise native collision through the frozen executable, not source Python."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def verify(exe: Path) -> None:
    exe = exe.resolve()
    expected_dll = (exe.parent / "_internal" / "pet" / "native" / "_bin" / "pet_core.dll").resolve()
    with tempfile.TemporaryDirectory(prefix="pet-frozen-native-") as raw_temp:
        temp = Path(raw_temp)
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PET_CORE_DLL", None)
        env["APPDATA"] = str(temp / "AppData")
        env["LOCALAPPDATA"] = str(temp / "LocalAppData")
        env["TEMP"] = str(temp)
        env["TMP"] = str(temp)
        windows = Path(env.get("SystemRoot", r"C:\Windows"))
        env["PATH"] = os.pathsep.join((str(windows / "System32"), str(windows)))
        (temp / "AppData").mkdir()
        (temp / "LocalAppData").mkdir()

        def run(name: str, mode: str, override: Path | None = None) -> tuple[int, dict]:
            result_path = temp / f"{name}.json"
            case_env = env.copy()
            if override is not None:
                case_env["PET_CORE_DLL"] = str(override)
            completed = subprocess.run(
                [str(exe), "--native-self-test", str(result_path),
                 "--native-self-test-mode", mode],
                cwd=temp, env=case_env, capture_output=True, timeout=60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            if not result_path.is_file():
                raise AssertionError(f"{name}: frozen executable wrote no result; exit={completed.returncode}")
            result = json.loads(result_path.read_text(encoding="utf-8"))
            return completed.returncode, result

        code, native = run("native", "native")
        if code != 0 or not native["ok"]:
            raise AssertionError(f"frozen native failed: {native}")
        if native["actual_backend"] != "native" or native["native_calls"] != 1:
            raise AssertionError(f"native call not observed: {native}")
        if native["abi_version"] != 2 or not native["build_id"]:
            raise AssertionError(f"native ABI/build ID invalid: {native}")
        if Path(native["dll_path"]).resolve() != expected_dll:
            raise AssertionError(f"frozen DLL path escaped bundle: {native}")

        missing = temp / "missing.dll"
        code, forced_missing = run("forced-missing", "native", missing)
        if code == 0 or forced_missing["ok"] or forced_missing["native_calls"] != 0:
            raise AssertionError(f"forced missing DLL did not fail: {forced_missing}")
        code, fallback = run("auto-fallback", "auto", missing)
        if code != 0 or not fallback["ok"] or fallback["actual_backend"] != "python" or fallback["native_calls"] != 0:
            raise AssertionError(f"auto fallback failed: {fallback}")

        if os.name == "nt":
            code, wrong_abi = run("wrong-abi", "native", windows / "System32" / "kernel32.dll")
            if code == 0 or wrong_abi["ok"] or wrong_abi["native_calls"] != 0:
                raise AssertionError(f"wrong ABI DLL did not fail: {wrong_abi}")

        print(json.dumps({"status": "FROZEN_NATIVE_OK", "exe": str(exe),
                          "dll": str(expected_dll), "abi": native["abi_version"],
                          "build_id": native["build_id"], "native_calls": native["native_calls"]},
                         ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    args = parser.parse_args()
    verify(args.exe)


if __name__ == "__main__":
    main()
