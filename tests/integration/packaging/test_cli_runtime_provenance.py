from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
from pathlib import Path


def test_doctor_reports_current_checkout(tmp_path: Path) -> None:
    del tmp_path
    repo = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evidence_review",
            "doctor",
            "--repository-root",
            str(repo),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    document = json.loads(completed.stdout)
    assert document["status"] == "OK"
    assert Path(document["repository_root"]).resolve() == repo.resolve()
    assert document["package_checkout_match"] is True


def _run_module(
    repo: Path,
    *arguments: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    if env is not None:
        process_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "evidence_review", *arguments],
        cwd=repo,
        env=process_env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_stale_ansim_source_fails_before_business_runtime_import(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    stale_root = tmp_path / "stale"
    package = stale_root / "ansim_review"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entrypoint.py").write_text(
        'raise AssertionError("business runtime imported before source preflight")\n',
        encoding="utf-8",
    )

    env = {"PYTHONPATH": os.pathsep.join([str(stale_root), str(repo / "src")])}
    completed = _run_module(repo, "query", env=env)

    assert completed.returncode == 2
    document = json.loads(completed.stdout)
    assert document["status"] == "SOURCE_MISMATCH"
    assert "business runtime imported" not in completed.stderr


def _dependency_empty_python(tmp_path: Path) -> Path:
    environment = tmp_path / "dependency-empty"
    venv.EnvBuilder(with_pip=False, clear=True).create(environment)
    if sys.platform == "win32":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def test_doctor_reports_missing_runtime_dependency_without_traceback(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[3]
    python = _dependency_empty_python(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")

    doctor = subprocess.run(
        [
            str(python),
            "-m",
            "evidence_review",
            "doctor",
            "--repository-root",
            str(repo),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert doctor.returncode == 2
    document = json.loads(doctor.stdout)
    assert document["status"] == "DEPENDENCY_MISSING"
    missing = {
        item["distribution"]
        for item in document["dependencies"]
        if item["status"] == "MISSING"
    }
    assert {"pypdf", "pypdfium2", "Pillow"} <= missing
    assert "Traceback" not in doctor.stderr

    version = subprocess.run(
        [str(python), "-m", "evidence_review", "--version"],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert version.returncode == 0
    assert version.stdout.strip()
    assert "Traceback" not in version.stderr
