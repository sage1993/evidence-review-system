"""Self-contained SVG renderer for reviewer drawing annotation."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path
from typing import cast

from evidence_review.contracts.drawing import CoordinateSystem

_ALLOWED_IMAGE_MIMES = ("image/png", "image/jpeg")
_COORDINATE_SYSTEMS: tuple[CoordinateSystem, ...] = (
    "PDF_BOTTOM_LEFT_POINTS",
    "IMAGE_TOP_LEFT_PIXELS",
)
_CANDIDATE_TYPE_LABELS = {
    "DIMENSION_TEXT": "치수 표기",
    "DRAWING_SCALE": "도면 축척",
    "MAIN_ENTRY": "주출입구",
    "NORTH_ARROW": "방위표",
    "ROAD_WIDTH_TEXT": "도로 폭 표기",
    "SETBACK_LINE": "이격 경계선",
    "SITE_BOUNDARY": "대지 경계",
    "TEXT_ELEMENT": "문자 요소",
    "VEHICLE_ENTRANCE": "차량 출입구",
}
_ORIGIN_LABELS = {
    "EXTRACTOR": "추출기",
    "REVIEWER_MANUAL": "검토자 수동",
}
_STATUS_LABELS = {
    "UNCONFIRMED": "미확인",
    "CREATED": "신규 생성",
}


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _optional_text(value: object) -> str:
    return "" if value is None else str(value)


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be finite")
    return result


def _positive_number(value: object, field: str) -> float:
    result = _number(value, field)
    if result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _coordinate_system(value: object, field: str) -> CoordinateSystem:
    candidate = _string(value, field)
    if candidate not in _COORDINATE_SYSTEMS:
        raise ValueError(f"unsupported {field}: {candidate}")
    return candidate


def _position(value: object, field: str) -> tuple[float, float]:
    items = _sequence(value, field)
    if len(items) != 2:
        raise ValueError(f"{field} must contain two numbers")
    return (_number(items[0], f"{field}[0]"), _number(items[1], f"{field}[1]"))


def _display_position(
    position: tuple[float, float],
    page_height: float,
    coordinate_system: CoordinateSystem,
) -> tuple[float, float]:
    x, y = position
    if coordinate_system == "PDF_BOTTOM_LEFT_POINTS":
        return (x, page_height - y)
    return position


def _points_text(
    value: object,
    field: str,
    page_height: float,
    coordinate_system: CoordinateSystem,
) -> str:
    positions = tuple(
        _display_position(
            _position(item, f"{field}[{index}]"), page_height, coordinate_system
        )
        for index, item in enumerate(_sequence(value, field))
    )
    if not positions:
        raise ValueError(f"{field} must not be empty")
    return " ".join(f"{x},{y}" for x, y in positions)


def _geometry_html(
    candidate_id: str,
    value: object,
    page_height: float,
    coordinate_system: CoordinateSystem,
) -> str:
    geometry = _mapping(value, "candidate.geometry")
    geometry_type = _string(geometry.get("type"), "candidate.geometry.type")
    geometry_coordinate_system = _coordinate_system(
        geometry.get("coordinate_system"), "candidate.geometry.coordinate_system"
    )
    if geometry_coordinate_system != coordinate_system:
        raise ValueError("candidate geometry coordinate system mismatch")
    coordinates = geometry.get("coordinates")
    candidate_attr = escape(candidate_id, quote=True)

    if geometry_type == "POINT":
        x, y = _display_position(
            _position(coordinates, "candidate.geometry.coordinates"),
            page_height,
            coordinate_system,
        )
        return (
            f'<circle data-candidate-id="{candidate_attr}" '
            'class="candidate-geometry candidate-point" '
            f'cx="{x}" cy="{y}" r="6"></circle>'
        )

    if geometry_type == "BBOX":
        items = _sequence(coordinates, "candidate.geometry.coordinates")
        if len(items) != 4:
            raise ValueError("BBOX requires four coordinates")
        left = _number(items[0], "candidate.geometry.coordinates[0]")
        first_y = _number(items[1], "candidate.geometry.coordinates[1]")
        right = _number(items[2], "candidate.geometry.coordinates[2]")
        second_y = _number(items[3], "candidate.geometry.coordinates[3]")
        if left > right or first_y > second_y:
            raise ValueError("BBOX coordinates are inverted")
        display_y = first_y
        if coordinate_system == "PDF_BOTTOM_LEFT_POINTS":
            display_y = page_height - second_y
        return (
            f'<rect data-candidate-id="{candidate_attr}" class="candidate-geometry" '
            f'x="{left}" y="{display_y}" width="{right - left}" '
            f'height="{second_y - first_y}"></rect>'
        )

    if geometry_type in ("LINESTRING", "POLYGON"):
        points = _points_text(
            coordinates,
            "candidate.geometry.coordinates",
            page_height,
            coordinate_system,
        )
        tag = "polyline" if geometry_type == "LINESTRING" else "polygon"
        fill = ' fill="none"' if geometry_type == "LINESTRING" else ""
        return (
            f'<{tag} data-candidate-id="{candidate_attr}" '
            f'class="candidate-geometry"{fill} '
            f'points="{escape(points, quote=True)}"></{tag}>'
        )

    raise ValueError(f"unsupported candidate geometry type: {geometry_type}")


def _candidate_button(value: object) -> str:
    candidate = _mapping(value, "candidate")
    candidate_id = _string(candidate.get("candidate_id"), "candidate.candidate_id")
    candidate_type = _string(candidate.get("candidate_type"), "candidate.candidate_type")
    origin = _string(candidate.get("origin"), "candidate.origin")
    status = _string(candidate.get("status"), "candidate.status")
    raw_value = _optional_text(candidate.get("raw_value"))
    normalized = _optional_text(candidate.get("normalized_candidate"))
    display_value = normalized or raw_value
    candidate_type_label = _CANDIDATE_TYPE_LABELS.get(candidate_type, "기타 근거")
    origin_label = _ORIGIN_LABELS.get(origin, "알 수 없음")
    status_label = _STATUS_LABELS.get(status, "알 수 없음")
    state_class = " pending" if status == "UNCONFIRMED" else ""
    state_label = "확인 대기" if status == "UNCONFIRMED" else status_label
    return (
        "<li>"
        f'<button class="feature{state_class}" type="button" data-candidate-button '
        f'data-candidate-id="{escape(candidate_id, quote=True)}" '
        f'data-candidate-type="{escape(candidate_type, quote=True)}" '
        f'data-candidate-type-label="{escape(candidate_type_label, quote=True)}" '
        f'data-candidate-origin="{escape(origin, quote=True)}" '
        f'data-candidate-origin-label="{escape(origin_label, quote=True)}" '
        f'data-candidate-status="{escape(status, quote=True)}" '
        f'data-candidate-status-label="{escape(status_label, quote=True)}" '
        f'data-candidate-value="{escape(display_value, quote=True)}" '
        'aria-pressed="false">'
        '<span class="feature-copy">'
        f'<strong>{escape(candidate_type_label)}</strong>'
        f'<small>{escape(candidate_id)}</small></span>'
        '<span class="feature-side">'
        f'<span class="feature-value">{escape(display_value or "—")}</span>'
        f'<span class="feature-state">{escape(state_label)}</span></span>'
        "</button></li>"
    )


def _render_annotation_metrics(
    *, candidate_count: int, confirmed_count: int, short_hash: str
) -> str:
    """Project server-validated workspace counts into the summary cards."""
    return "".join(
        (
            '<section class="metrics" aria-label="검토 현황">',
            '<article class="metric"><span>소스 무결성</span><strong>검증됨</strong>'
            f'<small>{escape(short_hash)}…</small></article>',
            f'<article class="metric"><span>검출 객체</span><strong data-candidate-count>'
            f'{candidate_count}</strong><small>현재 페이지 후보</small></article>',
            f'<article class="metric"><span>확인 기록</span><strong data-confirmed-count>'
            f'{confirmed_count}</strong><small>추가 전용 기록</small></article>',
            '<article class="metric" data-tone="alert"><span>현재 상태</span>'
            '<strong>확인 필요</strong><small>엔진 바인딩 전</small></article>',
            '</section>',
        )
    )


def _render_candidate_summary(candidates: Sequence[object]) -> str:
    """Render the already validated candidate records without new domain outcomes."""
    rows: list[str] = []
    for value in candidates:
        candidate = _mapping(value, "candidate")
        candidate_type = _string(candidate.get("candidate_type"), "candidate.candidate_type")
        status = _string(candidate.get("status"), "candidate.status")
        display_value = _optional_text(candidate.get("normalized_candidate")) or _optional_text(
            candidate.get("raw_value")
        )
        rows.append(
            '<div class="kv-row"><span>'
            f'{escape(_CANDIDATE_TYPE_LABELS.get(candidate_type, "기타 근거"))}</span>'
            f'<strong>{escape(display_value or "—")}</strong>'
            f'<small>{escape(_STATUS_LABELS.get(status, "알 수 없음"))}</small></div>'
        )
    return '<div class="candidate-summary">' + "".join(rows) + '</div>'


def _render_rule_readiness() -> str:
    return (
        '<div class="empty-state" data-rule-readiness>'
        '<strong>연결된 승인 규칙 없음</strong>'
        '<p>확인된 입력만 서버 측 규칙·계산 엔진으로 전달됩니다.</p>'
        '</div>'
    )


def _render_confirmation_guidance() -> str:
    return "".join(
        (
            '<div class="confirmation-guidance"><span class="section-kicker">인적 입력 확인</span>',
            '<h2>입력 확인 안내</h2>',
            '<p>아래 검토자 영역에서 명시적인 조치를 선택하고 저장해야 '
            '다음 단계로 진행할 수 있습니다.</p>',
            '<div class="hold-reason"><strong>보류 사유</strong>',
            '<p>후보 선택과 검토자 조치가 기록되기 전에는 후속 판단을 진행하지 않습니다.</p>',
            '</div></div>',
        )
    )


def _review_controls() -> str:
    return "".join(
        (
            '<section class="detail-section selected-detail"><h3>선택 객체</h3>',
            '<p>식별자: <code data-detail-id></code></p>',
            '<p>유형: <span data-detail-type></span></p>',
            '<p>출처: <span data-detail-origin></span></p>',
            '<p>상태: <span data-detail-status></span></p>',
            '<p class="detail-value" data-detail-value></p></section>',
            '<section class="detail-section"><h3>검토자 입력</h3>',
            '<label>검토자 ID<input type="text" maxlength="128" '
            'autocomplete="off" data-reviewer></label>',
            '<label>확인 값<input type="text" maxlength="256" inputmode="decimal" '
            'autocomplete="off" data-confirmed-value></label>',
            '<label>단위<input type="text" maxlength="32" autocomplete="off" '
            'data-unit></label></section>',
            '<section class="detail-section"><h3>수동 형상 보정</h3>',
            '<label>형상 도구<select data-geometry-tool>',
            '<option value="">도구 선택</option>',
            '<option value="POINT">점</option>',
            '<option value="BBOX">사각형</option>',
            '<option value="LINESTRING">선</option>',
            '<option value="POLYGON">다각형</option>',
            '</select></label><div class="button-row">',
            '<button type="button" data-finish-geometry>선/영역 완료</button>',
            '<button type="button" data-clear-geometry>형상 지우기</button></div>',
            '<label>주석 ID<input type="text" maxlength="128" autocomplete="off" '
            'data-annotation-id></label>',
            '<label>후보 유형<input type="text" maxlength="128" autocomplete="off" '
            'data-candidate-type-input></label></section>',
            '<fieldset><legend>검토자 조치</legend>',
            '<label><input type="radio" name="review-action" value="ACCEPTED"> 승인</label>',
            '<label><input type="radio" name="review-action" value="REJECTED"> 반려</label>',
            '<label><input type="radio" name="review-action" value="EDITED"> 수정</label>',
            '<label><input type="radio" name="review-action" value="CREATED"> 신규</label>',
            '</fieldset><button class="primary-action" type="button" '
            'data-submit-action>검토 기록 저장</button>',
            '<output class="action-status" role="status" aria-live="polite" '
            'data-action-status></output>',
        )
    )


def _render_reviewer_action_panel() -> str:
    return "".join(
        (
            '<section class="review-panel" id="reviewer-action"><div class="review-heading"><div>',
            '<span class="section-kicker">추가 전용 인적 조치</span>',
            '<h2>검토자 확인 기록</h2></div>',
            '<p>자동 판정과 분리된 별도 기록으로 저장됩니다.</p></div>',
            '<div class="review-grid">',
            _review_controls(),
            '</div></section>',
        )
    )


def render_annotation_html(
    view_model: Mapping[str, object], page_image: bytes, mime: str
) -> str:
    """Render one self-contained reviewer annotation workspace."""
    model = _mapping(view_model, "view_model")
    if model.get("format") != "evidence-review/drawing-review-view":
        raise ValueError("unsupported drawing review view format")
    if model.get("version") != 1:
        raise ValueError("unsupported drawing review view version")
    if mime not in _ALLOWED_IMAGE_MIMES:
        raise ValueError("unsupported image MIME")
    if not isinstance(page_image, bytes) or not page_image:
        raise ValueError("page image must contain bytes")

    page_width = _positive_number(model.get("page_width"), "page_width")
    page_height = _positive_number(model.get("page_height"), "page_height")
    coordinate_system = _coordinate_system(model.get("coordinate_system"), "coordinate_system")
    source_sha256 = _string(model.get("source_sha256"), "source_sha256")
    page = model.get("page")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer")

    candidates = _sequence(model.get("candidates"), "candidates")
    buttons: list[str] = []
    geometries: list[str] = []
    confirmed_count = 0
    for value in candidates:
        candidate = _mapping(value, "candidate")
        candidate_id = _string(candidate.get("candidate_id"), "candidate.candidate_id")
        status = _string(candidate.get("status"), "candidate.status")
        confirmed_count += status != "UNCONFIRMED"
        buttons.append(_candidate_button(candidate))
        geometries.append(
            _geometry_html(candidate_id, candidate.get("geometry"), page_height, coordinate_system)
        )

    asset_root = Path(__file__).with_name("assets")
    css = (asset_root / "annotation.css").read_text(encoding="utf-8")
    javascript = (asset_root / "annotation.js").read_text(encoding="utf-8")
    encoded = base64.b64encode(page_image).decode("ascii")
    image_uri = f"data:{mime};base64,{encoded}"
    coordinate_attr = escape(coordinate_system, quote=True)
    short_hash = source_sha256[:16]

    return "".join(
        (
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width,initial-scale=1">',
            '<title>도면 근거 검토 화면</title>',
            f'<style>{css}</style></head><body><div class="app-shell">',
            '<header class="topbar"><div class="topbar-copy"><div class="eyebrow-row">',
            '<span class="status-badge" id="topStatus"><span class="status-dot"></span>'
            '입력 확인 필요</span>',
            f'<span class="run-ref">페이지 {page} · {escape(short_hash)}</span></div>',
            '<h1>도면 근거 검토 화면</h1>',
            '<p>검출된 도면 근거를 원본과 대조하고, 검토자 확인 기록을 남겨 주세요.</p>',
            '</div><div class="topbar-actions"><span class="offline-mark">로컬 · 오프라인</span>',
            '<button type="button" class="secondary-action" '
            'data-open-confirmation>확인 기록 열기</button>',
            '<button type="button" class="secondary-action" data-print-workspace>'
            'HTML 인쇄</button>',
            '</div></header>',
            _render_annotation_metrics(
                candidate_count=len(candidates),
                confirmed_count=confirmed_count,
                short_hash=short_hash,
            ),
            '<main class="main-grid">',
            '<aside class="candidate-panel panel"><div class="panel-heading"><div>',
            '<span class="section-kicker">검출 근거</span><h2>도면 입력 확인</h2></div>',
            f'<span class="count-badge">{len(candidates)}</span></div>',
            '<p class="panel-note">객체를 선택하면 도면 위치와 추출값을 함께 '
            '확인할 수 있습니다.</p>',
            '<ul class="candidate-list" id="featureList">',
            ''.join(buttons),
            '</ul><div class="candidate-legend"><span><i class="legend-box"></i>검출 영역</span>',
            '<span><i class="legend-dot"></i>선택 객체</span></div></aside>',
            '<section class="viewer-panel panel"><div class="viewer-toolbar"><div>',
            '<span class="section-kicker">검증된 원본</span><h2>원본 도면 대조</h2></div>',
            '<div class="mode-switch" role="group" aria-label="도면 표시 모드">',
            '<button type="button" data-display-mode="original">원본</button>',
            '<button type="button" class="is-active" data-display-mode="detection">검출</button>',
            '<button type="button" data-display-mode="compare">비교</button></div></div>',
            '<div class="drawing-stage mode-detection" id="drawingStage"><div class="page-canvas">',
            f'<img alt="검증된 도면 원본" src="{image_uri}">',
            '<svg data-annotation-overlay '
            f'data-coordinate-system="{coordinate_attr}" data-page-width="{page_width}" '
            f'data-page-height="{page_height}" viewBox="0 0 {page_width} {page_height}" '
            'preserveAspectRatio="none" aria-label="도면 후보 오버레이">',
            ''.join(geometries),
            '</svg></div><div class="stage-label">해시 검증 완료 · 읽기 전용</div></div>',
            '<div class="viewer-meta"><div><span>선택 객체</span>',
            '<strong id="selectedObject" data-selected-object>선택 안 됨</strong></div>',
            '<div><span>좌표 / 형상</span><strong id="selectedCoords" '
            'data-selected-coordinates>—</strong></div>',
            '<div><span>확인 상태</span><strong id="selectedStatus" '
            'data-selected-status>대기</strong></div></div></section>',
            '<aside class="detail-panel panel"><div class="workspace-tabs" role="tablist" '
            'aria-label="검토 정보">',
            '<button type="button" class="is-active" role="tab" id="annotation-tab-evidence" '
            'data-workspace-tab="evidence" aria-controls="annotation-pane-evidence" '
            'aria-selected="true" tabindex="0">근거</button>',
            '<button type="button" role="tab" id="annotation-tab-rules" '
            'data-workspace-tab="rules" aria-controls="annotation-pane-rules" '
            'aria-selected="false" tabindex="-1">규칙</button>',
            '<button type="button" role="tab" id="annotation-tab-confirmation" '
            'data-workspace-tab="confirmation" aria-controls="annotation-pane-confirmation" '
            'aria-selected="false" tabindex="-1">입력 확인</button></div>',
            '<div class="tab-pane" data-workspace-pane="evidence" role="tabpanel" '
            'id="annotation-pane-evidence" aria-labelledby="annotation-tab-evidence"><div '
            'class="evidence-summary">',
            '<span class="section-kicker">선택 근거</span><h2>선택 근거 상세</h2>',
            '<p>왼쪽 후보 또는 도면 오버레이를 선택하세요. 원본 추출값과 '
            '출처 상태만 표시됩니다.</p>',
            _render_candidate_summary(candidates),
            '<dl><div><dt>객체 ID</dt><dd data-detail-id>—</dd></div>',
            '<div><dt>유형</dt><dd data-detail-type>—</dd></div>',
            '<div><dt>출처</dt><dd data-detail-origin>—</dd></div>',
            '<div><dt>상태</dt><dd data-detail-status>—</dd></div></dl>',
            '<div class="evidence-value"><span>추출값</span>'
            '<strong data-detail-value>—</strong></div>',
            '</div></div><div class="tab-pane" data-workspace-pane="rules" role="tabpanel" '
            'id="annotation-pane-rules" aria-labelledby="annotation-tab-rules" hidden>',
            '<span class="section-kicker">결정론적 실행 경계</span><h2>엔진 실행 경계</h2>',
            _render_rule_readiness(),
            '<div class="engine-row"><span>파싱 엔진</span><strong>완료</strong></div>',
            '<div class="engine-row"><span>규칙·계산 엔진</span>'
            '<strong>확인 후 실행</strong></div>',
            '<p class="boundary-note">브라우저는 계산하거나 규칙을 판정하지 않습니다. '
            '확인된 입력만 서버 측 결정론 엔진에 전달됩니다.</p>',
            '</div><div class="tab-pane" data-workspace-pane="confirmation" role="tabpanel" '
            'id="annotation-pane-confirmation" '
            'aria-labelledby="annotation-tab-confirmation" hidden>',
            _render_confirmation_guidance(),
            '</div></aside></main>',
            _render_reviewer_action_panel(),
            '<footer class="status-strip" data-status-strip>',
            '<span><i></i>소스 해시 검증 완료</span><span>파싱 → 사용자 입력 확인</span>',
            '<span>규칙·계산 엔진 → 최종 검토</span>',
            '<strong>인적 최종 결정 · 없음</strong></footer></div>',
            f'<script>{javascript}</script></body></html>',
        )
    )
