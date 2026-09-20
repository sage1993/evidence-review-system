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


def test_stale_legacy_package_cannot_override_canonical_runtime(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    stale_root = tmp_path / "stale"
    package = stale_root / "ansim_review"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entrypoint.py").write_text(
        'raise AssertionError("legacy runtime imported by canonical package")\n',
        encoding="utf-8",
    )

    env = {"PYTHONPATH": os.pathsep.join([str(stale_root), str(repo / "src")])}
    completed = _run_module(repo, "query", env=env)

    assert completed.returncode == 2
    assert "legacy runtime imported by canonical package" not in completed.stderr
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


def test_real_wheel_authority_and_shadow_rejection(tmp_path: Path) -> None:
    """Exercise the installed console script; no source injection for normal runs."""
    repo = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    wheels = tmp_path / "wheels"
    build = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(repo), "--no-deps",
         "--no-build-isolation", "--wheel-dir", str(wheels)],
        cwd=tmp_path, env=env, text=True, capture_output=True, check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheel, = wheels.glob("*.whl")
    environment = tmp_path / "installed"
    venv.EnvBuilder(with_pip=True).create(environment)
    scripts = environment / ("Scripts" if sys.platform == "win32" else "bin")
    python = scripts / ("python.exe" if sys.platform == "win32" else "python")
    cli = scripts / ("evidence-review.exe" if sys.platform == "win32" else "evidence-review")
    install = subprocess.run(
        [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
        cwd=tmp_path, env=env, text=True, capture_output=True, check=False,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    def doctor(cwd: Path, process_env: dict[str, str], *extra: str) -> dict:
        result = subprocess.run(
            [str(cli), "--runtime-mode", "installed", *extra, "doctor"],
            cwd=cwd, env=process_env, text=True, capture_output=True, check=False,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "Traceback" not in result.stderr
        return json.loads(result.stdout)

    # Dependencies are deliberately absent: wheel provenance succeeds first,
    # then dependency preflight fails. This is not full runtime acceptance.
    outside = doctor(tmp_path, env)
    nearby = doctor(repo, env)
    assert outside["status"] == nearby["status"] == "DEPENDENCY_MISSING"
    assert outside["runtime_mode"] == nearby["runtime_mode"] == "installed"
    assert outside["repository_root"] is None
    assert nearby["package_checkout_match"] is False
    assert outside["package_source_sha256"] == nearby["package_source_sha256"]
    assert Path(outside["package_root"]).is_relative_to(environment)
    assert doctor(tmp_path, env, "--expected-package-sha256", "0" * 64)["status"] == (
        "SOURCE_MISMATCH"
    )
    shadow = doctor(repo, {**env, "PYTHONPATH": str(repo / "src")})
    assert shadow["status"] == "BYPASS_DETECTED"
    assert Path(shadow["package_root"]).resolve() == repo / "src" / "evidence_review"
