"""Load the versioned pet_core C ABI and marshal one collision tick."""

from __future__ import annotations

import ctypes as C
from functools import lru_cache
import logging
import math
import os
from pathlib import Path
import sys
import time

from .. import collision


class Circle(C.Structure):
    _fields_ = [(name, C.c_double) for name in ("x", "y", "r")]


class Member(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ("struct_size", "flags", "circle_start", "circle_count", "infinite_mass", "reserved")]
    _fields_ += [(name, C.c_double) for name in ("x", "y", "rx", "ry", "vx", "vy", "mass")]


class PairInput(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ("struct_size", "a", "b", "history", "ignored", "swept", "sort_rank")]
    _fields_ += [(name, C.c_double) for name in (
        "fallback_nx", "fallback_ny", "swept_nx", "swept_ny", "swept_overlap", "swept_cx", "swept_cy")]


class Options(C.Structure):
    _fields_ = [("struct_size", C.c_uint32), ("max_separation_iterations", C.c_uint32),
                ("tick", C.c_int64), ("restitution", C.c_double),
                ("friction", C.c_double), ("impulse_cap", C.c_double)]


class PairOutput(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ("struct_size", "pair_index", "history", "flags")]
    _fields_ += [(name, C.c_double) for name in (
        "nx", "ny", "j", "sep", "contact_x", "contact_y", "ax", "ay", "bx", "by",
        "dvx_a", "dvy_a", "dvx_b", "dvy_b", "dx_a", "dy_a", "dx_b", "dy_b")]


class MemberOutput(C.Structure):
    _fields_ = [("struct_size", C.c_uint32), ("reserved", C.c_uint32)]
    _fields_ += [(name, C.c_double) for name in ("dvx", "dvy", "dx", "dy")]


class Request(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ("struct_size", "member_count", "circle_count", "pair_count")]
    _fields_ += [("members", C.POINTER(Member)), ("circles", C.POINTER(Circle)),
                ("pairs", C.POINTER(PairInput)), ("options", C.POINTER(Options))]


class Output(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ("struct_size", "pair_capacity", "member_capacity", "pair_count")]
    _fields_ += [("pairs", C.POINTER(PairOutput)), ("members", C.POINTER(MemberOutput))]


_LAYOUT = (Circle, Member, PairInput, Options, PairOutput, MemberOutput, Request, Output)
_LAYOUT_OFFSETS = tuple(getattr(cls, name).offset for cls in _LAYOUT for name, _ in cls._fields_)
ABI_VERSION = 2
MAX_MEMBERS = 512
MAX_CIRCLES = 8192
MAX_PAIRS = 130816
MAX_ITERATIONS = 64
_call_count = 0
_dll_dirs = []
_log = logging.getLogger(__name__)


def native_call_count() -> int:
    """Successful calls through the C ABI, used by the strict native test gate."""
    return _call_count


@lru_cache(maxsize=256)
def _stable_direction(id_a: str, id_b: str) -> tuple[float, float]:
    return collision.stable_hash_direction(id_a, id_b)


@lru_cache(maxsize=1)
def _default_path() -> Path:
    suffix = ".dll" if sys.platform == "win32" else ".dylib" if sys.platform == "darwin" else ".so"
    return Path(__file__).resolve().parent / "_bin" / f"pet_core{suffix}"


def native_library_path() -> Path:
    """Resolve an explicit override, or reuse the packaged absolute path."""
    override = os.environ.get("PET_CORE_DLL")
    return Path(override).resolve() if override else _default_path()


def _u32(value, name: str, *, maximum: int = 0xFFFFFFFF) -> int:
    number = int(value)
    if number < 0 or number > maximum:
        raise ValueError(f"native collision {name} outside 0..{maximum}")
    return number


def _i64(value, name: str) -> int:
    number = int(value)
    if not -(1 << 63) <= number < (1 << 63):
        raise ValueError(f"native collision {name} outside signed 64-bit range")
    return number


def _scalar(value, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or abs(number) > 1e12:
        raise ValueError(f"native collision {name} must be finite and within +/-1e12")
    return number


@lru_cache(maxsize=4)
def _load(path_text: str):
    started = time.perf_counter()
    path = Path(path_text).resolve()
    if not path.is_file():
        raise OSError(f"pet_core native backend missing: {path}")
    dll_dir = None
    try:
        if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
            dll_dir = os.add_dll_directory(str(path.parent))
        dll = C.CDLL(str(path))
        dll.pet_core_abi_version.argtypes = []
        dll.pet_core_abi_version.restype = C.c_uint32
        dll.pet_core_build_id.argtypes = []
        dll.pet_core_build_id.restype = C.c_char_p
        dll.pet_core_layout_sizes.argtypes = [C.POINTER(C.c_uint32), C.c_uint32]
        dll.pet_core_layout_sizes.restype = C.c_uint32
        dll.pet_core_layout_alignments.argtypes = [C.POINTER(C.c_uint32), C.c_uint32]
        dll.pet_core_layout_alignments.restype = C.c_uint32
        dll.pet_core_layout_offsets.argtypes = [C.POINTER(C.c_uint32), C.c_uint32]
        dll.pet_core_layout_offsets.restype = C.c_uint32
        dll.pet_solve_collisions.argtypes = [C.POINTER(Request), C.POINTER(Output), C.c_void_p, C.c_uint32]
        dll.pet_solve_collisions.restype = C.c_int32
        if dll.pet_core_abi_version() != ABI_VERSION:
            raise OSError(f"pet_core ABI version mismatch at {path}")
        actual = (C.c_uint32 * len(_LAYOUT))()
        if dll.pet_core_layout_sizes(actual, len(_LAYOUT)) != len(_LAYOUT) or \
                tuple(actual) != tuple(C.sizeof(cls) for cls in _LAYOUT):
            raise OSError(f"pet_core ABI structure layout mismatch at {path}")
        alignments = (C.c_uint32 * len(_LAYOUT))()
        if dll.pet_core_layout_alignments(alignments, len(_LAYOUT)) != len(_LAYOUT) or \
                tuple(alignments) != tuple(C.alignment(cls) for cls in _LAYOUT):
            raise OSError(f"pet_core ABI structure alignment mismatch at {path}")
        offset_count = dll.pet_core_layout_offsets(None, 0)
        offsets = (C.c_uint32 * len(_LAYOUT_OFFSETS))()
        if offset_count != len(_LAYOUT_OFFSETS) or \
                dll.pet_core_layout_offsets(offsets, len(offsets)) != len(offsets) or \
                tuple(offsets) != _LAYOUT_OFFSETS:
            raise OSError(f"pet_core ABI field offset mismatch at {path}")
    except (OSError, AttributeError) as exc:
        if dll_dir is not None:
            dll_dir.close()
        raise OSError(f"pet_core load or ABI check failed at {path}: {exc}") from exc
    if dll_dir is not None:
        _dll_dirs.append(dll_dir)
    _log.info("pet_core loaded path=%s abi=%s build=%s load_ms=%.3f", path, ABI_VERSION,
              dll.pet_core_build_id().decode("utf-8", "replace"),
              (time.perf_counter() - started) * 1000)
    return dll


def solve_native(members, *, tick=0, overlap_history=None,
                 restitution=collision.DEFAULT_RESTITUTION,
                 friction=collision.DEFAULT_FRICTION,
                 impulse_cap=collision.DEFAULT_IMPULSE_CAP,
                 max_separation_iterations=4, swept_collisions=None, ignored_pairs=None):
    """Call native batch solver; all memory is caller-owned and copied out."""
    global _call_count
    path = str(native_library_path())
    dll = _load(path)
    started = time.perf_counter()
    ordered = sorted(members, key=lambda member: member.runtime_id)
    if len(ordered) > MAX_MEMBERS:
        raise ValueError(f"native collision member count exceeds {MAX_MEMBERS}")
    if len({member.runtime_id for member in ordered}) != len(ordered):
        raise ValueError("native collision backend requires unique runtime_id values")

    flat_circles = []
    packed_members = []
    for item in ordered:
        start = 0xFFFFFFFF if item.circles is None else len(flat_circles)
        if item.circles is not None:
            flat_circles.extend(Circle(_scalar(raw[0], "circle.x"),
                                       _scalar(raw[1], "circle.y"), _scalar(raw[2], "circle.r"))
                                for raw in item.circles if len(raw) >= 3)
        if len(flat_circles) > MAX_CIRCLES:
            raise ValueError(f"native collision circle count exceeds {MAX_CIRCLES}")
        mass = _scalar(item.mass, "member.mass")
        if 0 < mass < 1e-12:
            raise ValueError("native collision positive member.mass below 1e-12")
        packed_members.append(Member(C.sizeof(Member), _u32(item.flags, "flags"), start,
                                     0 if item.circles is None else len(flat_circles) - start,
                                     int(bool(item.is_infinite_mass)), 0,
                                     _scalar(item.x, "member.x"), _scalar(item.y, "member.y"),
                                     _scalar(item.radius_x, "member.rx"), _scalar(item.radius_y, "member.ry"),
                                     _scalar(item.vx, "member.vx"), _scalar(item.vy, "member.vy"), mass))
    history = overlap_history or {}
    swept = swept_collisions or {}
    ignored = ignored_pairs or set()
    packed_pairs = []
    pair_keys = []
    if len(ordered) * (len(ordered) - 1) // 2 > MAX_PAIRS:
        raise ValueError(f"native collision pair count exceeds {MAX_PAIRS}")
    for a in range(len(ordered)):
        for b in range(a + 1, len(ordered)):
            key = f"{ordered[a].runtime_id}|{ordered[b].runtime_id}"
            nx, ny = _stable_direction(ordered[a].runtime_id, ordered[b].runtime_id)
            swept_data = swept.get(key, (False, 0.0, 0.0, 0.0, 0.0, 0.0))
            count = max(0, int(history.get(key, 0)))
            count = _u32(count, "history", maximum=0xFFFFFFFE)
            packed_pairs.append(PairInput(C.sizeof(PairInput), a, b,
                                           count, int(key in ignored),
                                           int(bool(swept_data[0])), 0,
                                           _scalar(nx, "fallback_nx"), _scalar(ny, "fallback_ny"),
                                           *(_scalar(value, "swept") for value in swept_data[1:6])))
            pair_keys.append(key)

    if pair_keys == sorted(pair_keys):
        for rank, raw in enumerate(packed_pairs):
            raw.sort_rank = rank
    else:
        rank_by_key = {key: rank for rank, key in enumerate(sorted(pair_keys))}
        for raw, key in zip(packed_pairs, pair_keys):
            raw.sort_rank = rank_by_key[key]

    member_buf = (Member * len(packed_members))(*packed_members)
    circle_buf = (Circle * len(flat_circles))(*flat_circles)
    pair_buf = (PairInput * len(packed_pairs))(*packed_pairs)
    pair_out = (PairOutput * len(packed_pairs))()
    member_out = (MemberOutput * len(packed_members))()
    iterations = max(0, int(max_separation_iterations))
    iterations = _u32(iterations, "iterations", maximum=MAX_ITERATIONS)
    settings = Options(C.sizeof(Options), iterations, _i64(tick, "tick"),
                       _scalar(restitution, "restitution"), _scalar(friction, "friction"),
                       _scalar(impulse_cap, "impulse_cap"))
    request = Request(C.sizeof(Request), len(packed_members), len(flat_circles), len(packed_pairs),
                      member_buf, circle_buf, pair_buf, C.pointer(settings))
    output = Output(C.sizeof(Output), len(packed_pairs), len(packed_members), 0,
                    pair_out, member_out)
    error = C.create_string_buffer(256)
    call_started = time.perf_counter()
    status = dll.pet_solve_collisions(C.byref(request), C.byref(output), error, len(error))
    call_done = time.perf_counter()
    if status:
        raise RuntimeError(f"pet_core status {status}: {error.value.decode('utf-8', 'replace')}")
    _call_count += 1

    impulse_results = []
    new_history = {}
    for raw in pair_out[:output.pair_count]:
        a, b = packed_pairs[raw.pair_index].a, packed_pairs[raw.pair_index].b
        key = pair_keys[raw.pair_index]
        new_history[key] = raw.history
        impulse_results.append(collision.ImpulseResult(
            tick=tick, pair=key, a=ordered[a].runtime_id, b=ordered[b].runtime_id,
            nx=raw.nx, ny=raw.ny, j=raw.j, sep=raw.sep,
            contact_x=raw.contact_x, contact_y=raw.contact_y, flags=raw.flags,
            ax=raw.ax, ay=raw.ay, bx=raw.bx, by=raw.by,
            dvx_a=raw.dvx_a, dvy_a=raw.dvy_a, dvx_b=raw.dvx_b, dvy_b=raw.dvy_b,
            dx_a=raw.dx_a, dy_a=raw.dy_a, dx_b=raw.dx_b, dy_b=raw.dy_b))
    combined = {item.runtime_id: (raw.dvx, raw.dvy, raw.dx, raw.dy)
                for item, raw in zip(ordered, member_out)}
    if _log.isEnabledFor(logging.DEBUG):
        _log.debug("pet_core tick=%s members=%s pairs=%s pack_ms=%.3f solve_ms=%.3f unpack_ms=%.3f",
                   tick, len(ordered), output.pair_count,
                   (call_started - started) * 1000, (call_done - call_started) * 1000,
                   (time.perf_counter() - call_done) * 1000)
    return impulse_results, combined, new_history
