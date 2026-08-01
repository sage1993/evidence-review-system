"""Immutable retrieval records and channel scores."""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from ansim_review.contracts.common import BBox, Citation


@dataclass(frozen=True, slots=True)
class ChannelScore:
    channel: str
    score: Decimal
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    evidence_id: str
    evidence_type: str
    document_id: str
    revision_id: str
    page_number: int
    bbox: BBox
    source_hash: str
    title: str
    text: str
    channel_scores: tuple[ChannelScore, ...] = ()
    final_score: Decimal = Decimal("0")

    def with_channel(self, channel: ChannelScore) -> RetrievalHit:
        scores = {item.channel: item for item in self.channel_scores}
        existing = scores.get(channel.channel)
        if existing is None or channel.score > existing.score:
            scores[channel.channel] = channel
        return replace(
            self,
            channel_scores=tuple(scores[name] for name in sorted(scores)),
        )

    def with_final_score(self, score: Decimal) -> RetrievalHit:
        return replace(self, final_score=score)

    def citation(self) -> Citation:
        return Citation(
            citation_id=f"CIT-{self.evidence_id}",
            document_id=self.document_id,
            revision_id=self.revision_id,
            page_number=self.page_number,
            evidence_id=self.evidence_id,
            bbox=self.bbox,
            source_hash=self.source_hash,
        )
