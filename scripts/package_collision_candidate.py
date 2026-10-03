"""Create an immutable candidate zip and its build-input receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


SOURCE_DIRS = ("pet", "scripts", "C++-Python", "packaging", "assets")
SOURCE_FILES = ("requirements.txt", "requirements-dev.txt", "pyproject.toml")
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", "_bin", "build", "build-native"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--upstream-candidate", required=True)
    parser.add_argument("--build-command", required=True)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    arguments = parser.parse_args()
    root, app = arguments.root.resolve(), arguments.app_dir.resolve()
    output, receipt_path = arguments.zip.resolve(), arguments.receipt.resolve()
    if output.exists() or receipt_path.exists():
        raise FileExistsError("candidate zip or receipt already exists; use a new candidate name")
    if not app.is_dir() or not (app / "_internal" / "pet" / "native" / "_bin" / "manifest.json").is_file():
        raise ValueError("built app or native dependency manifest missing")

    sources = []
    for directory in SOURCE_DIRS:
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and not SKIP_PARTS.intersection(path.relative_to(root).parts):
                sources.append(path)
    sources.extend(root / name for name in SOURCE_FILES)
    source_manifest = {str(path.relative_to(root)).replace("\\", "/"): sha256(path) for path in sources}
    package_list = subprocess.run(
        [str(arguments.python.resolve()), "-m", "pip", "list", "--format=freeze"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    build_manifest = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "upstream_candidate_commit": arguments.upstream_candidate,
        "source_provenance_limit": "local snapshot has no .git; matched upstream key files only",
        "build_command": arguments.build_command,
        "python_executable": str(arguments.python.resolve()),
        "python_packages": package_list,
        "source_sha256": source_manifest,
        "native_runtime": json.loads((app / "_internal" / "pet" / "native" / "_bin" / "manifest.json").read_text(encoding="utf-8")),
        "conda_runtime": json.loads((app / "_internal" / "conda-runtime-manifest.json").read_text(encoding="utf-8")),
    }
    embedded = app / "build-input-manifest.json"
    embedded.write_text(json.dumps(build_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(app.parent))
    with zipfile.ZipFile(output) as archive:
        corrupt = archive.testzip()
        if corrupt:
            raise ValueError(f"candidate zip CRC mismatch: {corrupt}")
        names = archive.namelist()
    receipt = {
        "zip": str(output),
        "zip_sha256": sha256(output),
        "zip_size_bytes": output.stat().st_size,
        "file_count": len(names),
        "embedded_manifest_sha256": sha256(embedded),
        "native_dll_sha256": sha256(app / "_internal" / "pet" / "native" / "_bin" / "pet_core.dll"),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
