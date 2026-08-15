"""Pure exact-scope selection for governed active rules."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import cast

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.formats import RULE_SELECTION_RESULT_FORMAT
from evidence_review.rule_engine.governance_contract import (
    ActiveRuleEntry,
    ExcludedRule,
    ExclusionCode,
    RuleScope,
    RuleSelectionContext,
    RuleSelectionResult,
    SelectedRule,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTEXT_FIELDS = (
    "document_family",
    "document_kind",
    "jurisdiction",
    "program",
)


def _duplicate_free_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be null or a non-empty string")
    return value.strip()


def load_rule_selection_context(value: object) -> RuleSelectionContext:
    """Strictly decode explicit selection context without accepting extra dimensions."""
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError("selection context must be an object")
    payload = cast(Mapping[str, object], value)
    unknown = sorted(set(payload) - set(_CONTEXT_FIELDS))
    if unknown:
        raise ValueError(f"selection context has unknown fields: {', '.join(unknown)}")
    return RuleSelectionContext(
        document_family=_optional_string(
            payload.get("document_family"), "document_family"
        ),
        document_kind=_optional_string(payload.get("document_kind"), "document_kind"),
        jurisdiction=_optional_string(payload.get("jurisdiction"), "jurisdiction"),
        program=_optional_string(payload.get("program"), "program"),
    )


def load_rule_selection_context_bytes(data: bytes) -> RuleSelectionContext:
    """Decode UTF-8 JSON while rejecting duplicate keys."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("selection context must be UTF-8 JSON") from error
    try:
        value: object = json.loads(text, object_pairs_hook=_duplicate_free_object)
    except json.JSONDecodeError as error:
        raise ValueError("selection context must be valid JSON") from error
    return load_rule_selection_context(value)


def _scope_values(scope: RuleScope) -> tuple[str | None, ...]:
    return (
        scope.document_family,
        scope.document_kind,
        scope.jurisdiction,
        scope.program,
    )


def _context_values(context: RuleSelectionContext) -> tuple[str | None, ...]:
    return (
        context.document_family,
        context.document_kind,
        context.jurisdiction,
        context.program,
    )


def _exclusion_code(
    scope: RuleScope,
    context: RuleSelectionContext,
) -> ExclusionCode | None:
    for expected, actual in zip(_scope_values(scope), _context_values(context), strict=True):
        if expected is None:
            continue
        if actual is None:
            return "MISSING_SCOPE_VALUE"
        if actual != expected:
            return "SCOPE_MISMATCH"
    return None


def _entry_sort_key(entry: ActiveRuleEntry) -> tuple[str, str, str]:
    return (entry.rule_id, entry.rule_version, entry.approval_path)


def select_active_rules(
    entries: Sequence[ActiveRuleEntry],
    context: RuleSelectionContext,
    manifest_sha256: str,
) -> RuleSelectionResult:
    """Select all exact-scope matches or explicitly abstain."""
    if _SHA256.fullmatch(manifest_sha256) is None:
        raise ValueError("manifest_sha256 must be a lowercase SHA-256")
    selected: list[SelectedRule] = []
    excluded: list[ExcludedRule] = []
    for entry in sorted(entries, key=_entry_sort_key):
        code = _exclusion_code(entry.scope, context)
        if code is None:
            selected.append(
                SelectedRule(
                    rule_id=entry.rule_id,
                    rule_version=entry.rule_version,
                    approved_rule_path=entry.approved_rule_path,
                    approved_rule_sha256=entry.approved_rule_sha256,
                    scope=entry.scope,
                )
            )
        else:
            excluded.append(
                ExcludedRule(
                    rule_id=entry.rule_id,
                    rule_version=entry.rule_version,
                    code=code,
                )
            )
    if selected:
        return RuleSelectionResult(
            status="SELECTED",
            context=context,
            manifest_sha256=manifest_sha256,
            selected_rules=tuple(selected),
            excluded_rules=tuple(excluded),
            reasons=(),
        )
    return RuleSelectionResult(
        status="ABSTAIN",
        context=context,
        manifest_sha256=manifest_sha256,
        selected_rules=(),
        excluded_rules=tuple(excluded),
        reasons=("NO_APPLICABLE_ACTIVE_RULE",),
    )


def _scope_payload(scope: RuleScope) -> dict[str, object]:
    payload: dict[str, object] = {"document_family": scope.document_family}
    if scope.document_kind is not None:
        payload["document_kind"] = scope.document_kind
    if scope.jurisdiction is not None:
        payload["jurisdiction"] = scope.jurisdiction
    if scope.program is not None:
        payload["program"] = scope.program
    return payload


def _context_payload(context: RuleSelectionContext) -> dict[str, object]:
    return {
        "document_family": context.document_family,
        "document_kind": context.document_kind,
        "jurisdiction": context.jurisdiction,
        "program": context.program,
    }


def rule_selection_result_bytes(result: RuleSelectionResult) -> bytes:
    """Serialize one deterministic selection result."""
    return dump_bytes(
        {
            "format": RULE_SELECTION_RESULT_FORMAT,
            "version": 1,
            "status": result.status,
            "context": _context_payload(result.context),
            "manifest_sha256": result.manifest_sha256,
            "selected_rules": [
                {
                    "rule_id": item.rule_id,
                    "rule_version": item.rule_version,
                    "approved_rule_path": item.approved_rule_path,
                    "approved_rule_sha256": item.approved_rule_sha256,
                    "scope": _scope_payload(item.scope),
                }
                for item in result.selected_rules
            ],
            "excluded_rules": [
                {
                    "rule_id": item.rule_id,
                    "rule_version": item.rule_version,
                    "code": item.code,
                }
                for item in result.excluded_rules
            ],
            "reasons": list(result.reasons),
        }
    )
