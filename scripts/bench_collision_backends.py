"""End-to-end collision A/B, including Python packing and ctypes unpacking."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pet import collision
from pet.native import loader


def scene(size: int, topology: str) -> list[collision.MemberState]:
    step = 18 if topology != "sparse" else 140
    members = []
    for index in range(size):
        x, y = (index % 6) * step, (index // 6) * step
        is_static = topology == "static" and index == 0
        members.append(collision.MemberState(
            runtime_id=f"pet-{index:02d}", x=x, y=y,
            radius_x=30, radius_y=30,
            vx=120 if index % 2 else -120, vy=20,
            is_infinite_mass=is_static,
            flags=collision.FLAG_VISIBLE | collision.FLAG_COLLISION_ENABLED
            | (collision.FLAG_STATIC if is_static else 0),
            circles=([[x, y, 24], [x + 12, y, 12]] if topology == "circles" else None),
        ))
    return members


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def run_one(mode: str, members, history: dict[str, int] | None = None) -> float:
    os.environ["PET_COLLISION_BACKEND"] = mode
    start = time.perf_counter_ns()
    collision.solve_multi_body_collision(members, overlap_history=history)
    return (time.perf_counter_ns() - start) / 1000


def measure(members, samples: int, rounds: int) -> dict:
    first = {mode: run_one(mode, members) for mode in ("python", "native")}
    raw = {mode: [] for mode in ("python", "native")}
    for round_index in range(rounds):
        for sample_index in range(samples):
            order = ("python", "native") if (round_index + sample_index) % 2 == 0 else ("native", "python")
            for mode in order:
                raw[mode].append(run_one(mode, members, {"pet-00|pet-01": 3}))
    result = {}
    for mode, values in raw.items():
        result[mode] = {
            "scenario_first_call_us": round(first[mode], 2),
            "median_us": round(statistics.median(values), 2),
            "p95_us": round(percentile(values, 95), 2),
            "p99_us": round(percentile(values, 99), 2),
            "raw_us": [round(value, 2) for value in values],
        }
    result["native_over_python"] = round(result["native"]["median_us"] / result["python"]["median_us"], 3)
    return result


def metadata() -> dict:
    path = loader.native_library_path()
    dll = loader._load(str(path.resolve()))
    return {
        "fixture_version": 2,
        "utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "native_dll": str(path),
        "native_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "native_build_id": dll.pet_core_build_id().decode("utf-8"),
        "timer": "perf_counter_ns; public solver call, including marshal and result conversion",
        "first_call_semantics": "first call for each scenario in this process; DLL may be cached",
        "sampling": "alternating backend order per sample; fixed input and overlap history",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.rounds < 1 or args.samples < 1:
        parser.error("rounds and samples must be positive")
    old_mode = os.environ.get("PET_COLLISION_BACKEND")
    try:
        result = metadata()
        result.update({"samples_per_round": args.samples, "rounds": args.rounds, "results": []})
        for size in (1, 3, 10, 30):
            for topology in ("sparse", "dense", "circles", "static"):
                if size == 1 and topology == "static":
                    continue
                result["results"].append({"members": size, "topology": topology,
                                          **measure(scene(size, topology), args.samples, args.rounds)})
    finally:
        if old_mode is None:
            os.environ.pop("PET_COLLISION_BACKEND", None)
        else:
            os.environ["PET_COLLISION_BACKEND"] = old_mode
    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
