"""Release integration contracts for ReviewMatter runtime packaging and guidance."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from evidence_review.packaging.codex_bundle import build_codex_bundle
from evidence_review.packaging.web_bundle import (
    build_public_runtime_zip,
    build_web_runtime_zip,
)
from evidence_review.release.validator import validate_release_workspace
from tests.integration.release.test_no_network_runtime import _workspace

ROOT = Path(__file__).resolve().parents[3]
_GUIDANCE_PATHS = (
    ROOT / ".agents/skills/ers-review/SKILL.md",
    ROOT / "README.md",
    ROOT / "docs/README.md",
    ROOT / "docs/CODEX_WORKFLOW.md",
    ROOT / "docs/CONTRACT_GOVERNANCE.md",
    ROOT / "docs/REVIEWER_WORKFLOW.md",
    ROOT / "docs/MANUAL_ACCEPTANCE_POLICY.md",
    ROOT / "AGENTS.md",
)


def test_release_validator_requires_runtime_packages_but_excludes_user_matter_data(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    run_id = _workspace(workspace)
    user_matter = workspace / "matters" / "MATTER-001.json"
    user_matter.parent.mkdir()
    user_matter.write_text('{"user": "mutable matter data"}', encoding="utf-8")
    shutil.copyfile(ROOT / "AGENTS.md", workspace / "AGENTS.md")
    for skill_name in ("ers-pdf", "ers-review"):
        skill_target = workspace / "skills" / skill_name / "SKILL.md"
        skill_target.parent.mkdir(parents=True)
        shutil.copyfile(
            ROOT / "skills" / skill_name / "SKILL.md",
            skill_target,
        )

    passing = validate_release_workspace(workspace, run_id=run_id)

    runtime_packages = passing["runtime_packages"]
    assert runtime_packages["status"] == "PASS"
    assert "matters/MATTER-001.json" not in str(runtime_packages)

    codex_directory = tmp_path / "codex-bundle"
    codex_manifest = build_codex_bundle(workspace, codex_directory)
    codex_paths = {item["path"] for item in codex_manifest["files"]}
    assert not any(
        path == "matters" or path.startswith("matters/") for path in codex_paths
    )
    assert "src/evidence_review/review_matter/schema.sql" in codex_paths

    for builder, filename in (
        (build_web_runtime_zip, "web-runtime.zip"),
        (build_public_runtime_zip, "public-runtime.zip"),
    ):
        archive_path = tmp_path / filename
        builder(workspace, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            archive_paths = set(archive.namelist())
        assert not any(
            path == "matters" or path.startswith("matters/")
            for path in archive_paths
        )
        assert "evidence_review/review_matter/schema.sql" in archive_paths

    (workspace / "src/evidence_review/review_matter/schema.sql").unlink()
    failed = validate_release_workspace(workspace, run_id=run_id)

    assert failed["status"] == "FAIL"
    assert "RUNTIME_PACKAGE_VALIDATION_FAILED" in failed["errors"]
    assert failed["runtime_packages"]["status"] == "FAIL"
    assert "evidence_review/review_matter/schema.sql" in failed["runtime_packages"][
        "missing"
    ]


def test_release_validator_reports_missing_legacy_runtime_package(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    run_id = _workspace(workspace)

    shutil.rmtree(workspace / "src" / "ansim_review")

    report = validate_release_workspace(workspace, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "RUNTIME_PACKAGE_VALIDATION_FAILED" in report["errors"]
    assert report["runtime_packages"]["status"] == "FAIL"
    assert "ansim_review" in report["runtime_packages"]["missing"]


def test_user_guidance_distinguishes_navigation_matter_formalization_and_formal_review() -> None:
    required_statements = (
        "Evidence Navigation",
        "mutable ReviewMatter work state",
        "Formalization",
        "Formal Review",
    )

    for path in _GUIDANCE_PATHS:
        text = " ".join(path.read_text(encoding="utf-8").split())
        for statement in required_statements:
            assert statement in text, f"{path.relative_to(ROOT)} lacks {statement!r}"

        stale_unconditional_statements = (
            "모든 질문을 정식 검토(formal review)",
            "모든 자연어 질문은 retrieval 전에 Question Planner를 거친다.",
            "모든 자연어 질문을 `$ERS_REVIEW`를 통해 실행합니다.",
            "One formal review for every question",
            "Every natural-language question follows this authority chain:",
        )
        for statement in stale_unconditional_statements:
            assert statement not in text, (
                f"{path.relative_to(ROOT)} retains unconditional wording: {statement!r}"
            )
