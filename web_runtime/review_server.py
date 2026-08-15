"""Compatibility import for the packaged protected review server."""

from evidence_review.review_packet.local_server import create_review_server

__all__ = ["create_review_server"]
