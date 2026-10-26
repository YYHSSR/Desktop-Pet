"""Run isolated regression modules, with an explicit asset-independent suite."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = (
    'test_quota_summary_data', 'test_spring_motion', 'test_status_reactions.SchedulerTests',
    'test_ring_metrics', 'test_work_actions', 'test_sustained_reactions',
    'test_soft_curves_navigation', 'test_loop_cache', 'test_decoder_runtime',
    'test_animation_quality', 'test_sustained_player', 'test_status_indicator',
    'test_read_completion', 'test_reset_card', 'test_reset_presentation',
    'test_material_store', 'test_material_controller', 'test_package_optimization',
    'test_embedded_assets',
    'test_shortcuts_startup.StartupTests', 'test_project_structure',
    'test_connection_and_sessions', 'test_enhanced_core', 'test_quota',
    'test_token_calendar', 'test_token_charts', 'test_daily_report',
    'test_refresh_flow',
    'test_runtime_resilience',
)


def run_module(name):
    with tempfile.TemporaryDirectory(prefix='desktop-pet-test-') as folder:
        env = os.environ.copy()
        env.update(LOCALAPPDATA=folder, APPDATA=str(Path(folder) / 'roaming'),
                   CODEX_HOME=str(Path(folder) / 'codex'), QT_QPA_PLATFORM='offscreen',
                   PYTHONIOENCODING='utf-8', PYTHONPATH=os.pathsep.join(
                       str(ROOT / item) for item in ('tests', 'app', 'tools')))
        command = [sys.executable, '-c',
                   'import faulthandler,unittest;faulthandler.dump_traceback_later(55);'
                   f'unittest.main(module=None,argv=["unittest",{name!r}],verbosity=2)']
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            output, _ = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            import psutil
            try:
                children = psutil.Process(process.pid).children(recursive=True)
            except psutil.Error:
                children = []
            for child in reversed(children):
                try:
                    child.kill()
                except psutil.Error:
                    pass
            process.kill()
            output, _ = process.communicate(timeout=10)
            return 124, output.decode('utf-8', errors='replace')
        return process.returncode, output.decode('utf-8', errors='replace')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('core', 'all'), default='core')
    parser.add_argument('modules', nargs='*', help='Explicit unittest module or class names')
    args = parser.parse_args(argv)
    names = args.modules or (CORE if args.suite == 'core' else
                            [p.stem for p in sorted((ROOT / 'tests').glob('test_*.py'))])
    output = ROOT / 'build/checks'
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for name in names:
        code, log = run_module(name)
        (output / (name + '.log')).write_text(log, encoding='utf-8')
        import re
        count = re.search(r'Ran (\d+) tests?', log)
        records.append(dict(module=name, passed=code == 0, tests=int(count[1]) if count else 0))
        print(f'{"PASS" if code == 0 else "FAIL"} {name}', flush=True)
        if code:
            print(log[-3500:], flush=True)
    report = dict(passed=all(r['passed'] for r in records), modules=len(records),
                  tests=sum(r['tests'] for r in records), records=records)
    (output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
