"""Candidate receipts bind build inputs, artifacts and manual acceptance."""

import hashlib
import json
import subprocess
import zipfile

import pytest

from scripts import candidate_release as candidate


def _git_source(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    source = tmp_path / "source.py"
    source.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "source.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "-qm", "test"], check=True)
    return source


def test_prebuild_snapshot_detects_source_change(tmp_path):
    source = _git_source(tmp_path)
    snapshot = candidate.source_snapshot(tmp_path, "build one; build two")
    assert snapshot["files"]["source.py"] == hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_text("after\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        candidate.verify_source_snapshot(tmp_path, snapshot)


def test_prebuild_snapshot_refuses_uncommitted_tracked_changes(tmp_path):
    source = _git_source(tmp_path)
    source.write_text("uncommitted\n", encoding="utf-8")
    with pytest.raises(ValueError, match="uncommitted"):
        candidate.source_snapshot(tmp_path, "build")


def test_receipt_detects_changed_or_missing_variant(tmp_path):
    artifacts = {}
    for variant in candidate.VARIANTS:
        stem = f"dsh-pet-standalone-{variant}"
        for suffix in ("-portable.zip", "-setup.exe"):
            name = stem + suffix
            if suffix.endswith(".zip"):
                with zipfile.ZipFile(tmp_path / name, "w") as bundle:
                    bundle.writestr("dummy.txt", name)
            else:
                (tmp_path / name).write_bytes(name.encode())
            artifacts[name] = candidate.file_record(tmp_path / name)
    receipt = {"candidate_id": "run-1", "commit": "a" * 40, "artifacts": artifacts}
    candidate.verify_receipt(tmp_path, receipt)
    changed = tmp_path / "dsh-pet-standalone-webm-setup.exe"
    changed.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        candidate.verify_receipt(tmp_path, receipt)
    changed.unlink()
    with pytest.raises(ValueError, match="missing"):
        candidate.verify_receipt(tmp_path, receipt)


def test_acceptance_rejects_wrong_commit_and_incomplete_checks(tmp_path):
    artifacts = {}
    for variant in candidate.VARIANTS:
        stem = f"dsh-pet-standalone-{variant}"
        for suffix in ("-portable.zip", "-setup.exe"):
            name = stem + suffix
            artifacts[name] = {"sha256": hashlib.sha256(name.encode()).hexdigest(), "size_bytes": len(name)}
    receipt = {"candidate_id": "run-17", "commit": "a" * 40, "artifacts": artifacts}
    record = {
        "candidate_run_id": 17,
        "commit": "a" * 40,
        "artifacts": {name: value["sha256"] for name, value in artifacts.items()},
        "desktop_checks": {variant: {key: True for key in candidate.CHECKS}
                           for variant in candidate.VARIANTS},
        "machine": "Windows 11 clean VM",
        "evidence": "manual log 2026-09-26",
        "resource_checks": {variant: {"duration_minutes": 30,
                                      "process_tree_cpu_percent_p95": 4.5,
                                      "process_tree_memory_mb_start": 180,
                                      "process_tree_memory_mb_end": 185,
                                      "residual_processes": 0,
                                      "no_sustained_growth": True,
                                      "evidence": "resource-log.csv"}
                            for variant in candidate.VARIANTS},
    }
    candidate.validate_acceptance(receipt, record, 17, "a" * 40)
    record["candidate_run_id"] = 18
    with pytest.raises(ValueError, match="run ID"):
        candidate.validate_acceptance(receipt, record, 17, "a" * 40)
    record["candidate_run_id"] = 17
    first = "dsh-pet-standalone-webm-chat-portable.zip"
    record["artifacts"][first] = "0" * 64
    with pytest.raises(ValueError, match="artifact hashes"):
        candidate.validate_acceptance(receipt, record, 17, "a" * 40)
    record["artifacts"][first] = artifacts[first]["sha256"]
    record["commit"] = "b" * 40
    with pytest.raises(ValueError, match="commit"):
        candidate.validate_acceptance(receipt, record, 17, "a" * 40)
    record["commit"] = "a" * 40
    record["desktop_checks"]["webm"]["normal_exit"] = False
    with pytest.raises(ValueError, match="webm"):
        candidate.validate_acceptance(receipt, record, 17, "a" * 40)
    record["desktop_checks"]["webm"]["normal_exit"] = True
    del record["desktop_checks"]["webm"]
    with pytest.raises(ValueError, match="webm"):
        candidate.validate_acceptance(receipt, record, 17, "a" * 40)
    record["desktop_checks"]["webm"] = {key: True for key in candidate.CHECKS}
    record["resource_checks"]["webm"]["residual_processes"] = 1
    with pytest.raises(ValueError, match="resource"):
        candidate.validate_acceptance(receipt, record, 17, "a" * 40)
    record["resource_checks"]["webm"]["residual_processes"] = 0
    del record["resource_checks"]["webm-chat"]
    with pytest.raises(ValueError, match="resource"):
        candidate.validate_acceptance(receipt, record, 17, "a" * 40)


def test_full_candidate_finalization_verifies_archive_internals(tmp_path):
    _git_source(tmp_path)
    snapshot = candidate.source_snapshot(tmp_path, "test build")
    dist = tmp_path / "dist"
    out = dist / "candidates" / "run-17"
    out.mkdir(parents=True)
    (out / "source-snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    for variant in candidate.VARIANTS:
        stem = f"dsh-pet-standalone-{variant}"
        (out / f"generated-{variant}-build_variant.py").write_text(f"VARIANT = '{variant}'\n", encoding="utf-8")
        (out / f"generated-{variant}.spec").write_text(f"name = '{stem}'\n", encoding="utf-8")
        app = dist / stem
        native = app / "_internal" / "pet" / "native" / "_bin"
        native.mkdir(parents=True)
        (app / f"{stem}.exe").write_bytes(b"fake executable")
        (native / "pet_core.dll").write_bytes(b"fake DLL")
        (native / "manifest.json").write_text("{}", encoding="utf-8")
        candidate.write_standard_runtime_manifest(app)
        (dist / f"{stem}-setup.exe").write_bytes(b"fake installer")
    candidate.embed_manifests(tmp_path, dist, out, snapshot, tmp_path / "plain-python")
    receipt = candidate.finalize(tmp_path, dist, out, snapshot)
    assert len(receipt["artifacts"]) == 4
    assert len(receipt["internals"]) == 8
    assert len(receipt["generated_inputs"]) == 4
    candidate.verify_receipt(out, receipt)
    generated = out / "generated-webm.spec"
    original = generated.read_bytes()
    generated.write_bytes(b"changed")
    with pytest.raises(ValueError, match="generated build input hash"):
        candidate.verify_receipt(out, receipt)
    generated.write_bytes(original)
    (out / "source-snapshot.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="source snapshot hash"):
        candidate.verify_receipt(out, receipt)


def test_plain_python_runtime_manifest_is_explicit(tmp_path):
    bundle = tmp_path / "app"
    (bundle / "_internal").mkdir(parents=True)
    prefix = tmp_path / "plain-python"
    prefix.mkdir()
    candidate.write_standard_runtime_manifest(bundle)
    runtime = candidate.load_runtime_manifest(bundle, prefix)
    assert runtime == {"schema_version": 2, "provider": "standard", "applicable": False,
                       "dependencies": []}


def test_conda_runtime_manifest_is_required_and_verified(tmp_path):
    bundle = tmp_path / "app"
    internal = bundle / "_internal"
    internal.mkdir(parents=True)
    prefix = tmp_path / "conda"
    (prefix / "Library" / "bin").mkdir(parents=True)
    with pytest.raises(ValueError, match="missing conda runtime"):
        candidate.load_runtime_manifest(bundle, prefix)
    candidate.write_standard_runtime_manifest(bundle)
    with pytest.raises(ValueError, match="provider mismatch"):
        candidate.load_runtime_manifest(bundle, prefix)
    dll = internal / "dependency.dll"
    dll.write_bytes(b"dependency")
    manifest = {"schema_version": 2, "provider": "conda", "applicable": True,
                "conda_bin": str(prefix / "Library" / "bin"), "extension_roots": ["root.pyd"],
                "dependencies": [{"name": dll.name, "sha256": candidate.sha256(dll),
                                  "source": str(prefix / "Library" / "bin" / dll.name),
                                  "imports": []}]}
    (internal / "conda-runtime-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert candidate.load_runtime_manifest(bundle, prefix) == manifest
    dll.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="dependency hash mismatch"):
        candidate.load_runtime_manifest(bundle, prefix)


@pytest.mark.parametrize("field", ["duration_minutes", "process_tree_cpu_percent_p95",
                                   "process_tree_memory_mb_start", "process_tree_memory_mb_end"])
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"),
                                   json.loads("1e309"), pytest.param(10 ** 1000, id="huge-int"),
                                   True, None])
def test_acceptance_rejects_invalid_resource_measurements(field, value):
    receipt = {"candidate_id": "run-17", "commit": "a" * 40, "artifacts": {}}
    resource = {"duration_minutes": 30, "process_tree_cpu_percent_p95": 4.5,
                "process_tree_memory_mb_start": 180, "process_tree_memory_mb_end": 185,
                "residual_processes": 0, "no_sustained_growth": True, "evidence": "resource-log.csv"}
    record = {"candidate_run_id": 17, "commit": "a" * 40, "artifacts": {},
              "machine": "Windows 11", "evidence": "acceptance-log.txt",
              "desktop_checks": {variant: {key: True for key in candidate.CHECKS}
                                 for variant in candidate.VARIANTS},
              "resource_checks": {variant: dict(resource) for variant in candidate.VARIANTS}}
    candidate.validate_acceptance(receipt, record, 17, "a" * 40)
    record["resource_checks"]["webm"][field] = value
    with pytest.raises(ValueError, match="resource"):
        candidate.validate_acceptance(receipt, record, 17, "a" * 40)


def test_acceptance_requires_textual_machine_and_resource_evidence():
    receipt = {"candidate_id": "run-17", "commit": "a" * 40, "artifacts": {}}
    resource = {"duration_minutes": 5, "process_tree_cpu_percent_p95": 0.0,
                "process_tree_memory_mb_start": 1, "process_tree_memory_mb_end": 1,
                "residual_processes": 0, "no_sustained_growth": True, "evidence": "log.csv"}
    record = {"candidate_run_id": 17, "commit": "a" * 40, "artifacts": {},
              "machine": "Windows", "evidence": "evidence.txt",
              "desktop_checks": {variant: {key: True for key in candidate.CHECKS}
                                 for variant in candidate.VARIANTS},
              "resource_checks": {variant: dict(resource) for variant in candidate.VARIANTS}}
    for field in ("machine", "evidence"):
        record[field] = 123
        with pytest.raises(ValueError, match="machine or evidence"):
            candidate.validate_acceptance(receipt, record, 17, "a" * 40)
        record[field] = "Windows" if field == "machine" else "evidence.txt"
    record["resource_checks"]["webm"]["evidence"] = "  "
    with pytest.raises(ValueError, match="resource"):
        candidate.validate_acceptance(receipt, record, 17, "a" * 40)


@pytest.mark.parametrize("value", ["", "f" * 63, "x" * 64, '$(echo unsafe)'])
def test_accept_cli_rejects_invalid_receipt_digest(value):
    with pytest.raises(ValueError, match="SHA-256"):
        candidate.validate_sha256(value)
    assert candidate.validate_sha256("F" * 64) == "f" * 64


def test_collects_recursive_imports_and_replaces_stale_bytes(tmp_path, monkeypatch):
    from pathlib import Path
    from scripts import collect_conda_runtime

    internal = tmp_path / "bundle" / "_internal"
    source = tmp_path / "conda" / "Library" / "bin"
    internal.mkdir(parents=True)
    source.mkdir(parents=True)
    (internal / "_codec.pyd").write_bytes(b"extension")
    (internal / "a.dll").write_bytes(b"stale")
    (source / "a.dll").write_bytes(b"a-v2")
    (source / "b.dll").write_bytes(b"b-v1")
    calls = {
        "_codec.pyd": ["a.dll", "api-ms-win-crt-stdio-l1-1-0.dll"],
        "a.dll": ["b.dll"],
        "b.dll": [],
    }
    monkeypatch.setattr(collect_conda_runtime, "imports", lambda path: calls[path.name])

    manifest = collect_conda_runtime.collect(tmp_path / "bundle", source)

    assert [item["name"] for item in manifest["dependencies"]] == ["a.dll", "b.dll"]
    assert (internal / "a.dll").read_bytes() == b"a-v2"
    assert (internal / "b.dll").read_bytes() == b"b-v1"
    assert all(Path(item["source"]).is_file() for item in manifest["dependencies"])
    assert manifest["schema_version"] == 2
    assert manifest["provider"] == "conda" and manifest["applicable"] is True
    (internal / "conda-runtime-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert candidate.load_runtime_manifest(tmp_path / "bundle", tmp_path / "conda") == manifest
