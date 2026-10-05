"""Load the packaged native collision DLL from its final onedir location."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pet import collision
from pet.native.loader import native_call_count, solve_native


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal", type=Path, required=True)
    args = parser.parse_args()
    directory = args.internal / "pet" / "native" / "_bin"
    dll = directory / "pet_core.dll"
    if not dll.is_file():
        raise SystemExit(f"native DLL missing from onedir: {dll}")
    os.environ["PET_CORE_DLL"] = str(dll.resolve())
    members = [
        collision.MemberState("a", 0, 0, 50, 50, vx=100),
        collision.MemberState("b", 70, 0, 50, 50, vx=-100),
    ]
    expected = collision.solve_multi_body_collision_python(members)
    actual = solve_native(members)
    if native_call_count() != 1 or len(actual[0]) != len(expected[0]) or \
            abs(actual[0][0].j - expected[0][0].j) > 1e-7:
        raise SystemExit("native ABI smoke mismatch")
    print(f"NATIVE_BUNDLE_OK {dll}")


if __name__ == "__main__":
    main()
