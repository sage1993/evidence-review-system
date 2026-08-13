"""Collapsed technical audit rendering for the Review Workspace."""
from __future__ import annotations

import json
from collections.abc import Mapping
from html import escape


def _text(value: object) -> str:
    return "" if value is None else escape(str(value), quote=True)


def _json_text(value: object) -> str:
    return escape(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        quote=False,
    )


def render_audit_details(model: Mapping[str, object]) -> str:
    """Preserve machine/audit data without exposing it on the default surface."""
    metadata = model.get("metadata", {})
    audit = model.get("audit", {})
    confidence = model.get("confidence")
    raw = {
        "metadata": metadata,
        "machine_status": model.get("status"),
        "audit": audit,
        "confidence": confidence,
        "exceptions": model.get("exceptions", []),
        "conflicts": model.get("conflicts", []),
        "abstention_reasons": model.get("abstention_reasons", []),
    }
    return "".join(
        (
            '<details id="packet-global-review" class="audit-details">',
            '<summary>감사 정보 <span>기술 정보 보기</span></summary>',
            '<div class="audit-body">',
            '<p>검토 재현성과 추적을 위한 내부 ID, 해시, 원시 상태, 신뢰도 요인입니다.</p>',
            '<pre aria-label="감사 정보 JSON">',
            _json_text(raw),
            "</pre></div></details>",
        )
    )


def render_citation_audit(citation: Mapping[str, object]) -> str:
    raw = {
        "citation_id": citation.get("citation_id"),
        "evidence_id": citation.get("evidence_id"),
        "document_id": citation.get("document_id"),
        "revision_id": citation.get("revision_id"),
        "source_hash": citation.get("source_hash"),
        "evidence_type": citation.get("evidence_type"),
    }
    return "".join(
        (
            '<details class="citation-audit">',
            '<summary>출처 세부정보</summary>',
            f'<pre>{_json_text(raw)}</pre>',
            "</details>",
        )
    )


def render_item_audit(
    item: Mapping[str, object],
    *,
    rules: object,
    calculations: object,
) -> str:
    raw = {
        "item": dict(item),
        "rules": rules,
        "calculations": calculations,
    }
    return "".join(
        (
            '<details class="item-audit">',
            '<summary>항목 기술정보</summary>',
            f'<pre>{_json_text(raw)}</pre>',
            "</details>",
        )
    )


__all__ = ["render_audit_details", "render_citation_audit", "render_item_audit"]
