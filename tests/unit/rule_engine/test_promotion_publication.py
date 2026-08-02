from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ansim_review.rule_engine.promotion import approve_candidate


def _candidate(tmp_path: Path) -> Path:
    path = tmp_path / "rules" / "candidates" / "candidate.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "rule_id": "PROMOTION-RACE",
                "version": "1.0.0",
                "title": "promotion race",
                "input_schema": {"value": {"type": "integer", "required": True}},
                "source_citations": [
                    {
                        "citation_id": "C-PROMOTION-RACE",
                        "document_id": "DOC-PROMOTION-RACE",
                        "revision_id": "REV-PROMOTION-RACE",
                        "page_number": 1,
                        "evidence_id": "EVID-PROMOTION-RACE",
                        "bbox": [0, 0, 1, 1],
                        "source_hash": "a" * 64,
                    }
                ],
                "human_decision_required": True,
                "expression": {
                    "compare": {
                        "operator": "gte",
                        "left": {"input": "value"},
                        "right": {"literal": 1},
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_write_failure_does_not_delete_concurrent_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate(tmp_path)
    approved_dir = tmp_path / "rules" / "approved"
    approved_path = approved_dir / "PROMOTION-RACE@1.0.0.json"
    original_fsync = os.fsync
    intercepted = False

    def concurrent_fsync(descriptor: int) -> None:
        nonlocal intercepted
        if not intercepted:
            intercepted = True
            approved_path.unlink()
            approved_path.write_bytes(b"competing approved copy")
            raise OSError("simulated write failure")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", concurrent_fsync)

    with pytest.raises(OSError, match="simulated write failure"):
        approve_candidate(
            candidate,
            approved_dir,
            reviewer_id="reviewer",
            review_date="2026-08-02",
        )

    assert approved_path.read_bytes() == b"competing approved copy"
