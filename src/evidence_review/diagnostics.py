"""Dependency-safe runtime provenance diagnostics for the CLI bootstrap."""
from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RuntimeStatus = Literal["OK", "SOURCE_MISMATCH", "DEPENDENCY_MISSING", "NOT_A_CHECKOUT"]
DependencyStatus = Literal["OK", "MISSING"]

_REQUIRED_DEPENDENCIES = (
    ("pypdf", "pypdf"),
    ("pypdfium2", "pypdfium2"),
    ("Pillow", "PIL"),
)


@dataclass(frozen=True, slots=True)
class DependencyDiagnostic:
    distribution: str
    import_name: str
    status: DependencyStatus
    version: str | None

    def to_document(self) -> dict[str, object]:
        return {
            "distribution": self.distribution,
            "import_name": self.import_name,
            "status": self.status,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class RuntimeDiagnostics:
    status: RuntimeStatus
    executable: Path
    command_path: Path | None
    distribution_version: str | None
    working_directory: Path
    repository_root: Path | None
    repository_head: str | None
    package_root: Path | None
    package_checkout_match: bool | None
    dependencies: tuple[DependencyDiagnostic, ...]

    def to_document(self) -> dict[str, object]:
        return {
            "status": self.status,
            "executable": str(self.executable),
            "command_path": None if self.command_path is None else str(self.command_path),
            "distribution_version": self.distribution_version,
            "working_directory": str(self.working_directory),
            "repository_root": None if self.repository_root is None else str(self.repository_root),
            "repository_head": self.repository_head,
            "package_root": None if self.package_root is None else str(self.package_root),
            "package_checkout_match": self.package_checkout_match,
            "dependencies": [item.to_document() for item in self.dependencies],
        }


def _detect_repository_root(start: Path) -> Path | None:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "src" / "ansim_review").is_dir()
            and (candidate / "src" / "evidence_review").is_dir()
        ):
            return candidate
    return None


def _package_root(import_name: str) -> Path | None:
    spec = importlib.util.find_spec(import_name)
    if spec is None:
        return None
    if spec.submodule_search_locations:
        location = next(iter(spec.submodule_search_locations), None)
        return None if location is None else Path(location).resolve()
    if spec.origin:
        return Path(spec.origin).resolve().parent
    return None


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _dependency_diagnostics() -> tuple[DependencyDiagnostic, ...]:
    result: list[DependencyDiagnostic] = []
    for distribution, import_name in _REQUIRED_DEPENDENCIES:
        available = importlib.util.find_spec(import_name) is not None
        result.append(
            DependencyDiagnostic(
                distribution=distribution,
                import_name=import_name,
                status="OK" if available else "MISSING",
                version=_distribution_version(distribution) if available else None,
            )
        )
    return tuple(result)


def _is_packaged_runtime(package_root: Path | None) -> bool:
    if package_root is None:
        return False
    candidates = (package_root.parent, package_root.parent.parent)
    return any(
        (candidate / "VALIDATE.md").is_file()
        or (candidate / "runtime-manifest.json").is_file()
        for candidate in candidates
    )

def _repository_head(repository_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and len(value) == 40 else None


def collect_runtime_diagnostics(
    repository_root: Path | None = None,
) -> RuntimeDiagnostics:
    working_directory = Path.cwd().resolve()
    detected = (
        repository_root.resolve()
        if repository_root is not None
        else _detect_repository_root(working_directory)
    )
    package_root = _package_root("ansim_review")
    dependencies = _dependency_diagnostics()

    package_checkout_match: bool | None = None
    if detected is not None:
        expected = (detected / "src" / "ansim_review").resolve()
        package_checkout_match = package_root == expected

    if (
        detected is not None
        and package_checkout_match is False
        and not _is_packaged_runtime(package_root)
    ):
        status: RuntimeStatus = "SOURCE_MISMATCH"
    elif any(item.status == "MISSING" for item in dependencies):
        status = "DEPENDENCY_MISSING"
    elif detected is None:
        status = "NOT_A_CHECKOUT"
    else:
        status = "OK"

    command = shutil.which("evidence-review")
    return RuntimeDiagnostics(
        status=status,
        executable=Path(sys.executable).resolve(),
        command_path=None if command is None else Path(command).resolve(),
        distribution_version=_distribution_version("evidence-review-system"),
        working_directory=working_directory,
        repository_root=detected,
        repository_head=None if detected is None else _repository_head(detected),
        package_root=package_root,
        package_checkout_match=package_checkout_match,
        dependencies=dependencies,
    )


def preflight_runtime(repository_root: Path | None = None) -> RuntimeDiagnostics:
    return collect_runtime_diagnostics(repository_root)
