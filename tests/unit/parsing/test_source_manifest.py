from pathlib import Path

from ansim_review.parsing.source_manifest import (
    build_source_entry,
    verify_source_entry,
)


def test_source_hash_mismatch_after_pdf_change(tmp_path: Path) -> None:
    pdf = tmp_path / "law-1.pdf"
    parser = tmp_path / "law-1.json"
    pdf.write_bytes(b"%PDF-1.7\noriginal")
    parser.write_text('{"number of pages": 2, "kids": []}', encoding="utf-8")

    entry = build_source_entry(
        pdf,
        document_id="LAW1",
        page_count=2,
        parser_artifacts=(parser,),
    )

    assert entry.revision_id == f"LAW1-{entry.source_hash[:12]}"
    assert entry.byte_size == len(b"%PDF-1.7\noriginal")
    assert entry.parser_artifacts[0].sha256

    pdf.write_bytes(b"%PDF-1.7\nchanged!")

    errors = verify_source_entry(entry, pdf, parser_artifacts=(parser,))
    assert [error.code for error in errors] == ["SOURCE_HASH_MISMATCH"]


def test_page_count_mismatch_is_reported(tmp_path: Path) -> None:
    pdf = tmp_path / "law-1.pdf"
    pdf.write_bytes(b"%PDF-1.7\noriginal")
    entry = build_source_entry(pdf, document_id="LAW1", page_count=2)

    errors = verify_source_entry(entry, pdf, actual_page_count=3)

    assert [error.code for error in errors] == ["PAGE_COUNT_MISMATCH"]
