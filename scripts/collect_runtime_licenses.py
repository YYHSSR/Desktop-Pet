"""Keep redistribution notices inside the portable runtime directory."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6",
            "imageio-ffmpeg", "Pillow", "psutil", "PyInstaller")


def collect(bundle: Path, ucrt_bin: Path) -> None:
    internal = bundle / "_internal"
    if not internal.is_dir():
        raise ValueError(f"Missing portable runtime: {internal}")
    target = internal / "licenses"
    target.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "LICENSE", target / "LICENSE")
    shutil.copy2(ROOT / "DEPENDENCY_LICENSES.md", target / "DEPENDENCY_LICENSES.md")
    versions = []
    for name in PACKAGES:
        distribution = importlib.metadata.distribution(name)
        files = [f for f in distribution.files or []
                 if any(token in f.name.upper() for token in ("LICENSE", "LICENCE", "COPYING", "NOTICE"))]
        if not files:
            raise ValueError(f"No license text installed for {name}")
        destination = target / name
        destination.mkdir(exist_ok=True)
        for file in files:
            shutil.copy2(distribution.locate_file(file), destination / file.name)
        versions.append(f"{name} {distribution.version}")
    python_license = next((p for p in (Path(sys.base_prefix) / "LICENSE_PYTHON.txt",
                                     Path(sys.base_prefix) / "LICENSE.txt") if p.is_file()), None)
    if python_license is None:
        raise ValueError("Python license text missing from this environment")
    shutil.copy2(python_license, target / "Python-LICENSE.txt")
    # Preserve licenses accompanying the compiler's redistributable DLLs.
    for name in ("libgcc", "libstdc++", "libwinpthread", "crt"):
        source = ucrt_bin.parent / "share" / "licenses" / name
        if source.is_dir():
            shutil.copytree(source, target / name, dirs_exist_ok=True)
    # Conda runtime extensions: match the bundled DLLs to their package metadata.
    dll_names = {p.name.lower() for p in internal.rglob("*.dll")}
    for metadata in (Path(sys.prefix) / "conda-meta").glob("*.json"):
        record = json.loads(metadata.read_text(encoding="utf-8"))
        if not any(Path(f).name.lower() in dll_names for f in record.get("files", [])):
            continue
        cache = Path(record.get("link", {}).get("source", "")) / "info" / "licenses"
        if cache.is_dir():
            shutil.copytree(cache, target / f"conda-{record['name']}", dirs_exist_ok=True)
    import imageio_ffmpeg

    license_result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-L"],
                                    capture_output=True, text=True, encoding="utf-8", check=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    (target / "FFmpeg-license.txt").write_text(license_result.stdout + license_result.stderr,
                                             encoding="utf-8")
    (target / "components.txt").write_text(
        "Python " + sys.version.split()[0] + "\n" + "\n".join(versions) + "\n\n"
        "Qt/PySide6 copyright: The Qt Company Ltd. and contributors.\n"
        "Qt/PySide6 sources and licenses: https://code.qt.io/ and https://github.com/pyside/pyside-setup\n"
        "Qt third-party notices: https://doc.qt.io/qtforpython-6/licenses.html\n"
        "FFmpeg source: https://ffmpeg.org/download.html\n"
        "Bundled FFmpeg build: https://github.com/imageio/imageio-ffmpeg\n"
        "Each component retains its own license.\n", encoding="utf-8")
    print(f"[licenses] Runtime license texts collected in {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--ucrt-bin", type=Path, required=True)
    args = parser.parse_args()
    collect(args.bundle, args.ucrt_bin)
