"""Promotion may resume only the same unpublished candidate."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import promote_candidate


IDENTITY = {"run_id": 17, "artifact_id": 42, "commit": "a" * 40,
            "receipt_sha256": "b" * 64}


def _release(*, draft=True, identity=IDENTITY, assets=()):
    return {"tag_name": "v1.2.3", "draft": draft,
            "body": promote_candidate.marker(identity) + "\nGenerated notes",
            "assets": [{"id": i + 1, "name": name, "state": "uploaded", "size": len(name)}
                       for i, name in enumerate(assets)]}


def test_release_state_creates_or_resumes_only_matching_draft():
    assert promote_candidate.release_state(None, "v1.2.3", IDENTITY) == "create"
    assert promote_candidate.release_state(_release(), "v1.2.3", IDENTITY) == "resume"
    for release in (_release(draft=False), _release(identity={**IDENTITY, "artifact_id": 43}),
                    {**_release(), "tag_name": "v1.2.4"}):
        with pytest.raises(ValueError, match="release"):
            promote_candidate.release_state(release, "v1.2.3", IDENTITY)


def test_resume_accepts_matching_assets_and_fills_only_missing(tmp_path):
    candidate = tmp_path / "candidate"
    published = tmp_path / "published"
    candidate.mkdir()
    published.mkdir()
    names = ("first.zip", "second.exe")
    artifacts = {}
    for name in names:
        data = name.encode()
        (candidate / name).write_bytes(data)
        artifacts[name] = {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
    (published / names[0]).write_bytes(names[0].encode())
    assert promote_candidate.missing_assets(_release(assets=(names[0],)), artifacts,
                                            published) == [names[1]]
    (published / names[0]).write_bytes(b"different")
    with pytest.raises(ValueError, match="hash"):
        promote_candidate.missing_assets(_release(assets=(names[0],)), artifacts, published)
    with pytest.raises(ValueError, match="unexpected"):
        promote_candidate.missing_assets(_release(assets=("foreign.txt",)), artifacts, published)


@pytest.mark.parametrize("value", ["", "a" * 63, "g" * 64, '"$(touch pwned)"', "NaN"])
def test_receipt_sha256_rejects_non_hex_input(value):
    with pytest.raises(ValueError, match="SHA-256"):
        promote_candidate.validate_receipt_sha256(value)


def test_receipt_sha256_accepts_uppercase_and_cli_rejects_literal_shell_text(tmp_path):
    assert promote_candidate.validate_receipt_sha256("A" * 64) == "a" * 64
    script = Path(promote_candidate.__file__)
    command = [sys.executable, str(script), "preflight", "--tag", "v1.2.3", "--run-id", "17",
               "--artifact-id", "42", "--commit", "a" * 40,
               "--receipt-sha256", '"$(touch pwned)"', "--body", str(tmp_path / "body.md"),
               "--output", str(tmp_path / "output.txt")]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0
    assert not (tmp_path / "pwned").exists()
    assert not (tmp_path / "body.md").exists()


def test_starter_asset_is_deleted_only_after_uploaded_asset_hash_matches(tmp_path):
    published = tmp_path / "published"
    published.mkdir()
    names = ("first.zip", "second.exe")
    artifacts = {name: {"sha256": hashlib.sha256(name.encode()).hexdigest(),
                        "size_bytes": len(name)} for name in names}
    release = _release(assets=(names[0],))
    release["assets"].append({"id": 123, "name": names[1], "state": "starter", "size": 0})
    events = []

    def download(name):
        events.append(("download", name))
        (published / name).write_bytes(name.encode())

    def delete(asset_id):
        events.append(("delete", asset_id))

    def upload(name):
        events.append(("upload", name))

    promote_candidate.recover_draft(release, "v1.2.3", IDENTITY, artifacts, published,
                                    download, delete, upload)
    assert events == [("download", names[0]), ("delete", 123), ("upload", names[1])]

    events.clear()
    def wrong_download(name):
        events.append(("download", name))
        (published / name).write_bytes(b"wrong")
    with pytest.raises(ValueError, match="hash"):
        promote_candidate.recover_draft(release, "v1.2.3", IDENTITY, artifacts, published,
                                        wrong_download, delete, upload)
    assert events == [("download", names[0])]


def test_starter_recovery_rejects_unsafe_asset_metadata(tmp_path):
    name = "first.zip"
    artifacts = {name: {"sha256": hashlib.sha256(b"first").hexdigest(), "size_bytes": 5}}
    for asset in ({"id": 123, "name": name, "state": "uploaded", "size": 0},
                  {"id": 123, "name": name, "state": "starter", "size": 1},
                  {"id": "123", "name": name, "state": "starter", "size": 0},
                  {"id": 123, "name": name, "state": "mystery", "size": 0}):
        release = _release()
        release["assets"] = [asset]
        with pytest.raises(ValueError, match="asset"):
            promote_candidate.recover_draft(release, "v1.2.3", IDENTITY, artifacts, tmp_path,
                                            lambda _: None, lambda _: None, lambda _: None)
    release = _release()
    release["assets"] = [{"id": 1, "name": name, "state": "starter", "size": 0},
                         {"id": 2, "name": name, "state": "starter", "size": 0}]
    with pytest.raises(ValueError, match="duplicate"):
        promote_candidate.recover_draft(release, "v1.2.3", IDENTITY, artifacts, tmp_path,
                                        lambda _: None, lambda _: None, lambda _: None)


def test_recovery_of_empty_draft_uploads_expected_files_only(tmp_path):
    artifacts = {"first.zip": {"sha256": hashlib.sha256(b"first").hexdigest(),
                               "size_bytes": 5}}
    events = []
    promote_candidate.recover_draft(_release(), "v1.2.3", IDENTITY, artifacts, tmp_path,
                                    lambda name: events.append(("download", name)),
                                    lambda asset_id: events.append(("delete", asset_id)),
                                    lambda name: events.append(("upload", name)))
    assert events == [("upload", "first.zip")]
    events.clear()
    with pytest.raises(ValueError, match="release"):
        promote_candidate.recover_draft(_release(draft=False), "v1.2.3", IDENTITY,
                                        artifacts, tmp_path, lambda name: events.append(name),
                                        lambda asset_id: events.append(asset_id),
                                        lambda name: events.append(name))
    assert events == []


def test_recover_cli_uses_api_and_cli_in_verified_order(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    published = tmp_path / "published"
    artifacts = {}
    for name in ("first.zip", "second.exe"):
        (candidate / name).write_bytes(name.encode())
        artifacts[name] = {"sha256": hashlib.sha256(name.encode()).hexdigest(),
                           "size_bytes": len(name)}
    receipt = {"candidate_id": "run-17", "commit": IDENTITY["commit"], "artifacts": artifacts}
    receipt_path = candidate / "candidate-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    identity = {**IDENTITY, "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
    release = _release(identity=identity, assets=("first.zip",))
    release["id"] = 77
    release["assets"].append({"id": 123, "name": "second.exe", "state": "starter", "size": 0})
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[:2] == ["gh", "api"] and "--method" not in command:
            return SimpleNamespace(stdout=json.dumps(release))
        if command[1:3] == ["release", "download"]:
            (published / "first.zip").write_bytes(b"first.zip")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(promote_candidate.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["promote_candidate.py", "recover", "--release-id", "77",
                                  "--repo", "owner/repo", "--tag", "v1.2.3", "--run-id", "17",
                                  "--artifact-id", "42", "--commit", IDENTITY["commit"],
                                  "--receipt-sha256", identity["receipt_sha256"],
                                  "--candidate-dir", str(candidate), "--published", str(published)])
    promote_candidate.main()
    assert [command[1:3] for command in commands] == [
        ["api", "repos/owner/repo/releases/77"], ["release", "download"],
        ["api", "--method"], ["release", "upload"]]
    assert commands[2][-1] == "repos/owner/repo/releases/assets/123"


def test_workflow_passes_receipt_input_as_data():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" /
                "promote-windows-release.yml").read_text(encoding="utf-8")
    assert '--receipt-sha256 "${{ inputs.receipt_sha256 }}"' not in workflow
    assert workflow.count("RECEIPT_SHA256: ${{ inputs.receipt_sha256 }}") == 3
    assert workflow.count('--receipt-sha256 "$RECEIPT_SHA256"') == 3
