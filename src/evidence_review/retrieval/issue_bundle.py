"""Issue-aware clause retrieval with deterministic fairness and global budgets."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from evidence_review.contracts.question_plan import (
    EvidenceRole,
    QuestionIssue,
    QuestionPlan,
    SearchRequest,
)
from evidence_review.retrieval.clause_resolution import (
    ClauseRetrievalHit,
    resolve_clause_to_evidence,
)
from evidence_review.retrieval.fallback import (
    FallbackStage,
    FallbackTrace,
    legal_compound_queries,
    search_clause_with_fallback,
)
from evidence_review.retrieval.graph import (
    MissingReference,
    ReferencePath,
    traverse_relations_with_provenance,
)
from evidence_review.retrieval.index import search_fts_token_prefix_and
from evidence_review.retrieval.models import ChannelScore, RetrievalHit
from evidence_review.retrieval.policy import RetrievalPolicy
from evidence_review.retrieval.relevance import evaluate_issue_clause_relevance

BudgetDropReason = Literal[
    "QUERY_BUDGET",
    "CANDIDATE_BUDGET",
    "REFERENCE_EVIDENCE_BUDGET",
]


@dataclass(frozen=True, slots=True)
class BudgetDrop:
    issue_id: str
    search_request_id: str
    reason: BudgetDropReason
    clause_id: str | None = None
    evidence_id: str | None = None


@dataclass(frozen=True, slots=True)
class IssueRelevanceDecision:
    issue_id: str
    search_request_id: str
    clause_id: str
    accepted: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IssueFallbackTrace:
    issue_id: str
    search_request_id: str
    role: EvidenceRole
    stage: FallbackStage
    input_query: str
    derived_query: str
    hit_count: int
    relevance_decisions: tuple[IssueRelevanceDecision, ...] = ()


@dataclass(frozen=True, slots=True)
class IssueCandidateMatch:
    search_request_id: str
    issue_id: str
    role: EvidenceRole
    query_text: str
    retrieval_query: str
    fallback_stage: FallbackStage


@dataclass(frozen=True, slots=True)
class IssueClauseCandidate:
    clause: ClauseRetrievalHit
    matches: tuple[IssueCandidateMatch, ...]
    evidence: tuple[RetrievalHit, ...] = ()
    evidence_budget_limited: bool = False

    @property
    def issue_ids(self) -> tuple[str, ...]:
        return tuple(sorted({match.issue_id for match in self.matches}))

    @property
    def search_request_ids(self) -> tuple[str, ...]:
        return tuple(sorted({match.search_request_id for match in self.matches}))

    @property
    def roles(self) -> tuple[EvidenceRole, ...]:
        return tuple(sorted({match.role for match in self.matches}))


@dataclass(frozen=True, slots=True)
class IssueReferenceMatch:
    evidence_id: str
    issue_id: str
    search_request_id: str
    role: EvidenceRole
    query_text: str
    retrieval_query: str
    source_evidence_id: str
    path: ReferencePath


@dataclass(frozen=True, slots=True)
class IssueReferenceMissing:
    issue_id: str
    reference: MissingReference


@dataclass(frozen=True, slots=True)
class IssueRetrievalBundle:
    candidates: tuple[IssueClauseCandidate, ...]
    selected_evidence: tuple[RetrievalHit, ...]
    budget_drops: tuple[BudgetDrop, ...]
    fallback_traces: tuple[IssueFallbackTrace, ...] = ()
    reference_matches: tuple[IssueReferenceMatch, ...] = ()
    reference_missing: tuple[IssueReferenceMissing, ...] = ()


@dataclass(frozen=True, slots=True)
class _IssueRoleBucket:
    issue_id: str
    role: EvidenceRole
    candidates: tuple[IssueClauseCandidate, ...]


def _match_sort_key(match: IssueCandidateMatch) -> tuple[str, str, str, str, str, str]:
    return (
        match.issue_id,
        match.role,
        match.search_request_id,
        match.query_text,
        match.fallback_stage.value,
        match.retrieval_query,
    )


def _drop_sort_key(drop: BudgetDrop) -> tuple[str, str, str, str, str]:
    return (
        drop.issue_id,
        drop.search_request_id,
        drop.reason,
        drop.clause_id or "",
        drop.evidence_id or "",
    )


def _reference_match_sort_key(
    match: IssueReferenceMatch,
) -> tuple[str, str, str, str, str]:
    return (
        match.issue_id,
        match.search_request_id,
        match.evidence_id,
        match.source_evidence_id,
        match.role,
    )


def _merge_channel_scores(
    left: tuple[ChannelScore, ...],
    right: tuple[ChannelScore, ...],
) -> tuple[ChannelScore, ...]:
    by_key: dict[tuple[str, str], ChannelScore] = {}
    for channel in (*left, *right):
        key = (channel.channel, channel.detail)
        current = by_key.get(key)
        if current is None or channel.score > current.score:
            by_key[key] = channel
    return tuple(
        sorted(
            by_key.values(),
            key=lambda item: (-item.score, item.channel, item.detail),
        )
    )


def _merge_clause_hit(
    left: ClauseRetrievalHit,
    right: ClauseRetrievalHit,
) -> ClauseRetrievalHit:
    if left.clause_id != right.clause_id:
        raise ValueError("cannot merge different clause ids")
    base = right if right.score > left.score else left
    return replace(
        base,
        channel_scores=_merge_channel_scores(left.channel_scores, right.channel_scores),
    )


def _merge_retrieval_hit(left: RetrievalHit, right: RetrievalHit) -> RetrievalHit:
    if left.evidence_id != right.evidence_id:
        raise ValueError("cannot merge different evidence ids")
    merged = left
    for channel in right.channel_scores:
        merged = merged.with_channel(channel)
    for match in right.matches:
        merged = merged.with_match(match)
    if right.final_score > merged.final_score:
        merged = merged.with_final_score(right.final_score)
    return merged


def _merge_candidate(
    left: IssueClauseCandidate,
    right: IssueClauseCandidate,
) -> IssueClauseCandidate:
    if left.clause.clause_id != right.clause.clause_id:
        raise ValueError("cannot merge different clause candidates")
    matches = {
        (
            match.issue_id,
            match.role,
            match.search_request_id,
            match.query_text,
            match.fallback_stage.value,
            match.retrieval_query,
        ): match
        for match in (*left.matches, *right.matches)
    }
    evidence_by_id = {item.evidence_id: item for item in left.evidence}
    evidence_order = [item.evidence_id for item in left.evidence]
    for item in right.evidence:
        current = evidence_by_id.get(item.evidence_id)
        if current is None:
            evidence_by_id[item.evidence_id] = item
            evidence_order.append(item.evidence_id)
        else:
            evidence_by_id[item.evidence_id] = _merge_retrieval_hit(current, item)
    return IssueClauseCandidate(
        clause=_merge_clause_hit(left.clause, right.clause),
        matches=tuple(sorted(matches.values(), key=_match_sort_key)),
        evidence=tuple(evidence_by_id[evidence_id] for evidence_id in evidence_order),
        evidence_budget_limited=(
            left.evidence_budget_limited or right.evidence_budget_limited
        ),
    )


def _requests_for_issue(
    plan: QuestionPlan,
    issue: QuestionIssue,
    policy: RetrievalPolicy,
) -> tuple[tuple[SearchRequest, ...], tuple[BudgetDrop, ...]]:
    by_role: dict[EvidenceRole, list[SearchRequest]] = {
        role: [] for role in issue.required_evidence_roles
    }
    for request in plan.search_requests:
        if issue.id in request.issue_ids and request.role in by_role:
            by_role[request.role].append(request)

    selected: list[SearchRequest] = []
    selected_ids: set[str] = set()
    depth = 0
    while len(selected) < policy.max_queries_per_issue:
        added = False
        for role in issue.required_evidence_roles:
            requests = by_role[role]
            if depth >= len(requests):
                continue
            request = requests[depth]
            selected.append(request)
            selected_ids.add(request.id)
            added = True
            if len(selected) >= policy.max_queries_per_issue:
                break
        if not added:
            break
        depth += 1

    drops = tuple(
        BudgetDrop(
            issue_id=issue.id,
            search_request_id=request.id,
            reason="QUERY_BUDGET",
        )
        for role in issue.required_evidence_roles
        for request in by_role[role]
        if request.id not in selected_ids
    )
    return tuple(selected), tuple(sorted(drops, key=_drop_sort_key))


def _bind_fallback_trace(
    issue: QuestionIssue,
    request: SearchRequest,
    trace: FallbackTrace,
) -> IssueFallbackTrace:
    return IssueFallbackTrace(
        issue_id=issue.id,
        search_request_id=request.id,
        role=request.role,
        stage=trace.stage,
        input_query=trace.input_query,
        derived_query=trace.derived_query,
        hit_count=trace.hit_count,
        relevance_decisions=tuple(
            IssueRelevanceDecision(
                issue_id=issue.id,
                search_request_id=request.id,
                clause_id=decision.clause_id,
                accepted=decision.accepted,
                reason_codes=decision.reason_codes,
            )
            for decision in trace.relevance_decisions
        ),
    )


def _legacy_queries_from_fallback(
    request: SearchRequest,
    traces: Sequence[FallbackTrace],
) -> tuple[str, ...]:
    allowed = {
        FallbackStage.FACT_DECONTAMINATED,
        FallbackStage.APPROVED_ALIAS,
        FallbackStage.LEGAL_COMPOUND_DECOMPOSITION,
        FallbackStage.CORE_TOKEN_AND,
    }
    values = [
        request.text,
        *(trace.derived_query for trace in traces if trace.stage in allowed),
        *legal_compound_queries(request.text),
    ]
    return tuple(dict.fromkeys(value for value in values if value))


def _legacy_clause(hit: RetrievalHit) -> ClauseRetrievalHit:
    return ClauseRetrievalHit(
        clause_id=hit.evidence_id,
        document_id=hit.document_id,
        revision_id=hit.revision_id,
        title=hit.title,
        text=hit.text,
        channel_scores=hit.channel_scores,
    )


def _bucket_candidates(
    connection: sqlite3.Connection,
    issue: QuestionIssue,
    role: EvidenceRole,
    requests: tuple[SearchRequest, ...],
    fact_texts: Sequence[str],
    policy: RetrievalPolicy,
) -> tuple[tuple[IssueClauseCandidate, ...], tuple[IssueFallbackTrace, ...]]:
    by_clause: dict[str, IssueClauseCandidate] = {}
    traces: list[IssueFallbackTrace] = []
    for request in requests:
        if request.role != role:
            continue
        result = search_clause_with_fallback(
            connection,
            request.text,
            fact_texts=fact_texts,
            limit=policy.per_issue_role_limit,
        )
        traces.extend(_bind_fallback_trace(issue, request, trace) for trace in result.traces)
        if result.success_stage is None or result.successful_query is None:
            legacy_queries = _legacy_queries_from_fallback(request, result.traces)
            legacy_hits: tuple[RetrievalHit, ...] = ()
            legacy_query = request.text
            for candidate_query in legacy_queries:
                raw_legacy_hits = search_fts_token_prefix_and(
                    connection,
                    candidate_query,
                    limit=policy.per_issue_role_limit,
                )
                accepted_legacy: list[RetrievalHit] = []
                legacy_decisions: list[IssueRelevanceDecision] = []
                for legacy_hit in raw_legacy_hits:
                    decision = evaluate_issue_clause_relevance(
                        issue_id=issue.id,
                        issue_question=issue.question,
                        search_request_id=request.id,
                        query_text=request.text,
                        clause=_legacy_clause(legacy_hit),
                    )
                    legacy_decisions.append(
                        IssueRelevanceDecision(
                            issue_id=issue.id,
                            search_request_id=request.id,
                            clause_id=legacy_hit.evidence_id,
                            accepted=decision.accepted,
                            reason_codes=decision.reason_codes,
                        )
                    )
                    if decision.accepted:
                        accepted_legacy.append(legacy_hit)
                traces.append(
                    IssueFallbackTrace(
                        issue_id=issue.id,
                        search_request_id=request.id,
                        role=role,
                        stage=FallbackStage.LEGACY_ELEMENT,
                        input_query=request.text,
                        derived_query=candidate_query,
                        hit_count=len(accepted_legacy),
                        relevance_decisions=tuple(legacy_decisions),
                    )
                )
                if accepted_legacy:
                    legacy_hits = tuple(accepted_legacy)
                    legacy_query = candidate_query
                    break
            if not legacy_hits:
                continue
            for legacy_hit in legacy_hits:
                candidate = IssueClauseCandidate(
                    clause=_legacy_clause(legacy_hit),
                    matches=(
                        IssueCandidateMatch(
                            search_request_id=request.id,
                            issue_id=issue.id,
                            role=role,
                            query_text=request.text,
                            retrieval_query=legacy_query,
                            fallback_stage=FallbackStage.LEGACY_ELEMENT,
                        ),
                    ),
                    evidence=(legacy_hit,),
                )
                current = by_clause.get(candidate.clause.clause_id)
                by_clause[candidate.clause.clause_id] = (
                    candidate
                    if current is None
                    else _merge_candidate(current, candidate)
                )
            continue
        for clause_hit in result.hits:
            candidate = IssueClauseCandidate(
                clause=clause_hit,
                matches=(
                    IssueCandidateMatch(
                        search_request_id=request.id,
                        issue_id=issue.id,
                        role=role,
                        query_text=request.text,
                        retrieval_query=result.successful_query,
                        fallback_stage=result.success_stage,
                    ),
                ),
            )
            current = by_clause.get(clause_hit.clause_id)
            by_clause[clause_hit.clause_id] = (
                candidate if current is None else _merge_candidate(current, candidate)
            )
    candidates = tuple(
        sorted(
            by_clause.values(),
            key=lambda item: (-item.clause.score, item.clause.clause_id),
        )[: policy.per_issue_role_limit]
    )
    return candidates, tuple(traces)


def _global_round_robin(
    buckets: tuple[_IssueRoleBucket, ...],
    policy: RetrievalPolicy,
) -> tuple[tuple[IssueClauseCandidate, ...], tuple[BudgetDrop, ...]]:
    selected: dict[str, IssueClauseCandidate] = {}
    order: list[str] = []
    drops: list[BudgetDrop] = []
    max_depth = max((len(bucket.candidates) for bucket in buckets), default=0)

    for rank in range(max_depth):
        for bucket in buckets:
            if rank >= len(bucket.candidates):
                continue
            candidate = bucket.candidates[rank]
            clause_id = candidate.clause.clause_id
            current = selected.get(clause_id)
            if current is not None:
                selected[clause_id] = _merge_candidate(current, candidate)
                continue
            if len(selected) < policy.global_candidate_cap:
                selected[clause_id] = candidate
                order.append(clause_id)
                continue
            drops.extend(
                BudgetDrop(
                    issue_id=match.issue_id,
                    search_request_id=match.search_request_id,
                    reason="CANDIDATE_BUDGET",
                    clause_id=clause_id,
                )
                for match in candidate.matches
            )

    return (
        tuple(selected[clause_id] for clause_id in order),
        tuple(sorted(drops, key=_drop_sort_key)),
    )


def _materialize_evidence(
    connection: sqlite3.Connection,
    candidates: tuple[IssueClauseCandidate, ...],
    policy: RetrievalPolicy,
) -> tuple[tuple[IssueClauseCandidate, ...], tuple[RetrievalHit, ...]]:
    selected_evidence: dict[str, RetrievalHit] = {}
    final_candidates: list[IssueClauseCandidate] = []

    for candidate in candidates:
        resolved = (
            candidate.evidence
            if candidate.evidence
            else resolve_clause_to_evidence(
                connection,
                candidate.clause,
                max_source_elements=policy.max_source_elements_per_clause,
            )
        )
        candidate_evidence: list[RetrievalHit] = []
        budget_limited = False
        for hit in resolved:
            existing = selected_evidence.get(hit.evidence_id)
            if existing is not None:
                candidate_evidence.append(existing)
                continue
            if len(selected_evidence) >= policy.max_selected_evidence:
                budget_limited = True
                continue
            selected_evidence[hit.evidence_id] = hit
            candidate_evidence.append(hit)
        final_candidates.append(
            replace(
                candidate,
                evidence=tuple(candidate_evidence),
                evidence_budget_limited=budget_limited,
            )
        )

    return tuple(final_candidates), tuple(selected_evidence.values())


def _seed_lineage(
    candidates: tuple[IssueClauseCandidate, ...],
) -> dict[str, dict[str, tuple[IssueCandidateMatch, ...]]]:
    by_issue: dict[str, dict[str, list[IssueCandidateMatch]]] = {}
    for candidate in candidates:
        for evidence in candidate.evidence:
            for match in candidate.matches:
                by_issue.setdefault(match.issue_id, {}).setdefault(
                    evidence.evidence_id,
                    [],
                ).append(match)
    return {
        issue_id: {
            evidence_id: tuple(sorted(matches, key=_match_sort_key))
            for evidence_id, matches in seeds.items()
        }
        for issue_id, seeds in by_issue.items()
    }


def _expand_references(
    connection: sqlite3.Connection,
    candidates: tuple[IssueClauseCandidate, ...],
    selected_evidence: tuple[RetrievalHit, ...],
    policy: RetrievalPolicy,
) -> tuple[
    tuple[RetrievalHit, ...],
    tuple[IssueReferenceMatch, ...],
    tuple[IssueReferenceMissing, ...],
    tuple[BudgetDrop, ...],
]:
    if policy.reference_max_depth == 0:
        return selected_evidence, (), (), ()

    lineage = _seed_lineage(candidates)
    selected = {hit.evidence_id: hit for hit in selected_evidence}
    reference_matches: dict[
        tuple[str, str, str, str, str], IssueReferenceMatch
    ] = {}
    missing: list[IssueReferenceMissing] = []
    drops: list[BudgetDrop] = []

    for issue_id in sorted(lineage):
        seeds = lineage[issue_id]
        if not seeds:
            continue
        result = traverse_relations_with_provenance(
            connection,
            tuple(sorted(seeds)),
            depth=policy.reference_max_depth,
            max_nodes=policy.reference_max_nodes_per_issue,
            max_fanout=policy.reference_max_fanout,
        )
        paths = {path.target_id: path for path in result.paths}
        for hit in result.hits:
            path = paths[hit.evidence_id]
            if not path.steps:
                continue
            source_evidence_id = path.steps[0].source_id
            source_matches = seeds.get(source_evidence_id, ())
            if not source_matches:
                continue
            if hit.evidence_id not in selected:
                if len(selected) >= policy.max_selected_evidence:
                    drops.extend(
                        BudgetDrop(
                            issue_id=match.issue_id,
                            search_request_id=match.search_request_id,
                            reason="REFERENCE_EVIDENCE_BUDGET",
                            evidence_id=hit.evidence_id,
                        )
                        for match in source_matches
                    )
                    continue
                selected[hit.evidence_id] = hit
            for match in source_matches:
                reference = IssueReferenceMatch(
                    evidence_id=hit.evidence_id,
                    issue_id=match.issue_id,
                    search_request_id=match.search_request_id,
                    role=match.role,
                    query_text=match.query_text,
                    retrieval_query=match.retrieval_query,
                    source_evidence_id=source_evidence_id,
                    path=path,
                )
                key = (
                    reference.issue_id,
                    reference.search_request_id,
                    reference.evidence_id,
                    reference.source_evidence_id,
                    reference.role,
                )
                reference_matches[key] = reference
        missing.extend(
            IssueReferenceMissing(issue_id=issue_id, reference=item)
            for item in result.missing
        )

    return (
        tuple(selected.values()),
        tuple(sorted(reference_matches.values(), key=_reference_match_sort_key)),
        tuple(
            sorted(
                missing,
                key=lambda item: (
                    item.issue_id,
                    item.reference.depth,
                    item.reference.source_id,
                    item.reference.target_id,
                    item.reference.reason_code,
                ),
            )
        ),
        tuple(sorted(drops, key=_drop_sort_key)),
    )


def retrieve_issue_bundle(
    connection: sqlite3.Connection,
    plan: QuestionPlan,
    *,
    policy: RetrievalPolicy | None = None,
) -> IssueRetrievalBundle:
    effective_policy = policy or RetrievalPolicy()
    if len(plan.issues) > effective_policy.max_issues:
        raise ValueError(
            f"question plan has {len(plan.issues)} issues; "
            f"policy maximum is {effective_policy.max_issues}"
        )

    fact_texts = tuple(fact.text for fact in plan.facts)
    buckets: list[_IssueRoleBucket] = []
    budget_drops: list[BudgetDrop] = []
    fallback_traces: list[IssueFallbackTrace] = []
    for issue in plan.issues:
        selected_requests, query_drops = _requests_for_issue(
            plan,
            issue,
            effective_policy,
        )
        budget_drops.extend(query_drops)
        for role in issue.required_evidence_roles:
            candidates, traces = _bucket_candidates(
                connection,
                issue,
                role,
                selected_requests,
                fact_texts,
                effective_policy,
            )
            fallback_traces.extend(traces)
            buckets.append(
                _IssueRoleBucket(
                    issue_id=issue.id,
                    role=role,
                    candidates=candidates,
                )
            )

    semantic_candidates, candidate_drops = _global_round_robin(
        tuple(buckets),
        effective_policy,
    )
    budget_drops.extend(candidate_drops)
    candidates, evidence = _materialize_evidence(
        connection,
        semantic_candidates,
        effective_policy,
    )
    evidence, reference_matches, reference_missing, reference_drops = _expand_references(
        connection,
        candidates,
        evidence,
        effective_policy,
    )
    budget_drops.extend(reference_drops)
    return IssueRetrievalBundle(
        candidates=candidates,
        selected_evidence=evidence,
        budget_drops=tuple(sorted(budget_drops, key=_drop_sort_key)),
        fallback_traces=tuple(fallback_traces),
        reference_matches=reference_matches,
        reference_missing=reference_missing,
    )
