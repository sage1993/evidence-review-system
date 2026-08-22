"""Render verified case drawings/images and localized visual findings."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from html import escape
from typing import cast


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _text(value: object) -> str:
    return "" if value is None else escape(str(value), quote=True)


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _shape(candidate: Mapping[str, object]) -> str:
    geometry = _mapping(candidate.get("geometry"), "case_visual.geometry")
    if geometry.get("coordinate_system") != "IMAGE_TOP_LEFT_PIXELS":
        raise ValueError("case visual renderer requires IMAGE_TOP_LEFT_PIXELS")
    geometry_type = str(geometry.get("type", ""))
    raw = _sequence(geometry.get("coordinates"), "case_visual.geometry.coordinates")
    if geometry_type == "POINT":
        if len(raw) != 2:
            raise ValueError("POINT coordinates are invalid")
        return (
            f'<circle cx="{_number(raw[0], "point.x"):g}" '
            f'cy="{_number(raw[1], "point.y"):g}" r="8"/>'
        )
    if geometry_type == "BBOX":
        if len(raw) != 4:
            raise ValueError("BBOX coordinates are invalid")
        left, top, right, bottom = (
            _number(raw[index], "bbox.coordinate") for index in range(4)
        )
        return (
            f'<rect x="{left:g}" y="{top:g}" width="{right - left:g}" '
            f'height="{bottom - top:g}" rx="4" ry="4"/>'
        )
    if geometry_type in {"LINESTRING", "POLYGON"}:
        points: list[str] = []
        for item in raw:
            point = _sequence(item, "case_visual.geometry.point")
            if len(point) != 2:
                raise ValueError("path coordinates are invalid")
            points.append(
                f'{_number(point[0], "path.x"):g},{_number(point[1], "path.y"):g}'
            )
        if not points:
            raise ValueError("path coordinates are empty")
        tag = "polyline" if geometry_type == "LINESTRING" else "polygon"
        return f'<{tag} points="{" ".join(points)}"/>'
    raise ValueError(f"unsupported case visual geometry: {geometry_type}")


def _candidate_label(candidate: Mapping[str, object]) -> str:
    value = candidate.get("display_value")
    if isinstance(value, str) and value.strip():
        return value
    return str(candidate.get("candidate_type", "시각 관찰"))


def _candidate_button(candidate: Mapping[str, object], page_key: str, index: int) -> str:
    candidate_id = str(candidate.get("candidate_id", ""))
    tone = str(candidate.get("tone", "observation"))
    issues = " · ".join(
        str(item) for item in _sequence(candidate.get("issue_ids", []), "candidate.issue_ids")
    )
    return "".join(
        (
            f'<button class="case-visual-finding tone-{_text(tone)}',
            " is-active" if index == 0 else "",
            '" type="button" ',
            f'data-case-candidate="{_text(candidate_id)}" ',
            f'data-case-page-key="{_text(page_key)}" ',
            f'aria-pressed="{"true" if index == 0 else "false"}">',
            f'<span class="case-visual-finding-index">{index + 1}</span>',
            '<span class="case-visual-finding-copy">',
            f'<strong>{_text(_candidate_label(candidate))}</strong>',
            f'<small>{_text(issues or "시각 관찰")}</small>',
            "</span></button>",
        )
    )


def _candidate_detail(candidate: Mapping[str, object], index: int) -> str:
    candidate_id = str(candidate.get("candidate_id", ""))
    issue_ids = [str(item) for item in _sequence(candidate.get("issue_ids", []), "issue_ids")]
    questions = [
        str(item) for item in _sequence(candidate.get("issue_questions", []), "issue_questions")
    ]
    claims = [
        _mapping(item, "candidate.claim")
        for item in _sequence(candidate.get("claims", []), "candidate.claims")
    ]
    statuses = [
        str(item) for item in _sequence(candidate.get("review_statuses", []), "review_statuses")
    ]
    issue_rows = "".join(
        f'<li><strong>{_text(issue_id)}</strong> {_text(questions[pos] if pos < len(questions) else "")}</li>'
        for pos, issue_id in enumerate(issue_ids)
    )
    claim_rows = "".join(
        f'<li><code>{_text(claim.get("claim_id"))}</code> {_text(claim.get("text"))}</li>'
        for claim in claims
    )
    return "".join(
        (
            f'<article class="case-visual-detail{" is-active" if index == 0 else ""}" ',
            f'data-case-detail="{_text(candidate_id)}"',
            "" if index == 0 else " hidden",
            ">",
            '<span class="case-visual-detail-label">시각 관찰</span>',
            f'<h3>{_text(_candidate_label(candidate))}</h3>',
            f'<p class="case-visual-candidate-id">{_text(candidate_id)}</p>',
            '<dl class="case-visual-meta">',
            f'<div><dt>유형</dt><dd>{_text(candidate.get("candidate_type"))}</dd></div>',
            f'<div><dt>상태</dt><dd>{_text(candidate.get("status"))}</dd></div>',
            f'<div><dt>연결 판정</dt><dd>{_text(", ".join(statuses) or "관찰 사실")}</dd></div>',
            "</dl>",
            '<h4>연결 쟁점</h4>',
            f'<ul>{issue_rows or "<li>연결 쟁점 없음</li>"}</ul>',
            '<h4>검토 설명</h4>',
            f'<ul>{claim_rows or "<li>Track A claim에 직접 사용되지 않은 관찰입니다.</li>"}</ul>',
            '<p class="case-visual-boundary">표시는 사용자 첨부자료에서 확인된 위치입니다. '
            '법적 기준의 근거는 별도의 판단 근거 문서에서 확인합니다.</p>',
            "</article>",
        )
    )


def render_case_visual_review(model: Mapping[str, object]) -> str:
    """Render a page-based case visual viewer only when verified visual data exists."""
    raw = model.get("case_visual_review")
    if raw is None:
        return ""
    visual = _mapping(raw, "case_visual_review")
    if visual.get("status") != "VISUAL_ANALYSIS_VALIDATED":
        raise ValueError("case visual review must be validated before rendering")
    pages = [
        _mapping(item, f"case_visual_review.pages[{index}]")
        for index, item in enumerate(_sequence(visual.get("pages", []), "case_visual_review.pages"))
    ]
    if not pages:
        raise ValueError("validated case visual review requires at least one page")

    page_html: list[str] = []
    finding_html: list[str] = []
    detail_html: list[str] = []
    global_index = 0
    for page_index, page in enumerate(pages):
        asset_key = str(page.get("asset_key", ""))
        width = _number(page.get("width"), "case_visual_page.width")
        height = _number(page.get("height"), "case_visual_page.height")
        candidates = [
            _mapping(item, "case_visual_page.candidate")
            for item in _sequence(page.get("candidates", []), "case_visual_page.candidates")
        ]
        overlays: list[str] = []
        for candidate in candidates:
            candidate_id = str(candidate.get("candidate_id", ""))
            tone = str(candidate.get("tone", "observation"))
            overlays.append(
                f'<g class="case-visual-overlay tone-{_text(tone)}" '
                f'data-case-overlay="{_text(candidate_id)}">{_shape(candidate)}</g>'
            )
            finding_html.append(_candidate_button(candidate, asset_key, global_index))
            detail_html.append(_candidate_detail(candidate, global_index))
            global_index += 1
        page_html.append(
            "".join(
                (
                    f'<figure class="case-visual-page{" is-active" if page_index == 0 else ""}" ',
                    f'data-case-page="{_text(asset_key)}"',
                    "" if page_index == 0 else " hidden",
                    ">",
                    '<div class="case-visual-stage" data-case-stage tabindex="0">',
                    '<div class="case-visual-transform" data-case-transform>',
                    f'<img src="{_text(page.get("data_uri"))}" '
                    f'alt="{_text(page.get("document_name"))} 페이지 {page.get("page")}">',
                    f'<svg viewBox="0 0 {width:g} {height:g}" preserveAspectRatio="xMidYMid meet" ',
                    'aria-label="첨부자료 이슈 위치">',
                    "".join(overlays),
                    "</svg></div></div>",
                    f'<figcaption>{_text(page.get("document_name"))} · p.{_text(page.get("page"))}</figcaption>',
                    "</figure>",
                )
            )
        )

    finding_list = "".join(finding_html)
    if not finding_list:
        finding_list = (
            '<p class="case-visual-empty">시각분석은 완료되었지만 위치로 표시할 관찰 항목은 없습니다.</p>'
        )
    details = "".join(detail_html)
    if not details:
        details = (
            '<article class="case-visual-detail is-active"><h3>시각분석 완료</h3>'
            '<p>위치 기반 관찰 항목이 생성되지 않았습니다.</p></article>'
        )

    return "".join(
        (
            f"<style>{CASE_VISUAL_CSS}</style>",
            '<section id="case-visual-review" aria-labelledby="case-visual-heading">',
            '<div class="case-visual-heading-row">',
            '<div><span class="section-kicker">첨부자료 검토</span>',
            '<h2 id="case-visual-heading">도면·이미지 확인 위치</h2></div>',
            '<div class="case-visual-legend" aria-label="표시 범례">',
            '<span class="tone-issue">문제 가능성</span>',
            '<span class="tone-review">추가 확인</span>',
            '<span class="tone-observation">관찰</span>',
            '<span class="tone-compliant">충족 연결</span>',
            "</div></div>",
            '<div class="case-visual-toolbar">',
            '<button type="button" data-case-prev aria-label="이전 첨부 페이지">‹</button>',
            f'<span><strong data-case-page-number>1</strong> / {len(pages)}</span>',
            '<button type="button" data-case-next aria-label="다음 첨부 페이지">›</button>',
            '<span class="case-visual-toolbar-spacer"></span>',
            '<span data-case-zoom>100%</span>',
            '<button type="button" data-case-reset>화면 맞춤</button>',
            "</div>",
            '<div class="case-visual-layout">',
            '<aside class="case-visual-findings" aria-label="시각 관찰 목록">',
            '<h3>관찰 항목</h3>', finding_list, "</aside>",
            '<div class="case-visual-viewer">', "".join(page_html), "</div>",
            '<aside class="case-visual-details" aria-label="선택 관찰 상세">',
            details, "</aside>",
            "</div>",
            '<p class="case-visual-help">마우스 휠로 확대·축소하고, 좌클릭 드래그로 화면을 이동할 수 있습니다.</p>',
            f"<script>{CASE_VISUAL_SCRIPT}</script>",
            "</section>",
        )
    )


CASE_VISUAL_CSS = r"""
#case-visual-review{margin:18px 0;border:1px solid var(--border,#d9dee7);border-radius:14px;background:var(--surface,#fff);overflow:hidden}
.case-visual-heading-row{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;padding:18px 20px 12px}.case-visual-heading-row h2{margin:3px 0 0;font-size:18px}.case-visual-legend{display:flex;gap:8px;flex-wrap:wrap;font-size:12px}.case-visual-legend span{display:inline-flex;align-items:center;gap:5px}.case-visual-legend span:before{content:"";width:9px;height:9px;border-radius:50%;background:currentColor}.tone-issue{color:#b42318}.tone-review{color:#b54708}.tone-observation{color:#175cd3}.tone-compliant{color:#027a48}
.case-visual-toolbar{height:42px;display:flex;align-items:center;gap:8px;padding:0 14px;border-top:1px solid var(--border,#d9dee7);border-bottom:1px solid var(--border,#d9dee7);background:#f8fafc}.case-visual-toolbar button{border:1px solid #d0d5dd;background:#fff;border-radius:7px;min-height:28px;padding:3px 9px}.case-visual-toolbar-spacer{flex:1}
.case-visual-layout{display:grid;grid-template-columns:minmax(210px,260px) minmax(0,1fr) minmax(250px,330px);height:min(68vh,720px);min-height:470px}.case-visual-findings,.case-visual-details{overflow:auto;padding:12px;background:#fff}.case-visual-findings{border-right:1px solid #e4e7ec}.case-visual-details{border-left:1px solid #e4e7ec}.case-visual-findings h3{font-size:13px;margin:0 0 10px;color:#475467}
.case-visual-finding{width:100%;display:flex;gap:9px;text-align:left;border:1px solid transparent;background:transparent;border-radius:9px;padding:9px;margin:0 0 5px;color:#344054}.case-visual-finding:hover,.case-visual-finding.is-active{background:#f2f4f7;border-color:#d0d5dd}.case-visual-finding-index{width:24px;height:24px;display:grid;place-items:center;border-radius:50%;background:#eef2f6;font-size:11px;flex:0 0 auto}.case-visual-finding-copy{min-width:0;display:grid;gap:3px}.case-visual-finding-copy strong{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.case-visual-finding-copy small{font-size:11px;color:#667085}.case-visual-finding.tone-issue .case-visual-finding-index{color:#b42318;background:#fef3f2}.case-visual-finding.tone-review .case-visual-finding-index{color:#b54708;background:#fffaeb}.case-visual-finding.tone-observation .case-visual-finding-index{color:#175cd3;background:#eff8ff}.case-visual-finding.tone-compliant .case-visual-finding-index{color:#027a48;background:#ecfdf3}
.case-visual-viewer{position:relative;overflow:hidden;background:#e9edf2}.case-visual-page{height:100%;margin:0;display:grid;grid-template-rows:minmax(0,1fr) 28px}.case-visual-stage{position:relative;overflow:hidden;cursor:grab;touch-action:none}.case-visual-stage.is-dragging{cursor:grabbing}.case-visual-transform{position:absolute;inset:0;transform-origin:0 0;will-change:transform}.case-visual-transform img,.case-visual-transform svg{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}.case-visual-transform svg{pointer-events:none}.case-visual-page figcaption{display:flex;align-items:center;justify-content:center;background:#fff;border-top:1px solid #d0d5dd;font-size:11px;color:#667085}.case-visual-overlay{fill:transparent;stroke-width:3;vector-effect:non-scaling-stroke;opacity:.78}.case-visual-overlay.tone-issue{stroke:#d92d20;fill:rgba(217,45,32,.07)}.case-visual-overlay.tone-review{stroke:#f79009;fill:rgba(247,144,9,.07)}.case-visual-overlay.tone-observation{stroke:#2e90fa;fill:rgba(46,144,250,.06)}.case-visual-overlay.tone-compliant{stroke:#12b76a;fill:rgba(18,183,106,.06)}.case-visual-overlay.is-active{stroke-width:5;opacity:1;filter:drop-shadow(0 0 3px rgba(0,0,0,.3))}
.case-visual-detail{display:none}.case-visual-detail.is-active{display:block}.case-visual-detail-label{font-size:11px;color:#667085}.case-visual-detail h3{font-size:16px;margin:5px 0 4px}.case-visual-candidate-id{font:11px ui-monospace,monospace;color:#667085;word-break:break-all}.case-visual-meta{display:grid;gap:6px;margin:14px 0}.case-visual-meta div{display:grid;grid-template-columns:74px 1fr;gap:8px;font-size:12px}.case-visual-meta dt{color:#667085}.case-visual-meta dd{margin:0}.case-visual-detail h4{font-size:12px;margin:14px 0 6px}.case-visual-detail ul{padding-left:18px;margin:0;font-size:12px;line-height:1.55}.case-visual-boundary{margin-top:16px;padding:9px;border-radius:8px;background:#f8fafc;font-size:11px;color:#475467}.case-visual-help{margin:0;padding:8px 14px;border-top:1px solid #e4e7ec;font-size:11px;color:#667085;background:#fff}.case-visual-empty{font-size:12px;color:#667085;padding:10px}
@media(max-width:1000px){.case-visual-layout{grid-template-columns:220px minmax(0,1fr);height:620px}.case-visual-details{display:none}}@media(max-width:720px){.case-visual-heading-row{align-items:flex-start;flex-direction:column}.case-visual-layout{grid-template-columns:1fr;grid-template-rows:150px minmax(0,1fr);height:650px}.case-visual-findings{border-right:0;border-bottom:1px solid #e4e7ec}.case-visual-details{display:none}}
"""


CASE_VISUAL_SCRIPT = r"""
(()=>{const root=document.getElementById('case-visual-review');if(!root||root.dataset.bound==='1')return;root.dataset.bound='1';
const pages=[...root.querySelectorAll('[data-case-page]')],buttons=[...root.querySelectorAll('[data-case-candidate]')],overlays=[...root.querySelectorAll('[data-case-overlay]')],details=[...root.querySelectorAll('[data-case-detail]')];let pageIndex=0;
const pageNumber=root.querySelector('[data-case-page-number]'),zoomLabel=root.querySelector('[data-case-zoom]');const states=new WeakMap();
function state(stage){let value=states.get(stage);if(!value){value={scale:1,x:0,y:0,drag:false,px:0,py:0};states.set(stage,value)}return value}
function apply(stage){const s=state(stage),target=stage.querySelector('[data-case-transform]');if(target)target.style.transform=`translate(${s.x}px,${s.y}px) scale(${s.scale})`;if(zoomLabel)zoomLabel.textContent=`${Math.round(s.scale*100)}%`}
function showPage(key){const idx=pages.findIndex(page=>page.dataset.casePage===key);if(idx<0)return;pageIndex=idx;pages.forEach((page,i)=>{page.hidden=i!==idx;page.classList.toggle('is-active',i===idx)});if(pageNumber)pageNumber.textContent=String(idx+1);const stage=pages[idx].querySelector('[data-case-stage]');if(stage)apply(stage)}
function activate(id){buttons.forEach(button=>{const active=button.dataset.caseCandidate===id;button.classList.toggle('is-active',active);button.setAttribute('aria-pressed',active?'true':'false');if(active)showPage(button.dataset.casePageKey||'')});overlays.forEach(item=>item.classList.toggle('is-active',item.dataset.caseOverlay===id));details.forEach(item=>{const active=item.dataset.caseDetail===id;item.hidden=!active;item.classList.toggle('is-active',active)})}
buttons.forEach(button=>button.addEventListener('click',()=>activate(button.dataset.caseCandidate||'')));root.querySelector('[data-case-prev]')?.addEventListener('click',()=>showPage(pages[(pageIndex-1+pages.length)%pages.length]?.dataset.casePage||''));root.querySelector('[data-case-next]')?.addEventListener('click',()=>showPage(pages[(pageIndex+1)%pages.length]?.dataset.casePage||''));root.querySelector('[data-case-reset]')?.addEventListener('click',()=>{const stage=pages[pageIndex]?.querySelector('[data-case-stage]');if(!stage)return;states.set(stage,{scale:1,x:0,y:0,drag:false,px:0,py:0});apply(stage)});
pages.forEach(page=>{const stage=page.querySelector('[data-case-stage]');if(!stage)return;stage.addEventListener('wheel',event=>{event.preventDefault();const s=state(stage),next=Math.min(4,Math.max(.5,s.scale*(event.deltaY<0?1.12:.89)));s.scale=next;apply(stage)},{passive:false});stage.addEventListener('pointerdown',event=>{if(event.button!==0)return;const s=state(stage);s.drag=true;s.px=event.clientX;s.py=event.clientY;stage.setPointerCapture(event.pointerId);stage.classList.add('is-dragging')});stage.addEventListener('pointermove',event=>{const s=state(stage);if(!s.drag)return;s.x+=event.clientX-s.px;s.y+=event.clientY-s.py;s.px=event.clientX;s.py=event.clientY;apply(stage)});const stop=event=>{const s=state(stage);s.drag=false;stage.classList.remove('is-dragging');try{stage.releasePointerCapture(event.pointerId)}catch(_){}};stage.addEventListener('pointerup',stop);stage.addEventListener('pointercancel',stop)});if(buttons[0])activate(buttons[0].dataset.caseCandidate||'');else showPage(pages[0]?.dataset.casePage||'');})();
"""


__all__ = ["render_case_visual_review"]
