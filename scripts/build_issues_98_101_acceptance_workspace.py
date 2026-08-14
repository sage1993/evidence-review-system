from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from ansim_review.canonical_json import dump_bytes
from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.store import EvidenceStore
from ansim_review.retrieval.index import build_fts_index

_PRIMARY_TEXT = (  # noqa: E501
    "\uccad\uc18c\ub144"
    "\ubb38\ud654\uc758\uc9d1"
    " \uc124\uce58\uae30\uc900\uc740"
    " \uc2dc\uc124\uc758 \ubaa9\uc801\uacfc"
    " \uc774\uc6a9\uc790 \uc548\uc804\uc744"
    " \ud568\uaed8 \uac80\ud1a0\ud55c\ub2e4."
)
_SECONDARY_TEXT = (
    "\uccad\uc18c\ub144\ubb38\ud654\uc758\uc9d1 \uc124\uce58\uae30\uc900\uc5d0\ub294"
    " \ub3c5\ub9bd\ub41c \ud65c\ub3d9\uacf5\uac04\uc758 \ud655\ubcf4\uac00"
    " \ud3ec\ud568\ub41c\ub2e4."
)
_TITLE = "\uccad\uc18c\ub144\uc218\ub828\uc2dc\uc124 \uae30\uc900"
_TRACK_A_EXPLANATION = "deterministic Track A fixture."

_ELEMENTS = (
    {
        "id": "E-CULTURE-PRIMARY",
        "revision_id": "REV-ACCEPT",
        "page_id": "REV-ACCEPT-P1",
        "page_number": 1,
        "element_type": "clause",
        "raw_json": {
            "text": _PRIMARY_TEXT
        },
        "raw_text": _PRIMARY_TEXT,
        "normalized_text": _PRIMARY_TEXT,
        "raw_payload_hash": "7" * 64,
        "bbox": [40.0, 80.0, 520.0, 140.0],
        "parser_order": 10,
    },
    {
        "id": "E-CULTURE-SECONDARY",
        "revision_id": "REV-ACCEPT",
        "page_id": "REV-ACCEPT-P2",
        "page_number": 2,
        "element_type": "clause",
        "raw_json": {
            "text": _SECONDARY_TEXT
        },
        "raw_text": _SECONDARY_TEXT,
        "normalized_text": _SECONDARY_TEXT,
        "raw_payload_hash": "8" * 64,
        "bbox": [50.0, 120.0, 530.0, 180.0],
        "parser_order": 20,
    },
)


def _workspace_path(value: str) -> Path:
    return Path(value).resolve()


def _seed(workspace: Path) -> None:
    database = workspace / "evidence" / "evidence.sqlite"
    image_directory = workspace / "page-images" / "REV-ACCEPT"
    if database.exists() or any(image_directory.glob("page-*.png")):
        raise FileExistsError("acceptance fixture refuses to overwrite existing assets")
    (workspace / "evidence").mkdir(parents=True, exist_ok=True)
    with EvidenceStore(database, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-ACCEPT", "title": _TITLE},),
                revisions=(
                    {
                        "id": "REV-ACCEPT",
                        "document_id": "DOC-ACCEPT",
                        "source_hash": "9" * 64,
                        "byte_size": 100,
                        "page_count": 2,
                    },
                ),
                pages=(
                    {
                        "id": "REV-ACCEPT-P1",
                        "revision_id": "REV-ACCEPT",
                        "page_number": 1,
                        "width": 595.0,
                        "height": 842.0,
                    },
                    {
                        "id": "REV-ACCEPT-P2",
                        "revision_id": "REV-ACCEPT",
                        "page_number": 2,
                        "width": 595.0,
                        "height": 842.0,
                    },
                ),
                elements=_ELEMENTS,
            ),
        )
        build_fts_index(store.require_connection())
    image_directory.mkdir(parents=True, exist_ok=True)
    for page_number in (1, 2):
        image_path = image_directory / f"page-{page_number:04d}.png"
        metadata_path = image_directory / f"page-{page_number:04d}.json"
        if image_path.exists() or metadata_path.exists():
            raise FileExistsError("acceptance fixture refuses to overwrite page assets")
        Image.new("RGB", (595, 842), "white").save(image_path, format="PNG")
        image_bytes = image_path.read_bytes()
        metadata = {
            "format": "ansim/page-image",
            "version": 1,
            "revision_id": "REV-ACCEPT",
            "page_number": page_number,
            "source_hash": "9" * 64,
            "pdf_width": 595.0,
            "pdf_height": 842.0,
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        }
        metadata_path.write_bytes(dump_bytes(metadata))


def _tracks(workspace: Path, run_id: str, write_track_b: bool) -> None:
    run_directory = workspace / "runs" / run_id
    bundle = json.loads(
        (run_directory / "track-a-bundle.json").read_text(encoding="utf-8")
    )
    evidence = bundle["evidence"]
    if len(evidence) < 2:
        raise ValueError("acceptance fixture requires at least two citations")
    if evidence[0]["citation"]["page_number"] == evidence[1]["citation"]["page_number"]:
        raise ValueError("acceptance fixture requires citations on distinct pages")
    first, second = evidence[0], evidence[1]
    first_id = first["citation"]["citation_id"]
    second_id = second["citation"]["citation_id"]
    if not write_track_b:
        track_a = {
            "run_id": run_id,
            "claims": [
                {
                    "claim_id": "CL-PRIMARY",
                    "text": first["text"],
                    "citation_ids": [first_id],
                    "numeric_tokens": [],
                    "calculation_result_ids": [],
                    "rule_references": [],
                },
                {
                    "claim_id": "CL-SECONDARY",
                    "text": second["text"],
                    "citation_ids": [second_id],
                    "numeric_tokens": [],
                    "calculation_result_ids": [],
                    "rule_references": [],
                },
                {
                    "claim_id": "CL-MULTI",
                    "text": "\ub450 \uadfc\uac70\ub97c \ud568\uaed8 \uac80\ud1a0\ud55c\ub2e4.",
                    "citation_ids": [first_id, second_id],
                    "numeric_tokens": [],
                    "calculation_result_ids": [],
                    "rule_references": [],
                },
            ],
            "citations": [first_id, second_id],
            "missing_inputs": [],
            "exceptions": [],
            "conflicts": [],
            "explanation": _TRACK_A_EXPLANATION,
        }
        output = run_directory / "acceptance-track-a.json"
        output.write_bytes(dump_bytes(track_a))
        print(json.dumps({"track_a": str(output)}, ensure_ascii=False))
        return
    if not (run_directory / "track-a-output.json").is_file():
        raise FileNotFoundError("canonical track-a-output.json is required before Track B")
    track_b = {
        "run_id": run_id,
        "claim_audits": [
            {
                "claim_id": claim_id,
                "disposition": "ACCEPT",
                "finding_codes": [],
                "notes": "",
            }
            for claim_id in ("CL-PRIMARY", "CL-SECONDARY", "CL-MULTI")
        ],
        "overall_disposition": "ACCEPT",
    }
    output = run_directory / "track-b-output.json"
    output.write_bytes(dump_bytes(track_b))
    print(json.dumps({"track_b": str(output)}))


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    seed_parser = subparsers.add_parser("seed")
    seed_parser.add_argument("--workspace", required=True)
    tracks_parser = subparsers.add_parser("tracks")
    tracks_parser.add_argument("--workspace", required=True)
    tracks_parser.add_argument("--run-id", required=True)
    tracks_parser.add_argument("--write-track-b", action="store_true")
    arguments = parser.parse_args()
    workspace = _workspace_path(arguments.workspace)
    if arguments.command == "seed":
        _seed(workspace)
    else:
        _tracks(workspace, arguments.run_id, arguments.write_track_b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
