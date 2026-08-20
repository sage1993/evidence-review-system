from __future__ import annotations

from decimal import Decimal

from evidence_review.contracts.common import BBox
from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.coverage import evaluate_issue_coverage
from evidence_review.retrieval.facets import (
    compile_required_facets,
    evaluate_facet_coverage,
)
from evidence_review.retrieval.fallback import FallbackStage
from evidence_review.retrieval.graph import ReferencePath, ReferenceStep
from evidence_review.retrieval.issue_bundle import (
    IssueCandidateMatch,
    IssueClauseCandidate,
    IssueReferenceMatch,
    IssueRetrievalBundle,
)
from evidence_review.retrieval.models import ChannelScore, RetrievalHit


def _plan(issue_question: str, query: str):
    question = issue_question
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [],
            "assumptions": [],
            "issues": [
                {
                    "id": "I1",
                    "question": issue_question,
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                }
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S1",
                    "issue_ids": ["I1"],
                    "text": query,
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                }
            ],
        },
        question,
    )


def _hit(evidence_id: str, text: str, *, title: str = "검토 기준") -> RetrievalHit:
    return RetrievalHit(
        evidence_id=evidence_id,
        evidence_type="paragraph",
        document_id="DOC-1",
        revision_id="REV-1",
        page_number=1,
        bbox=BBox(10.0, 10.0, 100.0, 20.0),
        source_hash="a" * 64,
        title=title,
        text=text,
        channel_scores=(ChannelScore("clause_citation", Decimal("1"), "C-1"),),
        final_score=Decimal("1"),
    )


def _bundle(text: str, *, title: str = "검토 기준") -> IssueRetrievalBundle:
    clause = ClauseRetrievalHit(
        clause_id="C-1",
        document_id="DOC-1",
        revision_id="REV-1",
        title=title,
        text=text,
        channel_scores=(ChannelScore("clause_phrase", Decimal("1"), text),),
    )
    match = IssueCandidateMatch(
        search_request_id="S1",
        issue_id="I1",
        role="rule",
        query_text="query",
        retrieval_query="query",
        fallback_stage=FallbackStage.PHRASE,
    )
    hit = _hit("E-1", text, title=title)
    return IssueRetrievalBundle(
        candidates=(IssueClauseCandidate(clause=clause, matches=(match,), evidence=(hit,)),),
        selected_evidence=(hit,),
        budget_drops=(),
    )


def test_compiles_distance_issue_into_normal_and_conditional_threshold_facets() -> None:
    plan = _plan(
        (
            "역 승강장 경계에서 300m 떨어진 부지가 역세권 거리 기준을 충족하거나 "
            "조건부 검토 대상이 되는가?"
        ),
        "역세권 승강장 경계 거리 기준",
    )

    facets = compile_required_facets(plan)

    assert [facet.facet_id for facet in facets.by_issue_id("I1").required_facets] == [
        "distance-normal-threshold",
        "distance-conditional-threshold",
    ]


def test_generic_distance_rule_does_not_resolve_issue_without_required_threshold_facets() -> None:
    plan = _plan(
        (
            "역 승강장 경계에서 300m 떨어진 부지가 역세권 거리 기준을 충족하거나 "
            "조건부 검토 대상이 되는가?"
        ),
        "역세권 승강장 경계 거리 기준",
    )
    bundle = _bundle(
        "역세권은 승강장 경계와의 거리 기준을 적용한다.",
        title="역세권 범위",
    )

    facet_report = evaluate_facet_coverage(plan, bundle)
    coverage = evaluate_issue_coverage(plan, bundle, facet_report=facet_report)

    facet_issue = facet_report.by_issue_id("I1")
    assert facet_issue.covered_facet_ids == ()
    assert facet_issue.missing_facet_ids == (
        "distance-normal-threshold",
        "distance-conditional-threshold",
    )
    support = coverage.by_issue_id("I1")
    assert support.status == "UNRESOLVED"
    assert "MISSING_REQUIRED_FACET" in support.gap_codes


def test_distance_clause_with_250_and_conditional_350_covers_both_facets() -> None:
    plan = _plan(
        (
            "역 승강장 경계에서 300m 떨어진 부지가 역세권 거리 기준을 충족하거나 "
            "조건부 검토 대상이 되는가?"
        ),
        "역세권 승강장 경계 거리 기준",
    )
    bundle = _bundle(
        "역세권은 승강장 경계로부터 250m 이내를 원칙으로 하며 통합심의를 거치는 "
        "경우 350m 이내까지 검토할 수 있다.",
        title="역세권 범위",
    )

    facet_report = evaluate_facet_coverage(plan, bundle)

    assert facet_report.by_issue_id("I1").missing_facet_ids == ()
    assert facet_report.by_issue_id("I1").covered_facet_ids == (
        "distance-normal-threshold",
        "distance-conditional-threshold",
    )


def test_facet_evidence_ids_exclude_unrelated_source_elements_from_same_clause() -> None:
    plan = _plan(
        (
            "역 승강장 경계에서 300m 떨어진 부지가 역세권 거리 기준을 충족하거나 "
            "조건부 검토 대상이 되는가?"
        ),
        "역세권 승강장 경계 거리 기준",
    )
    rule_text = (
        "역세권은 승강장 경계로부터 250m 이내를 원칙으로 하며 "
        "통합심의를 거치는 경우 350m 이내까지 검토할 수 있다."
    )
    clause = ClauseRetrievalHit(
        clause_id="C-1",
        document_id="DOC-1",
        revision_id="REV-1",
        title="역세권 범위",
        text=rule_text,
        channel_scores=(ChannelScore("clause_phrase", Decimal("1"), rule_text),),
    )
    match = IssueCandidateMatch(
        search_request_id="S1",
        issue_id="I1",
        role="rule",
        query_text="역세권 승강장 경계 거리 기준",
        retrieval_query="역세권 승강장 경계 거리 기준",
        fallback_stage=FallbackStage.PHRASE,
    )
    direct = _hit("E-DIRECT", rule_text, title="역세권 범위")
    unrelated = _hit(
        "E-CONTEXT",
        "통합심의 신청서류와 제출 절차를 정한다.",
        title="심의 절차",
    )
    bundle = IssueRetrievalBundle(
        candidates=(
            IssueClauseCandidate(
                clause=clause,
                matches=(match,),
                evidence=(direct, unrelated),
            ),
        ),
        selected_evidence=(direct, unrelated),
        budget_drops=(),
    )

    issue = evaluate_facet_coverage(plan, bundle).by_issue_id("I1")

    assert issue.evidence_by_facet == (
        ("distance-normal-threshold", ("E-DIRECT",)),
        ("distance-conditional-threshold", ("E-DIRECT",)),
    )


def test_mixed_dormitory_parking_issue_requires_base_and_mixed_application_facets() -> None:
    plan = _plan(
        "임대형기숙사에 적용할 주차장 설치기준과 복합 시 적용 방식은 무엇인가?",
        "임대형기숙사 주차장 설치기준 복합 적용",
    )
    bundle = _bundle(
        "임대형기숙사의 주차장 설치기준은 별표 2에 따른다.",
        title="임대형기숙사 주차기준",
    )

    facet_report = evaluate_facet_coverage(plan, bundle)

    issue = facet_report.by_issue_id("I1")
    assert "dormitory-parking-standard" in issue.covered_facet_ids
    assert "mixed-use-parking-application" in issue.missing_facet_ids


def test_dormitory_exclusion_does_not_cover_dormitory_parking_facet() -> None:
    plan = _plan(
        "임대형기숙사의 주차장 설치기준은 어떤 규정에 따라 적용되는가?",
        "임대형기숙사 주차장 설치기준 적용 규정",
    )
    bundle = _bundle(
        "사업시행자는 임대형기숙사를 제외한 안심주택인 경우 별도 주차기준을 따른다.",
        title="주차장 설치기준 완화",
    )

    issue = evaluate_facet_coverage(plan, bundle).by_issue_id("I1")

    assert issue.covered_facet_ids == ()
    assert issue.missing_facet_ids == ("dormitory-parking-standard",)


def test_linked_dormitory_clause_is_direct_facet_evidence() -> None:
    plan = _plan(
        "임대형기숙사의 주차장 설치기준은 어떤 규정에 따라 적용되는가?",
        "임대형기숙사 주차장 설치기준 적용 규정",
    )
    exclusion_text = (
        "사업시행자는 임대형기숙사를 제외한 안심주택인 경우 별도 주차기준을 따른다."
    )
    dormitory_text = (
        "사업시행자는 임대형기숙사인 경우 서울특별시 주차장 설치 및 관리 조례 "
        "제20조제1항 별표 2에 따라 주차장을 설치하여야 한다."
    )
    clause = ClauseRetrievalHit(
        clause_id="C-PARKING",
        document_id="DOC-1",
        revision_id="REV-1",
        title="주차장 설치기준 완화",
        text=exclusion_text,
        channel_scores=(ChannelScore("clause_phrase", Decimal("1"), exclusion_text),),
    )
    match = IssueCandidateMatch(
        search_request_id="S1",
        issue_id="I1",
        role="rule",
        query_text="임대형기숙사 주차장 설치기준 적용 규정",
        retrieval_query="임대형기숙사 주차장 설치기준 규정",
        fallback_stage=FallbackStage.LEGAL_COMPOUND_DECOMPOSITION,
    )
    exclusion = _hit("E-EXCLUSION", exclusion_text, title="주차장 설치기준 완화")
    dormitory = _hit("E-DORMITORY", dormitory_text, title="주차장 설치기준 완화")
    reference = IssueReferenceMatch(
        evidence_id="E-DORMITORY",
        issue_id="I1",
        search_request_id="S1",
        role="rule",
        query_text="임대형기숙사 주차장 설치기준 적용 규정",
        retrieval_query="임대형기숙사 주차장 설치기준 규정",
        source_evidence_id="E-EXCLUSION",
        path=ReferencePath(
            target_id="E-DORMITORY",
            steps=(
                ReferenceStep(
                    source_id="E-EXCLUSION",
                    target_id="E-DORMITORY",
                    relation_type="cited_clause",
                    depth=1,
                ),
            ),
        ),
    )
    bundle = IssueRetrievalBundle(
        candidates=(
            IssueClauseCandidate(
                clause=clause,
                matches=(match,),
                evidence=(exclusion,),
            ),
        ),
        selected_evidence=(exclusion, dormitory),
        budget_drops=(),
        reference_matches=(reference,),
    )

    issue = evaluate_facet_coverage(plan, bundle).by_issue_id("I1")

    assert issue.covered_facet_ids == ("dormitory-parking-standard",)
    assert issue.missing_facet_ids == ()
    assert issue.evidence_by_facet == (
        ("dormitory-parking-standard", ("E-DORMITORY",)),
    )
