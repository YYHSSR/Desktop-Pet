"""Replay mouse clicks using the shipped PYZ, Qt runtime and complete AppShell."""
from __future__ import annotations

import argparse
import json
import marshal
import os
from pathlib import Path
import shutil
import subprocess
import uuid

from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.archive.writers import CArchiveWriter


class ProbeArchiveWriter(CArchiveWriter):
    def _write_entry(self, fp, entry):
        name, source, compress, kind = entry
        if kind in {"s", "m", "M"}:
            return self._write_blob(fp, Path(source).read_bytes(), name, kind, compress=compress)
        return super()._write_entry(fp, entry)


def verify(exe: Path, output: Path, config: Path | None = None, run_key: bool = False, in_place: bool = False):
    exe, output = exe.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive = CArchiveReader(str(exe))
    entries = [(option, None, False, "o") for option in archive.options]
    for name, (_, _, _, compressed, kind) in archive.toc.items():
        source = output / f"entry-{len(entries)}"
        if name == "pet_entry":
            code = compile(Path(__file__).with_name("frozen_tray_entry.py").read_text(encoding="utf-8"),
                           "frozen_tray_entry.py", "exec")
            data = marshal.dumps(code)
        else:
            data = archive.extract(name)
        source.write_bytes(data)
        entries.append((name, str(source), compressed, kind))
    pkg = output / "probe.pkg"
    ProbeArchiveWriter(str(pkg), entries, "python313.dll")
    original_exe = exe.read_bytes()
    probe = exe if in_place else output / "tray-probe.exe"
    if in_place:
        (output / "original-exe.backup").write_bytes(original_exe)
    else:
        shutil.copytree(exe.parent / "_internal", output / "_internal", dirs_exist_ok=True)
    appdata = output / "AppData"
    appdata.mkdir(exist_ok=True)
    if config:
        dest = appdata / "dsh-pet-standalone-webm-chat" / "config.json"
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(config, dest)
    env = os.environ.copy()
    env["APPDATA"] = str(appdata)
    env.pop("QT_QPA_PLATFORM", None)
    env.pop("PYTHONPATH", None)
    env["PET_TRAY_TEST_DELAY"] = "10000" if in_place else "1000"
    key = (r"Software\Microsoft\Windows\CurrentVersion\Run" if run_key
           else rf"Software\DesktopPetFrozenTest-{uuid.uuid4().hex}")
    value_name = "dsh-pet-standalone-webm-chat"
    import winreg
    previous = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_QUERY_VALUE) as handle:
            previous = winreg.QueryValueEx(handle, value_name)
    except FileNotFoundError:
        pass
    report = output / "result.json"
    try:
        probe.write_bytes(original_exe[:archive._start_offset] + pkg.read_bytes())
        process = subprocess.run([str(probe), str(report), key, value_name], env=env, cwd=output,
                                 timeout=75, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        events = json.loads(report.read_text(encoding="utf-8")) if report.exists() else []
        print(json.dumps({"exit": process.returncode, "events": events}, ensure_ascii=False, indent=2))
        if process.returncode or not any(event["kind"] == "passed" for event in events):
            raise AssertionError("Frozen tray regression failed")
    finally:
        if in_place:
            exe.write_bytes(original_exe)
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as handle:
                if previous is None:
                    try:
                        winreg.DeleteValue(handle, value_name)
                    except FileNotFoundError:
                        pass
                else:
                    winreg.SetValueEx(handle, value_name, 0, previous[1], previous[0])
            if not run_key:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--run-key", action="store_true", help="Test the real Run value and restore it afterwards")
    parser.add_argument("--in-place", action="store_true", help="Probe the original executable path and restore its bytes")
    args = parser.parse_args()
    verify(args.exe, args.output, args.config, args.run_key, args.in_place)
