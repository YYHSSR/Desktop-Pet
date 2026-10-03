"""Measure read-only rollout polling against the real local session store."""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    sys.path.insert(0, str(args.source_root))
    import psutil
    from PySide6.QtCore import QCoreApplication
    from pet.agent_link import CodexDesktopMonitor

    app = QCoreApplication.instance() or QCoreApplication([])
    process = psutil.Process()
    with tempfile.TemporaryDirectory(prefix="pet-link-bench-") as folder:
        monitor = CodexDesktopMonitor(Path(folder))
        started = time.perf_counter()
        monitor._poll()
        cold = (time.perf_counter() - started) * 1000
        for _ in range(20):
            monitor._poll()
        gc.collect()
        before = process.memory_info().rss
        samples = []
        for _ in range(args.samples):
            started = time.perf_counter()
            monitor._poll()
            samples.append((time.perf_counter() - started) * 1000)
        app.processEvents()
        gc.collect()
        after = process.memory_info().rss
        print(json.dumps({
            "python": sys.version.split()[0], "samples": len(samples),
            "tracked_files": len(monitor._tailers),
            "cold_discovery_ms": round(cold, 4),
            "steady_mean_ms": round(statistics.mean(samples), 4),
            "steady_median_ms": round(statistics.median(samples), 4),
            "steady_max_ms": round(max(samples), 4),
            "rss_before_bytes": before, "rss_after_bytes": after, "rss_delta_bytes": after - before,
        }, ensure_ascii=False))
        monitor.stop()


if __name__ == "__main__":
    main()
