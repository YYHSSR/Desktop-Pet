"""Catch missing release inputs before expensive native or frozen builds."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_local_build_inputs_exist():
    for filename in ("requirements.txt", "requirements-dev.txt", "scripts/pet_entry.py",
                     "scripts/build_native.ps1", "scripts/collect_runtime_licenses.py"):
        assert (ROOT / filename).is_file(), filename


def test_required_portable_notices_exist():
    for filename in ("LICENSE", "DEPENDENCY_LICENSES.md"):
        assert (ROOT / filename).is_file(), filename


def test_local_packaging_keeps_flat_output():
    source = (ROOT / "scripts/build_onedir.ps1").read_text(encoding="utf-8-sig")
    assert "$finalAppDir = Join-Path $root 'dist-onedir'" in source
    assert "--specpath build-onedir" in source
    assert "THIRD_PARTY_NOTICES" not in source
    assert "README.portable" not in source
    assert "--collect-all tzdata" not in source


def test_readme_relative_links_exist():
    source = (ROOT / "README.md").read_text(encoding="utf-8-sig")
    for target in re.findall(r"\]\(([^)]+)\)", source):
        if "://" not in target and not target.startswith("#"):
            assert (ROOT / target.split("#")[0]).exists(), target
