from pathlib import Path

import pytest

from evidence_review.parsing.drawing_source import (
    DrawingIntakePolicy,
    ingest_drawing_source,
    sniff_drawing_mime,
    verify_immutable_attachment,
)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"%PDF-1.7\n", ("application/pdf", ".pdf")),
        (b"\x89PNG\r\n\x1a\n", ("image/png", ".png")),
        (b"II*\x00", ("image/tiff", ".tif")),
        (b"MM\x00*", ("image/tiff", ".tif")),
        (b"\xff\xd8\xff", ("image/jpeg", ".jpg")),
    ],
)
def test_sniff_drawing_mime(header: bytes, expected: tuple[str, str]) -> None:
    assert sniff_drawing_mime(header) == expected


def test_unknown_signature_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported drawing signature"):
        sniff_drawing_mime(b"GIF89a")


def test_ingest_rejects_extension_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "drawing.jpg"
    source.write_bytes(b"%PDF-1.7\n")
    with pytest.raises(ValueError, match="extension does not match MIME"):
        ingest_drawing_source(
            source,
            tmp_path / "cases" / "CASE-001",
            "ATT-001",
            "CASE_DRAWING",
            DrawingIntakePolicy(max_file_bytes=1024),
        )


def test_ingest_stops_when_stream_exceeds_policy(tmp_path: Path) -> None:
    source = tmp_path / "drawing.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 32)
    case_dir = tmp_path / "case"
    with pytest.raises(ValueError, match="FILE_SIZE_LIMIT_EXCEEDED"):
        ingest_drawing_source(
            source,
            case_dir,
            "ATT-001",
            "CASE_DRAWING",
            DrawingIntakePolicy(max_file_bytes=16),
        )
    assert not list(case_dir.rglob("*.tmp"))


def test_ingest_copies_source_bytes_and_never_overwrites(tmp_path: Path) -> None:
    source = tmp_path / "drawing.png"
    payload = b"\x89PNG\r\n\x1a\n" + b"payload"
    source.write_bytes(payload)
    case_dir = tmp_path / "case"
    attachment = ingest_drawing_source(
        source, case_dir, "ATT-001", "CASE_DRAWING", DrawingIntakePolicy()
    )
    stored = case_dir / "sources" / "drawings" / "ATT-001.png"
    assert stored.read_bytes() == payload
    assert attachment.stored_path == "inputs/original/ATT-001.png"

    source.write_bytes(payload)
    with pytest.raises(FileExistsError):
        ingest_drawing_source(
            source, case_dir, "ATT-001", "CASE_DRAWING", DrawingIntakePolicy()
        )


def test_ingest_accepts_extension_alias_and_normalizes_path(tmp_path: Path) -> None:
    source = tmp_path / "drawing.jpeg"
    source.write_bytes(b"\xff\xd8\xff" + b"fixture")
    attachment = ingest_drawing_source(
        source,
        tmp_path / "case",
        "ATT-002",
        "SUPPORTING_IMAGE",
        DrawingIntakePolicy(),
    )
    assert attachment.mime == "image/jpeg"
    assert attachment.stored_path == "inputs/original/ATT-002.jpg"


def test_verify_attachment_reports_size_and_hash_tampering(tmp_path: Path) -> None:
    source = tmp_path / "drawing.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fixture")
    case_dir = tmp_path / "case"
    attachment = ingest_drawing_source(
        source, case_dir, "ATT-001", "CASE_DRAWING", DrawingIntakePolicy()
    )
    stored = case_dir / "sources" / "drawings" / "ATT-001.png"
    stored.write_bytes(stored.read_bytes() + b"tamper")
    assert verify_immutable_attachment(case_dir, attachment) == (
        "SOURCE_SIZE_MISMATCH",
        "SOURCE_HASH_MISMATCH",
    )


def test_symlink_source_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "real.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    link = tmp_path / "link.png"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")
    with pytest.raises(ValueError, match="regular non-link file"):
        ingest_drawing_source(
            link,
            tmp_path / "case",
            "ATT-001",
            "CASE_DRAWING",
            DrawingIntakePolicy(),
        )
