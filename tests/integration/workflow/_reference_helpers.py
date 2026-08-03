from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from ansim_review.workflow.reference_ingestion import (
    ReferenceIngestionBatchResult,
    ReferenceSourceResult,
)


@dataclass
class FakeReferenceBackend:
    calls: list[tuple[str, ...]] = field(default_factory=list)
    snapshot_sha256: str = "b" * 64

    def ingest(self, *, request, attachments, run_dir: Path):
        del request
        self.calls.append(tuple(item.attachment_id for item in attachments))
        output = run_dir / "machine" / "evidence.sqlite"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake-evidence-db")
        sources = tuple(
            ReferenceSourceResult(
                attachment_ids=(attachment.attachment_id,),
                original_names=(attachment.original_name,),
                source_sha256=attachment.sha256,
                document_id=f"DOC-{attachment.sha256[:20].upper()}",
                revision_id=(
                    f"DOC-{attachment.sha256[:20].upper()}-"
                    f"{attachment.sha256[:12]}"
                ),
            )
            for attachment in attachments
        )
        return ReferenceIngestionBatchResult(
            snapshot_sha256=self.snapshot_sha256,
            output_db_relative_path="machine/evidence.sqlite",
            sources=sources,
        )


def write_source(path: Path, content: bytes) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest(), len(content)
