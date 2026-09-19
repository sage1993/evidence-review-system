from evidence_review.abstention.finalizer import _finalizer_confidence_factors
from evidence_review.confidence.scorer import FactorInput
from evidence_review.contracts.review import TrackBAudit


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
        "0.0", "track_b:audit=INCOMPLETE", "NOT_VERIFIED"
    )
