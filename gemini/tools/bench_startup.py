"""Measure how long Gemini takes to appear: launch -> first frame -> card ready.

Runs the built program (or the source) in smoke-test mode with a throwaway
state directory and reads the timestamps it records in smoke-result.json.
"""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run_once(command, state):
    launched = time.time()
    started = time.perf_counter()
    subprocess.run(command+['--smoke-test', '--no-tray', '--state-dir', str(state)],
                   check=True, timeout=60)
    total = time.perf_counter()-started
    timings = json.loads((state/'smoke-result.json').read_text(encoding='utf-8')).get('timings', {})
    result = dict(total=total*1000)
    for key in ('first_frame', 'card_ready'):
        if key in timings:
            result[key] = (timings[key]-launched)*1000
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=ROOT/'dist/GeminiPet/GeminiPet.exe')
    parser.add_argument('--source', action='store_true', help='measure app/main.py instead')
    parser.add_argument('--runs', type=int, default=5)
    args = parser.parse_args()
    command = [sys.executable, str(ROOT/'app/main.py')] if args.source else [str(args.exe)]
    runs = []
    with tempfile.TemporaryDirectory(prefix='gemini-bench-') as folder:
        for index in range(args.runs+1):
            state = Path(folder)/str(index)
            result = run_once(command, state)
            if index:  # the first run only warms the disk cache
                runs.append(result)
    for key in ('first_frame', 'card_ready', 'total'):
        values = [run[key] for run in runs if key in run]
        if values:
            print(f'{key:12s} median {statistics.median(values):7.0f} ms   '
                  f'min {min(values):7.0f}   max {max(values):7.0f}')


if __name__ == '__main__':
    main()
