"""Native collision contract and differential checks.

Run this file after scripts/build_native.ps1 has installed pet_core.dll.
"""

from dataclasses import asdict, replace
import ctypes as C
import os
import random

import pytest

from pet import collision
from pet.native import loader

pytestmark = pytest.mark.skipif(
    os.environ.get("PET_COLLISION_BACKEND", "").lower() != "native" and not loader._default_path().is_file(),
    reason="native DLL is not staged in the regular Python-only test job",
)


def _compare_case(members, **options):
    expected = collision.solve_multi_body_collision_python(members, **options)
    actual = loader.solve_native(members, **options)
    exp_pairs, exp_combined, exp_history = expected
    got_pairs, got_combined, got_history = actual
    assert [(x.pair, x.a, x.b, x.flags, x.tick) for x in got_pairs] == [
        (x.pair, x.a, x.b, x.flags, x.tick) for x in exp_pairs
    ]
    assert got_history == exp_history
    assert got_combined.keys() == exp_combined.keys()
    for pair, ref in zip(got_pairs, exp_pairs):
        for name, value in asdict(ref).items():
            if isinstance(value, float):
                assert getattr(pair, name) == pytest.approx(value, rel=1e-8, abs=1e-7), (pair.pair, name)
    for key, ref in exp_combined.items():
        assert got_combined[key] == pytest.approx(ref, rel=1e-8, abs=1e-7)


def test_native_path_called_and_empty_input():
    assert loader.native_call_count() >= 0
    before = loader.native_call_count()
    _compare_case([], tick=3)
    assert loader.native_call_count() == before + 1


def test_native_pair_geometry_and_history():
    a = collision.MemberState("a", 0, 0, 50, 50, vx=150, vy=20)
    b = collision.MemberState("b", 70, 0, 50, 50, vx=-150, vy=-30)
    _compare_case([b, a], tick=12, overlap_history={"a|b": 2})
    _compare_case([a, b], tick=13, restitution=0.4, friction=0.2, impulse_cap=100)


def test_native_coincident_circle_chain_and_static_body():
    a = collision.MemberState("鱼a", 0, 0, 50, 50, circles=[[0, 0, 20], [15, 0, 20]], vx=200)
    b = collision.MemberState("鱼b", 0, 0, 50, 50, circles=[[0, 0, 20]],
                              is_infinite_mass=True, flags=collision.FLAG_VISIBLE | collision.FLAG_COLLISION_ENABLED | collision.FLAG_STATIC)
    _compare_case([a, b], overlap_history={"鱼a|鱼b": 2})


def test_native_swept_and_ignored_pairs():
    a = collision.MemberState("a", 0, 0, 5, 5, vx=200)
    b = collision.MemberState("b", 100, 0, 5, 5, vx=-200)
    swept = {"a|b": (True, 1.0, 0.0, 1.0, 50.0, 0.0)}
    _compare_case([a, b], swept_collisions=swept)
    _compare_case([a, b], swept_collisions=swept, ignored_pairs={"a|b"})


def test_native_randomized_small_scenes():
    rng = random.Random(20260924)
    for _ in range(40):
        members = []
        for idx in range(rng.randrange(1, 8)):
            flags = collision.FLAG_VISIBLE | collision.FLAG_COLLISION_ENABLED
            if rng.random() < 0.1:
                flags |= collision.FLAG_PAUSED
            if rng.random() < 0.1:
                flags &= ~collision.FLAG_VISIBLE
            members.append(collision.MemberState(
                str(idx), rng.uniform(-80, 80), rng.uniform(-80, 80),
                rng.uniform(5, 50), rng.uniform(5, 50),
                vx=rng.uniform(-300, 300), vy=rng.uniform(-300, 300),
                mass=rng.uniform(0.5, 2.5), flags=flags,
            ))
        _compare_case(members, max_separation_iterations=rng.randrange(0, 6))


def test_native_equal_depth_prefix_ids_follow_reference_pair_order():
    members = [
        collision.MemberState("a", 0, 0, 30, 30),
        collision.MemberState("aa", 0, 0, 30, 30),
        collision.MemberState("b", 0, 0, 30, 30),
    ]
    _compare_case(members, max_separation_iterations=3)


def test_prefix_id_pair_sort_ranks_match_reference_strings(monkeypatch):
    seen = []

    class CaptureDll:
        def pet_solve_collisions(self, request_ptr, output_ptr, _error, _capacity):
            request = C.cast(request_ptr, C.POINTER(loader.Request)).contents
            seen.extend(request.pairs[index].sort_rank for index in range(request.pair_count))
            output = C.cast(output_ptr, C.POINTER(loader.Output)).contents
            output.pair_count = 0
            return 0

    monkeypatch.setattr(loader, "_load", lambda _: CaptureDll())
    loader.solve_native([collision.MemberState(name, 0, 0, 30, 30)
                         for name in ("a", "aa", "b")])
    assert seen == [1, 2, 0]


def test_native_multi_tick_history_pause_join_and_leave():
    members = [
        collision.MemberState("a", 0, 0, 30, 30, vx=80),
        collision.MemberState("b", 45, 0, 30, 30, vx=-80),
    ]
    history = {}
    for tick in range(8):
        if tick == 3:
            members[1] = replace(members[1], flags=members[1].flags | collision.FLAG_PAUSED)
        if tick == 4:
            members[1] = replace(members[1], flags=members[1].flags & ~collision.FLAG_PAUSED)
        if tick == 5:
            members.append(collision.MemberState("aa", 25, 10, 20, 20))
        if tick == 7:
            members = [member for member in members if member.runtime_id != "aa"]
        _compare_case(members, tick=tick, overlap_history=history)
        _events, combined, history = collision.solve_multi_body_collision_python(
            members, tick=tick, overlap_history=history,
        )
        members = [replace(member, x=member.x + combined[member.runtime_id][2],
                           y=member.y + combined[member.runtime_id][3],
                           vx=member.vx + combined[member.runtime_id][0],
                           vy=member.vy + combined[member.runtime_id][1])
                   for member in members]


def test_native_randomized_circle_chains_and_large_scenes():
    rng = random.Random(20260925)
    for size in (3, 10, 30):
        members = []
        for index in range(size):
            x, y = rng.uniform(-30, 30), rng.uniform(-30, 30)
            circles = [[x - 5, y, 12], [x + 5, y, 12]] if index % 3 else []
            members.append(collision.MemberState(
                f"pet-{index:02d}", x, y, 30, 30, circles=circles,
                vx=rng.uniform(-100, 100), vy=rng.uniform(-100, 100),
                mass=0 if index == 0 else rng.uniform(0.5, 2),
                is_infinite_mass=index == 1,
            ))
        _compare_case(members, max_separation_iterations=4)


def test_native_and_python_independent_trajectories_do_not_drift():
    initial = [
        collision.MemberState("a", 0, 0, 30, 30, vx=120, vy=10),
        collision.MemberState("b", 42, 0, 30, 30, vx=-100, vy=-5),
        collision.MemberState("c", 21, 36, 30, 30, vx=20, vy=-40),
    ]
    python_members = list(initial)
    native_members = list(initial)
    python_history: dict[str, int] = {}
    native_history: dict[str, int] = {}

    def advance(members, combined):
        result = []
        for member in members:
            dvx, dvy, dx, dy = combined[member.runtime_id]
            vx, vy = member.vx + dvx, member.vy + dvy
            result.append(replace(member, x=member.x + dx + vx * 0.016,
                                  y=member.y + dy + vy * 0.016, vx=vx, vy=vy))
        return result

    for tick in range(100):
        python_events, python_combined, python_history = collision.solve_multi_body_collision_python(
            python_members, tick=tick, overlap_history=python_history,
        )
        native_events, native_combined, native_history = loader.solve_native(
            native_members, tick=tick, overlap_history=native_history,
        )
        assert [event.pair for event in native_events] == [event.pair for event in python_events]
        assert native_history == python_history
        python_members = advance(python_members, python_combined)
        native_members = advance(native_members, native_combined)
        for actual, expected in zip(native_members, python_members):
            assert (actual.x, actual.y, actual.vx, actual.vy) == pytest.approx(
                (expected.x, expected.y, expected.vx, expected.vy), rel=1e-6, abs=1e-5,
            )
