"""The native build ID must change when private code inputs change."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_private_header_change_updates_native_build_id(tmp_path):
    cmake = shutil.which("cmake")
    ninja = shutil.which("ninja")
    compiler = shutil.which("g++")
    if not all((cmake, ninja, compiler)):
        pytest.skip("CMake, Ninja and g++ are required for the build ID integration test")
    root = Path(__file__).resolve().parents[1] / "C++-Python"
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(root / "CMakeLists.txt", source)
    shutil.copytree(root / "include", source / "include")
    shutil.copytree(root / "src", source / "src")
    build = tmp_path / "build"
    command = [cmake, "-S", str(source), "-B", str(build), "-G", "Ninja",
               "-DBUILD_TESTING=OFF", "-DCMAKE_BUILD_TYPE=Release",
               f"-DCMAKE_CXX_COMPILER={compiler}", f"-DCMAKE_MAKE_PROGRAM={ninja}"]
    subprocess.run(command, check=True, capture_output=True)
    before = (build / "pet_build_id.h").read_text(encoding="utf-8")
    internal = source / "src" / "collision_internal.h"
    internal.write_bytes(internal.read_bytes() + b"\n// build input probe\n")
    subprocess.run(command, check=True, capture_output=True)
    after = (build / "pet_build_id.h").read_text(encoding="utf-8")
    assert after != before
