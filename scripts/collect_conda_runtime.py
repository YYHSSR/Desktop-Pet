"""Collect conda DLLs imported by bundled top-level Python extensions.

The resulting manifest records the exact bytes copied into the bundle.  Only
DLLs present in the selected conda environment are considered conda runtime
dependencies; Windows and PyInstaller runtime imports are left to their own
providers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pefile


def imports(path: Path) -> list[str]:
    pe = pefile.PE(str(path), fast_load=True)
    try:
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
        return sorted(
            {entry.dll.decode("ascii") for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])},
            key=str.casefold,
        )
    finally:
        pe.close()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collect(bundle: Path, conda_bin: Path) -> dict:
    internal = bundle / "_internal"
    if not internal.is_dir() or not conda_bin.is_dir():
        raise ValueError("bundle _internal and conda Library/bin must exist")
    sources = {path.name.casefold(): path for path in conda_bin.glob("*.dll")}
    roots = sorted(internal.glob("*.pyd"), key=lambda path: path.name.casefold())
    if not roots:
        raise ValueError("no top-level Python extension modules found")
    pending = list(roots)
    seen: set[str] = set()
    copied: dict[str, dict] = {}
    while pending:
        binary = pending.pop(0)
        key = str(binary.resolve()).casefold()
        if key in seen:
            continue
        seen.add(key)
        for name in imports(binary):
            if name.casefold().startswith(("api-ms-win-", "ext-ms-win-")):
                continue
            source = sources.get(name.casefold())
            if source is None:
                continue
            target = internal / source.name
            source_hash = sha256(source)
            if not target.is_file() or sha256(target) != source_hash:
                target.write_bytes(source.read_bytes())
            if sha256(target) != source_hash:
                raise ValueError(f"conda DLL copy mismatch: {source.name}")
            copied[source.name.casefold()] = {
                "name": source.name,
                "sha256": source_hash,
                "source": str(source.resolve()),
                "imports": imports(source),
            }
            pending.append(target)
    return {
        "schema_version": 2,
        "provider": "conda",
        "applicable": True,
        "conda_bin": str(conda_bin.resolve()),
        "extension_roots": [path.name for path in roots],
        "dependencies": sorted(copied.values(), key=lambda item: item["name"].casefold()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--conda-bin", type=Path)
    arguments = parser.parse_args()
    if arguments.conda_bin is None:
        manifest = {"schema_version": 2, "provider": "standard", "applicable": False, "dependencies": []}
    else:
        manifest = collect(arguments.bundle, arguments.conda_bin)
    path = arguments.bundle / "_internal" / "conda-runtime-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[Python] staged {len(manifest['dependencies'])} {manifest['provider']} DLLs; manifest={path}")


if __name__ == "__main__":
    main()
