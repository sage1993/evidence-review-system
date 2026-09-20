"""Loopback-only HTTP server for the drawing annotation workspace."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Literal, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

from evidence_review.contracts.drawing import (
    ConfirmedInput,
    DrawingConfirmation,
    confirmed_input_document,
    drawing_candidate_document,
)
from evidence_review.contracts.engines import CalculationResult
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.drawing_review.actions import decode_annotation_action
from evidence_review.drawing_review.service import (
    AnnotationActionResult,
    record_annotation_action,
)
from evidence_review.drawing_review.view_model import DrawingPage
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.local_http_transport import (
    ContentLengthError,
    allowed_methods_for_tokenized_route,
    drain_rejected_body,
    loopback_request_is_authorized,
    reject_oversized_body,
    send_protected_response,
    tokenized_route_matches,
    validate_content_length,
)
from evidence_review.math_engine.formulas import (
    DRAWING_REGISTRY,
    DRAWING_SCALE_ID,
    DRAWING_SCALE_VERSION,
    run_calculation,
)
from evidence_review.parsing.drawing_calibration import (
    CalibrationRecord,
    CalibrationReference,
    build_calibration,
    persist_calibration,
)
from evidence_review.parsing.drawing_candidates import load_candidate
from evidence_review.parsing.drawing_case import CaseManifestEntry
from evidence_review.parsing.drawing_confirmation import (
    load_and_verify_confirmation,
    parse_confirmation_time,
    validate_confirmation_for_candidate,
)
from evidence_review.review_packet.drawing_evidence import render_drawing_evidence

_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_DEFAULT_MAX_BODY_BYTES = 64 * 1024
_CSP = (
    "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)


def _default_authority_hashes() -> tuple[str | None, str | None]:
    """Resolve only the bundled formula authority.

    Rule authority belongs to the caller's validated workspace. The public
    package does not bundle a repository ``rules/`` tree, so silently deriving
    a rule hash from the source checkout would make installed and source runs
    disagree.
    """
    try:
        from evidence_review.math_engine.formulas import DRAWING_REGISTRY
        from evidence_review.math_engine.manifest import formula_manifest_hash

        formula_hash = formula_manifest_hash(DRAWING_REGISTRY.values())
        return None, formula_hash
    except (OSError, ValueError):
        return None, None


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return validate_identifier(value, field)


def _query(path: str, allowed: set[str]) -> dict[str, str]:
    raw_query = urlsplit(path).query
    if not raw_query:
        return {}
    if "+" in raw_query or re.search(r"%(?![0-9A-Fa-f]{2})", raw_query):
        raise ValueError("invalid query encoding")
    try:
        pairs = parse_qsl(raw_query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise ValueError("invalid query encoding") from error
    result: dict[str, str] = {}
    for key, value in pairs:
        if key not in allowed or not value or key in result:
            raise ValueError("invalid query")
        result[key] = _identifier(value, key)
    return result


def _json_body(body: bytes) -> object:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("INVALID_CALIBRATION") from error


def _calibration_reference(payload: Mapping[str, object]) -> CalibrationReference:
    points = payload.get("pixel_points")
    if not isinstance(points, list) or len(points) != 2:
        raise ValueError("pixel_points must contain two points")
    converted: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("pixel_points must contain numeric pairs")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in point):
            raise ValueError("pixel_points must contain numeric pairs")
        converted.append((float(point[0]), float(point[1])))
    axis = payload.get("axis")
    real_length = payload.get("real_length")
    unit = payload.get("unit")
    if not isinstance(axis, str) or not isinstance(real_length, str) or not isinstance(unit, str):
        raise ValueError("invalid calibration reference")
    return CalibrationReference(
        pixel_points=(converted[0], converted[1]),
        real_length=real_length,
        unit=unit,
        axis=cast("Literal['x', 'y']", axis),
    )


def _calibration_html(
    *,
    page: DrawingPage,
    source_sha256: str,
    candidate_id: str | None,
    confirmation_id: str | None,
    reviewer: str | None,
    confirmed_at: str,
) -> str:
    candidate_value = "" if candidate_id is None else escape(candidate_id, quote=True)
    confirmation_value = "" if confirmation_id is None else escape(confirmation_id, quote=True)
    reviewer_value = "" if reviewer is None else escape(reviewer, quote=True)
    reviewer_readonly = "" if reviewer is None else " readonly"
    return (
        "<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><title>Calibration</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;color:#172033}"
        "label{display:block;margin:.7rem 0}input,select{display:block;padding:.4rem;"
        "width:20rem;max-width:100%}button{padding:.5rem 1rem}</style></head><body>"
        "<h1>Calibration</h1>"
        f"<p>Page: {page.page}</p><p>Source SHA-256: <code>{escape(source_sha256)}</code></p>"
        f"<form id=\"calibration-form\" method=\"post\" action=\"\"><input "
        f"type=\"hidden\" name=\"confirmed_at\" "
        f"value=\"{escape(confirmed_at, quote=True)}\">"
        f"<input type=\"hidden\" name=\"candidate_id\" value=\"{candidate_value}\">"
        f"<input type=\"hidden\" name=\"confirmation_id\" value=\"{confirmation_value}\">"
        f"<label>Reviewer ID<input name=\"reviewer\" value=\"{reviewer_value}\" required"
        f"{reviewer_readonly}></label>"
        "<label>Axis<select name=\"axis\"><option value=\"x\">x</option>"
        "<option value=\"y\">y</option></select></label>"
        "<label>First pixel point<input name=\"point_1\" value=\"1200,900\" required></label>"
        "<label>Second pixel point<input name=\"point_2\" value=\"8400,900\" required></label>"
        "<label>Real length<input name=\"real_length\" value=\"35.0\" required></label>"
        "<label>Unit<input name=\"unit\" value=\"m\" required></label>"
        "<button type=\"submit\">Save calibration</button></form>"
        "<output id=\"calibration-status\" role=\"status\"></output>"
        "<script>"
        "document.querySelector('#calibration-form').addEventListener("
        "'submit',async(event)=>{"
        "event.preventDefault();const form=event.currentTarget;"
        "const point=(name)=>form.elements[name].value.split(',').map(Number);"
        "const payload={candidate_id:form.elements.candidate_id.value,"
        "confirmation_id:form.elements.confirmation_id.value,"
        "reviewer:form.elements.reviewer.value,"
        "confirmed_at:form.elements.confirmed_at.value,axis:form.elements.axis.value,"
        "pixel_points:[point('point_1'),point('point_2')],"
        "real_length:form.elements.real_length.value,unit:form.elements.unit.value};"
        "const response=await fetch(window.location.pathname,{method:'POST',"
        "headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});"
        "const result=await response.json();"
        "document.querySelector('#calibration-status').innerHTML=response.ok?"
        "'<a href=\"'+result.packet_url+'\">Open Review Packet</a>':result.error;"
        "});</script></body></html>"
    )


def _annotation_handoff_html(html: str, calibration_url: str) -> str:
    link = (
        f'<p class="calibration-handoff"><a data-calibration-link hidden '
        f'aria-disabled="true" href="{escape(calibration_url, quote=True)}">'
        "Open calibration workspace</a></p>"
    )
    if "</body>" in html:
        return html.replace("</body>", f"{link}</body>", 1)
    return html + link


def _verified_bytes(case_dir: Path, entry: CaseManifestEntry) -> bytes:
    payload_path = verified_regular_file_below(
        case_dir,
        tuple(entry.relative_path.split("/")),
        field="case artifact",
    )
    payload = payload_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != entry.sha256:
        raise ValueError("ARTIFACT_HASH_MISMATCH")
    return payload


def _calculation_manifest_hash() -> str:
    from evidence_review.math_engine.formulas import DRAWING_REGISTRY
    from evidence_review.math_engine.manifest import formula_manifest_hash

    return formula_manifest_hash(DRAWING_REGISTRY.values())


def _calculation_document(result: CalculationResult) -> dict[str, object]:
    document: dict[str, object] = {
        "calculation_result_id": result.calculation_result_id,
        "status": result.status,
        "formula_id": result.formula_id,
        "formula_version": result.formula_version,
        "inputs": dict(result.inputs),
        "substitution": result.substitution,
        "raw_result": result.raw_result,
        "display_result": result.display_result,
        "comparison": result.comparison,
        "formula_manifest_hash": result.formula_manifest_hash,
        "result_hash": result.result_hash,
        "error_codes": list(result.error_codes),
    }
    if result.input_sources:
        document["input_sources"] = dict(result.input_sources)
    if result.input_units:
        document["input_units"] = dict(result.input_units)
    if result.precision is not None:
        document["precision"] = result.precision
    if result.rounding is not None:
        document["rounding"] = result.rounding
    if result.intermediate_rounding_policy is not None:
        document["intermediate_rounding_policy"] = result.intermediate_rounding_policy
    return document


def _entry_document(entry: CaseManifestEntry | None) -> dict[str, object] | None:
    if entry is None:
        return None
    return {
        "artifact_id": entry.artifact_id,
        "relative_path": entry.relative_path,
        "sha256": entry.sha256,
    }


def _result_document(result: AnnotationActionResult) -> dict[str, object]:
    return {
        "candidate": _entry_document(result.candidate_entry),
        "confirmation": _entry_document(result.confirmation_entry),
    }


def _validate_case_dir(case_dir: Path) -> Path:
    return verified_regular_directory(case_dir, field="case_dir")


def _validated_token(token: str | None) -> str:
    value = secrets.token_urlsafe(32) if token is None else token
    if not _TOKEN_PATTERN.fullmatch(value):
        raise ValueError("token must be a 32-128 character URL-safe string")
    return value


class _AnnotationHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        *,
        html: str,
        case_dir: Path,
        page: DrawingPage,
        candidate_entries: Mapping[str, CaseManifestEntry],
        token: str,
        port: int,
        max_body_bytes: int,
        page_image: bytes | None,
        mime: str,
        rule_manifest_sha256: str | None,
        formula_manifest_sha256: str | None,
    ) -> None:
        self.html_bytes = html.encode("utf-8")
        self.case_dir = case_dir
        self.page = page
        self.candidate_entries = dict(candidate_entries)
        self.token = token
        self.max_body_bytes = max_body_bytes
        self.page_image = page_image
        self.mime = mime
        default_rule_hash, default_formula_hash = _default_authority_hashes()
        self.rule_manifest_sha256 = rule_manifest_sha256 or default_rule_hash
        self.formula_manifest_sha256 = formula_manifest_sha256 or default_formula_hash
        self.results: list[AnnotationActionResult] = []
        self.confirmation_records: dict[
            str, tuple[DrawingConfirmation, CaseManifestEntry, str]
        ] = {}
        self.calibration_records: dict[str, tuple[CalibrationRecord, CaseManifestEntry]] = {}
        self.action_lock = Lock()
        super().__init__(("127.0.0.1", port), _AnnotationHandler)
        host, assigned_port = cast(tuple[str, int], self.server_address)
        self.expected_host = f"{host}:{assigned_port}"
        self.origin = f"http://{self.expected_host}"
        self.html_bytes = _annotation_handoff_html(
            html,
            f"{self.origin}/calibration/{self.token}",
        ).encode("utf-8")


class _AnnotationHandler(BaseHTTPRequestHandler):
    server_version = "EvidenceReviewAnnotation/1"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        return None

    @property
    def state(self) -> _AnnotationHTTPServer:
        return cast(_AnnotationHTTPServer, self.server)

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        allow: str | None = None,
    ) -> None:
        send_protected_response(
            self,
            status,
            body,
            content_type,
            content_security_policy=_CSP,
            allow=allow,
        )

    def _send_json(
        self,
        status: int,
        payload: Mapping[str, object],
        *,
        allow: str | None = None,
    ) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8", allow=allow)

    def _reject(
        self,
        status: int,
        code: str,
        *,
        drain_body: bool = True,
        allow: str | None = None,
    ) -> None:
        self._send_json(status, {"error": code}, allow=allow)
        if drain_body:
            # Publish the bounded rejection before waiting for any unread body.
            # This keeps Windows clients from aborting while the server drains a
            # slow rejected request, while drain_rejected_body still closes
            # incomplete or oversized requests before they can be reused.
            self.wfile.flush()
            drain_rejected_body(self)

    def _reject_oversized_body(self, length: int) -> None:
        reject_oversized_body(
            self,
            length,
            lambda status, code: self._reject(status, code, drain_body=False),
        )

    def _method_not_allowed(self) -> None:
        allow = allowed_methods_for_tokenized_route(
            urlsplit(self.path).path,
            expected_token=self.state.token,
            routes={
                ("annotation", ()): "GET",
                ("annotation", ("actions",)): "POST",
                ("calibration", ()): "GET, POST",
                ("review-packet", ()): "GET",
            },
        )
        if allow is None:
            self._reject(404, "NOT_FOUND")
            return
        self._reject(405, "METHOD_NOT_ALLOWED", allow=allow)

    def _matches_route(self, suffix: str) -> bool:
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment:
            self._reject(404, "NOT_FOUND")
            return False
        suffix_parts = () if not suffix else tuple(suffix.removeprefix("/").split("/"))
        if tokenized_route_matches(
            parsed.path,
            route_name="annotation",
            expected_token=self.state.token,
            suffix=suffix_parts,
        ):
            return True
        if parsed.path.startswith("/annotation/"):
            self._reject(403, "FORBIDDEN")
            return False
        self._reject(404, "NOT_FOUND")
        return False

    def _matches_workspace_route(self, name: str) -> tuple[object, str] | None:
        parsed = urlsplit(self.path)
        if parsed.fragment or not tokenized_route_matches(
            parsed.path,
            route_name=name,
            expected_token=self.state.token,
        ):
            if parsed.path.startswith(f"/{name}/"):
                self._reject(403, "FORBIDDEN")
            else:
                self._reject(404, "NOT_FOUND")
            return None
        return parsed, parsed.query

    def _authorized(self, *, require_origin: bool) -> bool:
        if not loopback_request_is_authorized(
            self.headers,
            expected_host=self.state.expected_host,
            expected_origin=self.state.origin,
            require_origin=require_origin,
        ):
            self._reject(403, "FORBIDDEN")
            return False
        return True

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if tokenized_route_matches(
            parsed.path,
            route_name="annotation",
            expected_token=self.state.token,
        ) and not parsed.query:
            if not self._authorized(require_origin=False):
                return
            self._send_bytes(200, self.state.html_bytes, "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/annotation/"):
            self._matches_route("")
            return
        if tokenized_route_matches(
            parsed.path,
            route_name="calibration",
            expected_token=self.state.token,
        ):
            if not self._authorized(require_origin=False):
                return
            try:
                query = _query(self.path, {"candidate_id", "confirmation_id"})
            except ValueError:
                self._reject(400, "INVALID_QUERY")
                return
            candidate_id = query.get("candidate_id")
            confirmation_id = query.get("confirmation_id")
            reviewer: str | None = None
            if (
                confirmation_id is not None
                and confirmation_id not in self.state.confirmation_records
            ):
                self._reject(404, "NOT_FOUND")
                return
            confirmed_at = datetime.now(UTC).isoformat(timespec="seconds")
            if confirmation_id is not None:
                confirmation = self.state.confirmation_records[confirmation_id][0]
                confirmed_at = confirmation.confirmed_at
                reviewer = confirmation.reviewer
                if candidate_id is None:
                    candidate_id = confirmation.candidate_id
            self._send_bytes(
                200,
                _calibration_html(
                    page=self.state.page,
                    source_sha256=self.state.page.source_sha256,
                    candidate_id=candidate_id,
                    confirmation_id=confirmation_id,
                    reviewer=reviewer,
                    confirmed_at=confirmed_at,
                ).encode("utf-8"),
                "text/html; charset=utf-8",
            )
            return
        if tokenized_route_matches(
            parsed.path,
            route_name="review-packet",
            expected_token=self.state.token,
        ):
            if not self._authorized(require_origin=False):
                return
            try:
                query = _query(
                    self.path,
                    {"candidate_id", "confirmation_id", "calibration_id"},
                )
            except ValueError:
                self._reject(400, "INVALID_QUERY")
                return
            try:
                present = set(query)
                if present not in (
                    set(),
                    {"calibration_id"},
                    {"candidate_id", "confirmation_id", "calibration_id"},
                ):
                    raise ValueError("invalid packet query")
                calibration_item: tuple[CalibrationRecord, CaseManifestEntry] | None = None
                if "calibration_id" in query:
                    calibration_item = self.state.calibration_records.get(query["calibration_id"])
                    if calibration_item is None:
                        self._reject(404, "NOT_FOUND")
                        return
                elif self.state.calibration_records:
                    calibration_item = max(
                        self.state.calibration_records.values(),
                        key=lambda item: (
                            parse_confirmation_time(item[0].confirmed_at),
                            item[0].calibration_id,
                        ),
                    )
                if calibration_item is None:
                    self._send_bytes(
                        200,
                        b"<!doctype html><html><body><h1>Review Packet</h1>"
                        b"<p>Pending calibration.</p></body></html>",
                        "text/html; charset=utf-8",
                    )
                    return
                record, calibration_entry = calibration_item
                if "candidate_id" in query and (
                    query["candidate_id"] != record.candidate_id
                    or query["confirmation_id"] != record.confirmation_id
                ):
                    self._reject(409, "BINDING_MISMATCH")
                    return
                if record.candidate_id is None or record.confirmation_id is None:
                    self._reject(409, "BINDING_MISMATCH")
                    return
                candidate_entry = self.state.candidate_entries.get(record.candidate_id)
                confirmation_item = self.state.confirmation_records.get(record.confirmation_id)
                if candidate_entry is None or confirmation_item is None:
                    self._reject(404, "ARTIFACT_MISSING")
                    return
                _verified_bytes(self.state.case_dir, calibration_entry)
                _verified_bytes(self.state.case_dir, candidate_entry)
                confirmation, confirmation_entry, _ = confirmation_item
                _verified_bytes(self.state.case_dir, confirmation_entry)
                candidate = load_candidate(self.state.case_dir, record.candidate_id)
                if self.state.page_image is None:
                    raise ValueError("page image is unavailable")
                rule_hash = self.state.rule_manifest_sha256
                formula_hash = self.state.formula_manifest_sha256 or _calculation_manifest_hash()
                if rule_hash is None or formula_hash is None:
                    raise ValueError("authority hash is unavailable")
                reference = record.references[0]
                first, second = reference.pixel_points
                pixel_length = (
                    abs(Decimal(str(second[0])) - Decimal(str(first[0])))
                    if reference.axis == "x"
                    else abs(Decimal(str(second[1])) - Decimal(str(first[1])))
                )
                calculation = run_calculation(
                    DRAWING_SCALE_ID,
                    DRAWING_SCALE_VERSION,
                    {
                        "real_length": reference.real_length,
                        "pixel_length": format(pixel_length, "f"),
                    },
                    registry=DRAWING_REGISTRY,
                )
                confirmed_input = confirmed_input_document(
                    ConfirmedInput(
                        input_id=record.calibration_id,
                        field="DRAWING_REAL_LENGTH",
                        value=reference.real_length,
                        unit=reference.unit,
                        status="CONFIRMED",
                        candidate_status="ACCEPTED",
                        source_sha256=candidate.source_sha256,
                        page=candidate.page,
                        evidence_id=candidate.candidate_id,
                        geometry=candidate.geometry,
                        confirmation_record=confirmation_entry.relative_path,
                        confirmation_sha256=confirmation_entry.sha256,
                    )
                )
                packet = {
                    "format": "evidence-review/review-packet",
                    "version": 2,
                    "run_id": f"RUN-{self.state.token[:20]}",
                    "case_id": self.state.case_dir.name,
                    "question": "Review confirmed drawing calibration evidence.",
                    "finalizer_status": "READY_FOR_HUMAN_REVIEW",
                    "snapshot_sha256": self.state.page.source_sha256,
                    "rule_manifest_sha256": rule_hash,
                    "formula_manifest_sha256": formula_hash,
                    "claims": [],
                    "evidence": [],
                    "drawing_evidence": [drawing_candidate_document(candidate)],
                    "confirmed_inputs": [confirmed_input],
                    "calculations": [_calculation_document(calculation)],
                    "rule_evaluations": [],
                    "exceptions": [],
                    "conflicts": [],
                    "confidence": None,
                    "abstention_reasons": [],
                    "human_decision": None,
                    "compatibility_source_version": None,
                }
                html = render_drawing_evidence(
                    packet,
                    page_images={self.state.page.page: self.state.page_image},
                    page_dimensions={
                        self.state.page.page:
                        (self.state.page.width, self.state.page.height)
                    },
                    mime=self.state.mime,
                    display_metadata={
                        "source_document": {
                            "document_id": self.state.case_dir.name,
                            "revision_id": f"page-{self.state.page.page}",
                            "page": self.state.page.page,
                            "source_sha256": self.state.page.source_sha256,
                        },
                        "candidate_id": record.candidate_id,
                        "confirmation_id": record.confirmation_id,
                        "calibration_id": record.calibration_id,
                        "reviewer": record.reviewer,
                        "confirmed_at": record.confirmed_at,
                        "calibration": {
                            "axis": reference.axis,
                            "pixel_points": [list(point) for point in reference.pixel_points],
                            "real_length": reference.real_length,
                            "unit": reference.unit,
                            "scale_x": record.scale_x,
                            "scale_y": record.scale_y,
                            "formula_id": record.formula_id,
                            "formula_version": record.formula_version,
                            "calculation_result_hash": record.calculation_result_hash,
                        },
                        "artifact_paths": {
                            "candidate": candidate_entry.relative_path,
                            "confirmation": confirmation_entry.relative_path,
                            "calibration": calibration_entry.relative_path,
                        },
                    },
                )
            except ValueError as error:
                code = str(error)
                self._reject(
                    409 if code in {"ARTIFACT_HASH_MISMATCH", "BINDING_MISMATCH"} else 500,
                    code
                    if code in {"ARTIFACT_HASH_MISMATCH", "BINDING_MISMATCH"}
                    else "RENDER_FAILED",
                )
                return
            except (FileNotFoundError, OSError):
                self._reject(404, "ARTIFACT_MISSING")
                return
            self._send_bytes(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/calibration/") or parsed.path.startswith("/review-packet/"):
            self._reject(403, "FORBIDDEN")
            return
        self._reject(404, "NOT_FOUND")

    def _content_length(self) -> int | None:
        try:
            return validate_content_length(self.headers, self.state.max_body_bytes)
        except ContentLengthError as error:
            if error.length is not None:
                self._reject_oversized_body(error.length)
                return None
            self._reject(411 if error.code == "CONTENT_LENGTH_REQUIRED" else 400, error.code)
            return None

    def _calibration_content_length(self) -> int | None:
        try:
            return validate_content_length(
                self.headers,
                self.state.max_body_bytes,
                reject_transfer_encoding=True,
            )
        except ContentLengthError as error:
            if error.length is not None:
                self._reject_oversized_body(error.length)
                return None
            if error.code == "CONTENT_LENGTH_REQUIRED":
                self._reject(411, error.code, drain_body=False)
            else:
                self._reject(400, "INVALID_CALIBRATION", drain_body=False)
            return None

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if tokenized_route_matches(
            parsed.path,
            route_name="calibration",
            expected_token=self.state.token,
        ):
            self._post_calibration()
            return
        if not self._matches_route("/actions"):
            return
        if not self._authorized(require_origin=True):
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if content_type != "application/json":
            self._reject(415, "UNSUPPORTED_MEDIA_TYPE")
            return
        length = self._content_length()
        if length is None:
            return
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
            action = decode_annotation_action(payload)
            with self.state.action_lock:
                result = record_annotation_action(
                    self.state.case_dir,
                    self.state.page,
                    self.state.candidate_entries,
                    action,
                )
                if result.candidate_entry is not None:
                    self.state.candidate_entries[
                        result.candidate_entry.artifact_id
                    ] = result.candidate_entry
                confirmation = load_and_verify_confirmation(
                    self.state.case_dir,
                    result.confirmation_entry,
                )
                candidate_entry = self.state.candidate_entries.get(confirmation.candidate_id)
                if candidate_entry is None:
                    raise FileNotFoundError("candidate is not indexed")
                self.state.confirmation_records[confirmation.confirmation_id] = (
                    confirmation,
                    result.confirmation_entry,
                    confirmation.candidate_id,
                )
                self.state.results.append(result)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            self._reject(400, "INVALID_ACTION", drain_body=False)
            return
        except FileNotFoundError:
            self._reject(404, "NOT_FOUND", drain_body=False)
            return
        except FileExistsError:
            self._reject(409, "ALREADY_EXISTS", drain_body=False)
            return
        except OSError:
            self._reject(500, "INTERNAL_ERROR", drain_body=False)
            return
        self._send_json(201, _result_document(result))

    def _post_calibration(self) -> None:
        if not self._authorized(require_origin=True):
            return
        if self.headers.get("Content-Type", "") != "application/json":
            self._reject(415, "UNSUPPORTED_MEDIA_TYPE")
            return
        length = self._calibration_content_length()
        if length is None:
            return
        try:
            payload = _json_body(self.rfile.read(length))
            if not isinstance(payload, Mapping):
                raise ValueError("INVALID_CALIBRATION")
            required = {
                "candidate_id", "confirmation_id", "reviewer", "confirmed_at",
                "axis", "pixel_points", "real_length", "unit",
            }
            if set(payload) != required:
                raise ValueError("INVALID_CALIBRATION")
            candidate_id = _identifier(payload["candidate_id"], "candidate_id")
            confirmation_id = _identifier(payload["confirmation_id"], "confirmation_id")
            reviewer = payload["reviewer"]
            confirmed_at = payload["confirmed_at"]
            if not isinstance(reviewer, str) or not reviewer or not isinstance(confirmed_at, str):
                raise ValueError("INVALID_CALIBRATION")
            parse_confirmation_time(confirmed_at)
            reference = _calibration_reference(payload)
            confirmation_item = self.state.confirmation_records.get(confirmation_id)
            if confirmation_item is None:
                raise FileNotFoundError("confirmation is not indexed")
            confirmation, confirmation_entry, indexed_candidate_id = confirmation_item
            if indexed_candidate_id != candidate_id or confirmation.reviewer != reviewer:
                raise ValueError("BINDING_MISMATCH")
            _verified_bytes(self.state.case_dir, confirmation_entry)
            candidate_entry = self.state.candidate_entries.get(candidate_id)
            if candidate_entry is None:
                raise FileNotFoundError("candidate is not indexed")
            candidate_path = verified_regular_file_below(
                self.state.case_dir,
                tuple(candidate_entry.relative_path.split("/")),
                field="case candidate artifact",
            )
            candidate_bytes = candidate_path.read_bytes()
            if hashlib.sha256(candidate_bytes).hexdigest() != candidate_entry.sha256:
                raise ValueError("ARTIFACT_HASH_MISMATCH")
            candidate = load_candidate(self.state.case_dir, candidate_id)
            if (
                candidate.source_sha256 != self.state.page.source_sha256
                or candidate.page != self.state.page.page
            ):
                raise ValueError("BINDING_MISMATCH")
            validate_confirmation_for_candidate(candidate, confirmation)
            if parse_confirmation_time(confirmed_at) < parse_confirmation_time(
                confirmation.confirmed_at
            ):
                raise ValueError("INVALID_CALIBRATION")
            record = build_calibration(
                source_sha256=self.state.page.source_sha256,
                page=self.state.page.page,
                references=(reference,),
                reviewer=reviewer,
                confirmed_at=confirmed_at,
                candidate_id=candidate_id,
                confirmation_id=confirmation_id,
            )
            entry = persist_calibration(self.state.case_dir, record)
            self.state.calibration_records[record.calibration_id] = (record, entry)
        except FileExistsError:
            self._reject(409, "ALREADY_EXISTS", drain_body=False)
            return
        except FileNotFoundError:
            self._reject(404, "NOT_FOUND", drain_body=False)
            return
        except ValueError as error:
            code = str(error)
            self._reject(
                409 if code in {"BINDING_MISMATCH", "ARTIFACT_HASH_MISMATCH"} else 400,
                code
                if code in {"BINDING_MISMATCH", "ARTIFACT_HASH_MISMATCH"}
                else "INVALID_CALIBRATION",
                drain_body=False,
            )
            return
        packet_url = f"{self.state.origin}/review-packet/{self.state.token}?" + urlencode(
            {
                "candidate_id": record.candidate_id,
                "confirmation_id": record.confirmation_id,
                "calibration_id": record.calibration_id,
            }
        )
        self._send_json(
            201,
            {
                "calibration": _entry_document(entry),
                "packet_url": packet_url,
            },
        )

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def do_OPTIONS(self) -> None:
        self._method_not_allowed()

    def do_HEAD(self) -> None:
        self._method_not_allowed()


@dataclass(slots=True)
class AnnotationServer:
    """Running annotation server with deterministic shutdown semantics."""

    _server: _AnnotationHTTPServer
    _thread: Thread

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def port(self) -> int:
        return cast(tuple[str, int], self._server.server_address)[1]

    @property
    def origin(self) -> str:
        return self._server.origin

    @property
    def url(self) -> str:
        return f"{self.origin}/annotation/{self._server.token}"

    @property
    def calibration_url(self) -> str:
        return f"{self.origin}/calibration/{self._server.token}"

    @property
    def review_packet_url(self) -> str:
        return f"{self.origin}/review-packet/{self._server.token}"

    @property
    def results(self) -> tuple[AnnotationActionResult, ...]:
        with self._server.action_lock:
            return tuple(self._server.results)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> AnnotationServer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self.close()


def serve_annotation_workspace(
    *,
    html: str,
    case_dir: Path,
    page: DrawingPage,
    candidate_entries: Mapping[str, CaseManifestEntry],
    token: str | None = None,
    port: int = 0,
    max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
    page_image: bytes | None = None,
    mime: str = "image/png",
    rule_manifest_sha256: str | None = None,
    formula_manifest_sha256: str | None = None,
) -> AnnotationServer:
    """Start one loopback-only annotation workspace server."""
    if not isinstance(html, str) or not html:
        raise ValueError("html must be a non-empty string")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    if (
        isinstance(max_body_bytes, bool)
        or not isinstance(max_body_bytes, int)
        or max_body_bytes < 1
    ):
        raise ValueError("max_body_bytes must be positive")
    server = _AnnotationHTTPServer(
        html=html,
        case_dir=_validate_case_dir(case_dir),
        page=page,
        candidate_entries=candidate_entries,
        token=_validated_token(token),
        port=port,
        max_body_bytes=max_body_bytes,
        page_image=page_image,
        mime=mime,
        rule_manifest_sha256=rule_manifest_sha256,
        formula_manifest_sha256=formula_manifest_sha256,
    )
    thread = Thread(
        target=server.serve_forever,
        name="drawing-annotation-server",
        daemon=True,
    )
    thread.start()
    return AnnotationServer(server, thread)
