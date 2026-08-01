from ansim_review.contracts.identifiers import validate_identifier
from ansim_review.parsing.drawing_case import (
    CaseManifest,
    case_manifest_document,
    decode_case_manifest,
    validate_artifact_id,
)


def test_drawing_artifact_ids_reuse_shared_identifier_policy() -> None:
    value = "CASE.2026-001_A"
    assert validate_artifact_id(value, "case_id") == validate_identifier(
        value, "case_id"
    )


def test_case_manifest_accepts_shared_dotted_identifier() -> None:
    manifest = CaseManifest(
        format="ansim/case-manifest",
        version=1,
        case_id="CASE.2026-001",
        policy_id="DRAWING-INTAKE-1",
        sources=(),
        quality_assessments=(),
        candidates=(),
        confirmations=(),
        confirmed_inputs_path=None,
        confirmed_inputs_sha256=None,
    )
    assert decode_case_manifest(case_manifest_document(manifest)) == manifest
