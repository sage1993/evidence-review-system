from evidence_review.abstention.finalizer import _finalizer_confidence_factors
from evidence_review.confidence.scorer import FactorInput
from evidence_review.contracts.review import TrackBAudit
from evidence_review.llm_layer.track_b import track_b_semantic_gate_status


def test_finalizer_rebinds_calculation_and_track_b_factor_states() -> None:
    factors = {
        "calculation validity": FactorInput("1.0", "legacy"),
        "Track B agreement": FactorInput("1.0", "legacy"),
    }
    audit = TrackBAudit(
        run_id="RUN-1",
        claim_audits=(),
        overall_disposition="INCOMPLETE",
    )

    bound = _finalizer_confidence_factors(factors, (), audit)

    assert bound["calculation validity"] == FactorInput(
        "0.0", "calculation:none", "NOT_APPLICABLE"
    )
    assert bound["Track B agreement"] == FactorInput(
        "0.0", "track_b:semantic_gate=NOT_VERIFIED", "NOT_VERIFIED"
    )


def test_finalizer_does_not_verify_track_b_with_incomplete_required_facets() -> None:
    audit = TrackBAudit(
        run_id="RUN-1",
        claim_audits=(),
        overall_disposition="ACCEPT",
        question_responsiveness="PASS",
        required_facet_completeness="INCOMPLETE",
    )

    bound = _finalizer_confidence_factors(
        {"Track B agreement": FactorInput("1.0", "legacy")},
        (),
        audit,
    )

    assert bound["Track B agreement"] == FactorInput(
        "0.0", "track_b:semantic_gate=NOT_VERIFIED", "NOT_VERIFIED"
    )


def test_question_nonresponsiveness_fails_track_b_agreement() -> None:
    audit = TrackBAudit(
        run_id="RUN-1",
        claim_audits=(),
        overall_disposition="ACCEPT",
        question_responsiveness="FAIL",
        required_facet_completeness="NOT_APPLICABLE",
    )

    assert track_b_semantic_gate_status(audit) == "FAILED"
    assert _finalizer_confidence_factors(
        {"Track B agreement": FactorInput("1.0", "legacy")},
        (),
        audit,
    )["Track B agreement"] == FactorInput(
        "0.0", "track_b:semantic_gate=FAILED", "FAILED"
    )


def test_zero_claim_track_b_cannot_be_verified() -> None:
    audit = TrackBAudit(
        run_id="RUN-1",
        claim_audits=(),
        overall_disposition="INCOMPLETE",
        question_responsiveness="NOT_VERIFIED",
        required_facet_completeness="NOT_APPLICABLE",
    )

    assert track_b_semantic_gate_status(audit) == "NOT_VERIFIED"
