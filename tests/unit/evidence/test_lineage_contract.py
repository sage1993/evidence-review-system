from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

import pytest

from evidence_review.evidence.lineage_contract import (
    decode_legacy_lineage_manifest,
    legacy_lineage_manifest_document,
)


def valid_payload() -> dict[str, object]:
    return {
        "format": "evidence-review/legacy-lineage-manifest",
        "version": 1,
        "source_database_sha256": "a" * 64,
        "reviewer_id": "ksh",
        "reviewed_at": "2026-08-02T16:49:00+09:00",
        "mappings": [
            {
                "legacy_document_id": "LAW3",
                "canonical_document_id": "DOC-ACFD68E34043268C",
                "source_sha256": "b" * 64,
                "reason": "same immutable PDF registered under a legacy alias",
                "revision_mappings": [
                    {
                        "legacy_revision_id": "REV-LAW3-001",
                        "canonical_revision_id": "REV-DOC-001",
                    }
                ],
            }
        ],
    }


def _mapping(payload: dict[str, object], index: int = 0) -> dict[str, object]:
    mappings = payload["mappings"]
    assert isinstance(mappings, list)
    mapping = mappings[index]
    assert isinstance(mapping, dict)
    return mapping


def _revision(mapping: dict[str, object], index: int = 0) -> dict[str, object]:
    revisions = mapping["revision_mappings"]
    assert isinstance(revisions, list)
    revision = revisions[index]
    assert isinstance(revision, dict)
    return revision


def test_manifest_round_trips_to_canonical_document() -> None:
    payload = valid_payload()
    decoded = decode_legacy_lineage_manifest(payload)
    assert legacy_lineage_manifest_document(decoded) == payload


def test_mappings_and_revisions_are_sorted_deterministically() -> None:
    payload = valid_payload()
    second = deepcopy(_mapping(payload))
    second["legacy_document_id"] = "LAW2"
    second["canonical_document_id"] = "DOC-SECOND"
    second_revision = _revision(second)
    second_revision["legacy_revision_id"] = "REV-LAW2-002"
    second_revision["canonical_revision_id"] = "REV-DOC-002"
    mappings = payload["mappings"]
    assert isinstance(mappings, list)
    mappings.insert(0, second)

    decoded = decode_legacy_lineage_manifest(payload)
    projected = legacy_lineage_manifest_document(decoded)
    projected_mappings = projected["mappings"]
    assert isinstance(projected_mappings, list)
    assert [item["legacy_document_id"] for item in projected_mappings] == [
        "LAW2",
        "LAW3",
    ]


def test_unknown_fields_are_rejected_at_every_level() -> None:
    top = valid_payload()
    top["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        decode_legacy_lineage_manifest(top)

    mapping_payload = valid_payload()
    _mapping(mapping_payload)["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        decode_legacy_lineage_manifest(mapping_payload)

    revision_payload = valid_payload()
    _revision(_mapping(revision_payload))["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        decode_legacy_lineage_manifest(revision_payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("format", "other/format", "unsupported format"),
        ("version", 2, "unsupported version"),
        ("source_database_sha256", "A" * 64, "lowercase SHA-256"),
        ("source_database_sha256", "not-a-hash", "lowercase SHA-256"),
        ("reviewer_id", "", "reviewer_id"),
        ("reviewed_at", "2026-08-02T16:49:00", "timezone"),
    ],
)
def test_invalid_top_level_values_are_rejected(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = valid_payload()
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        decode_legacy_lineage_manifest(payload)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: _mapping(payload).__setitem__(
                "legacy_document_id", "../LAW3"
            ),
            "legacy_document_id",
        ),
        (
            lambda payload: _mapping(payload).__setitem__(
                "canonical_document_id", "DOC/INVALID"
            ),
            "canonical_document_id",
        ),
        (
            lambda payload: _mapping(payload).__setitem__("source_sha256", "B" * 64),
            "lowercase SHA-256",
        ),
        (
            lambda payload: _mapping(payload).__setitem__("reason", ""),
            "reason",
        ),
        (
            lambda payload: _revision(_mapping(payload)).__setitem__(
                "legacy_revision_id", ""
            ),
            "legacy_revision_id",
        ),
    ],
)
def test_invalid_nested_values_are_rejected(
    mutate: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    payload = valid_payload()
    mutate(payload)
    with pytest.raises(ValueError, match=message):
        decode_legacy_lineage_manifest(payload)


def test_manifest_requires_non_empty_mappings_and_revision_mappings() -> None:
    payload = valid_payload()
    payload["mappings"] = []
    with pytest.raises(ValueError, match="mappings must not be empty"):
        decode_legacy_lineage_manifest(payload)

    payload = valid_payload()
    _mapping(payload)["revision_mappings"] = []
    with pytest.raises(ValueError, match="revision_mappings must not be empty"):
        decode_legacy_lineage_manifest(payload)


def test_equal_legacy_and_canonical_ids_are_rejected() -> None:
    payload = valid_payload()
    _mapping(payload)["canonical_document_id"] = "LAW3"
    with pytest.raises(ValueError, match="must differ"):
        decode_legacy_lineage_manifest(payload)

    payload = valid_payload()
    revision = _revision(_mapping(payload))
    revision["canonical_revision_id"] = revision["legacy_revision_id"]
    with pytest.raises(ValueError, match="revision IDs must differ"):
        decode_legacy_lineage_manifest(payload)


def test_duplicate_aliases_and_revision_ids_are_rejected() -> None:
    payload = valid_payload()
    duplicate = deepcopy(_mapping(payload))
    mappings = payload["mappings"]
    assert isinstance(mappings, list)
    mappings.append(duplicate)
    with pytest.raises(ValueError, match="duplicate legacy_document_id"):
        decode_legacy_lineage_manifest(payload)

    payload = valid_payload()
    mapping = _mapping(payload)
    revisions = mapping["revision_mappings"]
    assert isinstance(revisions, list)
    revisions.append(deepcopy(_revision(mapping)))
    with pytest.raises(ValueError, match="duplicate legacy_revision_id"):
        decode_legacy_lineage_manifest(payload)


def test_canonical_revision_target_cannot_be_reused() -> None:
    payload = valid_payload()
    second = deepcopy(_mapping(payload))
    second["legacy_document_id"] = "LAW4"
    second["canonical_document_id"] = "DOC-OTHER"
    second_revision = _revision(second)
    second_revision["legacy_revision_id"] = "REV-LAW4-001"
    mappings = payload["mappings"]
    assert isinstance(mappings, list)
    mappings.append(second)

    with pytest.raises(ValueError, match="duplicate canonical_revision_id"):
        decode_legacy_lineage_manifest(payload)
