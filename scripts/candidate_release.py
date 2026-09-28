"""Create and verify digest-bound Windows candidate artifacts.

Snapshot is taken before native/app builds; finalize refuses changed tracked inputs.
Promotion consumes the uploaded receipt and archives without rebuilding them.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import zipfile


VARIANTS = ("webm-chat", "webm")
CHECKS = ("portable", "installer_install", "installer_uninstall", "gui", "python",
          "native", "normal_exit", "config_retained")
NATIVE_RELATIVE = "_internal/pet/native/_bin/pet_core.dll"
RUNTIME_RELATIVE = "_internal/conda-runtime-manifest.json"


def validate_sha256(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise ValueError("receipt SHA-256 must be exactly 64 hexadecimal characters")
    return value.lower()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict:
    return {"sha256": sha256(path), "size_bytes": path.stat().st_size}


def _tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True, capture_output=True,
    )
    paths = sorted(path.decode("utf-8") for path in result.stdout.split(b"\0") if path)
    if not paths:
        raise ValueError("git checkout has no tracked source files")
    return paths


def source_snapshot(root: Path, build_command: str) -> dict:
    paths = _tracked_files(root)
    clean = subprocess.run(["git", "-C", str(root), "diff", "--quiet", "HEAD", "--"], check=False)
    if clean.returncode != 0:
        raise ValueError("uncommitted tracked source changes before build")
    files = {name: sha256(root / name) for name in paths}
    packages = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--format=freeze"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return {
        "schema_version": 2,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "build_command": build_command,
        "python": {"version": platform.python_version(), "packages": packages},
        "tools": {},
        "files": files,
    }


def verify_source_snapshot(root: Path, snapshot: dict) -> None:
    current = {name: sha256(root / name) for name in _tracked_files(root)}
    if current != snapshot["files"]:
        changed = sorted(name for name in current.keys() | snapshot["files"].keys()
                         if current.get(name) != snapshot["files"].get(name))
        raise ValueError(f"tracked source changed during build: {changed}")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_standard_runtime_manifest(app: Path) -> None:
    """Record that the Python wheel environment has no Conda DLL closure."""
    path = app / RUNTIME_RELATIVE
    if not path.parent.is_dir():
        raise ValueError(f"missing bundle _internal: {path.parent}")
    _write_json(path, {"schema_version": 2, "provider": "standard", "applicable": False,
                       "dependencies": []})


def load_runtime_manifest(app: Path, python_prefix: Path) -> dict:
    path = app / RUNTIME_RELATIVE
    conda_bin = python_prefix / "Library" / "bin"
    expected_provider = "conda" if conda_bin.is_dir() else "standard"
    if not path.is_file():
        raise ValueError(f"missing {expected_provider} runtime manifest: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid runtime manifest: {path}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 2:
        raise ValueError("invalid runtime manifest schema")
    if (manifest.get("provider") != expected_provider or
            manifest.get("applicable") is not (expected_provider == "conda")):
        raise ValueError(f"runtime provider mismatch: expected {expected_provider}")
    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, list):
        raise ValueError("invalid runtime dependencies")
    if expected_provider == "standard":
        if manifest != {"schema_version": 2, "provider": "standard", "applicable": False,
                        "dependencies": []}:
            raise ValueError("invalid standard runtime manifest")
        return manifest
    if (Path(manifest.get("conda_bin", "")).resolve() != conda_bin.resolve() or
            not isinstance(manifest.get("extension_roots"), list) or
            not manifest["extension_roots"]):
        raise ValueError("invalid conda runtime origin")
    names: set[str] = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise ValueError("invalid conda runtime dependency")
        name = dependency.get("name", "")
        if (not isinstance(name, str) or not name.lower().endswith(".dll") or
                Path(name).name != name or name.casefold() in names):
            raise ValueError("invalid conda runtime dependency name")
        names.add(name.casefold())
        target = app / "_internal" / name
        if not target.is_file() or sha256(target) != dependency.get("sha256"):
            raise ValueError(f"conda dependency hash mismatch: {name}")
    return manifest


def _app_name(variant: str) -> str:
    return f"dsh-pet-standalone-{variant}"


def _artifact_names() -> set[str]:
    return {_app_name(variant) + suffix for variant in VARIANTS
            for suffix in ("-portable.zip", "-setup.exe")}


def _generated_names(variant: str) -> tuple[str, str]:
    return f"generated-{variant}-build_variant.py", f"generated-{variant}.spec"


def embed_manifests(root: Path, dist: Path, candidate_dir: Path, snapshot: dict,
                    python_prefix: Path | None = None) -> None:
    verify_source_snapshot(root, snapshot)
    python_prefix = python_prefix or Path(sys.prefix)
    for variant in VARIANTS:
        app = dist / _app_name(variant)
        if not (app / _app_name(variant)).with_suffix(".exe").is_file():
            raise ValueError(f"missing executable: {variant}")
        manifest = dict(snapshot)
        manifest["generated_inputs"] = {}
        for name in _generated_names(variant):
            path = candidate_dir / name
            if not path.is_file():
                raise ValueError(f"missing generated build input: {path}")
            manifest["generated_inputs"][name] = file_record(path)
        path = app / "_internal/pet/native/_bin/manifest.json"
        if not path.is_file():
            raise ValueError(f"missing native runtime: {path}")
        manifest["native_runtime"] = json.loads(path.read_text(encoding="utf-8"))
        manifest["conda_runtime"] = load_runtime_manifest(app, python_prefix)
        _write_json(app / "build-input-manifest.json", manifest)


def finalize(root: Path, dist: Path, candidate_dir: Path, snapshot: dict) -> dict:
    verify_source_snapshot(root, snapshot)
    allowed = {"source-snapshot.json"} | {name for variant in VARIANTS for name in _generated_names(variant)}
    if {path.name for path in candidate_dir.iterdir()} != allowed:
        raise FileExistsError("candidate directory already has outputs; use a new run ID")
    artifacts: dict[str, dict] = {}
    internals: dict[str, dict] = {}
    generated_inputs = {name: file_record(candidate_dir / name) for name in allowed - {"source-snapshot.json"}}
    for variant in VARIANTS:
        stem = _app_name(variant)
        app = dist / stem
        manifest = app / "build-input-manifest.json"
        if not manifest.is_file() or json.loads(manifest.read_text(encoding="utf-8"))["files"] != snapshot["files"]:
            raise ValueError(f"embedded manifest missing or stale: {variant}")
        embedded_inputs = json.loads(manifest.read_text(encoding="utf-8"))["generated_inputs"]
        if embedded_inputs != {name: generated_inputs[name] for name in _generated_names(variant)}:
            raise ValueError(f"generated build input mismatch: {variant}")
        for relative in (f"{stem}.exe", NATIVE_RELATIVE, RUNTIME_RELATIVE,
                         "build-input-manifest.json"):
            path = app / relative
            if not path.is_file():
                raise ValueError(f"missing internal file: {path}")
            internals[f"{stem}/{relative}"] = file_record(path)
        archive = candidate_dir / f"{stem}-portable.zip"
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for path in sorted(app.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(dist))
        installer = dist / f"{stem}-setup.exe"
        if not installer.is_file():
            raise ValueError(f"missing installer: {installer}")
        target = candidate_dir / installer.name
        shutil.copyfile(installer, target)
        artifacts[archive.name] = file_record(archive)
        artifacts[target.name] = file_record(target)
    receipt = {
        "schema_version": 2,
        "candidate_id": candidate_dir.name,
        "commit": snapshot["commit"],
        "source_snapshot_sha256": sha256(candidate_dir / "source-snapshot.json"),
        "generated_inputs": generated_inputs,
        "artifacts": artifacts,
        "internals": internals,
    }
    _write_json(candidate_dir / "candidate-receipt.json", receipt)
    verify_receipt(candidate_dir, receipt)
    return receipt


def verify_receipt(candidate_dir: Path, receipt: dict) -> None:
    if receipt.get("schema_version") == 2:
        snapshot = candidate_dir / "source-snapshot.json"
        if not snapshot.is_file() or sha256(snapshot) != receipt["source_snapshot_sha256"]:
            raise ValueError("source snapshot hash mismatch")
        prebuild = json.loads(snapshot.read_text(encoding="utf-8"))
    else:
        prebuild = None
    for name, expected in receipt.get("generated_inputs", {}).items():
        path = candidate_dir / name
        if not path.is_file() or file_record(path) != expected:
            raise ValueError(f"generated build input hash mismatch: {name}")
    artifacts = receipt["artifacts"]
    if set(artifacts) != _artifact_names():
        raise ValueError("receipt missing or has unexpected zip/setup variant")
    for name, expected in artifacts.items():
        path = candidate_dir / name
        if not path.is_file():
            raise ValueError(f"missing artifact: {name}")
        if file_record(path) != expected:
            raise ValueError(f"artifact hash or size mismatch: {name}")
    for variant in VARIANTS:
        stem = _app_name(variant)
        with zipfile.ZipFile(candidate_dir / f"{stem}-portable.zip") as bundle:
            if bundle.testzip() is not None:
                raise ValueError(f"zip CRC failure: {variant}")
            for relative in (f"{stem}.exe", NATIVE_RELATIVE, RUNTIME_RELATIVE,
                             "build-input-manifest.json"):
                member = f"{stem}/{relative}"
                expected = receipt.get("internals", {}).get(member)
                if expected is None:
                    if receipt.get("schema_version") == 2:
                        raise ValueError(f"missing internal receipt: {member}")
                    continue
                digest = hashlib.sha256()
                size = 0
                with bundle.open(member) as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(block)
                        size += len(block)
                if {"sha256": digest.hexdigest(), "size_bytes": size} != expected:
                    raise ValueError(f"internal hash mismatch: {member}")
            if prebuild is not None:
                embedded = json.loads(bundle.read(f"{stem}/build-input-manifest.json"))
                if embedded["files"] != prebuild["files"] or embedded["commit"] != receipt["commit"]:
                    raise ValueError(f"embedded source snapshot mismatch: {variant}")
                if embedded["generated_inputs"] != {
                    name: receipt["generated_inputs"][name] for name in _generated_names(variant)
                }:
                    raise ValueError(f"embedded generated inputs mismatch: {variant}")
                if embedded["conda_runtime"] != json.loads(bundle.read(f"{stem}/{RUNTIME_RELATIVE}")):
                    raise ValueError(f"embedded runtime manifest mismatch: {variant}")


def _valid_measurement(value: object, minimum: float) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= minimum
    except OverflowError:
        return False


def validate_acceptance(receipt: dict, record: dict, run_id: int, commit: str) -> None:
    if receipt["candidate_id"] != f"run-{run_id}" or record.get("candidate_run_id") != run_id:
        raise ValueError("candidate run ID mismatch")
    if receipt["commit"] != commit or record.get("commit") != commit:
        raise ValueError("candidate commit mismatch")
    expected = {name: value["sha256"] for name, value in receipt["artifacts"].items()}
    if record.get("artifacts") != expected:
        raise ValueError("acceptance artifact hashes do not match every variant")
    if not all(isinstance(record.get(key), str) and record[key].strip()
               for key in ("machine", "evidence")):
        raise ValueError("desktop acceptance machine or evidence missing")
    checks = record.get("desktop_checks", {})
    for variant in VARIANTS:
        if not all(checks.get(variant, {}).get(key) is True for key in CHECKS):
            raise ValueError(f"incomplete desktop acceptance: {variant}")
        resource = record.get("resource_checks", {}).get(variant, {})
        measurements = (("duration_minutes", 5), ("process_tree_cpu_percent_p95", 0),
                        ("process_tree_memory_mb_start", 0),
                        ("process_tree_memory_mb_end", 0))
        if (not all(_valid_measurement(resource.get(key), minimum)
                    for key, minimum in measurements) or
                type(resource.get("residual_processes")) is not int or
                resource["residual_processes"] != 0 or
                resource.get("no_sustained_growth") is not True or
                not isinstance(resource.get("evidence"), str) or
                not resource["evidence"].strip()):
            raise ValueError(f"incomplete resource acceptance: {variant}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("snapshot", "embed", "finalize", "verify", "accept", "runtime-standard"):
        cmd = sub.add_parser(name)
        if name in ("snapshot", "embed", "finalize"):
            cmd.add_argument("--root", type=Path, required=True)
            cmd.add_argument("--dist", type=Path, required=True)
            cmd.add_argument("--candidate-dir", type=Path, required=True)
        elif name in ("verify", "accept"):
            cmd.add_argument("--candidate-dir", type=Path, required=True)
        elif name == "runtime-standard":
            cmd.add_argument("--bundle", type=Path, required=True)
        if name == "snapshot":
            cmd.add_argument("--build-command", required=True)
            cmd.add_argument("--ucrt-bin", type=Path, required=True)
            cmd.add_argument("--language-file", type=Path, required=True)
        if name == "accept":
            cmd.add_argument("--record", type=Path, required=True)
            cmd.add_argument("--run-id", type=int, required=True)
            cmd.add_argument("--commit", required=True)
            cmd.add_argument("--receipt-sha256", required=True)
    args = parser.parse_args()
    if args.command == "accept":
        args.receipt_sha256 = validate_sha256(args.receipt_sha256)
    if args.command == "runtime-standard":
        write_standard_runtime_manifest(args.bundle.resolve())
        return
    candidate_dir = args.candidate_dir.resolve()
    if args.command == "snapshot":
        candidate_dir.mkdir(parents=True, exist_ok=False)
        snapshot = source_snapshot(args.root.resolve(), args.build_command)
        for name, executable, arguments in (
            ("gcc", args.ucrt_bin / "g++.exe", ["--version"]),
            ("cmake", args.ucrt_bin / "cmake.exe", ["--version"]),
            ("ninja", args.ucrt_bin / "ninja.exe", ["--version"]),
            ("inno", "ISCC.exe", ["/?"]),
        ):
            proc = subprocess.run([str(executable), *arguments], capture_output=True, text=True,
                                  errors="replace", timeout=30)
            snapshot["tools"][name] = {"path": str(executable), "version": (proc.stdout + proc.stderr)[:2000]}
        language = args.language_file.resolve()
        if not language.is_file():
            raise ValueError(f"missing installer language input: {language}")
        snapshot["tools"]["inno_language"] = {"path": str(language), **file_record(language)}
        pacman = args.ucrt_bin.resolve().parents[1] / "usr" / "bin" / "pacman.exe"
        snapshot["tools"]["msys_packages"] = subprocess.run(
            [str(pacman), "-Q"], check=True, capture_output=True, text=True,
            errors="replace", timeout=60,
        ).stdout.splitlines()
        _write_json(candidate_dir / "source-snapshot.json", snapshot)
    elif args.command in ("embed", "finalize"):
        snapshot = json.loads((candidate_dir / "source-snapshot.json").read_text(encoding="utf-8"))
        if args.command == "embed":
            embed_manifests(args.root.resolve(), args.dist.resolve(), candidate_dir, snapshot)
        else:
            print(json.dumps(finalize(args.root.resolve(), args.dist.resolve(), candidate_dir, snapshot)))
    else:
        receipt_path = candidate_dir / "candidate-receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        verify_receipt(candidate_dir, receipt)
        if args.command == "accept":
            if sha256(receipt_path) != args.receipt_sha256.lower():
                raise ValueError("candidate receipt hash mismatch")
            record = json.loads(args.record.read_text(encoding="utf-8"))
            validate_acceptance(receipt, record, args.run_id, args.commit)
        print("CANDIDATE_RECEIPT_OK")


if __name__ == "__main__":
    main()
