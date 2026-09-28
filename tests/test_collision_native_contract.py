"""Native ABI rejects malformed values before writing caller-owned outputs."""

import ctypes as C
import math

import pytest

from pet import collision
from pet.native import loader


pytestmark = pytest.mark.skipif(not loader._default_path().is_file(), reason="native DLL not staged")


def _request_with_one_member():
    member = loader.Member(C.sizeof(loader.Member), 513, 0xFFFFFFFF, 0, 0, 0,
                           0, 0, 50, 50, 0, 0, 1)
    members = (loader.Member * 1)(member)
    options = loader.Options(C.sizeof(loader.Options), 4, 0, 0.82, 0.08, 9000)
    request = loader.Request(C.sizeof(loader.Request), 1, 0, 0,
                             members, None, None, C.pointer(options))
    output_members = (loader.MemberOutput * 1)()
    output_members[0].reserved = 0x12345678
    output = loader.Output(C.sizeof(loader.Output), 0, 1, 77,
                           None, output_members)
    return request, output, members, options, output_members


@pytest.mark.parametrize("field", ["x", "vx", "rx", "mass"])
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_native_rejects_nonfinite_member_without_output_writes(field, bad):
    dll = loader._load(str(loader._default_path()))
    request, output, members, _options, out_members = _request_with_one_member()
    setattr(members[0], field, bad)
    error = C.create_string_buffer(128)
    status = dll.pet_solve_collisions(C.byref(request), C.byref(output), error, len(error))
    assert status == 1
    assert output.pair_count == 0
    assert out_members[0].reserved == 0x12345678
    assert error.value


def test_python_wrapper_rejects_integer_truncation():
    members = [
        collision.MemberState("a", 0, 0, 50, 50),
        collision.MemberState("b", 70, 0, 50, 50),
    ]
    with pytest.raises(ValueError, match="history"):
        loader.solve_native(members, overlap_history={"a|b": 2**32})
    with pytest.raises(ValueError, match="iterations"):
        loader.solve_native(members, max_separation_iterations=2**32)
    with pytest.raises(ValueError, match="tick"):
        loader.solve_native(members, tick=2**63)


def test_layout_offsets_and_build_id_are_exposed():
    dll = loader._load(str(loader._default_path()))
    assert hasattr(dll, "pet_core_layout_offsets")
    assert dll.pet_core_abi_version() == 2
    assert dll.pet_core_build_id().decode().startswith("collision-core/2.0+")


def test_loader_rejects_same_size_but_wrong_field_offsets(monkeypatch):
    path = str(loader._default_path())
    real = C.CDLL(path)

    def wrong_offsets(values, capacity):
        expected = loader._LAYOUT_OFFSETS
        if not values or capacity < len(expected):
            return len(expected)
        for index, value in enumerate(expected):
            values[index] = value
        values[1] += 4
        return len(expected)

    class WrongLayout:
        def __getattr__(self, name):
            return wrong_offsets if name == "pet_core_layout_offsets" else getattr(real, name)

    loader._load.cache_clear()
    with monkeypatch.context() as patch:
        patch.setattr(loader.C, "CDLL", lambda _: WrongLayout())
        with pytest.raises(OSError, match="offset mismatch"):
            loader._load(path)
    loader._load.cache_clear()


def test_loader_rejects_wrong_abi_version(monkeypatch):
    path = str(loader._default_path())
    real = C.CDLL(path)

    def wrong_version():
        return 1

    class WrongAbi:
        def __getattr__(self, name):
            return wrong_version if name == "pet_core_abi_version" else getattr(real, name)

    loader._load.cache_clear()
    with monkeypatch.context() as patch:
        patch.setattr(loader.C, "CDLL", lambda _: WrongAbi())
        with pytest.raises(OSError, match="ABI version mismatch"):
            loader._load(path)
    loader._load.cache_clear()
