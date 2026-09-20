"""Dependency-safe runtime provenance diagnostics for the CLI bootstrap."""
from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RuntimeStatus = Literal[
    "OK", "SOURCE_MISMATCH", "DEPENDENCY_MISSING", "NOT_A_CHECKOUT", "BYPASS_DETECTED"
]
RuntimeMode = Literal["auto", "development", "installed"]
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
    runtime_mode: str = "development"
    distribution_package_root: Path | None = None
    package_source_sha256: str | None = None
    expected_package_sha256: str | None = None
    identity_error: str | None = None

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
            "runtime_mode": self.runtime_mode,
            "distribution_package_root": (
                None if self.distribution_package_root is None
                else str(self.distribution_package_root)
            ),
            "package_source_sha256": self.package_source_sha256,
            "expected_package_sha256": self.expected_package_sha256,
            "identity_error": self.identity_error,
        }


def _detect_repository_root(start: Path) -> Path | None:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (
            (candidate / "pyproject.toml").is_file()
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


def _installed_identity() -> tuple[Path | None, str | None, str | None, str | None]:
    """Verify wheel-owned content, independently of the current checkout.

    RECORD establishes local installation consistency, not publisher authenticity.
    An externally recorded expected content digest pins a particular candidate.
    Editable distributions do not own the imported source as wheel content.
    """
    try:
        distribution = importlib.metadata.distribution("evidence-review-system")
    except importlib.metadata.PackageNotFoundError:
        return None, None, None, None
    files = distribution.files or ()
    owned = [item for item in files if item.parts[0] == "evidence_review"]
    if not owned:
        return None, distribution.version, None, None
    root = Path(str(distribution.locate_file("evidence_review"))).resolve()
    inventory: list[str] = []
    expected_files: set[Path] = set()
    try:
        for item in owned:
            if "__pycache__" in item.parts or item.suffix == ".pyc":
                continue
            path = Path(str(distribution.locate_file(item))).resolve()
            if not path.is_relative_to(root):
                raise ValueError("distribution file escapes package root")
            if item.hash is None or item.hash.mode != "sha256":
                raise ValueError(f"missing SHA-256 RECORD hash: {item}")
            content = path.read_bytes()
            digest = hashlib.sha256(content).digest()
            recorded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
            if recorded != item.hash.value or len(content) != item.size:
                raise ValueError(f"installed file differs from RECORD: {item}")
            expected_files.add(path)
            inventory.append(f"{item.as_posix()}\0{digest.hex()}\n")
        if root / "__init__.py" not in expected_files:
            raise ValueError("distribution does not own package __init__.py")
        actual_files = {
            path.resolve() for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.relative_to(root).parts
            and path.suffix != ".pyc"
        }
        if actual_files != expected_files:
            raise ValueError("installed package inventory differs from RECORD")
    except (OSError, ValueError) as error:
        return root, distribution.version, None, str(error)
    digest_hex = hashlib.sha256("".join(sorted(inventory)).encode("utf-8")).hexdigest()
    return root, distribution.version, digest_hex, None

def _repository_head(repository_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and len(value) == 40 else None


def collect_runtime_diagnostics(
    repository_root: Path | None = None,
    *,
    runtime_mode: RuntimeMode = "auto",
    expected_package_sha256: str | None = None,
) -> RuntimeDiagnostics:
    working_directory = Path.cwd().resolve()
    detected = (
        repository_root.resolve()
        if repository_root is not None
        else _detect_repository_root(working_directory)
    )
    package_root = _package_root("evidence_review")
    dependencies = _dependency_diagnostics()
    installed_root, version, source_sha, identity_error = _installed_identity()
    selected_mode = runtime_mode
    if selected_mode == "auto":
        selected_mode = "installed" if installed_root is not None else "development"
    if expected_package_sha256 is not None:
        selected_mode = "installed"

    package_checkout_match: bool | None = None
    if detected is not None:
        expected = (detected / "src" / "evidence_review").resolve()
        package_checkout_match = package_root == expected

    status: RuntimeStatus
    if selected_mode == "installed" and os.environ.get("PYTHONPATH"):
        status = "BYPASS_DETECTED"
        identity_error = "production runtime requires PYTHONPATH to be unset"
    elif selected_mode == "installed" and (
        installed_root is None or package_root != installed_root or source_sha is None
    ):
        status = "SOURCE_MISMATCH"
        identity_error = identity_error or "imported package is not the installed wheel"
    elif expected_package_sha256 is not None and source_sha != expected_package_sha256:
        status = "SOURCE_MISMATCH"
        identity_error = "installed package differs from expected candidate digest"
    elif (
        selected_mode == "development"
        and detected is not None
        and package_checkout_match is False
    ):
        status = "SOURCE_MISMATCH"
    elif any(item.status == "MISSING" for item in dependencies):
        status = "DEPENDENCY_MISSING"
    elif detected is None and selected_mode == "development":
        status = "NOT_A_CHECKOUT"
    else:
        status = "OK"

    command = shutil.which("evidence-review")
    return RuntimeDiagnostics(
        status=status,
        executable=Path(sys.executable).resolve(),
        command_path=None if command is None else Path(command).resolve(),
        distribution_version=version,
        working_directory=working_directory,
        repository_root=detected,
        repository_head=None if detected is None else _repository_head(detected),
        package_root=package_root,
        package_checkout_match=package_checkout_match,
        dependencies=dependencies,
        runtime_mode=selected_mode,
        distribution_package_root=installed_root,
        package_source_sha256=source_sha,
        expected_package_sha256=expected_package_sha256,
        identity_error=identity_error,
    )


def preflight_runtime(
    repository_root: Path | None = None,
    *,
    runtime_mode: RuntimeMode = "auto",
    expected_package_sha256: str | None = None,
) -> RuntimeDiagnostics:
    return collect_runtime_diagnostics(
        repository_root, runtime_mode=runtime_mode,
        expected_package_sha256=expected_package_sha256,
    )
