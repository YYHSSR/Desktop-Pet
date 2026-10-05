"""The public collision entry keeps the reference behavior under backend selection."""

import pytest
import os
from pathlib import Path
import sys

from pet import collision


def _members():
    return [
        collision.MemberState("b", 65, 0, 50, 50, vx=-120),
        collision.MemberState("a", 0, 0, 50, 50, vx=120),
    ]


def test_python_backend_matches_reference(monkeypatch):
    monkeypatch.setenv("PET_COLLISION_BACKEND", "python")
    expected = collision.solve_multi_body_collision_python(_members(), tick=3, overlap_history={"a|b": 1})
    actual = collision.solve_multi_body_collision(_members(), tick=3, overlap_history={"a|b": 1})
    assert actual == expected


def test_forced_native_does_not_silently_fall_back(monkeypatch):
    monkeypatch.setenv("PET_COLLISION_BACKEND", "native")
    monkeypatch.setenv("PET_CORE_DLL", "Z:/missing/pet_core.dll")
    with pytest.raises((OSError, RuntimeError), match="pet_core|native"):
        collision.solve_multi_body_collision(_members())


def test_auto_backend_falls_back_when_dll_is_absent(monkeypatch):
    monkeypatch.setenv("PET_COLLISION_BACKEND", "auto")
    monkeypatch.setenv("PET_CORE_DLL", "Z:/missing/pet_core.dll")
    assert collision.solve_multi_body_collision(_members()) == collision.solve_multi_body_collision_python(_members())


def test_auto_missing_dll_failure_is_cached_until_path_changes(monkeypatch):
    from pet.native import collision_backend, loader

    monkeypatch.setenv("PET_COLLISION_BACKEND", "auto")
    monkeypatch.setenv("PET_CORE_DLL", "Z:/missing/first.dll")
    collision_backend.reset_auto_fallback()
    attempts = []

    def fail_load(path):
        attempts.append(path)
        raise OSError("missing native library")

    monkeypatch.setattr(loader, "_load", fail_load)
    for _ in range(3):
        assert collision.solve_multi_body_collision(_members()) == collision.solve_multi_body_collision_python(_members())
    assert len(attempts) == 1
    monkeypatch.setenv("PET_CORE_DLL", "Z:/missing/second.dll")
    collision.solve_multi_body_collision(_members())
    assert len(attempts) == 2
    monkeypatch.setenv("PET_COLLISION_BACKEND", "native")
    with pytest.raises(OSError):
        collision.solve_multi_body_collision(_members())
    assert len(attempts) == 3


def test_default_native_path_is_cached():
    from pet.native import loader

    loader._default_path.cache_clear()
    first = loader._default_path()
    second = loader._default_path()
    assert first is second


@pytest.mark.skipif(sys.platform != "win32", reason="Windows system DLL probe")
def test_auto_backend_falls_back_when_dll_lacks_abi_exports(monkeypatch):
    monkeypatch.setenv("PET_COLLISION_BACKEND", "auto")
    monkeypatch.setenv("PET_CORE_DLL", str(Path(os.environ["SystemRoot"]) / "System32" / "kernel32.dll"))
    assert collision.solve_multi_body_collision(_members()) == collision.solve_multi_body_collision_python(_members())


def test_private_header_change_updates_native_build_id(tmp_path):
    import shutil
    import subprocess

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


def test_circle_chain_uses_each_members_world_coordinates():
    from scripts.bench_collision_backends import scene

    members = scene(3, "circles")
    for member in members:
        assert member.circles == [[member.x, member.y, 24], [member.x + 12, member.y, 12]]
        assert all(abs(cx - member.x) + radius <= member.radius_x + 12
                   for cx, _, radius in member.circles)
    assert members[0].circles != members[1].circles
    contact = collision.check_collision_circles(
        members[0].circles, members[1].circles,
        members[0].runtime_id, members[1].runtime_id,
    )
    assert contact[0]
    assert 0 <= contact[4] <= members[1].x + members[1].radius_x


def test_held_scene_sets_dragging_flag_only_on_held_pet():
    from scripts.bench_collision_backends import scene

    members = scene(3, "held")
    assert members[0].is_infinite_mass
    assert members[0].flags & collision.FLAG_DRAGGING
    assert all(not (member.flags & collision.FLAG_DRAGGING) for member in members[1:])
