from __future__ import annotations

from pathlib import Path

import evidence_review.evidence
import evidence_review.release
import evidence_review.review_packet
import evidence_review.rule_engine


def test_runtime_implementation_is_owned_by_canonical_namespace() -> None:
    modules = (
        evidence_review.evidence,
        evidence_review.release,
        evidence_review.review_packet,
        evidence_review.rule_engine,
    )

    assert all(module.__name__.startswith("evidence_review.") for module in modules)


def test_canonical_production_modules_do_not_import_legacy_namespace() -> None:
    source_root = Path("src/evidence_review")
    offenders = [
        path
        for path in source_root.rglob("*.py")
        if any(
            line.startswith(("import ansim_review", "from ansim_review"))
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    ]

    assert offenders == []




