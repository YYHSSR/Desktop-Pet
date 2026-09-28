"""Backend selection for the batched collision solver."""

from __future__ import annotations

import logging
import os
from threading import Lock

from .. import collision

_log = logging.getLogger(__name__)
_failed_auto_paths: set[str] = set()
_ready_auto_paths: set[str] = set()
_fallback_lock = Lock()


def reset_auto_fallback() -> None:
    """Retry auto loading after repairing a DLL at the same path."""
    with _fallback_lock:
        _failed_auto_paths.clear()
        _ready_auto_paths.clear()


def solve_collisions(members, **options):
    """Select Python, native, or auto via PET_COLLISION_BACKEND.

    Python remains the default until end-to-end benchmarks justify enabling
    native by default. A forced native selection never silently falls back.
    """
    mode = os.environ.get("PET_COLLISION_BACKEND", "python").strip().lower()
    if mode not in {"python", "native", "auto"}:
        raise ValueError(f"invalid PET_COLLISION_BACKEND: {mode!r}")
    if mode == "python":
        return collision.solve_multi_body_collision_python(members, **options)
    from . import loader
    if mode == "native":
        return loader.solve_native(members, **options)
    path = str(loader.native_library_path())
    # Only the first load for a path is serialized. Solves run without this
    # lock, so the DLL's batch computation is not forced onto one thread.
    unavailable = False
    with _fallback_lock:
        if path in _failed_auto_paths:
            unavailable = True
        elif path not in _ready_auto_paths:
            try:
                loader._load(path)
            except OSError as exc:
                _failed_auto_paths.add(path)
                _log.warning("pet_core native backend unavailable; using Python: %s", exc)
                unavailable = True
            else:
                _ready_auto_paths.add(path)
    if unavailable:
        return collision.solve_multi_body_collision_python(members, **options)
    try:
        return loader.solve_native(members, **options)
    except OSError as exc:
        with _fallback_lock:
            _failed_auto_paths.add(path)
            _log.warning("pet_core native backend unavailable; using Python: %s", exc)
        return collision.solve_multi_body_collision_python(members, **options)
