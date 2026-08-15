"""Immutable retrieval records and channel scores."""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

from evidence_review.contracts.common import BBox, Citation


class CitationQuality(StrEnum):
    """Location precision available for a retrieval hit."""

    EXACT_BBOX = "EXACT_BBOX"
    PAGE_ONLY = "PAGE_ONLY"


class CitationUnavailableError(RuntimeError):
    """Raised when a retrieval hit cannot produce an exact citation."""

    def __init__(self, reason_code: str, evidence_id: str) -> None:
        self.reason_code = reason_code
        self.evidence_id = evidence_id
        super().__init__(
            f"{reason_code}: exact citation unavailable for {evidence_id}"
        )


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
    bbox: BBox | None
    source_hash: str
    title: str
    text: str
    channel_scores: tuple[ChannelScore, ...] = ()
    final_score: Decimal = Decimal("0")

    @property
    def citation_quality(self) -> CitationQuality:
        """Return whether this hit supports an exact bbox citation."""
        if self.bbox is None:
            return CitationQuality.PAGE_ONLY
        return CitationQuality.EXACT_BBOX

    def with_channel(self, channel: ChannelScore) -> RetrievalHit:
        scores = {item.channel: item for item in self.channel_scores}
        existing = scores.get(channel.channel)
        if existing is None:
            scores[channel.channel] = channel
        else:
            details = tuple(
                sorted(
                    {
                        detail
                        for detail in (existing.detail, channel.detail)
                        if detail
                    }
                )
            )
            scores[channel.channel] = ChannelScore(
                channel=channel.channel,
                score=max(existing.score, channel.score),
                detail=" | ".join(details),
            )
        return replace(
            self,
            channel_scores=tuple(scores[name] for name in sorted(scores)),
        )

    def with_final_score(self, score: Decimal) -> RetrievalHit:
        return replace(self, final_score=score)

    def citation(self) -> Citation:
        """Return an exact citation or fail closed when bbox is unavailable."""
        if self.bbox is None:
            raise CitationUnavailableError("BBOX_UNAVAILABLE", self.evidence_id)
        return Citation(
            citation_id=f"CIT-{self.evidence_id}",
            document_id=self.document_id,
            revision_id=self.revision_id,
            page_number=self.page_number,
            evidence_id=self.evidence_id,
            bbox=self.bbox,
            source_hash=self.source_hash,
        )
