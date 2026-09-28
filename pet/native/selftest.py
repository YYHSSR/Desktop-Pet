"""Self-test the frozen collision wrapper and its bundled native DLL."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .. import collision
from . import loader


def run_self_test(output_path: Path, *, mode: str = "native") -> int:
    """Write a machine-readable result without initializing QApplication."""
    output_path = Path(output_path)
    path = Path(os.environ.get("PET_CORE_DLL") or loader._default_path()).resolve()
    result = {
        "schema": 1,
        "ok": False,
        "requested_mode": mode,
        "actual_backend": None,
        "dll_path": str(path),
        "abi_version": None,
        "build_id": None,
        "native_calls": 0,
        "pair_count": None,
        "impulse": None,
        "error": None,
    }
    before = loader.native_call_count()
    old_mode = os.environ.get("PET_COLLISION_BACKEND")
    try:
        if mode not in {"python", "native", "auto"}:
            raise ValueError(f"invalid self-test mode: {mode}")
        os.environ["PET_COLLISION_BACKEND"] = mode
        members = [
            collision.MemberState("a", 0, 0, 50, 50, vx=100),
            collision.MemberState("b", 70, 0, 50, 50, vx=-100),
        ]
        expected = collision.solve_multi_body_collision_python(members)
        actual = collision.solve_multi_body_collision(members)
        calls = loader.native_call_count() - before
        backend = "native" if calls else "python"
        if mode == "native" and calls != 1:
            raise RuntimeError("forced native self-test did not call the C ABI")
        if len(actual[0]) != len(expected[0]) or len(actual[0]) != 1 or \
                abs(actual[0][0].j - expected[0][0].j) > 1e-7:
            raise RuntimeError("collision result differs from Python reference")
        result.update(actual_backend=backend, native_calls=calls,
                      pair_count=len(actual[0]), impulse=actual[0][0].j, ok=True)
        if calls:
            dll = loader._load(str(path))
            result["abi_version"] = dll.pet_core_abi_version()
            result["build_id"] = dll.pet_core_build_id().decode("utf-8", "replace")
    except Exception as exc:
        result["native_calls"] = loader.native_call_count() - before
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if old_mode is None:
            os.environ.pop("PET_COLLISION_BACKEND", None)
        else:
            os.environ["PET_COLLISION_BACKEND"] = old_mode
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["ok"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe the bundled collision backend")
    parser.add_argument("--native-self-test", type=Path, required=True, metavar="JSON_PATH")
    parser.add_argument("--native-self-test-mode", choices=("native", "auto", "python"), default="native")
    args = parser.parse_args(argv)
    return run_self_test(args.native_self_test, mode=args.native_self_test_mode)


if __name__ == "__main__":
    raise SystemExit(main())
