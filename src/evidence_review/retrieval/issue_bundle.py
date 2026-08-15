"""Issue-aware clause retrieval with deterministic fairness and global budgets."""

from __future__ import annotations

import sqlite3
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
    search_clause_exact,
    search_clause_phrase,
    search_clause_token_and,
)
from evidence_review.retrieval.models import ChannelScore, RetrievalHit
from evidence_review.retrieval.policy import RetrievalPolicy

BudgetDropReason = Literal["QUERY_BUDGET", "CANDIDATE_BUDGET"]


@dataclass(frozen=True, slots=True)
class BudgetDrop:
    """One deterministic retrieval item excluded by a hard policy bound."""

    issue_id: str
    search_request_id: str
    reason: BudgetDropReason
    clause_id: str | None = None


@dataclass(frozen=True, slots=True)
class IssueCandidateMatch:
    """Lineage binding one semantic clause candidate to one planned issue query."""

    search_request_id: str
    issue_id: str
    role: EvidenceRole
    query_text: str


@dataclass(frozen=True, slots=True)
class IssueClauseCandidate:
    """One semantic clause selected across one or more issue/role buckets."""

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
class IssueRetrievalBundle:
    """Bounded semantic candidates plus citation-grade evidence."""

    candidates: tuple[IssueClauseCandidate, ...]
    selected_evidence: tuple[RetrievalHit, ...]
    budget_drops: tuple[BudgetDrop, ...]


@dataclass(frozen=True, slots=True)
class _IssueRoleBucket:
    issue_id: str
    role: EvidenceRole
    candidates: tuple[IssueClauseCandidate, ...]


def _match_sort_key(match: IssueCandidateMatch) -> tuple[str, str, str, str]:
    return (match.issue_id, match.role, match.search_request_id, match.query_text)


def _drop_sort_key(drop: BudgetDrop) -> tuple[str, str, str, str]:
    return (
        drop.issue_id,
        drop.search_request_id,
        drop.reason,
        drop.clause_id or "",
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


def _merge_candidate(
    left: IssueClauseCandidate,
    right: IssueClauseCandidate,
) -> IssueClauseCandidate:
    if left.clause.clause_id != right.clause.clause_id:
        raise ValueError("cannot merge different clause candidates")
    matches = {
        (match.issue_id, match.role, match.search_request_id, match.query_text): match
        for match in (*left.matches, *right.matches)
    }
    return IssueClauseCandidate(
        clause=_merge_clause_hit(left.clause, right.clause),
        matches=tuple(sorted(matches.values(), key=_match_sort_key)),
    )


def _initial_clause_hits(
    connection: sqlite3.Connection,
    request: SearchRequest,
    *,
    limit: int,
) -> tuple[ClauseRetrievalHit, ...]:
    if request.kind == "legal_anchor":
        return search_clause_exact(connection, request.text, limit=limit)
    if request.kind == "phrase":
        return search_clause_phrase(connection, request.text, limit=limit)
    return search_clause_token_and(connection, request.text, limit=limit)


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


def _bucket_candidates(
    connection: sqlite3.Connection,
    issue: QuestionIssue,
    role: EvidenceRole,
    requests: tuple[SearchRequest, ...],
    policy: RetrievalPolicy,
) -> tuple[IssueClauseCandidate, ...]:
    by_clause: dict[str, IssueClauseCandidate] = {}
    for request in requests:
        if request.role != role:
            continue
        for clause_hit in _initial_clause_hits(
            connection,
            request,
            limit=policy.per_issue_role_limit,
        ):
            candidate = IssueClauseCandidate(
                clause=clause_hit,
                matches=(
                    IssueCandidateMatch(
                        search_request_id=request.id,
                        issue_id=issue.id,
                        role=role,
                        query_text=request.text,
                    ),
                ),
            )
            current = by_clause.get(clause_hit.clause_id)
            by_clause[clause_hit.clause_id] = (
                candidate if current is None else _merge_candidate(current, candidate)
            )
    return tuple(
        sorted(
            by_clause.values(),
            key=lambda item: (-item.clause.score, item.clause.clause_id),
        )[: policy.per_issue_role_limit]
    )


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
        resolved = resolve_clause_to_evidence(
            connection,
            candidate.clause,
            max_source_elements=policy.max_source_elements_per_clause,
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


def retrieve_issue_bundle(
    connection: sqlite3.Connection,
    plan: QuestionPlan,
    *,
    policy: RetrievalPolicy | None = None,
) -> IssueRetrievalBundle:
    """Retrieve fair per-issue clause candidates under deterministic hard budgets."""
    effective_policy = policy or RetrievalPolicy()
    if len(plan.issues) > effective_policy.max_issues:
        raise ValueError(
            f"question plan has {len(plan.issues)} issues; "
            f"policy maximum is {effective_policy.max_issues}"
        )

    buckets: list[_IssueRoleBucket] = []
    budget_drops: list[BudgetDrop] = []
    for issue in plan.issues:
        selected_requests, query_drops = _requests_for_issue(
            plan,
            issue,
            effective_policy,
        )
        budget_drops.extend(query_drops)
        for role in issue.required_evidence_roles:
            buckets.append(
                _IssueRoleBucket(
                    issue_id=issue.id,
                    role=role,
                    candidates=_bucket_candidates(
                        connection,
                        issue,
                        role,
                        selected_requests,
                        effective_policy,
                    ),
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
    return IssueRetrievalBundle(
        candidates=candidates,
        selected_evidence=evidence,
        budget_drops=tuple(sorted(budget_drops, key=_drop_sort_key)),
    )
