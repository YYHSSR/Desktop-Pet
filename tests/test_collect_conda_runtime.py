from pathlib import Path
import json

from scripts import candidate_release, collect_conda_runtime


def test_collects_recursive_imports_and_replaces_stale_bytes(tmp_path, monkeypatch):
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
    assert candidate_release.load_runtime_manifest(tmp_path / "bundle", tmp_path / "conda") == manifest
