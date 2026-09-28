"""Guard draft Release recovery against candidate substitution."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def validate_receipt_sha256(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise ValueError("receipt SHA-256 must be exactly 64 hexadecimal characters")
    return value.lower()


def marker(identity: dict) -> str:
    required = {"run_id", "artifact_id", "commit", "receipt_sha256"}
    if set(identity) != required:
        raise ValueError("invalid release identity fields")
    return f"<!-- dsh-pet-candidate: {json.dumps(identity, sort_keys=True, separators=(',', ':'))} -->"


def release_state(release: dict | None, tag: str, identity: dict) -> str:
    if release is None:
        return "create"
    if release.get("tag_name") != tag or release.get("draft") is not True:
        raise ValueError("release is public or belongs to a different tag")
    body = release.get("body")
    if not isinstance(body, str) or marker(identity) not in body.splitlines():
        raise ValueError("release draft does not identify this exact candidate")
    return "resume"


def _file_record(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return {"sha256": digest.hexdigest(), "size_bytes": path.stat().st_size}


def _classify_assets(release: dict, artifacts: dict) -> tuple[list[str], list[int]]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("release draft asset list missing")
    uploaded: list[str] = []
    starters: list[int] = []
    names: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("invalid release asset metadata")
        name = asset.get("name")
        if not isinstance(name, str) or name not in artifacts:
            raise ValueError("release draft has unexpected asset")
        if name in names:
            raise ValueError("release draft has duplicate assets")
        names.add(name)
        asset_id = asset.get("id")
        if type(asset_id) is not int or asset_id <= 0:
            raise ValueError("release asset ID missing or invalid")
        size = asset.get("size")
        if type(size) is not int or size < 0:
            raise ValueError("release asset size missing or invalid")
        if asset.get("state") == "uploaded" and size == artifacts[name]["size_bytes"]:
            uploaded.append(name)
        elif asset.get("state") == "starter" and size == 0:
            starters.append(asset_id)
        else:
            raise ValueError(f"release asset state or size invalid: {name}")
    return uploaded, starters


def missing_assets(release: dict, artifacts: dict, published: Path) -> list[str]:
    uploaded, _ = _classify_assets(release, artifacts)
    for name in uploaded:
        path = published / name
        if not path.is_file() or _file_record(path) != artifacts[name]:
            raise ValueError(f"release draft asset hash mismatch: {name}")
    return sorted(set(artifacts) - set(uploaded))


def recover_draft(release: dict, tag: str, identity: dict, artifacts: dict, published: Path,
                  download, delete, upload) -> None:
    release_state(release, tag, identity)
    uploaded, starters = _classify_assets(release, artifacts)
    published.mkdir(parents=True, exist_ok=True)
    for name in uploaded:
        download(name)
    missing = missing_assets(release, artifacts, published)
    for asset_id in starters:
        delete(asset_id)
    for name in missing:
        upload(name)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--release-json", type=Path)
    preflight.add_argument("--tag", required=True)
    preflight.add_argument("--run-id", type=int, required=True)
    preflight.add_argument("--artifact-id", type=int, required=True)
    preflight.add_argument("--commit", required=True)
    preflight.add_argument("--receipt-sha256", required=True)
    preflight.add_argument("--body", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)
    recover = sub.add_parser("recover")
    recover.add_argument("--release-id", type=int, required=True)
    recover.add_argument("--repo", required=True)
    recover.add_argument("--tag", required=True)
    recover.add_argument("--run-id", type=int, required=True)
    recover.add_argument("--artifact-id", type=int, required=True)
    recover.add_argument("--commit", required=True)
    recover.add_argument("--receipt-sha256", required=True)
    recover.add_argument("--candidate-dir", type=Path, required=True)
    recover.add_argument("--published", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        identity = {"run_id": args.run_id, "artifact_id": args.artifact_id,
                    "commit": args.commit,
                    "receipt_sha256": validate_receipt_sha256(args.receipt_sha256)}
        release = json.loads(args.release_json.read_text(encoding="utf-8")) if args.release_json else None
        state = release_state(release, args.tag, identity)
        args.body.write_text(marker(identity) + "\n\nVerified Windows candidate.\n", encoding="utf-8")
        with args.output.open("a", encoding="utf-8") as target:
            target.write(f"release_state={state}\n")
    else:
        if (args.release_id <= 0 or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo)
                is None):
            raise ValueError("invalid release ID or repository")
        identity = {"run_id": args.run_id, "artifact_id": args.artifact_id,
                    "commit": args.commit,
                    "receipt_sha256": validate_receipt_sha256(args.receipt_sha256)}
        candidate = args.candidate_dir.resolve()
        receipt_path = candidate / "candidate-receipt.json"
        if _file_record(receipt_path)["sha256"] != identity["receipt_sha256"]:
            raise ValueError("candidate receipt SHA-256 mismatch")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (receipt.get("candidate_id") != f"run-{args.run_id}" or
                receipt.get("commit") != args.commit):
            raise ValueError("candidate receipt identity mismatch")
        for name, expected in receipt["artifacts"].items():
            if _file_record(candidate / name) != expected:
                raise ValueError(f"candidate artifact hash mismatch: {name}")
        result = subprocess.run(["gh", "api", f"repos/{args.repo}/releases/{args.release_id}"],
                                check=True, capture_output=True, text=True)
        release = json.loads(result.stdout)
        if release.get("id") != args.release_id:
            raise ValueError("release ID changed during recovery")

        def download(name: str) -> None:
            subprocess.run(["gh", "release", "download", args.tag, "--dir", str(args.published),
                            "--pattern", name], check=True)

        def delete(asset_id: int) -> None:
            subprocess.run(["gh", "api", "--method", "DELETE",
                            f"repos/{args.repo}/releases/assets/{asset_id}"], check=True)

        def upload(name: str) -> None:
            subprocess.run(["gh", "release", "upload", args.tag, str(candidate / name)], check=True)

        recover_draft(release, args.tag, identity, receipt["artifacts"], args.published,
                      download, delete, upload)


if __name__ == "__main__":
    main()
