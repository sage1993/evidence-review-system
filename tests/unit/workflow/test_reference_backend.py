from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from ansim_review.contracts.attachments import ImmutableAttachment
from ansim_review.contracts.source_batch import SourceBatch, SourceItem
from ansim_review.workflow.reference_ingestion import SourceBatchReferenceBackend
from ansim_review.workflow.request import decode_review_request


def test_source_batch_backend_delegates_to_existing_importer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_payload = b"reference"
    source_sha256 = hashlib.sha256(source_payload).hexdigest()
    source_path = tmp_path / "inputs" / "original" / "reference.pdf"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source_payload)
    batch = SourceBatch(
        format="evidence-review/source-batch",
        version=2,
        batch_id="BATCH-001",
        sources=(
            SourceItem(
                source_path="inputs/original/reference.pdf",
                role="REFERENCE_DOCUMENT",
                parser=None,
                document_id=None,
            ),
        ),
    )
    request = decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "질문",
            "attachments": [
                {
                    "attachment_id": "ATT-REF-001",
                    "original_name": "reference.pdf",
                    "stored_path": "inputs/original/reference.pdf",
                    "sha256": source_sha256,
                    "byte_size": len(source_payload),
                    "mime": "application/pdf",
                    "role": "REFERENCE_DOCUMENT",
                    "role_confirmation": "USER_CONFIRMED",
                    "proposed_role": None,
                }
            ],
        }
    )
    attachment = ImmutableAttachment(
        attachment_id="ATT-REF-001",
        original_name="reference.pdf",
        stored_path="inputs/original/reference.pdf",
        sha256=source_sha256,
        byte_size=len(source_payload),
        mime="application/pdf",
        role="REFERENCE_DOCUMENT",
    )

    def fake_import(root, supplied_batch, output, registry):
        assert root == tmp_path
        assert supplied_batch == batch
        assert registry is None
        assert output.parent.is_dir()
        output.write_bytes(b"sqlite-bytes")
        return SimpleNamespace(
            snapshot_hash="b" * 64,
            sources=(
                SimpleNamespace(
                    role="REFERENCE_DOCUMENT",
                    source_sha256=source_sha256,
                    document_id="DOC-001",
                    revision_id="REV-001",
                ),
            ),
        )

    monkeypatch.setattr(
        "ansim_review.workflow.reference_ingestion.import_source_batch",
        fake_import,
    )
    result = SourceBatchReferenceBackend(batch).ingest(
        request=request,
        attachments=(attachment,),
        run_dir=tmp_path,
    )

    assert result.snapshot_sha256 == "b" * 64
    assert result.output_db_byte_size == len(b"sqlite-bytes")
    assert result.output_db_sha256 == hashlib.sha256(b"sqlite-bytes").hexdigest()
    assert result.sources[0].document_id == "DOC-001"
    assert result.sources[0].revision_id == "REV-001"
