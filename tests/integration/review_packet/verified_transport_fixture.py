"""Finalized authority for protected transport fixtures (never archive authority)."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.drawing_review.visual_pages import VisualPageAsset, ensure_visual_page_tiles
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from tests.integration.review_packet.test_local_server import RUN_ID, _artifacts


def _replace_run_id(value: object, run_id: str) -> object:
    if isinstance(value, dict):
        return {
            key: run_id if key == "run_id" else _replace_run_id(item, run_id)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_run_id(item, run_id) for item in value]
    return value


def install_visual_authority(
    root: Path, model: dict, *, run_id: str = RUN_ID
) -> None:
    """Bind synthetic visual inputs before finalization, preserving the archive under test."""
    attachments = {}
    pages = []
    for page in model["case_visual_review"]["pages"]:
        attachment_id = page["attachment_id"]
        source_hash = page.get("source_sha256", "a" * 64)
        case_id = page.get("case_id")
        attachment = {
            "attachment_id": attachment_id,
            "original_name": page["document_name"],
            "stored_path": (
                f"cases/{case_id}/sources/drawings/{attachment_id}.pdf"
                if case_id
                else f"inputs/original/{attachment_id}.pdf"
            ),
            "sha256": source_hash, "byte_size": 1,
            "mime": "application/pdf", "role": "CASE_DRAWING",
        }
        if case_id:
            attachment["case_id"] = case_id
        attachments[attachment_id] = attachment
        identity = f"{case_id}--{attachment_id}--{source_hash}" if case_id else attachment_id
        page_path = root / "case-page-images-hq-v1" / identity / f"page-{page['page']:04d}.png"
        legacy_path = root / "case-page-images-hq-v1" / attachment_id / page_path.name
        if not page_path.exists() and legacy_path.exists():
            page_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(legacy_path, page_path)
        width, height = page["width"], page["height"]
        if page.get("tiles"):
            asset = VisualPageAsset(
                case_id=case_id, attachment_id=attachment_id, source_sha256=source_hash,
                page=page["page"], width=width, height=height,
                coordinate_system="IMAGE_TOP_LEFT_PIXELS", image_path=page_path,
                image_sha256=page["image_sha256"],
            )
            ensure_visual_page_tiles(root, asset)
        pages.append({
            "attachment_id": attachment_id, "source_sha256": source_hash,
            "page": page["page"], "width": width, "height": height,
            "coordinate_system": "IMAGE_TOP_LEFT_PIXELS", "image_sha256": page["image_sha256"],
        })
    staging = root / f"fixture-authority-{run_id}"
    staging.mkdir()
    run, _ = _artifacts(staging, inputs={"case_visual_context": {
        "attachments": list(attachments.values()), "visual_pages": pages,
        "visual_status": "VISUAL_ANALYSIS_VALIDATED", "drawing_candidates": [],
        "candidate_lineage": [], "reason_codes": [],
    }})
    shutil.copytree(staging / "evidence", root / "evidence", dirs_exist_ok=True)
    shutil.copytree(staging / "page-images", root / "page-images", dirs_exist_ok=True)
    target = root / "runs" / run_id
    target.mkdir(parents=True, exist_ok=True)
    artifact_names = (
        "track-a-bundle.json",
        "track-a-output.json",
        "track-b-output.json",
        "confidence-input.json",
    )
    hashes: dict[str, str] = {}
    for name in artifact_names:
        document = _replace_run_id(json.loads((run / name).read_bytes()), run_id)
        data = dump_bytes(document)
        (target / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    (target / "run-manifest.json").write_bytes(
        dump_bytes({"run_id": run_id, "artifacts": hashes})
    )
    finalize_run(target)
    provenance = finalized_evidence_provenance(root / "evidence" / "evidence.sqlite")
    (target / "review-request.json").write_bytes(
        dump_bytes({"inputs": {
            "snapshot_hash": provenance["evidence_snapshot_hash"],
            "evidence_snapshot_provenance": provenance,
        }})
    )
    if not (target / "review.html").exists():
        shutil.copyfile(run / "review.html", target / "review.html")
