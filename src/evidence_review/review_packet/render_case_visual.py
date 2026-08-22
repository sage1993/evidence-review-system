# ruff: noqa: E501
"""Render the Issue #119 reference-subject-findings visual review workspace."""
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


def _geometry(candidate: Mapping[str, object]) -> tuple[str, Sequence[object]]:
    geometry = _mapping(candidate.get("geometry"), "case_visual.geometry")
    if geometry.get("coordinate_system") != "IMAGE_TOP_LEFT_PIXELS":
        raise ValueError("case visual renderer requires IMAGE_TOP_LEFT_PIXELS")
    return str(geometry.get("type", "")), _sequence(
        geometry.get("coordinates"), "case_visual.geometry.coordinates"
    )


def _shape(candidate: Mapping[str, object]) -> str:
    geometry_type, raw = _geometry(candidate)
    if geometry_type == "POINT":
        if len(raw) != 2:
            raise ValueError("POINT coordinates are invalid")
        return f'<circle class="case-visual-shape" cx="{_number(raw[0], "point.x"):g}" cy="{_number(raw[1], "point.y"):g}" r="8"/>'
    if geometry_type == "BBOX":
        if len(raw) != 4:
            raise ValueError("BBOX coordinates are invalid")
        left, top, right, bottom = (_number(raw[index], "bbox.coordinate") for index in range(4))
        return f'<rect class="case-visual-shape" x="{left:g}" y="{top:g}" width="{right-left:g}" height="{bottom-top:g}" rx="4" ry="4"/>'
    if geometry_type in {"LINESTRING", "POLYGON"}:
        points: list[str] = []
        for item in raw:
            point = _sequence(item, "case_visual.geometry.point")
            if len(point) != 2:
                raise ValueError("path coordinates are invalid")
            points.append(f'{_number(point[0], "path.x"):g},{_number(point[1], "path.y"):g}')
        if not points:
            raise ValueError("path coordinates are empty")
        tag = "polyline" if geometry_type == "LINESTRING" else "polygon"
        return f'<{tag} class="case-visual-shape" points="{" ".join(points)}"/>'
    raise ValueError(f"unsupported case visual geometry: {geometry_type}")


def _anchor(candidate: Mapping[str, object]) -> tuple[float, float]:
    geometry_type, raw = _geometry(candidate)
    if geometry_type == "POINT" and len(raw) == 2:
        return _number(raw[0], "point.x"), _number(raw[1], "point.y")
    if geometry_type == "BBOX" and len(raw) == 4:
        left, top, right, bottom = (_number(raw[index], "bbox.coordinate") for index in range(4))
        return (left + right) / 2, (top + bottom) / 2
    points: list[tuple[float, float]] = []
    for item in raw:
        point = _sequence(item, "case_visual.geometry.point")
        if len(point) == 2:
            points.append((_number(point[0], "path.x"), _number(point[1], "path.y")))
    if not points:
        raise ValueError("visual geometry has no focus point")
    return sum(x for x, _ in points) / len(points), sum(y for _, y in points) / len(points)


def _label(candidate: Mapping[str, object]) -> str:
    value = candidate.get("display_value")
    return value.strip() if isinstance(value, str) and value.strip() else str(candidate.get("candidate_type", "시각 관찰"))


def _status(tone: str) -> tuple[str, str]:
    return {
        "issue": ("불일치", "mismatch"),
        "compliant": ("일치", "match"),
        "review": ("확인 필요", "needs-check"),
        "observation": ("비교 불가", "not-comparable"),
    }.get(tone, ("비교 불가", "not-comparable"))


def _claim_index(model: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for index, item in enumerate(_sequence(model.get("claims", []), "claims")):
        claim = _mapping(item, f"claims[{index}]")
        claim_id = str(claim.get("claim_id", ""))
        if claim_id:
            result[claim_id] = claim
    return result


def _references(candidate: Mapping[str, object], claims: Mapping[str, Mapping[str, object]]) -> tuple[str, str]:
    linked_ids = [
        str(_mapping(item, "candidate.claim").get("claim_id", ""))
        for item in _sequence(candidate.get("claims", []), "candidate.claims")
    ]
    cards: list[str] = []
    criterion = "연결된 기준 근거 없음"
    for claim_id in linked_ids:
        claim = claims.get(claim_id)
        if claim is None:
            continue
        citations = [_mapping(item, "claim.citation") for item in _sequence(claim.get("citations", []), "claim.citations")]
        if citations:
            for citation in citations:
                quote = str(citation.get("quote", ""))
                if criterion == "연결된 기준 근거 없음" and quote.strip():
                    criterion = quote.strip()
                cards.append(
                    "".join(
                        (
                            '<article class="reference-card">',
                            f'<div class="reference-source"><strong>{_text(citation.get("document_name") or citation.get("title") or "기준 근거")}</strong>',
                            f'<span>p.{_text(citation.get("page_number"))}</span></div>',
                            f'<blockquote>{_text(quote)}</blockquote>',
                            "</article>",
                        )
                    )
                )
        else:
            text = str(claim.get("text", ""))
            if criterion == "연결된 기준 근거 없음" and text.strip():
                criterion = text.strip()
            cards.append(f'<article class="reference-card"><p>{_text(text)}</p></article>')
    if not cards:
        cards.append('<div class="reference-empty"><strong>직접 연결된 기준 근거가 없습니다.</strong><p>이 관찰은 사용자 파일에서 확인된 위치이며, 법규·설계기준과 동일 비교대상인지 추가 확인이 필요합니다.</p></div>')
    return "".join(cards), criterion


def _icon(name: str) -> str:
    paths = {
        "prev": '<path d="M15 18l-6-6 6-6"/>',
        "next": '<path d="M9 18l6-6-6-6"/>',
        "plus": '<path d="M12 5v14M5 12h14"/>',
        "minus": '<path d="M5 12h14"/>',
        "fit": '<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/>',
    }
    return f'<svg class="toolbar-icon" viewBox="0 0 24 24" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{paths[name]}</g></svg>'


def _strip_case_raster_payload(model: Mapping[str, object]) -> None:
    """Keep raster bytes in rendered <img> only; omit them from review-model JSON."""
    visual = model.get("case_visual_review")
    if not isinstance(visual, dict):
        return
    pages = visual.get("pages")
    if not isinstance(pages, list):
        return
    for page in pages:
        if isinstance(page, dict):
            page.pop("data_uri", None)


def render_case_visual_review(model: Mapping[str, object]) -> str:
    """Render a reference ↔ subject ↔ findings workspace for verified CASE visuals."""
    raw = model.get("case_visual_review")
    if raw is None:
        return ""
    visual = _mapping(raw, "case_visual_review")
    if visual.get("status") != "VISUAL_ANALYSIS_VALIDATED":
        raise ValueError("case visual review must be validated before rendering")
    pages = [_mapping(item, f"case_visual_review.pages[{index}]") for index, item in enumerate(_sequence(visual.get("pages", []), "case_visual_review.pages"))]
    if not pages:
        raise ValueError("validated case visual review requires at least one page")

    claims = _claim_index(model)
    page_html: list[str] = []
    reference_html: list[str] = []
    finding_html: list[str] = []
    candidate_count = 0

    for page_index, page in enumerate(pages):
        asset_key = str(page.get("asset_key", ""))
        width = _number(page.get("width"), "case_visual_page.width")
        height = _number(page.get("height"), "case_visual_page.height")
        data_uri = str(page.get("data_uri", ""))
        if not data_uri.startswith("data:image/"):
            raise ValueError("case visual raster data URI is missing")
        overlays: list[str] = []
        candidates = [_mapping(item, "case_visual_page.candidate") for item in _sequence(page.get("candidates", []), "case_visual_page.candidates")]
        for candidate in candidates:
            candidate_id = str(candidate.get("candidate_id", ""))
            tone = str(candidate.get("tone", "observation"))
            x, y = _anchor(candidate)
            overlays.append(
                f'<g class="case-visual-overlay tone-{_text(tone)}" data-case-overlay="{_text(candidate_id)}">'
                f'{_shape(candidate)}<circle class="case-visual-marker" cx="{x:g}" cy="{y:g}" r="7"/></g>'
            )
            refs, criterion = _references(candidate, claims)
            reference_html.append(
                f'<section class="reference-focus{" is-active" if candidate_count == 0 else ""}" data-case-reference="{_text(candidate_id)}"{"" if candidate_count == 0 else " hidden"}>{refs}</section>'
            )
            label = _label(candidate)
            status_label, status_class = _status(tone)
            issues = " · ".join(str(item) for item in _sequence(candidate.get("issue_ids", []), "candidate.issue_ids"))
            finding_html.append(
                "".join(
                    (
                        f'<article class="finding-panel status-{status_class}{" is-active" if candidate_count == 0 else ""}" data-case-finding="{_text(candidate_id)}" data-case-page-key="{_text(asset_key)}"{"" if candidate_count == 0 else " hidden"}>',
                        '<div class="finding-title-row">',
                        f'<span class="finding-number">{candidate_count + 1:02d}</span>',
                        f'<span class="finding-status">{_text(status_label)}</span></div>',
                        f'<h3>{_text(label)}</h3>',
                        f'<p class="finding-issue">{_text(issues or "시각 관찰")}</p>',
                        '<dl class="comparison-grid">',
                        f'<div><dt>기준</dt><dd>{_text(criterion)}</dd></div>',
                        f'<div><dt>사용자 파일</dt><dd>{_text(label)}</dd></div>',
                        "</dl>",
                        '<p class="finding-boundary">Finding 선택 시 기준 근거와 사용자 파일 위치가 각각 독립적으로 Focus됩니다.</p>',
                        "</article>",
                    )
                )
            )
            candidate_count += 1
        page_html.append(
            "".join(
                (
                    f'<figure class="case-visual-page{" is-active" if page_index == 0 else ""}" data-case-page="{_text(asset_key)}"{"" if page_index == 0 else " hidden"}>',
                    '<div class="case-visual-stage" data-case-stage tabindex="0">',
                    '<div class="case-visual-transform" data-case-transform>',
                    f'<img src="{_text(data_uri)}" alt="{_text(page.get("document_name"))} 페이지 {_text(page.get("page"))}">',
                    f'<svg viewBox="0 0 {width:g} {height:g}" preserveAspectRatio="xMidYMid meet" aria-label="사용자 파일 검토 위치">{"".join(overlays)}</svg>',
                    "</div></div>",
                    f'<figcaption>{_text(page.get("document_name"))} · p.{_text(page.get("page"))}</figcaption>',
                    "</figure>",
                )
            )
        )

    if candidate_count == 0:
        reference_html.append('<section class="reference-focus is-active"><div class="reference-empty">연결된 Finding이 없습니다.</div></section>')
        finding_html.append('<article class="finding-panel is-active"><h3>시각분석 완료</h3><p>위치 기반 Finding이 생성되지 않았습니다.</p></article>')

    _strip_case_raster_payload(model)
    return "".join(
        (
            f"<style>{CASE_VISUAL_CSS}</style>",
            '<section id="case-visual-review" class="visual-review-workspace" aria-label="기준 근거와 사용자 파일 대조 Workspace">',
            '<div class="workspace-grid">',
            '<div class="comparison-workspace" data-case-split style="--reference-width:42%">',
            '<section class="reference-viewer" aria-label="기준 근거 Viewer"><header><strong>기준 근거</strong><span>Reference</span></header><div class="reference-body">',
            "".join(reference_html),
            "</div></section>",
            '<button class="viewer-divider" type="button" role="separator" aria-label="기준 근거와 사용자 파일 폭 조절" aria-orientation="vertical" aria-valuemin="26" aria-valuemax="70" aria-valuenow="42" data-case-divider><span></span></button>',
            '<section class="subject-viewer" aria-label="사용자 파일 Viewer">',
            '<header class="subject-toolbar"><div><strong>사용자 파일</strong><span>Subject</span></div><div class="viewer-controls">',
            f'<button type="button" data-case-prev aria-label="이전 페이지">{_icon("prev")}</button><span><b data-case-page-number>1</b> / {len(pages)}</span><button type="button" data-case-next aria-label="다음 페이지">{_icon("next")}</button>',
            '<span class="control-separator"></span>',
            f'<button type="button" data-case-zoom-out aria-label="축소">{_icon("minus")}</button><span data-case-zoom>100%</span><button type="button" data-case-zoom-in aria-label="확대">{_icon("plus")}</button><button type="button" data-case-reset aria-label="화면 맞춤">{_icon("fit")}</button>',
            '</div></header><div class="subject-body">',
            "".join(page_html),
            "</div></section></div>",
            '<aside class="findings-panel" aria-label="대조 결과"><header><strong>대조 결과</strong><span>Findings</span></header><div class="findings-body">',
            "".join(finding_html),
            '</div><footer class="finding-pagination"><button type="button" data-finding-prev aria-label="이전 Finding">‹</button>',
            f'<span><b data-finding-number>{1 if candidate_count else 0}</b> / {candidate_count}</span><button type="button" data-finding-next aria-label="다음 Finding">›</button></footer></aside>',
            "</div>",
            '<p class="case-visual-help">마우스 휠로 커서 위치 기준 확대·축소 · 좌클릭 드래그 Pan · 더블클릭 Fit · 중앙 Divider 드래그로 Viewer 폭 조절</p>',
            f"<script>{CASE_VISUAL_SCRIPT}</script>",
            "</section>",
        )
    )


CASE_VISUAL_CSS = r"""
#case-visual-review{--line:#d0d5dd;--muted:#667085;--panel:#fff;--canvas:#e9edf2;height:calc(100vh - 24px);min-height:560px;max-height:920px;margin:12px 0;border:1px solid var(--line);border-radius:12px;background:#fff;overflow:hidden;display:grid;grid-template-rows:minmax(0,1fr) 30px}.workspace-grid{min-height:0;display:grid;grid-template-columns:minmax(0,1fr) minmax(280px,330px)}.comparison-workspace{min-width:0;display:grid;grid-template-columns:var(--reference-width,42%) 10px minmax(0,1fr)}.reference-viewer,.subject-viewer,.findings-panel{min-width:0;min-height:0;background:var(--panel);display:grid}.reference-viewer,.subject-viewer{grid-template-rows:42px minmax(0,1fr)}.findings-panel{grid-template-rows:42px minmax(0,1fr) 44px;border-left:1px solid var(--line)}.reference-viewer>header,.findings-panel>header,.subject-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:0 12px;border-bottom:1px solid var(--line);background:#f8fafc;font-size:12px}.reference-viewer header span,.findings-panel header span,.subject-toolbar span{font-size:10px;color:var(--muted)}.reference-body{min-height:0;overflow:hidden;padding:12px}.reference-focus{height:100%;overflow:auto}.reference-card{border:1px solid #e4e7ec;border-radius:9px;padding:12px;margin-bottom:9px;background:#fff}.reference-source{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:var(--muted)}.reference-source strong{color:#344054}.reference-card blockquote{margin:10px 0 0;padding:0;font-size:13px;line-height:1.65;color:#101828}.reference-empty{display:grid;place-content:center;height:100%;text-align:center;color:var(--muted);font-size:12px}.reference-empty p{max-width:320px;line-height:1.55}.viewer-divider{padding:0;border:0;border-left:1px solid #e4e7ec;border-right:1px solid #e4e7ec;background:#f2f4f7;cursor:col-resize;display:grid;place-items:center}.viewer-divider span{width:3px;height:42px;border-radius:2px;background:#98a2b3}.viewer-divider:hover,.viewer-divider:focus-visible{background:#e4e7ec;outline:none}.subject-toolbar>div:first-child{display:flex;align-items:baseline;gap:7px}.viewer-controls{display:flex;align-items:center;gap:5px}.viewer-controls button{width:28px;height:28px;border:1px solid #d0d5dd;border-radius:6px;background:#fff;display:grid;place-items:center;color:#344054}.toolbar-icon{width:15px;height:15px}.control-separator{width:1px;height:18px;background:#d0d5dd;margin:0 3px}.subject-body{position:relative;min-height:0;overflow:hidden;background:var(--canvas)}.case-visual-page{position:absolute;inset:0;margin:0;display:grid;grid-template-rows:minmax(0,1fr) 26px}.case-visual-stage{position:relative;overflow:hidden;cursor:grab;touch-action:none}.case-visual-stage.is-dragging{cursor:grabbing}.case-visual-transform{position:absolute;inset:0;transform-origin:0 0;will-change:transform}.case-visual-transform img,.case-visual-transform svg{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}.case-visual-transform svg{pointer-events:none}.case-visual-page figcaption{display:grid;place-items:center;border-top:1px solid var(--line);background:#fff;color:var(--muted);font-size:10px}.case-visual-overlay{stroke-width:2.5;vector-effect:non-scaling-stroke}.case-visual-shape{fill:transparent;opacity:.1}.case-visual-marker{vector-effect:non-scaling-stroke;stroke-width:2;fill:#fff;opacity:.9}.case-visual-overlay.tone-issue{stroke:#d92d20}.case-visual-overlay.tone-review{stroke:#f79009}.case-visual-overlay.tone-observation{stroke:#2e90fa}.case-visual-overlay.tone-compliant{stroke:#12b76a}.case-visual-overlay.is-active .case-visual-shape{opacity:.9;fill:rgba(46,144,250,.05)}.case-visual-overlay.is-active{stroke-width:4;filter:drop-shadow(0 0 2px rgba(0,0,0,.25))}.findings-body{min-height:0;overflow:hidden;padding:14px}.finding-panel{height:100%;overflow:auto}.finding-title-row{display:flex;align-items:center;justify-content:space-between}.finding-number{font:600 11px ui-monospace,monospace;color:var(--muted)}.finding-status{font-size:11px;font-weight:700;padding:4px 7px;border-radius:999px}.status-mismatch .finding-status{color:#b42318;background:#fef3f2}.status-match .finding-status{color:#027a48;background:#ecfdf3}.status-needs-check .finding-status{color:#b54708;background:#fffaeb}.status-not-comparable .finding-status{color:#175cd3;background:#eff8ff}.finding-panel h3{font-size:16px;margin:12px 0 5px}.finding-issue{font-size:11px;color:var(--muted);margin:0 0 16px}.comparison-grid{display:grid;gap:9px;margin:0}.comparison-grid div{padding:10px;border:1px solid #e4e7ec;border-radius:8px}.comparison-grid dt{font-size:10px;color:var(--muted);margin-bottom:4px}.comparison-grid dd{margin:0;font-size:12px;line-height:1.5}.finding-boundary{font-size:10px;line-height:1.5;color:var(--muted);margin-top:14px}.finding-pagination{display:flex;align-items:center;justify-content:center;gap:14px;border-top:1px solid var(--line);background:#f8fafc;font-size:11px}.finding-pagination button{width:30px;height:28px;border:1px solid #d0d5dd;border-radius:6px;background:#fff}.case-visual-help{margin:0;padding:6px 12px;border-top:1px solid #e4e7ec;color:var(--muted);font-size:10px;background:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}@media(max-width:900px){.workspace-grid{grid-template-columns:minmax(0,1fr) 285px}.comparison-workspace{--reference-width:38%}}@media(max-width:720px){#case-visual-review{height:calc(100vh - 12px);margin:6px 0}.workspace-grid{grid-template-columns:1fr}.findings-panel{position:absolute;right:8px;top:54px;bottom:38px;width:min(86vw,310px);z-index:5;box-shadow:0 8px 28px rgba(16,24,40,.18)}.comparison-workspace{grid-template-columns:0 0 1fr}.reference-viewer,.viewer-divider{visibility:hidden}}
"""


CASE_VISUAL_SCRIPT = r"""
(()=>{const root=document.getElementById('case-visual-review');if(!root||root.dataset.bound==='1')return;root.dataset.bound='1';const pages=[...root.querySelectorAll('[data-case-page]')],findings=[...root.querySelectorAll('[data-case-finding]')],refs=[...root.querySelectorAll('[data-case-reference]')],overlays=[...root.querySelectorAll('[data-case-overlay]')];let pageIndex=0,findingIndex=0;const states=new WeakMap(),pageNo=root.querySelector('[data-case-page-number]'),zoomLabel=root.querySelector('[data-case-zoom]'),findingNo=root.querySelector('[data-finding-number]');function state(stage){let s=states.get(stage);if(!s){s={scale:1,x:0,y:0,drag:false,px:0,py:0};states.set(stage,s)}return s}function apply(stage){const s=state(stage),t=stage.querySelector('[data-case-transform]');if(t)t.style.transform=`translate(${s.x}px,${s.y}px) scale(${s.scale})`;if(zoomLabel)zoomLabel.textContent=`${Math.round(s.scale*100)}%`}function reset(stage){states.set(stage,{scale:1,x:0,y:0,drag:false,px:0,py:0});apply(stage)}function showPage(key){const idx=pages.findIndex(p=>p.dataset.casePage===key);if(idx<0)return;pageIndex=idx;pages.forEach((p,i)=>{p.hidden=i!==idx;p.classList.toggle('is-active',i===idx)});if(pageNo)pageNo.textContent=String(idx+1);const stage=pages[idx].querySelector('[data-case-stage]');if(stage)apply(stage)}function activate(index){if(!findings.length)return;findingIndex=(index+findings.length)%findings.length;const active=findings[findingIndex],id=active.dataset.caseFinding||'';findings.forEach((f,i)=>{f.hidden=i!==findingIndex;f.classList.toggle('is-active',i===findingIndex)});refs.forEach(r=>{const on=r.dataset.caseReference===id;r.hidden=!on;r.classList.toggle('is-active',on)});overlays.forEach(o=>o.classList.toggle('is-active',o.dataset.caseOverlay===id));showPage(active.dataset.casePageKey||'');if(findingNo)findingNo.textContent=String(findingIndex+1)}root.querySelector('[data-finding-prev]')?.addEventListener('click',()=>activate(findingIndex-1));root.querySelector('[data-finding-next]')?.addEventListener('click',()=>activate(findingIndex+1));root.querySelector('[data-case-prev]')?.addEventListener('click',()=>showPage(pages[(pageIndex-1+pages.length)%pages.length]?.dataset.casePage||''));root.querySelector('[data-case-next]')?.addEventListener('click',()=>showPage(pages[(pageIndex+1)%pages.length]?.dataset.casePage||''));function zoom(factor,clientX,clientY){const stage=pages[pageIndex]?.querySelector('[data-case-stage]');if(!stage)return;const s=state(stage),rect=stage.getBoundingClientRect(),cx=clientX??rect.left+rect.width/2,cy=clientY??rect.top+rect.height/2,lx=(cx-rect.left-s.x)/s.scale,ly=(cy-rect.top-s.y)/s.scale,next=Math.min(5,Math.max(.5,s.scale*factor));s.x=cx-rect.left-lx*next;s.y=cy-rect.top-ly*next;s.scale=next;apply(stage)}root.querySelector('[data-case-zoom-in]')?.addEventListener('click',()=>zoom(1.2));root.querySelector('[data-case-zoom-out]')?.addEventListener('click',()=>zoom(.8333));root.querySelector('[data-case-reset]')?.addEventListener('click',()=>{const stage=pages[pageIndex]?.querySelector('[data-case-stage]');if(stage)reset(stage)});pages.forEach(page=>{const stage=page.querySelector('[data-case-stage]');if(!stage)return;stage.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?1.12:.89,e.clientX,e.clientY)},{passive:false});stage.addEventListener('dblclick',()=>reset(stage));stage.addEventListener('pointerdown',e=>{if(e.button!==0)return;const s=state(stage);s.drag=true;s.px=e.clientX;s.py=e.clientY;stage.setPointerCapture(e.pointerId);stage.classList.add('is-dragging')});stage.addEventListener('pointermove',e=>{const s=state(stage);if(!s.drag)return;s.x+=e.clientX-s.px;s.y+=e.clientY-s.py;s.px=e.clientX;s.py=e.clientY;apply(stage)});const stop=e=>{state(stage).drag=false;stage.classList.remove('is-dragging');try{stage.releasePointerCapture(e.pointerId)}catch(_){}};stage.addEventListener('pointerup',stop);stage.addEventListener('pointercancel',stop)});const split=root.querySelector('[data-case-split]'),divider=root.querySelector('[data-case-divider]');function setSplit(percent){if(!split||!divider)return;const value=Math.min(70,Math.max(26,percent));split.style.setProperty('--reference-width',`${value}%`);divider.setAttribute('aria-valuenow',String(Math.round(value)))}if(split&&divider){let dragging=false;divider.addEventListener('pointerdown',e=>{if(e.button!==0)return;dragging=true;divider.setPointerCapture(e.pointerId)});divider.addEventListener('pointermove',e=>{if(!dragging)return;const rect=split.getBoundingClientRect();setSplit((e.clientX-rect.left)/rect.width*100)});const stop=e=>{dragging=false;try{divider.releasePointerCapture(e.pointerId)}catch(_){}};divider.addEventListener('pointerup',stop);divider.addEventListener('pointercancel',stop);divider.addEventListener('dblclick',()=>setSplit(42));divider.addEventListener('keydown',e=>{const now=Number(divider.getAttribute('aria-valuenow')||42);if(e.key==='ArrowLeft'){e.preventDefault();setSplit(now-2)}if(e.key==='ArrowRight'){e.preventDefault();setSplit(now+2)}if(e.key==='Home'){e.preventDefault();setSplit(42)}})}if(findings.length)activate(0);else showPage(pages[0]?.dataset.casePage||'');})();
"""


__all__ = ["render_case_visual_review"]
