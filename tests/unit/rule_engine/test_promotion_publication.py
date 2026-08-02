from __future__ import annotations

import json
import os
from pathlib import Path
from typing import BinaryIO

import pytest

from ansim_review.rule_engine.promotion import approve_candidate


class _ReplaceOnExit:
    def __init__(self, stream: BinaryIO, destination: Path) -> None:
        self._stream = stream
        self._destination = destination

    def __enter__(self) -> _ReplaceOnExit:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self._stream.close()
        self._destination.unlink()
        self._destination.write_bytes(b"competing approved copy")

    def write(self, data: bytes) -> int:
        return self._stream.write(data)

    def flush(self) -> None:
        self._stream.flush()

    def fileno(self) -> int:
        return self._stream.fileno()


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
    original_fdopen = os.fdopen

    def replacement_fdopen(descriptor: int, mode: str) -> _ReplaceOnExit:
        stream = original_fdopen(descriptor, mode)
        return _ReplaceOnExit(stream, approved_path)

    def failing_fsync(descriptor: int) -> None:
        del descriptor
        raise OSError("simulated write failure")

    monkeypatch.setattr(os, "fdopen", replacement_fdopen)
    monkeypatch.setattr(os, "fsync", failing_fsync)

    with pytest.raises(OSError, match="simulated write failure"):
        approve_candidate(
            candidate,
            approved_dir,
            reviewer_id="reviewer",
            review_date="2026-08-02",
        )

    assert approved_path.read_bytes() == b"competing approved copy"
