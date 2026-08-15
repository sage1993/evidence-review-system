"""Build a deterministic Codex Desktop evidence-review workspace."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.formats import CODEX_WORKSPACE_FORMAT
from evidence_review.packaging.file_selection import iter_bundle_source_files
from evidence_review.packaging.runtime_packages import runtime_package_roots
from evidence_review.release.config import (
    DEFAULT_RELEASE_CONFIG,
    resolve_evidence_database,
)

CODEX_ROUTING_SECTION = """

## Evidence Review Runtime Routing

For a regulatory review question, follow this order:

1. Retrieve citation-resolved evidence from the local SQLite snapshot.
2. Run registered Math Engine formulas; never calculate in prose.
3. Run only approved Rule Engine rules from the active manifest.
4. Produce Track A explanation and Track B audit as separate files.
5. Run the deterministic finalizer and render the reviewer packet.
6. Leave `human_decision` blank. Never decide for the reviewer.

### Codex Desktop shortcuts

- `$ERS_PDF` loads `ers-pdf` and parses the attached or explicitly named PDF.
- `$ERS_REVIEW` loads `ers-review` and answers from parsed evidence before opening the
  finalized review HTML.

Do not use network APIs or remote search from project code.
"""

USER_FACING_SKILL_NAMES = ("ers-pdf", "ers-review")


def render_validation_document() -> str:
    """Return the canonical offline validation procedure for Codex bundles."""
    return (
        "# Offline validation\n\n"
        "Run these checks from the repository or extracted bundle root. "
        "They do not require network access.\n\n"
        "```bash\n"
        "python -m evidence_review --help\n"
        "python -m evidence_review source-batch --help\n"
        "python -m evidence_review rules --help\n"
        "python -m evidence_review documentation validate --help\n"
        "python -m compileall -q src\n"
        "pytest -q\n"
        "ruff check src tests\n"
        "mypy src\n"
        "```\n"
    )


def _copy_tree(source: Path, destination: Path) -> None:
    for path in iter_bundle_source_files(source):
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _manifest(root: Path) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "bundle-manifest.json":
            data = path.read_bytes()
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": len(data),
                }
            )
    return {"format": CODEX_WORKSPACE_FORMAT, "version": 1, "files": files}


def build_codex_bundle(
    workspace_root: Path,
    output_directory: Path,
) -> dict[str, object]:
    """Copy required offline runtime assets and write a canonical manifest."""
    if output_directory.exists():
        raise FileExistsError(output_directory)
    output_directory.mkdir(parents=True)

    agents = (workspace_root / "AGENTS.md").read_text(encoding="utf-8")
    if "## Evidence Review Runtime Routing" not in agents:
        agents += CODEX_ROUTING_SECTION
    (output_directory / "AGENTS.md").write_text(
        agents,
        encoding="utf-8",
        newline="\n",
    )

    for name, source in runtime_package_roots(workspace_root / "src"):
        _copy_tree(source, output_directory / "src" / name)
    _copy_file(
        resolve_evidence_database(workspace_root, DEFAULT_RELEASE_CONFIG),
        output_directory / "evidence" / "evidence.sqlite",
    )
    _copy_tree(
        workspace_root / "rules" / "approved",
        output_directory / "rules" / "approved",
    )
    _copy_tree(
        workspace_root / "rules" / "manifests",
        output_directory / "rules" / "manifests",
    )

    skill_files = sorted(
        source
        for source in (workspace_root / "skills").glob("*/SKILL.md")
        if source.parent.name not in USER_FACING_SKILL_NAMES
    )
    if len(skill_files) != 5:
        raise ValueError("Codex bundle requires exactly five PDF workflow skills")
    for source in skill_files:
        _copy_file(
            source,
            output_directory / "skills" / source.parent.name / "SKILL.md",
        )

    for name in USER_FACING_SKILL_NAMES:
        source = workspace_root / "skills" / name / "SKILL.md"
        if source.is_file():
            _copy_file(
                source,
                output_directory / ".agents" / "skills" / name / "SKILL.md",
            )

    (output_directory / "VALIDATE.md").write_text(
        render_validation_document(),
        encoding="utf-8",
        newline="\n",
    )
    manifest = _manifest(output_directory)
    (output_directory / "bundle-manifest.json").write_bytes(dump_bytes(manifest))
    return manifest
