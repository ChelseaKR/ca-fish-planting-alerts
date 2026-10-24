"""scripts/check_greenlight.py: the gate must pass on the real tree and fail on
a seeded violation.

The controls run the real pinned scanner on temporary COPIES of the app
targets. Each one asserts the sabotage changed the copy before it expects the
gate to fail, so a seed that silently did nothing reads as an error, not as a
pass. Without Go the scanner cannot be built: locally these tests skip, under
CI they fail (the same rule the gate itself applies).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_greenlight.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_greenlight", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gl = _load()
IGNORE = shutil.ignore_patterns("build", ".gradle", "node_modules", ".build")


@pytest.fixture(scope="module")
def scanner() -> Path:
    binary = gl.ensure_tool()
    if binary is None:
        if gl.in_ci():
            pytest.fail("greenlight could not be installed, and CI may not skip it")
        pytest.skip("greenlight not installed (no Go toolchain)")
    return binary


def _gate(root: Path, only: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--only", only],
        capture_output=True,
        text=True,
        check=False,
    )


def _copy(tmp_path: Path, *relative: str) -> Path:
    for rel in relative:
        shutil.copytree(REPO_ROOT / rel, tmp_path / rel, ignore=IGNORE)
    return tmp_path


def test_self_test_passes() -> None:
    assert gl.self_test() == []


def test_positive_control_real_tree(scanner: Path) -> None:
    for target in gl.TARGETS:
        done = _gate(REPO_ROOT, target.name)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "1 target(s) clean" in done.stdout


def test_negative_control_ios_missing_privacy_manifest(
    scanner: Path, tmp_path: Path
) -> None:
    root = _copy(tmp_path, "ios/CAFishPlanting")
    assert _gate(root, "ios app").returncode == 0  # the unmodified copy is clean
    manifest = root / "ios/CAFishPlanting/Resources/PrivacyInfo.xcprivacy"
    assert manifest.is_file()
    manifest.unlink()
    assert not manifest.exists()  # the seed changed the copy
    done = _gate(root, "ios app")
    assert done.returncode != 0, done.stdout
    assert "CRITICAL" in done.stdout or "critical" in done.stdout


def test_negative_control_android_restricted_permission(
    scanner: Path, tmp_path: Path
) -> None:
    root = _copy(tmp_path, "android")
    assert _gate(root, "android").returncode == 0
    manifest = root / "android/app/src/main/AndroidManifest.xml"
    before = manifest.read_text(encoding="utf-8")
    seeded = before.replace(
        "<application",
        '<uses-permission android:name="android.permission.READ_SMS" />\n    <application',
        1,
    )
    assert seeded != before  # the seed changed the copy
    manifest.write_text(seeded, encoding="utf-8")
    done = _gate(root, "android")
    assert done.returncode != 0, done.stdout
    assert "[HIGH]" in done.stdout


def test_a_scan_that_read_nothing_fails(scanner: Path, tmp_path: Path) -> None:
    """An empty directory scans as 'no issues'; the gate must not accept that."""
    (tmp_path / "ios/CAFishPlanting").mkdir(parents=True)
    done = _gate(tmp_path, "ios app")
    assert done.returncode != 0, done.stdout


def test_missing_directory_fails(tmp_path: Path) -> None:
    done = _gate(tmp_path, "android")
    assert done.returncode != 0


def test_skip_is_loud_and_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gl, "ensure_tool", lambda: None)
    status = tmp_path / "status"
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert gl.run_gate(REPO_ROOT, gl.TARGETS, status) == 0
    assert "SKIPPED: greenlight not installed" in capsys.readouterr().out
    assert status.read_text(encoding="utf-8").strip() == "skipped"
    assert gl.summary(status) == 0
    assert "NOT counted as passed" in capsys.readouterr().out


def test_skip_in_ci_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gl, "ensure_tool", lambda: None)
    monkeypatch.setenv("CI", "true")
    status = tmp_path / "status"
    assert gl.run_gate(REPO_ROOT, gl.TARGETS, status) == 1
    assert gl.summary(status) == 1
    assert os.environ["CI"] == "true"
    capsys.readouterr()


def test_summary_without_a_status_file_is_not_a_pass(tmp_path: Path) -> None:
    assert gl.summary(tmp_path / "absent") == 1
