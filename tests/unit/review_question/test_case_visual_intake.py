from __future__ import annotations

from pathlib import Path

import pytest

from evidence_review.case_visual import prepare_case_visual_sources


def test_prepare_case_visual_sources_is_deterministic_and_reusable(tmp_path: Path) -> None:
    drawing = tmp_path / "drawing.pdf"
    drawing.write_bytes(b"%PDF-1.7\ncase-visual-fixture")

    first = prepare_case_visual_sources(tmp_path / "workspace", case_drawings=[drawing])
    second = prepare_case_visual_sources(tmp_path / "workspace", case_drawings=[drawing])

    assert second == first
    assert len(first) == 1
    attachment = first[0]
    assert attachment.role == "CASE_DRAWING"
    assert attachment.mime == "application/pdf"
    stored = list((tmp_path / "workspace" / "cases").rglob(f"{attachment.attachment_id}.pdf"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == drawing.read_bytes()


def test_prepare_case_visual_sources_separates_supporting_image_role(tmp_path: Path) -> None:
    image = tmp_path / "support.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nvisual-fixture")

    attachments = prepare_case_visual_sources(
        tmp_path / "workspace",
        supporting_images=[image],
    )

    assert len(attachments) == 1
    assert attachments[0].role == "SUPPORTING_IMAGE"
    assert attachments[0].mime == "image/png"


def test_prepare_case_visual_sources_rejects_extension_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "drawing.jpg"
    source.write_bytes(b"%PDF-1.7\nfixture")

    with pytest.raises(ValueError, match="extension does not match MIME"):
        prepare_case_visual_sources(tmp_path / "workspace", case_drawings=[source])


def test_case_visual_identity_does_not_depend_on_source_directory(tmp_path: Path) -> None:
    first_dir = tmp_path / "a"
    second_dir = tmp_path / "b"
    first_dir.mkdir()
    second_dir.mkdir()
    payload = b"%PDF-1.7\nsame-bytes"
    first_path = first_dir / "drawing.pdf"
    second_path = second_dir / "drawing.pdf"
    first_path.write_bytes(payload)
    second_path.write_bytes(payload)

    first = prepare_case_visual_sources(tmp_path / "workspace-a", case_drawings=[first_path])
    second = prepare_case_visual_sources(tmp_path / "workspace-b", case_drawings=[second_path])

    assert first[0] == second[0]
