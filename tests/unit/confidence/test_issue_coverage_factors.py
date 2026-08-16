from evidence_review.confidence.coverage import apply_issue_coverage_factors
from evidence_review.retrieval.coverage import CoverageReport, IssueSupport


def _request() -> dict[str, object]:
    names = (
        "source completeness",
        "traceability",
        "parse quality",
        "human review status",
        "rule coverage",
        "input completeness",
        "calculation validity",
        "Track B agreement",
        "source freshness",
        "unresolved conflict factor",
    )
    return {
        "confidence_input": {
            "factors": {
                name: {"value": "1.0", "source": "legacy"}
                for name in names
            }
        }
    }


def _issue(
    issue_id: str,
    status: str,
    *,
    covered_roles: tuple[str, ...] = (),
    missing_roles: tuple[str, ...] = (),
    gap_codes: tuple[str, ...] = (),
) -> IssueSupport:
    return IssueSupport(
        issue_id=issue_id,
        status=status,
        evidence_ids=(),
        covered_roles=covered_roles,
        missing_roles=missing_roles,
        gap_codes=gap_codes,
    )


def test_issue_coverage_updates_all_coverage_dependent_confidence_factors() -> None:
    report = CoverageReport(
        issues=(
            _issue("I1", "RESOLVED", covered_roles=("rule",)),
            _issue(
                "I2",
                "SOURCE_MISSING",
                covered_roles=("rule",),
                gap_codes=("SOURCE_NOT_INGESTED",),
            ),
        )
    )

    result = apply_issue_coverage_factors(_request(), report)
    factors = result["confidence_input"]["factors"]

    assert factors["source completeness"] == {
        "value": "0.5000",
        "source": "issue_coverage:source_complete=1/2",
    }
    assert factors["traceability"] == {
        "value": "0.5000",
        "source": "issue_coverage:traceable=1/2",
    }
    assert factors["rule coverage"] == {
        "value": "1.0000",
        "source": "issue_coverage:required_roles=2/2",
    }
    assert factors["input completeness"] == {
        "value": "0.5000",
        "source": "issue_coverage:complete_inputs=1/2",
    }
    assert factors["parse quality"] == {
        "value": "1.0000",
        "source": "issue_coverage:parse_gap_free=2/2",
    }
    assert factors["human review status"] == {
        "value": "0.0000",
        "source": "human_review:pending",
    }
    assert factors["unresolved conflict factor"] == {
        "value": "1.0000",
        "source": "issue_coverage:conflicts=0/2",
    }


def test_retrieval_miss_is_not_reported_as_complete_source_input() -> None:
    report = CoverageReport(
        issues=(
            _issue("I1", "RESOLVED", covered_roles=("rule",)),
            _issue(
                "I2",
                "UNRESOLVED",
                missing_roles=("rule",),
                gap_codes=("RETRIEVAL_MISS",),
            ),
        )
    )

    factors = apply_issue_coverage_factors(_request(), report)["confidence_input"]["factors"]

    assert factors["source completeness"]["value"] == "0.5000"
    assert factors["traceability"]["value"] == "0.5000"
    assert factors["input completeness"]["value"] == "0.5000"


def test_source_missing_with_local_rule_is_not_complete_or_traceable() -> None:
    report = CoverageReport(
        issues=(
            _issue(
                "I1",
                "SOURCE_MISSING",
                covered_roles=("rule",),
                gap_codes=("REFERENCE_TARGET_MISSING",),
            ),
        )
    )

    factors = apply_issue_coverage_factors(_request(), report)["confidence_input"]["factors"]

    assert factors["rule coverage"]["value"] == "1.0000"
    assert factors["source completeness"]["value"] == "0.0000"
    assert factors["traceability"]["value"] == "0.0000"
    assert factors["input completeness"]["value"] == "0.0000"


def test_parse_gap_and_conflict_are_reflected_without_changing_policy_weights() -> None:
    report = CoverageReport(
        issues=(
            _issue(
                "I1",
                "UNRESOLVED",
                missing_roles=("rule",),
                gap_codes=("PARSE_GAP",),
            ),
            _issue(
                "I2",
                "CONFLICT",
                covered_roles=("rule",),
                gap_codes=("CONFLICTING_RULES",),
            ),
        )
    )

    factors = apply_issue_coverage_factors(_request(), report)["confidence_input"]["factors"]
    assert factors["parse quality"]["value"] == "0.5000"
    assert factors["unresolved conflict factor"]["value"] == "0.0000"


def test_empty_coverage_report_is_rejected() -> None:
    try:
        apply_issue_coverage_factors(_request(), CoverageReport(issues=()))
    except ValueError as error:
        assert "issue coverage" in str(error)
    else:
        raise AssertionError("empty issue coverage accepted")
