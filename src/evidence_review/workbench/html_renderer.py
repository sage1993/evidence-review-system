"""HTML projection for mutable ReviewMatter Workbench data."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path
from typing import cast


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _items(value: object, field: str) -> Sequence[Mapping[str, object]]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"Workbench model {field} must be a sequence")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"Workbench model {field} must contain objects")
    return cast(Sequence[Mapping[str, object]], value)


def _object(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Workbench model {field} must be an object")
    return cast(Mapping[str, object], value)


def _asset(name: str) -> str:
    return (Path(__file__).with_name("assets") / name).read_text(encoding="utf-8")


def _model_json(model: Mapping[str, object]) -> str:
    return json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def _render_issues(issues: Sequence[Mapping[str, object]]) -> str:
    return "".join(
        "".join(
            (
                '<article class="workbench-issue" ',
                f'data-issue-id="{_text(issue.get("issue_id"))}">',
                f"<h2>{_text(issue.get('question'))}</h2>",
                '<p class="issue-identifier">MatterIssue ',
                _text(issue.get("issue_id")),
                "</p>",
                '<p class="work-state">',
                _text(issue.get("work_state_label")),
                "</p>",
                (
                    '<p class="recheck-marker">재확인 필요</p>'
                    if issue.get("recheck_required") is True
                    else ""
                ),
                "</article>",
            )
        )
        for issue in issues
    ) or '<p class="empty-state">등록된 MatterIssue가 없습니다.</p>'


def _render_evidence(evidence: Sequence[Mapping[str, object]]) -> str:
    cards: list[str] = []
    for binding in evidence:
        provenance = _object(binding.get("provenance"), "evidence.provenance")
        evidence_id = _text(provenance.get("evidence_id"))
        binding_id = _text(binding.get("binding_id"))
        target_id = f"provenance-{binding_id}"
        bbox_values = provenance.get("bbox", ())
        if isinstance(bbox_values, (str, bytes, bytearray)) or not isinstance(
            bbox_values, Sequence
        ):
            raise ValueError("Workbench model evidence.bbox must be a sequence")
        bbox = ", ".join(str(value) for value in bbox_values)
        cards.append(
            "".join(
                (
                    '<article class="evidence-card">',
                    '<button type="button" class="evidence-reference" ',
                    f'data-evidence-reference data-evidence-id="{evidence_id}" ',
                    f'aria-controls="{target_id}">근거 위치 보기</button>',
                    '<p class="citation-location">',
                    f"{_text(provenance.get('document_id'))} · ",
                    f"{_text(provenance.get('revision_id'))} · p. ",
                    _text(provenance.get("page_number")),
                    "</p>",
                    f'<details id="{target_id}" tabindex="-1"><summary>정확한 출처</summary>',
                    f"<p>Evidence: {evidence_id}</p>",
                    f"<p>Bounding box: {_text(bbox)}</p>",
                    f"<p>Source hash: {_text(provenance.get('source_hash'))}</p>",
                    f"<p>Evidence snapshot: {_text(provenance.get('evidence_snapshot_hash'))}</p>",
                    f"<p>Evidence DB: {_text(provenance.get('evidence_db_sha256'))}</p>",
                    "</details></article>",
                )
            )
        )
    return "".join(cards) or '<p class="empty-state">선택된 근거가 없습니다.</p>'


def _render_navigation(navigation: Mapping[str, object] | None) -> str:
    if navigation is None:
        return '<p class="empty-state">탐색 결과가 없습니다.</p>'
    hits = _items(navigation.get("hits", ()), "navigation.hits")
    cards: list[str] = []
    for hit in hits:
        citation_id = _text(hit.get("citation_id"))
        evidence_id = _text(hit.get("evidence_id"))
        target_id = f"navigation-provenance-{citation_id}"
        bbox_values = hit.get("bbox", ())
        if isinstance(bbox_values, (str, bytes, bytearray)) or not isinstance(
            bbox_values, Sequence
        ):
            raise ValueError("Workbench model navigation.bbox must be a sequence")
        bbox = ", ".join(str(value) for value in bbox_values)
        cards.append(
            "".join(
                (
                    '<article class="navigation-hit">',
                    f"<h3>{_text(hit.get('title'))}</h3>",
                    f"<p>{_text(hit.get('text'))}</p>",
                    '<p class="citation-location">',
                    f"{_text(hit.get('document_id'))} · {_text(hit.get('revision_id'))} · ",
                    f"p. {_text(hit.get('page_number'))}</p>",
                    '<button type="button" class="evidence-reference" ',
                    f'data-evidence-reference data-navigation-evidence-id="{evidence_id}" ',
                    f'aria-controls="{target_id}">정확한 출처 보기</button>',
                    f'<details id="{target_id}" tabindex="-1"><summary>정확한 출처</summary>',
                    f"<p>Evidence: {evidence_id}</p>",
                    f"<p>Bounding box: {_text(bbox)}</p>",
                    f"<p>Source hash: {_text(hit.get('source_hash'))}</p>",
                    f"<p>Evidence snapshot: {_text(navigation.get('evidence_snapshot_hash'))}</p>",
                    f"<p>Evidence DB: {_text(navigation.get('evidence_db_sha256'))}</p>",
                    "</details></article>",
                )
            )
        )
    rendered_cards = "".join(cards) or '<p class="empty-state">일치하는 탐색 결과가 없습니다.</p>'
    return "".join(
        (
            f"<p>{_text(navigation.get('promotion_label'))}</p>",
            '<p class="recheck-marker">재확인 필요</p>'
            if navigation.get("recheck_required") is True
            else "",
            rendered_cards,
        )
    )


def _render_drafts(observations: Sequence[Mapping[str, object]]) -> str:
    return "".join(
        "".join(
            (
                '<article class="draft-observation" ',
                f'data-issue-id="{_text(observation.get("issue_id"))}">',
                f"<p class=\"draft-label\">{_text(observation.get('draft_label'))}</p>",
                '<p class="draft-issue-identifier">MatterIssue ',
                _text(observation.get("issue_id")),
                "</p>",
                f'<p class="draft-source">{_text(observation.get("source_label"))}</p>',
                f"<p>{_text(observation.get('text'))}</p>",
                f"<p>{_text(observation.get('verification_label'))}</p>",
                "</article>",
            )
        )
        for observation in observations
    ) or '<p class="empty-state">검토 초안이 없습니다.</p>'


def _render_formal_history(history: Sequence[Mapping[str, object]]) -> str:
    return "".join(
        "".join(
            (
                '<li><strong>정식 검토 run ',
                _text(entry.get("run_id")),
                "</strong> · Matter revision ",
                _text(entry.get("matter_revision")),
                " · snapshot ",
                _text(entry.get("snapshot_id")),
                " · ",
                _text(entry.get("stage_label")),
                "</li>",
            )
        )
        for entry in history
    ) or '<li>아직 정식 검토 이력이 없습니다.</li>'


def _render_formalize(formalize: Mapping[str, object]) -> str:
    blockers = _items(formalize.get("blockers", ()), "formalize.blockers")
    enabled = formalize.get("enabled") is True
    disabled = "" if enabled else " disabled"
    blocker_html = "".join(
        f"<li>{_text(blocker.get('issue_id'))} {_text(blocker.get('label'))}</li>"
        for blocker in blockers
    ) or "<li>없음</li>"
    return "".join(
        (
            '<section class="formalize-panel" aria-labelledby="formalize-heading">',
            '<h2 id="formalize-heading">정식화</h2>',
            f"<p>{_text(formalize.get('confirmation_label'))}</p>",
            '<button type="button" data-workbench-formalize',
            disabled,
            f' data-formalize-expected-revision="{_text(formalize.get("expected_revision"))}"',
            ' aria-describedby="formalize-blockers"',
            ">정식화 요청</button>",
            '<ul id="formalize-blockers">',
            blocker_html,
            "</ul><p data-formalize-status aria-live=\"polite\"></p></section>",
        )
    )


def _render_navigation_search() -> str:
    return "".join(
        (
            '<form data-workbench-navigation-form>',
            '<label for="workbench-navigation-query">탐색어</label>',
            '<input id="workbench-navigation-query" name="query" type="search" '
            'required maxlength="240" autocomplete="off">',
            '<button type="submit">근거 탐색</button>',
            '</form><p data-workbench-navigation-status aria-live="polite"></p>',
            '<div data-workbench-navigation-results></div>',
        )
    )


def render_workbench_html(model: Mapping[str, object], *, nonce: str | None = None) -> str:
    """Render a mutable-work surface with no Formal Review decision controls."""
    if model.get("surface") != "workbench":
        raise ValueError("Workbench model surface is required")
    issues = _items(model.get("issues"), "issues")
    evidence = _items(model.get("evidence", ()), "evidence")
    drafts = _items(model.get("draft_observations", ()), "draft_observations")
    history = _items(model.get("formal_run_history", ()), "formal_run_history")
    navigation_value = model.get("navigation")
    navigation = None if navigation_value is None else _object(navigation_value, "navigation")
    formalize = _object(model.get("formalize"), "formalize")
    css = _asset("workbench.css")
    javascript = _asset("workbench.js")
    nonce_attribute = "" if nonce is None else f' nonce="{_text(nonce)}"'
    return "".join(
        (
            "<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">",
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>검토 작업 · {_text(model.get('title'))}</title>",
            f"<style{nonce_attribute}>{css}</style></head>",
            '<body><main class="workbench-shell" data-surface="workbench">',
            '<header><p class="eyebrow">Mutable ReviewMatter work</p>',
            f"<h1>{_text(model.get('title'))}</h1>",
            "<p>Matter ",
            _text(model.get("matter_id")),
            " · revision ",
            _text(model.get("revision")),
            "</p>",
            "</header>",
            '<section aria-labelledby="issues-heading">',
            '<h2 id="issues-heading">MatterIssue 작업</h2>',
            _render_issues(issues),
            "</section>",
            '<section aria-labelledby="evidence-heading"><h2 id="evidence-heading">선택 근거</h2>',
            _render_evidence(evidence),
            "</section>",
            '<section aria-labelledby="navigation-heading">',
            '<h2 id="navigation-heading">근거 탐색</h2>',
            _render_navigation_search(),
            _render_navigation(navigation),
            "</section>",
            '<section aria-labelledby="draft-heading"><h2 id="draft-heading">검토 초안</h2>',
            _render_drafts(drafts),
            "</section>",
            '<section aria-labelledby="history-heading">',
            '<h2 id="history-heading">정식 검토 이력</h2><ul>',
            _render_formal_history(history),
            "</ul></section>",
            _render_formalize(formalize),
            "</main>",
            f'<script id="workbench-model" type="application/json"{nonce_attribute}>',
            _model_json(model),
            "</script>",
            f"<script{nonce_attribute}>{javascript}</script></body></html>",
        )
    )
