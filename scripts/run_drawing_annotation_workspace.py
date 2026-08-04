"""Run the local browser workspace used for manual drawing QA."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import Event
from typing import cast

from ansim_review.contracts.drawing import (
    CoordinateSystem,
    DrawingCandidate,
    decode_drawing_candidate,
)
from ansim_review.contracts.validation import (
    expect_sha256,
    expect_string,
    reject_unknown,
    require_fields,
)
from ansim_review.drawing_review.html_renderer import render_annotation_html
from ansim_review.drawing_review.local_server import serve_annotation_workspace
from ansim_review.drawing_review.view_model import (
    DrawingPage,
    build_drawing_review_view_model,
)
from ansim_review.parsing.drawing_candidates import load_candidate, persist_candidate
from ansim_review.parsing.drawing_case import (
    CaseManifestEntry,
    case_artifact_path,
    decode_case_manifest,
    validate_artifact_id,
)
from ansim_review.parsing.drawing_source import sniff_drawing_mime, validate_source_path

_REPARSE_POINT_ATTRIBUTE = 0x400
_COORDINATE_SYSTEMS: tuple[CoordinateSystem, ...] = (
    "PDF_BOTTOM_LEFT_POINTS",
    "IMAGE_TOP_LEFT_PIXELS",
)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _read_json(path: Path) -> object:
    return cast(object, json.loads(path.read_text(encoding="utf-8")))


def _validate_case_dir(case_dir: Path) -> Path:
    try:
        status = case_dir.lstat()
    except FileNotFoundError:
        raise ValueError("case_dir must be an existing directory") from None
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise ValueError("case_dir must be a regular non-link directory")
    if getattr(status, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE:
        raise ValueError("case_dir cannot be a Windows reparse point")
    return case_dir.resolve()


def _entry(value: object, field: str) -> CaseManifestEntry:
    mapping = _mapping(value, field)
    required = {"artifact_id", "relative_path", "sha256"}
    require_fields(mapping, required, field)
    reject_unknown(mapping, required, field)
    artifact_id = validate_artifact_id(
        expect_string(mapping.get("artifact_id"), f"{field}.artifact_id"),
        f"{field}.artifact_id",
    )
    relative_path = expect_string(mapping.get("relative_path"), f"{field}.relative_path")
    sha256 = expect_sha256(mapping.get("sha256"), f"{field}.sha256")
    return CaseManifestEntry(artifact_id, relative_path, sha256)


def _manifest_entries(path: Path) -> tuple[CaseManifestEntry, ...]:
    payload = _read_json(path)
    if isinstance(payload, Mapping) and "format" in payload:
        return decode_case_manifest(payload).candidates
    if isinstance(payload, Mapping):
        payload = payload.get("candidates")
    return tuple(
        _entry(item, f"candidates[{index}]")
        for index, item in enumerate(_sequence(payload, "candidates"))
    )


def _verified_candidate(case_dir: Path, entry: CaseManifestEntry) -> DrawingCandidate:
    expected_path = f"candidates/{entry.artifact_id}.json"
    if entry.relative_path != expected_path:
        raise ValueError("candidate manifest path mismatch")
    path = case_artifact_path(case_dir, entry.relative_path)
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != entry.sha256:
        raise ValueError("candidate manifest hash mismatch")
    return load_candidate(case_dir, entry.artifact_id)


def _fixture_candidates(
    case_dir: Path,
    path: Path,
    source_sha256: str,
) -> tuple[DrawingCandidate, ...]:
    candidates = tuple(
        decode_drawing_candidate(item)
        for index, item in enumerate(_sequence(_read_json(path), "candidate_fixture"))
    )
    for candidate in candidates:
        if candidate.source_sha256 != source_sha256:
            raise ValueError("candidate fixture source_sha256 does not match source")
    for candidate in candidates:
        persist_candidate(case_dir, candidate)
    return candidates


def prepare_workspace(
    *,
    case_dir: Path,
    source: Path,
    width: float,
    height: float,
    coordinate_system: CoordinateSystem,
    page: int = 1,
    candidate_manifest: Path | None = None,
    candidate_fixture: Path | None = None,
) -> tuple[str, dict[str, CaseManifestEntry]]:
    """Build the self-contained page and verified candidate index for browser QA."""
    if candidate_manifest is not None and candidate_fixture is not None:
        raise ValueError("use one of candidate_manifest or candidate_fixture")
    if coordinate_system not in _COORDINATE_SYSTEMS:
        raise ValueError("coordinate_system is invalid")
    resolved_case_dir = _validate_case_dir(case_dir)
    validate_source_path(source)
    source_bytes = source.read_bytes()
    mime, _ = sniff_drawing_mime(source_bytes[:16])
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    page_metadata = DrawingPage(
        source_sha256=source_sha256,
        page=page,
        coordinate_system=coordinate_system,
        width=width,
        height=height,
    )

    if candidate_fixture is not None:
        candidates = _fixture_candidates(resolved_case_dir, candidate_fixture, source_sha256)
        entries = {
            candidate.candidate_id: CaseManifestEntry(
                candidate.candidate_id,
                f"candidates/{candidate.candidate_id}.json",
                hashlib.sha256(
                    case_artifact_path(
                        resolved_case_dir,
                        f"candidates/{candidate.candidate_id}.json",
                    ).read_bytes()
                ).hexdigest(),
            )
            for candidate in candidates
        }
    elif candidate_manifest is not None:
        entries = {
            entry.artifact_id: entry for entry in _manifest_entries(candidate_manifest)
        }
        candidates = tuple(
            _verified_candidate(resolved_case_dir, entry) for entry in entries.values()
        )
    else:
        entries = {}
        candidates = ()

    view_model = build_drawing_review_view_model(page_metadata, candidates)
    return render_annotation_html(view_model, source_bytes, mime), entries


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--width", type=float, required=True)
    parser.add_argument("--height", type=float, required=True)
    parser.add_argument("--page", type=_positive_int, default=1)
    parser.add_argument("--coordinate-system", choices=_COORDINATE_SYSTEMS, required=True)
    parser.add_argument("--port", type=int, default=0)
    candidates = parser.add_mutually_exclusive_group()
    candidates.add_argument("--candidate-manifest", type=Path)
    candidates.add_argument("--candidate-fixture", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        html, entries = prepare_workspace(
            case_dir=args.case_dir,
            source=args.source,
            width=args.width,
            height=args.height,
            coordinate_system=args.coordinate_system,
            page=args.page,
            candidate_manifest=args.candidate_manifest,
            candidate_fixture=args.candidate_fixture,
        )
        server = serve_annotation_workspace(
            html=html,
            case_dir=args.case_dir,
            page=DrawingPage(
                source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
                page=args.page,
                coordinate_system=args.coordinate_system,
                width=args.width,
                height=args.height,
            ),
            candidate_entries=entries,
            port=args.port,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    stop = Event()
    try:
        print(f"Annotation workspace URL: {server.url}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)
        while not stop.wait(60):
            pass
    except KeyboardInterrupt:
        return 0
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
