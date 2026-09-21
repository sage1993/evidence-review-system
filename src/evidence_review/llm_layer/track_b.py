"""Independent Track B audit contract and validator."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from evidence_review.contracts.review import (
    AuditDisposition,
    ClaimAudit,
    QuestionResponsiveness,
    RequiredFacetCompleteness,
    TrackBAudit,
    TrackBSemanticGateStatus,
)
from evidence_review.llm_layer.claim_lineage import validate_claim_id_issue_binding
from evidence_review.llm_layer.track_a import ValidatedTrackA

_ALLOWED_DISPOSITIONS = frozenset({"ACCEPT", "REJECT", "INCOMPLETE"})
_ALLOWED_FINDING_CODES = frozenset(
    {
        "MISSING_EXCEPTION",
        "CITATION_MISMATCH",
        "UNSUPPORTED_CLAIM",
        "CALCULATION_MISMATCH",
        "RULE_STATUS_MISMATCH",
        "FINAL_DECISION_LANGUAGE",
        "SOURCE_CONFLICT",
    }
)
_FORBIDDEN_FIELDS = frozenset(
    {
        "rewritten_claims",
        "claims",
        "human_decision",
        "final_decision",
        "confidence",
        "abstention",
    }
)
_ALLOWED_QUESTION_RESPONSIVENESS = frozenset({"PASS", "FAIL", "NOT_VERIFIED"})
_ALLOWED_FACET_COMPLETENESS = frozenset({"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"})


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _string(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise ValueError(f"{field} must be {qualifier}")
    return value


def _derive_overall(audits: Sequence[ClaimAudit]) -> AuditDisposition:
    dispositions = {audit.disposition for audit in audits}
    if "REJECT" in dispositions:
        return "REJECT"
    if "INCOMPLETE" in dispositions:
        return "INCOMPLETE"
    return "ACCEPT"


def required_facet_completeness_status(value: object) -> RequiredFacetCompleteness:
    """Derive required-facet obligation status from immutable request inputs."""
    if value is None:
        return "NOT_APPLICABLE"
    coverage = _sequence(value, "facet_coverage")
    if not coverage:
        return "NOT_APPLICABLE"
    for index, item in enumerate(coverage):
        entry = _mapping(item, f"facet_coverage[{index}]")
        missing = _sequence(
            entry.get("missing_facet_ids", []),
            f"facet_coverage[{index}].missing_facet_ids",
        )
        if missing:
            return "INCOMPLETE"
    return "COMPLETE"


def required_facets_from_inputs(inputs: Mapping[str, object]) -> dict[str, frozenset[str]]:
    """Return planner-declared answer obligations; retrieval coverage is not consulted."""
    plan = inputs.get("question_plan")
    if not isinstance(plan, Mapping):
        return {}
    issue_values = plan.get("issues")
    if not isinstance(issue_values, Sequence) or isinstance(issue_values, (str, bytes, bytearray)):
        return {}
    result: dict[str, frozenset[str]] = {}
    for item in issue_values:
        if not isinstance(item, Mapping) or "required_facet_ids" not in item:
            continue
        issue_id = item.get("id")
        facets = item.get("required_facet_ids")
        if not isinstance(issue_id, str) or not issue_id:
            raise ValueError("question_plan issue id must be non-empty")
        if not isinstance(facets, Sequence) or isinstance(facets, (str, bytes, bytearray)):
            raise ValueError(f"question_plan issue {issue_id} required_facet_ids must be an array")
        if not facets or not all(isinstance(facet, str) and facet for facet in facets):
            raise ValueError(f"question_plan issue {issue_id} required_facet_ids must be non-empty")
        if len(set(facets)) != len(facets):
            raise ValueError(f"question_plan issue {issue_id} required_facet_ids must be unique")
        result[issue_id] = frozenset(cast(str, facet) for facet in facets)
    return result


def required_facet_completeness_for_audit(
    track_a: ValidatedTrackA,
    audits: Sequence[ClaimAudit],
    required_facets_by_issue: Mapping[str, frozenset[str]],
) -> RequiredFacetCompleteness:
    """Derive answer completeness from accepted cited claims, never retrieval similarity."""
    if not required_facets_by_issue:
        return "NOT_APPLICABLE"
    accepted = {audit.claim_id for audit in audits if audit.disposition == "ACCEPT"}
    fulfilled: dict[str, set[str]] = {issue_id: set() for issue_id in required_facets_by_issue}
    for claim in track_a.draft.claims:
        if claim.claim_id not in accepted or not claim.citation_ids:
            continue
        for issue_id in claim.issue_ids:
            required = required_facets_by_issue.get(issue_id)
            if required is not None:
                fulfilled[issue_id].update(set(claim.fulfilled_facet_ids) & required)
    return (
        "COMPLETE"
        if all(
            required <= fulfilled[issue_id]
            for issue_id, required in required_facets_by_issue.items()
        )
        else "INCOMPLETE"
    )


def track_b_semantic_gate_status(audit: TrackBAudit) -> TrackBSemanticGateStatus:
    """Return the final semantic acceptance state for the independent audit."""
    if audit.overall_disposition == "REJECT" or audit.question_responsiveness == "FAIL":
        return "FAILED"
    if audit.overall_disposition != "ACCEPT":
        return "NOT_VERIFIED"
    if audit.question_responsiveness != "PASS":
        return "NOT_VERIFIED"
    if audit.required_facet_completeness == "INCOMPLETE":
        return "NOT_VERIFIED"
    if audit.required_facet_completeness not in {"COMPLETE", "NOT_APPLICABLE"}:
        return "NOT_VERIFIED"
    return "PASS"


def validate_track_b_output(
    value: object,
    track_a: ValidatedTrackA,
    *,
    expected_question: str | None = None,
    expected_facet_completeness: RequiredFacetCompleteness | None = None,
    required_facets_by_issue: Mapping[str, frozenset[str]] | None = None,
) -> TrackBAudit:
    """Validate an independent audit covering every Track A claim exactly once."""
    payload = _mapping(value, "track_b")
    forbidden = sorted(set(payload) & _FORBIDDEN_FIELDS)
    if forbidden:
        raise ValueError(f"track_b contains forbidden fields: {', '.join(forbidden)}")
    required = {
        "run_id",
        "audited_question",
        "question_responsiveness",
        "required_facet_completeness",
        "claim_audits",
        "overall_disposition",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"track_b is missing required fields: {', '.join(missing)}")
    unknown = sorted(set(payload) - required)
    if unknown:
        raise ValueError(f"track_b has unknown fields: {', '.join(unknown)}")

    run_id = _string(payload.get("run_id"), "run_id")
    if run_id != track_a.draft.run_id:
        raise ValueError("track_b run_id does not match track_a")
    audited_question = _string(payload.get("audited_question"), "audited_question")
    question_responsiveness_value = _string(
        payload.get("question_responsiveness"), "question_responsiveness"
    )
    if question_responsiveness_value not in _ALLOWED_QUESTION_RESPONSIVENESS:
        raise ValueError("unsupported question_responsiveness: " + question_responsiveness_value)
    facet_value = _string(
        payload.get("required_facet_completeness"),
        "required_facet_completeness",
    )
    if facet_value not in _ALLOWED_FACET_COMPLETENESS:
        raise ValueError("unsupported required_facet_completeness: " + facet_value)
    if expected_question is not None:
        if audited_question != expected_question and question_responsiveness_value != "FAIL":
            raise ValueError("audited_question does not match the immutable review question")
    if expected_facet_completeness is not None and facet_value != expected_facet_completeness:
        raise ValueError("required_facet_completeness does not match immutable facet coverage")
    for claim in track_a.draft.claims:
        validate_claim_id_issue_binding(claim.claim_id, claim.issue_ids)
    expected_claim_ids = {claim.claim_id for claim in track_a.draft.claims}
    if not expected_claim_ids:
        audits_value = _sequence(payload.get("claim_audits"), "claim_audits")
        if audits_value:
            raise ValueError("empty Track A claim set cannot contain claim audits")
        overall = _string(payload.get("overall_disposition"), "overall_disposition")
        if overall != "INCOMPLETE":
            raise ValueError("empty Track A claim set must be INCOMPLETE")
        if required_facets_by_issue is not None:
            expected = required_facet_completeness_for_audit(track_a, (), required_facets_by_issue)
            if facet_value != expected:
                raise ValueError(
                    "required_facet_completeness does not match cited accepted claim facets"
                )
        return TrackBAudit(
            run_id=run_id,
            claim_audits=(),
            overall_disposition="INCOMPLETE",
            question_responsiveness=cast(QuestionResponsiveness, question_responsiveness_value),
            required_facet_completeness=cast(RequiredFacetCompleteness, facet_value),
        )

    audits: list[ClaimAudit] = []
    seen: set[str] = set()
    for index, item in enumerate(_sequence(payload.get("claim_audits"), "claim_audits")):
        audit_payload = _mapping(item, f"claim_audits[{index}]")
        allowed = {"claim_id", "disposition", "finding_codes", "notes"}
        audit_unknown = sorted(set(audit_payload) - allowed)
        if audit_unknown:
            raise ValueError(
                f"claim_audits[{index}] has unknown fields: {', '.join(audit_unknown)}"
            )
        claim_id = _string(audit_payload.get("claim_id"), f"claim_audits[{index}].claim_id")
        if claim_id in seen:
            raise ValueError(f"duplicate claim audit: {claim_id}")
        if claim_id not in expected_claim_ids:
            raise ValueError(f"unknown audited claim: {claim_id}")
        seen.add(claim_id)
        disposition_value = _string(
            audit_payload.get("disposition"), f"claim_audits[{index}].disposition"
        )
        if disposition_value not in _ALLOWED_DISPOSITIONS:
            raise ValueError(f"unsupported audit disposition: {disposition_value}")
        finding_codes = tuple(
            _string(code, f"claim_audits[{index}].finding_codes[{code_index}]")
            for code_index, code in enumerate(
                _sequence(
                    audit_payload.get("finding_codes", []),
                    f"claim_audits[{index}].finding_codes",
                )
            )
        )
        unsupported = sorted(set(finding_codes) - _ALLOWED_FINDING_CODES)
        if unsupported:
            raise ValueError(f"unsupported Track B finding codes: {', '.join(unsupported)}")
        if disposition_value == "ACCEPT" and finding_codes:
            raise ValueError("ACCEPT audit must not contain finding codes")
        audits.append(
            ClaimAudit(
                claim_id=claim_id,
                disposition=cast(AuditDisposition, disposition_value),
                finding_codes=finding_codes,
                notes=_string(
                    audit_payload.get("notes", ""),
                    f"claim_audits[{index}].notes",
                    allow_empty=True,
                ),
            )
        )

    unaudited = sorted(expected_claim_ids - seen)
    if unaudited:
        raise ValueError(f"unaudited claims: {', '.join(unaudited)}")
    audits.sort(key=lambda audit: audit.claim_id)
    if required_facets_by_issue is not None:
        expected_facet_completeness = required_facet_completeness_for_audit(
            track_a, audits, required_facets_by_issue
        )
        if facet_value != expected_facet_completeness:
            raise ValueError(
                "required_facet_completeness does not match cited accepted claim facets"
            )
    expected_overall = _derive_overall(audits)
    overall_value = _string(payload.get("overall_disposition"), "overall_disposition")
    if overall_value not in _ALLOWED_DISPOSITIONS:
        raise ValueError(f"unsupported audit disposition: {overall_value}")
    if overall_value != expected_overall:
        raise ValueError(f"overall_disposition must be {expected_overall}")
    return TrackBAudit(
        run_id=run_id,
        claim_audits=tuple(audits),
        overall_disposition=expected_overall,
        question_responsiveness=cast(QuestionResponsiveness, question_responsiveness_value),
        required_facet_completeness=cast(RequiredFacetCompleteness, facet_value),
    )
