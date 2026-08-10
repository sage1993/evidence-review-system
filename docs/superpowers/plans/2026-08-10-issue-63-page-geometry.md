# Issue #63 PDF Page Geometry Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the silent A4 `595 × 842` fallback and make verified source-PDF page geometry the single coordinate contract used by OpenDataLoader ingestion, evidence storage, citations, and Review Workspace overlays.

**Architecture:** Add one focused PDF geometry resolver backed by the existing `pypdf>=5,<6` runtime dependency. OpenDataLoader metadata becomes a cross-check rather than the canonical geometry source; ingestion fails closed on invalid or mismatched geometry. The Review Workspace receives canonical page dimensions from the evidence DB and refuses to render an overlay when those dimensions diverge from verified page-image metadata.

**Tech Stack:** Python 3.11+, `pypdf>=5,<6`, SQLite, pytest, Ruff, mypy, compileall.

## Global Constraints

- Do not add a new runtime dependency; `pypdf>=5,<6` is already declared in `pyproject.toml`.
- Do not change the evidence DB schema or bbox storage format.
- Canonical bbox remains `[left, bottom, right, top]` in PDF points.
- Canonical page dimensions are the unrotated effective page-box width/height; do not swap width/height because of `/Rotate`.
- Effective page-box priority is valid `CropBox`, then valid `MediaBox`.
- Page-box width/height are calculated as `urx - llx` and `ury - lly`; non-zero lower-left origins must not inflate page size.
- Normalize integer quarter-turn rotations modulo 360; reject non-multiples of 90 with `PAGE_ROTATION_INVALID`.
- Parser/PDF width and height comparison tolerance is exactly `0.5 pt` per axis.
- Do not auto-scale, infer a paper standard, or downgrade geometry mismatch to warning-only behavior.
- Geometry failures must occur before evidence DB creation so no partial/empty DB is presented as a successful import.
- Keep existing `@page { size: A4; }` print CSS unchanged; it controls print layout, not source-PDF geometry.
- Preserve existing stable parser element IDs and existing valid bbox golden coordinates.
- Before Task 1 implementation, use `superpowers:using-git-worktrees` to create an isolated worktree from the branch containing this approved plan.

---

## File Structure

### Create

- `src/ansim_review/parsing/pdf_page_geometry.py` — read and validate canonical page geometry from the source PDF.
- `tests/helpers/pdf_fixtures.py` — create deterministic valid PDF fixtures with explicit MediaBox/CropBox/rotation values.
- `tests/unit/parsing/test_pdf_page_geometry.py` — unit contract for CropBox/MediaBox/origin/rotation/page-size behavior.

### Modify

- `src/ansim_review/parsing/odl_source.py` — remove A4 constants and represent parser dimensions as `ABSENT`, `VALID`, or `INVALID`.
- `src/ansim_review/parsing/odl_adapter.py` — reconcile parser dimensions/page count against canonical PDF geometry before bbox normalization.
- `src/ansim_review/review_packet/builder.py` — join `retrieval_records.page_id` to `pages.id` and add `page_width`/`page_height` to resolved citations.
- `src/ansim_review/review_packet/html_renderer.py` — verify DB citation geometry against verified page-image geometry before rendering.
- `tests/unit/parsing/test_odl_adapter.py` — parser geometry state, PDF fallback replacement, mismatch, page-count, and A3 landscape behavior.
- `tests/unit/parsing/test_coordinate_normalization.py` — A3 landscape and 0.5 pt boundary regression cases.
- `tests/unit/parsing/test_source_batch_importer.py` — use valid PDF fixtures on ingest paths and verify DB geometry/failure atomicity.
- `tests/unit/review_packet/test_builder.py` — verify page geometry is projected into citation view-model records.
- `tests/integration/review_packet/test_html_renderer.py` — geometry cross-check, A3/custom viewBox, and mismatch rejection.

### Explicitly unchanged

- `src/ansim_review/evidence/schema.sql`
- `pyproject.toml`
- bbox JSON representation
- print CSS A4 page size

The page-image producer is not in the planned edit set. Task 6 verifies the consumer-side contract. If the full suite proves that an existing producer writes display-swapped or otherwise noncanonical `pdf_width`/`pdf_height`, stop execution and revise this plan/spec before expanding scope rather than opportunistically refactoring unrelated rendering code.

---

### Task 1: Canonical PDF geometry resolver and valid PDF fixtures

**Files:**
- Create: `tests/helpers/pdf_fixtures.py`
- Create: `tests/unit/parsing/test_pdf_page_geometry.py`
- Create: `src/ansim_review/parsing/pdf_page_geometry.py`

**Interfaces:**
- Produces: `PdfPageGeometry(page_number, width, height, box_kind, origin_x, origin_y, rotation)`.
- Produces: `read_pdf_page_geometries(source_path: Path) -> tuple[PdfPageGeometry, ...]`.
- Produces test helper: `write_pdf_fixture(path: Path, *, page_sizes: Sequence[tuple[float, float]], crop_boxes: Mapping[int, tuple[float, float, float, float]] | None = None, rotations: Mapping[int, int] | None = None) -> Path`.
- Error contract: `PAGE_DIMENSIONS_UNAVAILABLE` and `PAGE_ROTATION_INVALID` are present in raised `ValueError` messages.

- [ ] **Step 1: Add the valid PDF fixture helper**

Create `tests/helpers/pdf_fixtures.py` with a 1-based page-number API so tests can specify mixed sizes, CropBox, and rotation without raw PDF byte manipulation:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import NameObject, NumberObject, RectangleObject

PageSize = tuple[float, float]
PageBox = tuple[float, float, float, float]


def write_pdf_fixture(
    path: Path,
    *,
    page_sizes: Sequence[PageSize],
    crop_boxes: Mapping[int, PageBox] | None = None,
    rotations: Mapping[int, int] | None = None,
) -> Path:
    writer = PdfWriter()
    crop_values = crop_boxes or {}
    rotation_values = rotations or {}
    for page_number, (width, height) in enumerate(page_sizes, start=1):
        page = writer.add_blank_page(width=width, height=height)
        crop_box = crop_values.get(page_number)
        if crop_box is not None:
            page.cropbox = RectangleObject(crop_box)
        rotation = rotation_values.get(page_number)
        if rotation is not None:
            page[NameObject("/Rotate")] = NumberObject(rotation)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        writer.write(stream)
    return path
```

- [ ] **Step 2: Write failing resolver tests**

Create `tests/unit/parsing/test_pdf_page_geometry.py` with at least these exact behaviors:

```python
from pathlib import Path

import pytest

from ansim_review.parsing.pdf_page_geometry import read_pdf_page_geometries
from tests.helpers.pdf_fixtures import write_pdf_fixture


def test_cropbox_is_canonical_and_non_zero_origin_is_subtracted(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "crop.pdf",
        page_sizes=((600.0, 800.0),),
        crop_boxes={1: (10.0, 20.0, 510.0, 720.0)},
    )

    page = read_pdf_page_geometries(source)[0]

    assert page.page_number == 1
    assert page.box_kind == "CROP_BOX"
    assert (page.origin_x, page.origin_y) == (10.0, 20.0)
    assert (page.width, page.height) == (500.0, 700.0)


def test_missing_cropbox_uses_mediabox(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "media.pdf",
        page_sizes=((842.0, 1191.0),),
    )

    page = read_pdf_page_geometries(source)[0]

    assert page.box_kind == "MEDIA_BOX"
    assert (page.width, page.height) == (842.0, 1191.0)


def test_invalid_cropbox_falls_back_to_valid_mediabox(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "invalid-crop.pdf",
        page_sizes=((1000.0, 700.0),),
        crop_boxes={1: (0.0, 0.0, 0.0, 0.0)},
    )

    page = read_pdf_page_geometries(source)[0]

    assert page.box_kind == "MEDIA_BOX"
    assert (page.width, page.height) == (1000.0, 700.0)


def test_mixed_page_sizes_and_rotation_are_preserved(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "mixed.pdf",
        page_sizes=((595.0, 842.0), (1191.0, 842.0)),
        rotations={2: -90},
    )

    pages = read_pdf_page_geometries(source)

    assert [(page.width, page.height) for page in pages] == [
        (595.0, 842.0),
        (1191.0, 842.0),
    ]
    assert [page.rotation for page in pages] == [0, 270]


def test_non_quarter_turn_rotation_is_rejected(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "bad-rotation.pdf",
        page_sizes=((600.0, 800.0),),
        rotations={1: 45},
    )

    with pytest.raises(ValueError, match="PAGE_ROTATION_INVALID"):
        read_pdf_page_geometries(source)


def test_unreadable_pdf_has_explicit_geometry_reason(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"not-a-pdf")

    with pytest.raises(ValueError, match="PAGE_DIMENSIONS_UNAVAILABLE"):
        read_pdf_page_geometries(source)
```

- [ ] **Step 3: Run the resolver tests and verify they fail for the missing module**

Run:

```powershell
python -m pytest tests/unit/parsing/test_pdf_page_geometry.py -v
```

Expected: FAIL during collection with `ModuleNotFoundError: ansim_review.parsing.pdf_page_geometry`.

- [ ] **Step 4: Implement the minimal PDF geometry resolver**

Create `src/ansim_review/parsing/pdf_page_geometry.py`. The implementation must inspect whether `/CropBox` exists before calling `page.cropbox`, because pypdf's `cropbox` property itself falls back to MediaBox and would otherwise hide which box supplied the geometry.

```python
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal

from pypdf import PageObject, PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import RectangleObject

PageBoxKind = Literal["CROP_BOX", "MEDIA_BOX"]


@dataclass(frozen=True, slots=True)
class PdfPageGeometry:
    page_number: int
    width: float
    height: float
    box_kind: PageBoxKind
    origin_x: float
    origin_y: float
    rotation: int


def _validated_rectangle(
    rectangle: RectangleObject,
) -> tuple[float, float, float, float] | None:
    values = (
        float(rectangle.left),
        float(rectangle.bottom),
        float(rectangle.right),
        float(rectangle.top),
    )
    if not all(isfinite(value) for value in values):
        return None
    left, bottom, right, top = values
    if right <= left or top <= bottom:
        return None
    return values


def _resolved_rectangle(
    page: PageObject,
    *,
    key: str,
    attribute: str,
) -> tuple[float, float, float, float] | None:
    if key == "/CropBox" and page.get(key) is None:
        return None
    try:
        rectangle = getattr(page, attribute)
        if not isinstance(rectangle, RectangleObject):
            rectangle = RectangleObject(rectangle)
        return _validated_rectangle(rectangle)
    except (PdfReadError, TypeError, ValueError, IndexError):
        return None


def _normalized_rotation(page: PageObject, page_number: int) -> int:
    value = page.get("/Rotate", 0)
    if hasattr(value, "get_object"):
        value = value.get_object()
    if isinstance(value, bool) or not isinstance(value, int) or value % 90 != 0:
        raise ValueError(f"PAGE_ROTATION_INVALID: page {page_number}")
    return int(value) % 360


def read_pdf_page_geometries(source_path: Path) -> tuple[PdfPageGeometry, ...]:
    try:
        reader = PdfReader(source_path)
        pages = tuple(reader.pages)
    except (OSError, PdfReadError, ValueError) as error:
        raise ValueError(
            f"PAGE_DIMENSIONS_UNAVAILABLE: unable to read {source_path.name}"
        ) from error
    if not pages:
        raise ValueError("PAGE_DIMENSIONS_UNAVAILABLE: PDF contains no pages")

    result: list[PdfPageGeometry] = []
    for page_number, page in enumerate(pages, start=1):
        rotation = _normalized_rotation(page, page_number)
        crop = _resolved_rectangle(page, key="/CropBox", attribute="cropbox")
        media = _resolved_rectangle(page, key="/MediaBox", attribute="mediabox")
        selected = crop if crop is not None else media
        if selected is None:
            raise ValueError(f"PAGE_DIMENSIONS_UNAVAILABLE: page {page_number}")
        left, bottom, right, top = selected
        result.append(
            PdfPageGeometry(
                page_number=page_number,
                width=right - left,
                height=top - bottom,
                box_kind="CROP_BOX" if crop is not None else "MEDIA_BOX",
                origin_x=left,
                origin_y=bottom,
                rotation=rotation,
            )
        )
    return tuple(result)
```

- [ ] **Step 5: Run resolver tests and static checks**

Run:

```powershell
python -m pytest tests/unit/parsing/test_pdf_page_geometry.py -v
python -m ruff check src/ansim_review/parsing/pdf_page_geometry.py tests/helpers/pdf_fixtures.py tests/unit/parsing/test_pdf_page_geometry.py
python -m mypy src/ansim_review/parsing/pdf_page_geometry.py
```

Expected: all PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
git add src/ansim_review/parsing/pdf_page_geometry.py tests/helpers/pdf_fixtures.py tests/unit/parsing/test_pdf_page_geometry.py
git commit -m "feat: resolve canonical PDF page geometry"
```

---

### Task 2: Remove the A4 fallback and classify parser dimensions

**Files:**
- Modify: `src/ansim_review/parsing/odl_source.py`
- Modify: `tests/unit/parsing/test_odl_adapter.py`

**Interfaces:**
- Produces: `ParserDimensionState = Literal["ABSENT", "VALID", "INVALID"]`.
- Produces: `ParserPageDimensionsResult(state, width, height)`.
- Changes: `parser_page_dimensions(payload, page_number) -> ParserPageDimensionsResult`.
- Preserves: `parser_bbox(element, width, height) -> list[float] | None`.

- [ ] **Step 1: Write failing parser-dimension state tests**

Extend `tests/unit/parsing/test_odl_adapter.py`:

```python
from math import inf, nan

import pytest

from ansim_review.parsing.odl_source import (
    ParserPageDimensionsResult,
    parser_page_dimensions,
)


def test_missing_parser_dimensions_are_absent_not_a4() -> None:
    assert parser_page_dimensions({"number of pages": 1}, 1) == (
        ParserPageDimensionsResult("ABSENT", None, None)
    )


def test_valid_parser_dimensions_are_preserved() -> None:
    payload = {"pages": [{"page_number": 1, "width": 1000.0, "height": 700.0}]}

    assert parser_page_dimensions(payload, 1) == ParserPageDimensionsResult(
        "VALID", 1000.0, 700.0
    )


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (0.0, 700.0),
        (-1.0, 700.0),
        (1000.0, 0.0),
        (1000.0, -1.0),
        (nan, 700.0),
        (inf, 700.0),
        (True, 700.0),
        ("1000", 700.0),
    ],
)
def test_invalid_parser_dimensions_are_not_treated_as_missing(
    width: object,
    height: object,
) -> None:
    payload = {"pages": [{"page_number": 1, "width": width, "height": height}]}

    assert parser_page_dimensions(payload, 1).state == "INVALID"


def test_partial_parser_dimensions_are_invalid() -> None:
    payload = {"pages": [{"page_number": 1, "width": 1000.0}]}

    assert parser_page_dimensions(payload, 1).state == "INVALID"
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```powershell
python -m pytest tests/unit/parsing/test_odl_adapter.py -v
```

Expected: FAIL because `ParserPageDimensionsResult` does not exist and the current function returns the A4 tuple.

- [ ] **Step 3: Replace the fallback with an explicit result type**

In `src/ansim_review/parsing/odl_source.py`, remove `_DEFAULT_PAGE_WIDTH` and `_DEFAULT_PAGE_HEIGHT`, remove the runtime import of `RawElement`, and add explicit state handling:

```python
from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from ansim_review.parsing.odl_adapter import RawElement

ParserDimensionState = Literal["ABSENT", "VALID", "INVALID"]


@dataclass(frozen=True, slots=True)
class ParserPageDimensionsResult:
    state: ParserDimensionState
    width: float | None
    height: float | None


def parser_page_dimensions(
    payload: Mapping[str, Any], page_number: int
) -> ParserPageDimensionsResult:
    pages = payload.get("pages")
    if pages is None:
        return ParserPageDimensionsResult("ABSENT", None, None)
    if not isinstance(pages, list):
        return ParserPageDimensionsResult("INVALID", None, None)

    for page in pages:
        if not isinstance(page, dict):
            continue
        number = page.get("page_number", page.get("page number"))
        if number != page_number:
            continue
        has_width = "width" in page
        has_height = "height" in page
        if not has_width and not has_height:
            return ParserPageDimensionsResult("ABSENT", None, None)
        width = page.get("width")
        height = page.get("height")
        if (
            isinstance(width, (int, float))
            and not isinstance(width, bool)
            and isinstance(height, (int, float))
            and not isinstance(height, bool)
            and isfinite(float(width))
            and isfinite(float(height))
            and float(width) > 0
            and float(height) > 0
        ):
            return ParserPageDimensionsResult("VALID", float(width), float(height))
        return ParserPageDimensionsResult("INVALID", None, None)

    return ParserPageDimensionsResult("ABSENT", None, None)
```

Keep `from __future__ import annotations`, so the `RawElement` annotations remain valid without the runtime circular import.

- [ ] **Step 4: Run focused tests and verify the A4 constants are gone**

Run:

```powershell
python -m pytest tests/unit/parsing/test_odl_adapter.py -v
git grep -n "_DEFAULT_PAGE_WIDTH\|_DEFAULT_PAGE_HEIGHT" -- src/ansim_review/parsing
```

Expected: pytest PASS; `git grep` returns no matches.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/ansim_review/parsing/odl_source.py tests/unit/parsing/test_odl_adapter.py
git commit -m "fix: remove silent A4 parser fallback"
```

---

### Task 3: Reconcile OpenDataLoader geometry against the source PDF

**Files:**
- Modify: `src/ansim_review/parsing/odl_adapter.py`
- Modify: `tests/unit/parsing/test_odl_adapter.py`

**Interfaces:**
- Consumes: `read_pdf_page_geometries(Path) -> tuple[PdfPageGeometry, ...]` from Task 1.
- Consumes: `parser_page_dimensions(...) -> ParserPageDimensionsResult` from Task 2.
- Produces private boundary: `_reconcile_page_dimensions(payload: Mapping[str, Any], page_count: int, pdf_pages: tuple[PdfPageGeometry, ...]) -> tuple[PageDimensions, ...]`.
- Error contract: `PARSER_PDF_PAGE_COUNT_MISMATCH`, `PARSER_PAGE_DIMENSIONS_INVALID`, `PARSER_PDF_PAGE_DIMENSIONS_MISMATCH`.
- Invariant: dimensions used by `parser_bbox()` are exactly the canonical PDF dimensions returned in `NormalizedParserContribution.page_dimensions`.

- [ ] **Step 1: Add failing adapter tests for source-PDF geometry**

Extend `tests/unit/parsing/test_odl_adapter.py` with a parser writer and adapter helper:

```python
import json

from ansim_review.parsing.odl_adapter import OpenDataLoaderJsonAdapter
from ansim_review.parsing.parser_registry import ParserContext
from tests.helpers.pdf_fixtures import write_pdf_fixture


def _write_parser(
    path: Path,
    *,
    file_name: str,
    page_count: int,
    bbox: tuple[float, float, float, float],
    dimensions: tuple[float, float] | None = None,
) -> Path:
    payload: dict[str, object] = {
        "file name": file_name,
        "number of pages": page_count,
        "kids": [
            {
                "type": "paragraph",
                "page number": 1,
                "bounding box": list(bbox),
                "content": "geometry fixture",
            }
        ],
    }
    if dimensions is not None:
        payload["pages"] = [
            {
                "page_number": 1,
                "width": dimensions[0],
                "height": dimensions[1],
            }
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _parse(source: Path, parser: Path):
    return OpenDataLoaderJsonAdapter().parse(
        ParserContext(source_path=source, parser_artifact_path=parser, options={})
    )
```

Add these behavior tests:

```python
def test_missing_parser_dimensions_use_a3_landscape_pdf_geometry(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "drawing.pdf",
        page_sizes=((1191.0, 842.0),),
    )
    parser = _write_parser(
        tmp_path / "drawing.json",
        file_name=source.name,
        page_count=1,
        bbox=(100.0, 100.0, 1100.0, 700.0),
    )

    contribution = _parse(source, parser)

    assert [(p.width, p.height) for p in contribution.page_dimensions] == [
        (1191.0, 842.0)
    ]
    assert contribution.elements[0].bbox == (100.0, 100.0, 1100.0, 700.0)


def test_parser_dimensions_within_half_point_use_canonical_pdf_values(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "custom.pdf", page_sizes=((1000.0, 700.0),))
    parser = _write_parser(
        tmp_path / "custom.json",
        file_name=source.name,
        page_count=1,
        bbox=(10.0, 20.0, 100.0, 40.0),
        dimensions=(999.6, 700.4),
    )

    contribution = _parse(source, parser)

    assert contribution.page_dimensions[0].width == 1000.0
    assert contribution.page_dimensions[0].height == 700.0


def test_parser_pdf_dimension_mismatch_is_rejected(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "custom.pdf", page_sizes=((1000.0, 700.0),))
    parser = _write_parser(
        tmp_path / "custom.json",
        file_name=source.name,
        page_count=1,
        bbox=(10.0, 20.0, 100.0, 40.0),
        dimensions=(998.0, 700.0),
    )

    with pytest.raises(ValueError, match="PARSER_PDF_PAGE_DIMENSIONS_MISMATCH"):
        _parse(source, parser)


def test_invalid_parser_dimension_is_rejected_even_when_pdf_is_valid(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "custom.pdf", page_sizes=((1000.0, 700.0),))
    parser = _write_parser(
        tmp_path / "custom.json",
        file_name=source.name,
        page_count=1,
        bbox=(10.0, 20.0, 100.0, 40.0),
        dimensions=(0.0, 700.0),
    )

    with pytest.raises(ValueError, match="PARSER_PAGE_DIMENSIONS_INVALID"):
        _parse(source, parser)


def test_parser_pdf_page_count_mismatch_is_rejected(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "one-page.pdf", page_sizes=((600.0, 800.0),))
    parser = _write_parser(
        tmp_path / "one-page.json",
        file_name=source.name,
        page_count=2,
        bbox=(10.0, 20.0, 100.0, 40.0),
    )

    with pytest.raises(ValueError, match="PARSER_PDF_PAGE_COUNT_MISMATCH"):
        _parse(source, parser)
```

- [ ] **Step 2: Run the adapter tests and verify the old fallback behavior fails the new expectations**

Run:

```powershell
python -m pytest tests/unit/parsing/test_odl_adapter.py -v
```

Expected: the new parse-path tests FAIL because `parser_page_dimensions()` no longer returns a `(width, height)` tuple and the adapter has not yet reconciled PDF geometry.

- [ ] **Step 3: Implement deterministic reconciliation in the adapter**

In `src/ansim_review/parsing/odl_adapter.py`, import the canonical resolver and metadata helpers at module scope now that Task 2 removed the runtime circular import. Add:

```python
from collections.abc import Mapping

from ansim_review.parsing.odl_source import (
    parser_bbox,
    parser_document_title,
    parser_page_count,
    parser_page_dimensions,
    read_parser_json,
)
from ansim_review.parsing.pdf_page_geometry import (
    PdfPageGeometry,
    read_pdf_page_geometries,
)

_GEOMETRY_TOLERANCE = 0.5


def _reconcile_page_dimensions(
    payload: Mapping[str, Any],
    page_count: int,
    pdf_pages: tuple[PdfPageGeometry, ...],
) -> tuple[PageDimensions, ...]:
    if len(pdf_pages) != page_count:
        raise ValueError(
            "PARSER_PDF_PAGE_COUNT_MISMATCH: "
            f"parser={page_count} pdf={len(pdf_pages)}"
        )

    dimensions: list[PageDimensions] = []
    for pdf_page in pdf_pages:
        declared = parser_page_dimensions(payload, pdf_page.page_number)
        if declared.state == "INVALID":
            raise ValueError(
                f"PARSER_PAGE_DIMENSIONS_INVALID: page {pdf_page.page_number}"
            )
        if declared.state == "VALID":
            assert declared.width is not None
            assert declared.height is not None
            if (
                abs(declared.width - pdf_page.width) > _GEOMETRY_TOLERANCE
                or abs(declared.height - pdf_page.height) > _GEOMETRY_TOLERANCE
            ):
                raise ValueError(
                    "PARSER_PDF_PAGE_DIMENSIONS_MISMATCH: "
                    f"page {pdf_page.page_number} "
                    f"parser={declared.width}x{declared.height} "
                    f"pdf={pdf_page.width}x{pdf_page.height}"
                )
        dimensions.append(
            PageDimensions(
                pdf_page.page_number,
                pdf_page.width,
                pdf_page.height,
            )
        )
    return tuple(dimensions)
```

Replace the old tuple comprehension in `OpenDataLoaderJsonAdapter.parse()` with:

```python
raw_elements = load_raw_elements(
    context.parser_artifact_path,
    document_id="PARSER",
    revision_id="PARSER",
)
page_count = parser_page_count(payload, raw_elements)
pdf_pages = read_pdf_page_geometries(context.source_path)
dimensions = _reconcile_page_dimensions(payload, page_count, pdf_pages)
size_by_page = {
    page.page_number: (page.width, page.height) for page in dimensions
}
```

Keep source filename binding before `read_pdf_page_geometries()` so `PARSER_SOURCE_MISMATCH` remains the first deterministic failure for a wrongly bound parser artifact.

- [ ] **Step 4: Run adapter, bbox, and resolver tests**

Run:

```powershell
python -m pytest tests/unit/parsing/test_odl_adapter.py tests/unit/parsing/test_coordinate_normalization.py tests/unit/parsing/test_pdf_page_geometry.py -v
python -m ruff check src/ansim_review/parsing tests/unit/parsing/test_odl_adapter.py
python -m mypy src/ansim_review/parsing
```

Expected: all PASS.

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/ansim_review/parsing/odl_adapter.py tests/unit/parsing/test_odl_adapter.py
git commit -m "fix: reconcile parser geometry with source PDF"
```

---

### Task 4: Make source-batch ingestion use valid PDFs and verify stored geometry

**Files:**
- Modify: `tests/unit/parsing/test_source_batch_importer.py`

**Interfaces:**
- Consumes: the Task 3 adapter behavior through `import_source_batch()`.
- Verifies: `pages.width`/`pages.height` persist canonical PDF geometry.
- Verifies: geometry failure occurs before `EvidenceStore(output, create=True)` and leaves no output DB.

- [ ] **Step 1: Replace the ingest-path fake PDF with a valid custom-size PDF**

Import the helper:

```python
from tests.helpers.pdf_fixtures import write_pdf_fixture
```

In `test_arbitrary_pdf_and_parser_create_searchable_evidence_database`, replace the synthetic `%PDF-1.7` bytes with:

```python
write_pdf_fixture(
    source,
    page_sizes=((1000.0, 700.0),),
)
```

Then extend the DB assertions:

```python
with sqlite3.connect(output) as connection:
    title = connection.execute("SELECT title FROM documents").fetchone()
    indexed = connection.execute("SELECT COUNT(*) FROM retrieval_records").fetchone()
    page_geometry = connection.execute(
        "SELECT width, height FROM pages WHERE page_number = 1"
    ).fetchone()
assert title == ("사용자 제공 기준",)
assert indexed == (1,)
assert page_geometry == (1000.0, 700.0)
```

- [ ] **Step 2: Add failure-atomicity tests**

Add:

```python
def test_geometry_mismatch_does_not_create_output_database(tmp_path: Path) -> None:
    source = tmp_path / "inputs" / "original" / "document.pdf"
    parser = tmp_path / "inputs" / "parser" / "result.json"
    write_pdf_fixture(source, page_sizes=((1000.0, 700.0),))
    _write_parser(parser, source.name)
    payload = json.loads(parser.read_text(encoding="utf-8"))
    payload["pages"] = [{"page_number": 1, "width": 595.0, "height": 842.0}]
    parser.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "evidence.sqlite"

    with pytest.raises(ValueError, match="PARSER_PDF_PAGE_DIMENSIONS_MISMATCH"):
        import_source_batch(
            tmp_path,
            _batch(
                _source(
                    "inputs/original/document.pdf",
                    parser_path="inputs/parser/result.json",
                )
            ),
            output,
        )

    assert not output.exists()


def test_unreadable_source_pdf_does_not_create_output_database(tmp_path: Path) -> None:
    source = tmp_path / "inputs" / "original" / "document.pdf"
    parser = tmp_path / "inputs" / "parser" / "result.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"not-a-pdf")
    _write_parser(parser, source.name)
    output = tmp_path / "evidence.sqlite"

    with pytest.raises(ValueError, match="PAGE_DIMENSIONS_UNAVAILABLE"):
        import_source_batch(
            tmp_path,
            _batch(
                _source(
                    "inputs/original/document.pdf",
                    parser_path="inputs/parser/result.json",
                )
            ),
            output,
        )

    assert not output.exists()
```

Keep prepare/hash/dedup-only tests on arbitrary bytes; those tests intentionally do not parse PDF geometry.

- [ ] **Step 3: Run source-batch tests**

Run:

```powershell
python -m pytest tests/unit/parsing/test_source_batch_importer.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit Task 4**

```powershell
git add tests/unit/parsing/test_source_batch_importer.py
git commit -m "test: verify canonical geometry during source import"
```

---

### Task 5: Project canonical page dimensions into Review Workspace citations

**Files:**
- Modify: `src/ansim_review/review_packet/builder.py`
- Modify: `tests/unit/review_packet/test_builder.py`

**Interfaces:**
- Produces citation fields: `page_width: float` and `page_height: float`.
- Source of truth: `pages.width`/`pages.height`, joined through `retrieval_records.page_id = pages.id`.
- Preserves packet citation identity fields; `page_width`/`page_height` are DB-resolved metadata and are not part of `_citation_identity()`.

- [ ] **Step 1: Add failing builder assertions**

In `test_view_model_resolves_all_required_sections_and_blank_decision`, add:

```python
assert citation["page_width"] == 120.0
assert citation["page_height"] == 200.0
```

- [ ] **Step 2: Run the builder test and verify failure**

Run:

```powershell
python -m pytest tests/unit/review_packet/test_builder.py::test_view_model_resolves_all_required_sections_and_blank_decision -v
```

Expected: FAIL with missing `page_width`/`page_height` keys.

- [ ] **Step 3: Join `pages` in `_resolve_citation()` and return dimensions**

Replace the query in `src/ansim_review/review_packet/builder.py` with:

```python
row = connection.execute(
    """SELECT r.evidence_id, r.document_id, r.revision_id, r.page_number,
              r.bbox_json, r.source_hash, r.title, r.raw_text, r.evidence_type,
              p.width, p.height
         FROM retrieval_records AS r
         JOIN pages AS p ON p.id = r.page_id
        WHERE r.evidence_id = ?""",
    (evidence_id,),
).fetchone()
```

Extend the returned dictionary:

```python
return {
    "citation_id": citation_id,
    "evidence_id": row[0],
    "document_id": row[1],
    "revision_id": row[2],
    "page_number": row[3],
    "bbox": _bbox(row[4]),
    "source_hash": row[5],
    "title": row[6],
    "quote": row[7],
    "evidence_type": row[8],
    "page_width": float(row[9]),
    "page_height": float(row[10]),
}
```

Do not add these fields to `_citation_identity()`. Packet identity verification must continue comparing the existing citation identity only; page geometry is independently resolved from the evidence DB.

- [ ] **Step 4: Run builder tests and static checks**

Run:

```powershell
python -m pytest tests/unit/review_packet/test_builder.py -v
python -m ruff check src/ansim_review/review_packet/builder.py tests/unit/review_packet/test_builder.py
python -m mypy src/ansim_review/review_packet/builder.py
```

Expected: all PASS.

- [ ] **Step 5: Commit Task 5**

```powershell
git add src/ansim_review/review_packet/builder.py tests/unit/review_packet/test_builder.py
git commit -m "feat: attach canonical page geometry to citations"
```

---

### Task 6: Fail closed when Review Workspace page-image geometry diverges

**Files:**
- Modify: `src/ansim_review/review_packet/html_renderer.py`
- Modify: `tests/integration/review_packet/test_html_renderer.py`

**Interfaces:**
- Consumes citation `page_width`/`page_height` from Task 5.
- Consumes `_PageAsset.pdf_width`/`pdf_height` from verified page-image metadata.
- Produces private check: `_verify_page_geometry(citation: Mapping[str, object], page_asset: _PageAsset) -> None`.
- Error contract: `PAGE_RENDER_GEOMETRY_MISMATCH`.
- Tolerance: exactly `0.5 pt` per axis.

- [ ] **Step 1: Update renderer fixtures to carry DB page geometry**

In `_model()`, add to the citation:

```python
"page_width": 120.0,
"page_height": 200.0,
```

Change `_write_page_assets()` to accept geometry:

```python
def _write_page_assets(
    root: Path,
    *,
    pdf_width: float = 120.0,
    pdf_height: float = 200.0,
) -> bytes:
    # existing setup remains unchanged
    metadata = {
        "format": "ansim/page-image",
        "version": 1,
        "revision_id": "REV1",
        "page_number": 3,
        "source_hash": "a" * 64,
        "pdf_width": pdf_width,
        "pdf_height": pdf_height,
        "image_sha256": hashlib.sha256(page_bytes).hexdigest(),
    }
```

- [ ] **Step 2: Add failing mismatch and large-page overlay tests**

Add:

```python
def test_page_image_geometry_mismatch_is_rejected(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages", pdf_width=121.0, pdf_height=200.0)

    with pytest.raises(ValueError, match="PAGE_RENDER_GEOMETRY_MISMATCH"):
        render_review_html(_model(), tmp_path / "pages")


def test_a3_landscape_overlay_uses_canonical_page_geometry(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages", pdf_width=1191.0, pdf_height=842.0)
    model = _model()
    claims = model["claims"]
    assert isinstance(claims, list)
    claim = claims[0]
    assert isinstance(claim, dict)
    citations = claim["citations"]
    assert isinstance(citations, list)
    citation = citations[0]
    assert isinstance(citation, dict)
    citation["page_width"] = 1191.0
    citation["page_height"] = 842.0
    citation["bbox"] = [100.0, 100.0, 1100.0, 700.0]

    html = render_review_html(model, tmp_path / "pages")

    assert '<svg viewBox="0 0 1191.0 842.0"' in html
    assert '<rect x="100.0" y="142.0" width="1000.0" height="600.0">' in html


def test_page_geometry_within_half_point_is_accepted(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages", pdf_width=120.4, pdf_height=199.6)

    html = render_review_html(_model(), tmp_path / "pages")

    assert '<svg viewBox="0 0 120.4 199.6"' in html
```

- [ ] **Step 3: Run the new renderer tests and verify mismatch is not yet rejected**

Run:

```powershell
python -m pytest tests/integration/review_packet/test_html_renderer.py -v
```

Expected: the mismatch test FAILS because the current renderer trusts page-image metadata without comparing citation page geometry.

- [ ] **Step 4: Add the geometry cross-check to `_page_assets()`**

In `src/ansim_review/review_packet/html_renderer.py`, add:

```python
_GEOMETRY_TOLERANCE = 0.5


def _verify_page_geometry(
    citation: Mapping[str, object],
    page_asset: _PageAsset,
) -> None:
    width = _positive_number(citation.get("page_width"), "citation.page_width")
    height = _positive_number(citation.get("page_height"), "citation.page_height")
    if (
        abs(width - page_asset.pdf_width) > _GEOMETRY_TOLERANCE
        or abs(height - page_asset.pdf_height) > _GEOMETRY_TOLERANCE
    ):
        raise ValueError(
            "PAGE_RENDER_GEOMETRY_MISMATCH: "
            f"citation={width}x{height} "
            f"page_image={page_asset.pdf_width}x{page_asset.pdf_height}"
        )
```

Update `_page_assets()` so every citation is checked, while each image/metadata pair is still read once:

```python
identity = _citation_identity(citation)
if identity not in assets:
    revision_id, page_number, source_hash = identity
    page_asset = _verified_page_image(
        page_root,
        revision_id,
        page_number,
        source_hash,
    )
    _verify_page_geometry(citation, page_asset)
    assets[identity] = (f"page-{len(assets) + 1}", page_asset)
else:
    _, page_asset = assets[identity]
    _verify_page_geometry(citation, page_asset)
```

This second branch is required: two citations for the same page must not be allowed to carry inconsistent DB geometry just because the page asset is cached.

- [ ] **Step 5: Run renderer and builder suites**

Run:

```powershell
python -m pytest tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_html_renderer.py -v
python -m ruff check src/ansim_review/review_packet tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_html_renderer.py
python -m mypy src/ansim_review/review_packet
```

Expected: all PASS, including the pre-existing shared-page-once and bbox-bounds tests.

- [ ] **Step 6: Commit Task 6**

```powershell
git add src/ansim_review/review_packet/html_renderer.py tests/integration/review_packet/test_html_renderer.py
git commit -m "fix: verify review overlay page geometry"
```

---

### Task 7: Lock bbox and paper-size regression invariants

**Files:**
- Modify: `tests/unit/parsing/test_coordinate_normalization.py`
- Verify: all files changed in Tasks 1–6

**Interfaces:**
- Preserves: `normalize_bbox(raw_bbox, source_system, page_width, page_height, *, rotation=0) -> BBox`.
- Verifies: large valid coordinates are not rejected because of A4 assumptions.
- Verifies: existing `0.5 pt` bbox boundary tolerance remains unchanged.

- [ ] **Step 1: Add A3 landscape and half-point clamp regressions**

Append to `tests/unit/parsing/test_coordinate_normalization.py`:

```python
def test_pdf_bottom_left_a3_landscape_coordinates_are_preserved() -> None:
    assert normalize_bbox(
        (100.0, 100.0, 1100.0, 700.0),
        "PDF_BOTTOM_LEFT",
        1191.0,
        842.0,
    ) == BBox(100.0, 100.0, 1100.0, 700.0)


def test_bbox_boundary_tolerance_clamps_exactly_half_point() -> None:
    assert normalize_bbox(
        (-0.5, 0.0, 1191.5, 842.0),
        "PDF_BOTTOM_LEFT",
        1191.0,
        842.0,
    ) == BBox(0.0, 0.0, 1191.0, 842.0)
```

- [ ] **Step 2: Run the complete Issue #63 targeted suite**

Run:

```powershell
python -m pytest `
  tests/unit/parsing/test_pdf_page_geometry.py `
  tests/unit/parsing/test_odl_adapter.py `
  tests/unit/parsing/test_coordinate_normalization.py `
  tests/unit/parsing/test_source_batch_importer.py `
  tests/unit/review_packet/test_builder.py `
  tests/integration/review_packet/test_html_renderer.py `
  -v
```

Expected: all PASS.

- [ ] **Step 3: Verify the silent fallback cannot remain in production parsing code**

Run:

```powershell
git grep -n "_DEFAULT_PAGE_WIDTH\|_DEFAULT_PAGE_HEIGHT" -- src/ansim_review/parsing
git grep -n "595\.0.*842\.0\|595.*842" -- src/ansim_review/parsing
```

Expected: no matches. A4 values may remain in explicit tests/fixtures and print CSS, but not as production parser fallback constants.

- [ ] **Step 4: Run diff hygiene and targeted static checks**

Run:

```powershell
git diff --check
python -m ruff check src tests
python -m mypy src
```

Expected: all PASS.

- [ ] **Step 5: Commit Task 7**

```powershell
git add tests/unit/parsing/test_coordinate_normalization.py
git commit -m "test: lock page geometry regression invariants"
```

---

### Task 8: Full repository verification and handoff evidence

**Files:**
- No planned source changes.
- Verify the implementation branch exact HEAD after Tasks 1–7.

**Interfaces:**
- Produces validation evidence for Issue #63 and the PR.
- No empty verification commit; exact command outputs belong in the PR/Issue handoff comment.

- [ ] **Step 1: Run repository documentation validation**

Run the same command used by CI:

```powershell
evidence-review documentation validate --repository-root . --config documentation-integrity.json --output build/documentation-integrity-report.json
```

Expected: exit code 0. Record error/warning counts from the generated report.

- [ ] **Step 2: Run the full test suite**

```powershell
python -m pytest -v
```

Expected: exit code 0 with no new failures.

- [ ] **Step 3: Run static and bytecode validation**

```powershell
python -m ruff check src tests
python -m mypy src
python -m compileall -q src scripts web_runtime tests
git diff --check
```

Expected: all exit code 0.

- [ ] **Step 4: Build the wheel to verify the new parsing module is packaged normally**

```powershell
python -m pip install build
python -m build --wheel
```

Expected: wheel build succeeds. No `pyproject.toml` package-data change is required because `pdf_page_geometry.py` is a Python module discovered by setuptools package discovery.

- [ ] **Step 5: Re-run the exact Issue #63 acceptance subset at final HEAD**

```powershell
python -m pytest `
  tests/unit/parsing/test_pdf_page_geometry.py `
  tests/unit/parsing/test_odl_adapter.py `
  tests/unit/parsing/test_coordinate_normalization.py `
  tests/unit/parsing/test_source_batch_importer.py `
  tests/unit/review_packet/test_builder.py `
  tests/integration/review_packet/test_html_renderer.py `
  -v
```

Expected: all PASS at the same HEAD that will be reviewed.

- [ ] **Step 6: Prepare the PR/Issue #63 verification summary**

The handoff must state the exact final commit SHA and report these items explicitly:

```text
Issue #63 acceptance
- A4 silent fallback removed: PASS
- CropBox/MediaBox canonical geometry: PASS
- A3/landscape/custom-size bbox normalization: PASS
- parser/PDF dimensions mismatch detection: PASS
- parser/PDF page-count mismatch detection: PASS
- invalid parser dimensions fail closed: PASS
- PAGE_DIMENSIONS_UNAVAILABLE failure path: PASS
- evidence DB page geometry: PASS
- Review Workspace DB/page-image geometry cross-check: PASS
- targeted pytest: <exact result from command>
- full pytest: <exact result from command>
- documentation validation: <exact result from command>
- Ruff: PASS
- mypy: PASS
- compileall: PASS
- wheel build: PASS
- GitHub Actions: report actual observed state; do not label manual validation as Actions PASS
```

Do not close Issue #63 solely from code review. Close only after the implementation PR is merged and the final merged `main` HEAD is rechecked or the project’s established manual-acceptance policy explicitly permits closure from the verified PR HEAD.
