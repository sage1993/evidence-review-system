"""Deterministic routing of retrieved evidence into visual related references.

Related references are intentionally weaker than direct references. They expose
retrieved, issue-bound source material that is semantically connected to a
visual finding without promoting it to a deterministic compliance comparison.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

_RELATED_REFERENCE_LIMIT = 5
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")
_STOPWORDS = frozenset(
    {
        "관련",
        "도면",
        "도면의",
        "기준",
        "검토",
        "사용자",
        "파일",
        "주요",
        "구성",
        "적합",
        "여부",
    }
)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _tokens(value: object) -> frozenset[str]:
    return frozenset(
        token.casefold()
        for token in _TOKEN_RE.findall(_text(value))
        if token.casefold() not in _STOPWORDS
    )


def _issue_ids(value: object, field: str) -> frozenset[str]:
    return frozenset(
        _text(item)
        for item in _sequence(value, field)
        if _text(item)
    )


def _search_requests(inputs: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw_plan = inputs.get("question_plan")
    if raw_plan is None:
        return ()
    plan = _mapping(raw_plan, "inputs.question_plan")
    return tuple(
        _mapping(item, f"inputs.question_plan.search_requests[{index}]")
        for index, item in enumerate(
            _sequence(plan.get("search_requests", []), "inputs.question_plan.search_requests")
        )
    )


def _matching_search_request_ids(
    finding: Mapping[str, object],
    inputs: Mapping[str, object],
) -> tuple[str, ...]:
    finding_issues = _issue_ids(finding.get("issue_ids", []), "finding.issue_ids")
    finding_tokens = _tokens(finding.get("title"))
    if not finding_issues or not finding_tokens:
        return ()

    scored: list[tuple[int, str]] = []
    for request in _search_requests(inputs):
        request_id = _text(request.get("id"))
        if not request_id:
            continue
        request_issues = _issue_ids(
            request.get("issue_ids", []),
            f"search_request[{request_id}].issue_ids",
        )
        if not finding_issues.intersection(request_issues):
            continue
        score = len(finding_tokens.intersection(_tokens(request.get("text"))))
        if score:
            scored.append((score, request_id))
    if not scored:
        return ()
    best = max(score for score, _ in scored)
    return tuple(sorted(request_id for score, request_id in scored if score == best))


def _semantic_context_tokens(
    finding: Mapping[str, object],
    inputs: Mapping[str, object],
    request_ids: frozenset[str],
) -> frozenset[str]:
    context: set[str] = set()
    for value in (
        finding.get("title"),
        finding.get("category"),
        finding.get("subject_value"),
    ):
        context.update(_tokens(value))
    for request in _search_requests(inputs):
        if _text(request.get("id")) in request_ids:
            context.update(_tokens(request.get("text")))
    return frozenset(context)


def _lineage_by_evidence(
    inputs: Mapping[str, object],
) -> dict[str, tuple[Mapping[str, object], ...]]:
    result: dict[str, tuple[Mapping[str, object], ...]] = {}
    for index, item in enumerate(
        _sequence(inputs.get("retrieval_lineage", []), "inputs.retrieval_lineage")
    ):
        entry = _mapping(item, f"inputs.retrieval_lineage[{index}]")
        evidence_id = _text(entry.get("evidence_id"))
        if not evidence_id:
            continue
        matches = tuple(
            _mapping(match, f"inputs.retrieval_lineage[{index}].matches[{match_index}]")
            for match_index, match in enumerate(
                _sequence(entry.get("matches", []), f"inputs.retrieval_lineage[{index}].matches")
            )
        )
        result[evidence_id] = matches
    return result


def _reference_document(evidence: Mapping[str, object]) -> dict[str, object] | None:
    citation = _mapping(evidence.get("citation"), "evidence.citation")
    evidence_id = _text(citation.get("evidence_id"))
    text = _text(evidence.get("text"))
    if not evidence_id or not text:
        return None
    return {
        "evidence_id": evidence_id,
        "claim_id": f"RELATED-{evidence_id}",
        "text": text,
        "issue_ids": list(_issue_ids(evidence.get("issue_ids", []), "evidence.issue_ids")),
        "role": _text(evidence.get("role")),
        "citation": dict(citation),
    }


def _lineage_matches_finding(
    matches: Sequence[Mapping[str, object]],
    *,
    finding_issues: frozenset[str],
    request_ids: frozenset[str],
) -> bool:
    for match in matches:
        match_issues = _issue_ids(
            match.get("issue_ids", []), "retrieval_lineage.match.issue_ids"
        )
        if (
            _text(match.get("search_request_id")) in request_ids
            and finding_issues.intersection(match_issues)
        ):
            return True
    return False


def bind_related_retrieval_references(
    bundle: Mapping[str, object],
    inputs: Mapping[str, object],
    findings: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Bind retrieval evidence to semantically matching visual findings.

    The returned bindings never create direct references or change finding
    status. Evidence is eligible only when its retrieval lineage shares both a
    finding issue and the best-matching QuestionPlan search request. Eligible
    evidence is then ranked against the finding and request semantics before
    the result limit is applied, so input order cannot change the selection.
    """
    lineage = _lineage_by_evidence(inputs)
    evidence_values = tuple(
        _mapping(item, f"track_a_bundle.evidence[{index}]")
        for index, item in enumerate(
            _sequence(bundle.get("evidence", []), "track_a_bundle.evidence")
        )
    )
    references_by_id: dict[str, dict[str, object]] = {}
    projected_findings: list[dict[str, object]] = []

    for raw_finding in findings:
        finding = dict(raw_finding)
        finding_issues = _issue_ids(finding.get("issue_ids", []), "finding.issue_ids")
        request_ids = frozenset(_matching_search_request_ids(finding, inputs))
        related_ids: list[str] = []
        related_claim_ids = [
            _text(item)
            for item in _sequence(
                finding.get("related_claim_ids", []), "finding.related_claim_ids"
            )
            if _text(item)
        ]
        if finding_issues and request_ids:
            semantic_tokens = _semantic_context_tokens(finding, inputs, request_ids)
            candidates: list[tuple[int, str, dict[str, object]]] = []
            for evidence in evidence_values:
                evidence_issues = _issue_ids(
                    evidence.get("issue_ids", []), "evidence.issue_ids"
                )
                if not finding_issues.intersection(evidence_issues):
                    continue
                citation = _mapping(evidence.get("citation"), "evidence.citation")
                evidence_id = _text(citation.get("evidence_id"))
                if not evidence_id or not _lineage_matches_finding(
                    lineage.get(evidence_id, ()),
                    finding_issues=finding_issues,
                    request_ids=request_ids,
                ):
                    continue
                reference = _reference_document(evidence)
                if reference is None:
                    continue
                score = len(semantic_tokens.intersection(_tokens(evidence.get("text"))))
                if score:
                    candidates.append((score, evidence_id, reference))

            if candidates:
                best_score = max(score for score, _, _ in candidates)
                selected = sorted(
                    (
                        (evidence_id, reference)
                        for score, evidence_id, reference in candidates
                        if score == best_score
                    ),
                    key=lambda item: item[0],
                )[:_RELATED_REFERENCE_LIMIT]
                for evidence_id, reference in selected:
                    references_by_id.setdefault(evidence_id, reference)
                    related_ids.append(evidence_id)
                    claim_id = cast(str, reference["claim_id"])
                    if claim_id not in related_claim_ids:
                        related_claim_ids.append(claim_id)

        finding["related_evidence_ids"] = related_ids
        finding["related_claim_ids"] = related_claim_ids
        projected_findings.append(finding)

    referenced_ids = {
        evidence_id
        for finding in projected_findings
        for evidence_id in cast(list[str], finding["related_evidence_ids"])
    }
    related_references = [
        references_by_id[evidence_id]
        for evidence_id in sorted(referenced_ids)
        if evidence_id in references_by_id
    ]
    return projected_findings, related_references


def related_reference_claims(visual: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    """Adapt projected related references to the renderer's claim-card shape."""
    claims: list[dict[str, object]] = []
    for index, item in enumerate(
        _sequence(visual.get("related_references", []), "case_visual_review.related_references")
    ):
        reference = _mapping(item, f"case_visual_review.related_references[{index}]")
        claim_id = _text(reference.get("claim_id"))
        text = _text(reference.get("text"))
        citation = dict(_mapping(reference.get("citation"), "related_reference.citation"))
        if not claim_id or not text:
            continue
        citation["quote"] = text
        citation.setdefault(
            "document_name",
            citation.get("title") or citation.get("document_id") or "기준 근거",
        )
        claims.append(
            {
                "claim_id": claim_id,
                "text": text,
                "citations": [citation],
            }
        )
    return tuple(claims)


__all__ = ["bind_related_retrieval_references", "related_reference_claims"]
