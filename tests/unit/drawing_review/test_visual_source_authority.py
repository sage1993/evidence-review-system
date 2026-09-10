from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter

from evidence_review.contracts.attachments import ImmutableAttachment
from evidence_review.drawing_review import visual_pages as visual_pages_module
from evidence_review.drawing_review.visual_pages import prepare_visual_page_assets


def _png_bytes(path: Path, color: str = "white") -> bytes:
    Image.new("RGB", (8, 6), color).save(path, format="PNG")
    return path.read_bytes()


def _attachment(
    case_id: str,
    attachment_id: str,
    payload: bytes,
    *,
    stored_path: str | None = None,
    sha256: str | None = None,
) -> ImmutableAttachment:
    return ImmutableAttachment(
        case_id=case_id,
        attachment_id=attachment_id,
        original_name="plan.png",
        stored_path=(
            stored_path
            or f"cases/{case_id}/sources/drawings/{attachment_id}.png"
        ),
        sha256=sha256 or hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
        mime="image/png",
        role="CASE_DRAWING",
    )


def _visual_attachment(
    case_id: str,
    attachment_id: str,
    payload: bytes,
    mime: str,
    extension: str,
) -> ImmutableAttachment:
    return ImmutableAttachment(
        case_id=case_id,
        attachment_id=attachment_id,
        original_name=f"plan{extension}",
        stored_path=(
            f"cases/{case_id}/sources/drawings/{attachment_id}{extension}"
        ),
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
        mime=mime,
        role="CASE_DRAWING",
    )


def _store(workspace: Path, attachment: ImmutableAttachment, payload: bytes) -> Path:
    destination = workspace.joinpath(*Path(attachment.stored_path).parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return destination


def _image_payload(image_format: str, suffix: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 6), "white").save(output, format=image_format)
    return output.getvalue()


def _pdf_payload() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize(
    ("content_format", "declared_mime", "stored_extension"),
    [
        ("PDF", "image/png", ".png"),
        ("PNG", "image/jpeg", ".jpg"),
        ("JPEG", "image/tiff", ".tif"),
        ("TIFF", "application/pdf", ".pdf"),
    ],
)
def test_visual_source_rejects_declared_mime_that_differs_from_content(
    tmp_path: Path,
    content_format: str,
    declared_mime: str,
    stored_extension: str,
) -> None:
    payload = (
        _pdf_payload()
        if content_format == "PDF"
        else _image_payload(content_format, stored_extension)
    )
    attachment = _visual_attachment(
        "CASE-ALPHA",
        "ATT-SOURCE",
        payload,
        declared_mime,
        stored_extension,
    )
    _store(tmp_path, attachment, payload)

    with pytest.raises(ValueError, match="MIME/content binding mismatch"):
        prepare_visual_page_assets(tmp_path, (attachment,))


def test_visual_source_rejects_unrecognized_content_before_decoder(
    tmp_path: Path,
) -> None:
    payload = b"not a supported visual source"
    attachment = _visual_attachment(
        "CASE-ALPHA",
        "ATT-SOURCE",
        payload,
        "image/png",
        ".png",
    )
    _store(tmp_path, attachment, payload)

    with pytest.raises(ValueError, match="unsupported drawing signature"):
        prepare_visual_page_assets(tmp_path, (attachment,))


@pytest.mark.parametrize(
    ("payload", "mime", "extension"),
    [
        (b"\x89PNG\r\n\x1a\nbroken", "image/png", ".png"),
        (b"\xff\xd8\xffbroken", "image/jpeg", ".jpg"),
        (b"II*\x00broken", "image/tiff", ".tif"),
    ],
)
def test_visual_source_rejects_magic_valid_malformed_image_before_normalization(
    tmp_path: Path,
    payload: bytes,
    mime: str,
    extension: str,
) -> None:
    attachment = _visual_attachment(
        "CASE-ALPHA",
        "ATT-SOURCE",
        payload,
        mime,
        extension,
    )
    _store(tmp_path, attachment, payload)

    with pytest.raises(ValueError, match="CASE_VISUAL_IMAGE_DECODER_INVALID"):
        prepare_visual_page_assets(tmp_path, (attachment,))


@pytest.mark.parametrize("reported_format", [None, "JPEG"])
def test_visual_source_rejects_decoder_format_that_does_not_match_validated_mime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reported_format: str | None,
) -> None:
    payload = _image_payload("PNG", ".png")
    attachment = _visual_attachment(
        "CASE-ALPHA",
        "ATT-SOURCE",
        payload,
        "image/png",
        ".png",
    )
    _store(tmp_path, attachment, payload)
    original_open = Image.open

    def open_with_reported_format(path: Path) -> Image.Image:
        opened = original_open(path)
        opened.format = reported_format
        return opened

    monkeypatch.setattr(visual_pages_module.Image, "open", open_with_reported_format)

    with pytest.raises(ValueError, match="CASE_VISUAL_IMAGE_DECODER_INVALID"):
        prepare_visual_page_assets(tmp_path, (attachment,))


def test_visual_source_keeps_pillow_pixel_limit_after_format_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _image_payload("PNG", ".png")
    attachment = _visual_attachment(
        "CASE-ALPHA",
        "ATT-SOURCE",
        payload,
        "image/png",
        ".png",
    )
    _store(tmp_path, attachment, payload)
    monkeypatch.setattr(visual_pages_module, "_MAX_IMAGE_PIXELS", 47)

    with pytest.raises(ValueError, match="CASE_VISUAL_IMAGE_SIZE_INVALID"):
        prepare_visual_page_assets(tmp_path, (attachment,))


def test_visual_source_resolves_same_plan_basename_in_its_own_case(
    tmp_path: Path,
) -> None:
    first_fixture = tmp_path / "first.png"
    first_payload = _png_bytes(first_fixture, "white")
    second_fixture = tmp_path / "second.png"
    second_payload = _png_bytes(second_fixture, "black")
    first = _attachment("CASE-ALPHA", "ATT-ALPHA", first_payload)
    second = _attachment("CASE-BETA", "ATT-BETA", second_payload)
    _store(tmp_path, first, first_payload)
    _store(tmp_path, second, second_payload)

    first_page = prepare_visual_page_assets(tmp_path, (first,))
    second_page = prepare_visual_page_assets(tmp_path, (second,))

    assert first_page[0].source_sha256 == hashlib.sha256(first_payload).hexdigest()
    assert second_page[0].source_sha256 == hashlib.sha256(second_payload).hexdigest()


def test_visual_image_cache_identity_includes_case_id_for_same_attachment_id(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "plan.png"
    payload = _png_bytes(fixture)
    first = _attachment("CASE-ALPHA", "ATT-SAME", payload)
    second = _attachment("CASE-BETA", "ATT-SAME", payload)
    _store(tmp_path, first, payload)
    _store(tmp_path, second, payload)

    pages = prepare_visual_page_assets(tmp_path, (first, second))

    assert [page.case_id for page in pages] == ["CASE-ALPHA", "CASE-BETA"]
    assert pages[0].image_path != pages[1].image_path
    for page in pages:
        metadata_path = page.image_path.with_suffix(".json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["case_id"] == page.case_id


def test_visual_pdf_cache_identity_includes_case_id_for_same_attachment_id(
    tmp_path: Path,
) -> None:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    payload = output.getvalue()
    first = ImmutableAttachment(
        case_id="CASE-ALPHA",
        attachment_id="ATT-SAME",
        original_name="plan.pdf",
        stored_path="cases/CASE-ALPHA/sources/drawings/ATT-SAME.pdf",
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
        mime="application/pdf",
        role="CASE_DRAWING",
    )
    second = ImmutableAttachment(
        case_id="CASE-BETA",
        attachment_id="ATT-SAME",
        original_name="plan.pdf",
        stored_path="cases/CASE-BETA/sources/drawings/ATT-SAME.pdf",
        sha256=first.sha256,
        byte_size=first.byte_size,
        mime="application/pdf",
        role="CASE_DRAWING",
    )
    _store(tmp_path, first, payload)
    _store(tmp_path, second, payload)

    pages = prepare_visual_page_assets(tmp_path, (first, second))

    assert [page.case_id for page in pages] == ["CASE-ALPHA", "CASE-BETA"]
    assert pages[0].image_path != pages[1].image_path
    for page in pages:
        metadata_path = page.image_path.with_suffix(".json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["case_id"] == page.case_id


@pytest.mark.parametrize(
    ("attachment_id", "sha256", "match"),
    [
        ("ATT-SOURCE", "0" * 64, "hash mismatch"),
        ("ATT-OTHER", None, "identity"),
    ],
)
def test_visual_source_rejects_wrong_hash_or_attachment_identity(
    tmp_path: Path,
    attachment_id: str,
    sha256: str | None,
    match: str,
) -> None:
    fixture = tmp_path / "plan.png"
    payload = _png_bytes(fixture)
    stored = _attachment("CASE-ALPHA", "ATT-SOURCE", payload)
    _store(tmp_path, stored, payload)
    requested = _attachment(
        "CASE-ALPHA",
        attachment_id,
        payload,
        stored_path=stored.stored_path,
        sha256=sha256,
    )

    with pytest.raises(ValueError, match=match):
        prepare_visual_page_assets(tmp_path, (requested,))


def test_visual_source_rejects_missing_case_local_path(tmp_path: Path) -> None:
    fixture = tmp_path / "plan.png"
    payload = _png_bytes(fixture)
    attachment = _attachment("CASE-ALPHA", "ATT-SOURCE", payload)

    with pytest.raises(FileNotFoundError, match="case visual source"):
        prepare_visual_page_assets(tmp_path, (attachment,))


def test_visual_source_rejects_ambiguous_attachment_binding(tmp_path: Path) -> None:
    fixture = tmp_path / "plan.png"
    payload = _png_bytes(fixture)
    attachment = _attachment("CASE-ALPHA", "ATT-SOURCE", payload)
    _store(tmp_path, attachment, payload)

    with pytest.raises(ValueError, match="ambiguous"):
        prepare_visual_page_assets(tmp_path, (attachment, attachment))


def test_visual_source_rejects_traversal_in_stored_path(tmp_path: Path) -> None:
    fixture = tmp_path / "plan.png"
    payload = _png_bytes(fixture)
    attachment = _attachment(
        "CASE-ALPHA",
        "ATT-SOURCE",
        payload,
        stored_path="cases/CASE-ALPHA/sources/drawings/../../outside.png",
    )

    with pytest.raises(ValueError, match="safe relative path|identity"):
        prepare_visual_page_assets(tmp_path, (attachment,))


def test_visual_source_rejects_symlinked_case_local_file(tmp_path: Path) -> None:
    fixture = tmp_path / "plan.png"
    payload = _png_bytes(fixture)
    attachment = _attachment("CASE-ALPHA", "ATT-SOURCE", payload)
    outside = tmp_path / "outside.png"
    outside.write_bytes(payload)
    destination = tmp_path.joinpath(*Path(attachment.stored_path).parts)
    destination.parent.mkdir(parents=True)
    try:
        destination.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        prepare_visual_page_assets(tmp_path, (attachment,))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction semantics")
def test_visual_source_rejects_reparse_case_local_directory(tmp_path: Path) -> None:
    fixture = tmp_path / "plan.png"
    payload = _png_bytes(fixture)
    attachment = _attachment("CASE-ALPHA", "ATT-SOURCE", payload)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "ATT-SOURCE.png").write_bytes(payload)
    drawings = tmp_path / "cases" / "CASE-ALPHA" / "sources" / "drawings"
    drawings.parent.mkdir(parents=True)
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(drawings), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        pytest.skip(f"junction creation unavailable: {detail or completed.returncode}")

    with pytest.raises(ValueError, match="reparse"):
        prepare_visual_page_assets(tmp_path, (attachment,))
