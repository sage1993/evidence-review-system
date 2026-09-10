"""Fail-closed local selector for one canonical run-local Formal Review packet."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.review import ReviewPacket
from evidence_review.contracts.validation import expect_sha256
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.review_matter.formal_run_binding import verify_formal_run_authority

CURRENT_REVIEW_BINDING_FORMAT = "evidence-review/current-review-binding"
CURRENT_REVIEW_BINDING_VERSION = 1
_CURRENT_REVIEW_RELATIVE_PATH = (".ers", "current-review.json")
_RUN_ID = re.compile(r"^RUN-[0-9A-F]{20}$")


@dataclass(frozen=True, slots=True)
class CurrentReviewBinding:
    """Canonical control-state selector; it is not packet authority."""

    run_id: str
    packet_sha256: str

    def to_document(self) -> dict[str, object]:
        return {
            "format": CURRENT_REVIEW_BINDING_FORMAT,
            "version": CURRENT_REVIEW_BINDING_VERSION,
            "run_id": self.run_id,
            "packet_sha256": self.packet_sha256,
        }


@dataclass(frozen=True, slots=True)
class ResolvedCurrentReview:
    """A selector resolved only after revalidating its run-local packet authority."""

    run_id: str
    packet_sha256: str
    run_directory: Path
    packet_path: Path
    packet: ReviewPacket


def _run_id(value: object) -> str:
    run_id = validate_identifier(value, "run_id")
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be a Formal Run identifier")
    return run_id


def _binding(value: object) -> CurrentReviewBinding:
    if not isinstance(value, dict):
        raise ValueError("current review binding must be a JSON object")
    required = {"format", "version", "run_id", "packet_sha256"}
    if set(value) != required:
        raise ValueError("current review binding fields are invalid")
    if value["format"] != CURRENT_REVIEW_BINDING_FORMAT:
        raise ValueError("current review binding format is invalid")
    if value["version"] != CURRENT_REVIEW_BINDING_VERSION:
        raise ValueError("current review binding version is invalid")
    return CurrentReviewBinding(
        run_id=_run_id(value["run_id"]),
        packet_sha256=expect_sha256(value["packet_sha256"], "packet_sha256"),
    )


def _state_directory(repository_root: Path) -> tuple[Path, Path]:
    root = verified_regular_directory(repository_root, field="repository root")
    state = root / ".ers"
    state.mkdir(parents=True, exist_ok=True)
    return root, verified_regular_directory(state, field="current review state directory")


def _write_binding(path: Path, binding: CurrentReviewBinding) -> None:
    try:
        verified_regular_file_below(
            path.parent.parent,
            _CURRENT_REVIEW_RELATIVE_PATH,
            field="current review binding",
        )
    except FileNotFoundError:
        pass
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".current-review-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            stream.write(dump_bytes(binding.to_document()))
            stream.flush()
            os.fsync(stream.fileno())
            temporary_path = Path(stream.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def bind_current_review(
    repository_root: Path,
    run_id: str,
    packet_sha256: str,
    *,
    workspace_root: Path,
) -> CurrentReviewBinding:
    """Atomically replace only the local current-review selector."""
    root, _state = _state_directory(repository_root)
    binding = CurrentReviewBinding(
        run_id=_run_id(run_id),
        packet_sha256=expect_sha256(packet_sha256, "packet_sha256"),
    )
    _resolve_binding(workspace_root, binding)
    _write_binding(root / ".ers" / "current-review.json", binding)
    return binding


def _resolve_binding(
    workspace_root: Path, binding: CurrentReviewBinding
) -> ResolvedCurrentReview:
    """Verify one selected run-local packet without accepting a pointer file."""
    try:
        workspace = verified_regular_directory(
            workspace_root,
            field="current review workspace",
        )
        runs = verified_regular_directory(workspace / "runs", field="current review runs")
        run_directory = verified_regular_directory(
            runs / binding.run_id,
            field="current review run directory",
        )
        packet_path = verified_regular_file_below(
            run_directory,
            ("final-review-packet.json",),
            field="current review packet",
        )
        before = packet_path.read_bytes()
        _verified_run_directory, packet, _normalized_request = verify_formal_run_authority(
            workspace_root,
            run_id=binding.run_id,
            packet_sha256=binding.packet_sha256,
            require_persisted_binding=True,
        )
        after = packet_path.read_bytes()
        if before != after or packet.run_id != binding.run_id:
            raise ValueError("current review packet identity changed")
    except (FileNotFoundError, OSError, ValueError) as error:
        raise ValueError("CURRENT_REVIEW_STALE") from error
    return ResolvedCurrentReview(
        run_id=binding.run_id,
        packet_sha256=binding.packet_sha256,
        run_directory=run_directory,
        packet_path=packet_path,
        packet=packet,
    )


def resolve_current_review(
    repository_root: Path,
    *,
    workspace_root: Path,
) -> ResolvedCurrentReview:
    """Resolve a canonical pointer only when its local final packet still verifies."""
    root = verified_regular_directory(repository_root, field="repository root")
    try:
        binding_path = verified_regular_file_below(
            root,
            _CURRENT_REVIEW_RELATIVE_PATH,
            field="current review binding",
        )
    except FileNotFoundError as error:
        raise FileNotFoundError("CURRENT_REVIEW_NOT_BOUND") from error
    except (OSError, ValueError) as error:
        raise ValueError("CURRENT_REVIEW_BINDING_INVALID") from error
    try:
        raw_binding = binding_path.read_bytes()
        binding = _binding(json.loads(raw_binding.decode("utf-8")))
        if raw_binding != dump_bytes(binding.to_document()):
            raise ValueError("current review binding is not canonical")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("CURRENT_REVIEW_BINDING_INVALID") from error
    return _resolve_binding(workspace_root, binding)


__all__ = [
    "CURRENT_REVIEW_BINDING_FORMAT",
    "CURRENT_REVIEW_BINDING_VERSION",
    "CurrentReviewBinding",
    "ResolvedCurrentReview",
    "bind_current_review",
    "resolve_current_review",
]
