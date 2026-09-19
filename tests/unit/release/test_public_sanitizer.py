from __future__ import annotations

import json

import pytest

from evidence_review.release.public_sanitizer import (
    PublicSanitizationError,
    sanitize_public_document,
    sanitize_public_json,
)


def test_public_sanitizer_redacts_paths_loopback_urls_and_secrets() -> None:
    source = {
        "packet_sha256": "a" * 64,
        "workspace": r"F:\2026-PJ\새 폴더\workspace",
        "local_url": "http://127.0.0.1:8765/review?token=abc123",
        "session": {"access_token": "do-not-publish", "reviewer_id": "reviewer-01"},
        "notes": "see /home/reviewer/private/report.json",
    }

    sanitized = sanitize_public_document(source)

    assert sanitized["workspace"] == "<redacted:local-path>"
    assert sanitized["local_url"] == "<redacted:loopback-url>"
    assert sanitized["session"] == "<redacted:secret>"
    assert sanitized["notes"] == "see <redacted:local-path>"
    encoded = sanitize_public_json(source).decode("utf-8")
    assert json.loads(encoded) == sanitized
    assert "do-not-publish" not in encoded
    assert "127.0.0.1" not in encoded


def test_public_sanitizer_rejects_non_json_values() -> None:
    with pytest.raises(PublicSanitizationError, match="unsupported"):
        sanitize_public_document({"value": object()})


def test_public_sanitizer_redacts_inline_secret_assignments() -> None:
    sanitized = sanitize_public_document(
        {"text": "Authorization=Bearer-secret session_token=xyz"}
    )
    assert sanitized == {
        "text": "Authorization=<redacted:secret> session_token=<redacted:secret>"
    }


def test_public_sanitizer_redacts_sensitive_drawing_and_workspace_fields() -> None:
    sanitized = sanitize_public_document(
        {
            "drawing": {"raw_image": "data:image/png;base64,secret"},
            "subject_assets": ["private-page.png"],
            "workspace_id": "ansim-housing-private",
            "public_status": "ABSTAIN",
        }
    )

    assert sanitized == {
        "drawing": "<redacted:sensitive-artifact>",
        "subject_assets": "<redacted:sensitive-artifact>",
        "workspace_id": "<redacted:sensitive-artifact>",
        "public_status": "ABSTAIN",
    }
