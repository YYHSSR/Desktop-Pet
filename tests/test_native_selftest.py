"""The frozen entry's native probe must prove the selected backend ran."""

import json

import pytest

from pet.native import loader


def test_native_selftest_uses_default_path_and_records_native_call(tmp_path, monkeypatch):
    if not loader._default_path().is_file():
        pytest.skip("native DLL is not staged")
    monkeypatch.delenv("PET_CORE_DLL", raising=False)
    from pet.native.diagnostics import run_self_test

    output = tmp_path / "result.json"
    assert run_self_test(output, mode="native") == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["requested_mode"] == "native"
    assert result["actual_backend"] == "native"
    assert result["native_calls"] == 1
    assert result["abi_version"] == loader.ABI_VERSION
    assert result["build_id"]
    assert result["dll_path"] == str(loader._default_path())


def test_native_selftest_forced_missing_fails_and_auto_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("PET_CORE_DLL", str(tmp_path / "missing.dll"))
    from pet.native.diagnostics import run_self_test

    native_output = tmp_path / "native.json"
    assert run_self_test(native_output, mode="native") != 0
    native_result = json.loads(native_output.read_text(encoding="utf-8"))
    assert native_result["ok"] is False
    assert native_result["actual_backend"] is None
    assert native_result["native_calls"] == 0

    auto_output = tmp_path / "auto.json"
    assert run_self_test(auto_output, mode="auto") == 0
    auto_result = json.loads(auto_output.read_text(encoding="utf-8"))
    assert auto_result["ok"] is True
    assert auto_result["actual_backend"] == "python"
    assert auto_result["native_calls"] == 0
