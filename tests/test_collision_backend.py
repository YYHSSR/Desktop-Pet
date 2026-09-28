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
