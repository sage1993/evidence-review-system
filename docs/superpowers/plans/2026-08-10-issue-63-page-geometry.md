# Issue #63 PDF Page Geometry Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the silent A4 `595 × 842` fallback and make verified source-PDF page geometry the single coordinate contract used by OpenDataLoader ingestion, evidence storage, citations, and Review Workspace overlays.

**Architecture:** Add a focused `pypdf` geometry resolver that returns canonical page-box dimensions, origin, and rotation. OpenDataLoader page dimensions become validation metadata rather than the canonical source; invalid or mismatched parser/PDF geometry fails closed before DB creation. Review Workspace citations receive canonical page dimensions from the DB and the renderer refuses overlays when verified page-image metadata diverges.

**Tech Stack:** Python 3.11+, `pypdf>=5,<6`, SQLite, pytest, Ruff, mypy, compileall.

## Global Constraints

- No new runtime dependency. `pypdf>=5,<6` already exists in `pyproject.toml`.
- No evidence DB schema migration and no bbox JSON format change.
- Canonical bbox remains `[left, bottom, right, top]` in PDF points.
- Canonical page size is the **unrotated** effective page-box width/height; `/Rotate` never swaps stored width/height.
- Effective box priority: valid CropBox, then valid MediaBox.
- Box size is `urx - llx` and `ury - lly`; non-zero lower-left origins must not inflate size.
- Normalize integer multiples of 90 with `% 360`; reject every non-multiple of 90 as `PAGE_ROTATION_INVALID`.
- Parser/PDF size tolerance is exactly `0.5 pt` independently for width and height.
- No heuristic scaling, paper-size inference, or warning-only continuation on geometry mismatch.
- Geometry failure must happen before `EvidenceStore(output, create=True)` so a failed import leaves no output DB.
- Existing `@page { size: A4; }` print CSS remains unchanged because it controls print layout, not source geometry.
- Stable parser element IDs and existing valid bbox golden coordinates must remain unchanged.
- Before Task 1, invoke `superpowers:using-git-worktrees` and create an isolated worktree from the branch containing this approved plan.

---

## File Map

### Create

- `src/ansim_review/parsing/pdf_page_geometry.py` — canonical source-PDF page geometry resolver.
- `tests/helpers/pdf_fixtures.py` — deterministic valid PDF fixture writer.
- `tests/unit/parsing/test_pdf_page_geometry.py` — resolver contract tests.

### Modify

- `src/ansim_review/parsing/odl_source.py` — remove A4 constants; classify parser dimensions as `ABSENT`, `VALID`, `INVALID`.
- `src/ansim_review/parsing/odl_adapter.py` — compare parser page count/dimensions with PDF geometry and normalize bbox using the PDF values.
- `src/ansim_review/review_packet/builder.py` — resolve `page_width`/`page_height` from `pages`.
- `src/ansim_review/review_packet/html_renderer.py` — DB/page-image geometry cross-check.
- `tests/unit/parsing/test_odl_adapter.py`
- `tests/unit/parsing/test_coordinate_normalization.py`
- `tests/unit/parsing/test_source_batch_importer.py`
- `tests/unit/review_packet/test_builder.py`
- `tests/integration/review_packet/test_html_renderer.py`

### Explicitly unchanged

- `src/ansim_review/evidence/schema.sql`
- `pyproject.toml`
- print CSS A4 page size
- bbox storage representation

The page-image producer is not part of the planned edit set. Task 6 verifies the current metadata contract from the consumer side. If the full suite proves that a producer emits display-swapped or otherwise noncanonical `pdf_width`/`pdf_height`, stop execution and amend the approved design/plan before changing that producer.

---

### Task 1: Add valid PDF fixtures and the canonical PDF geometry resolver

**Files:**
- Create: `tests/helpers/pdf_fixtures.py`
- Create: `tests/unit/parsing/test_pdf_page_geometry.py`
- Create: `src/ansim_review/parsing/pdf_page_geometry.py`

**Interfaces:**
- Produces `PdfPageGeometry(page_number, width, height, box_kind, origin_x, origin_y, rotation)`.
- Produces `read_pdf_page_geometries(source_path: Path) -> tuple[PdfPageGeometry, ...]`.
- Produces `write_pdf_fixture(path, *, page_sizes, crop_boxes=None, rotations=None) -> Path` for tests.
- Raises `ValueError` containing `PAGE_DIMENSIONS_UNAVAILABLE` or `PAGE_ROTATION_INVALID` on fail-closed paths.

- [ ] **Step 1: Create the valid PDF fixture writer**

Create `tests/helpers/pdf_fixtures.py`:

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
    crops = crop_boxes or {}
    page_rotations = rotations or {}
    for page_number, (width, height) in enumerate(page_sizes, start=1):
        page = writer.add_blank_page(width=width, height=height)
        crop = crops.get(page_number)
        if crop is not None:
            page.cropbox = RectangleObject(crop)
        rotation = page_rotations.get(page_number)
        if rotation is not None:
            page[NameObject("/Rotate")] = NumberObject(rotation)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        writer.write(stream)
    return path
```

- [ ] **Step 2: Write failing resolver tests**

Create `tests/unit/parsing/test_pdf_page_geometry.py`:

```python
from pathlib import Path

import pytest

from ansim_review.parsing.pdf_page_geometry import read_pdf_page_geometries
from tests.helpers.pdf_fixtures import write_pdf_fixture


def test_cropbox_uses_size_difference_and_preserves_origin(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "crop.pdf",
        page_sizes=((600.0, 800.0),),
        crop_boxes={1: (10.0, 20.0, 510.0, 720.0)},
    )
    page = read_pdf_page_geometries(source)[0]
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


def test_invalid_cropbox_falls_back_to_mediabox(tmp_path: Path) -> None:
    source = write_pdf_fixture(
        tmp_path / "invalid-crop.pdf",
        page_sizes=((1000.0, 700.0),),
        crop_boxes={1: (0.0, 0.0, 0.0, 0.0)},
    )
    page = read_pdf_page_geometries(source)[0]
    assert page.box_kind == "MEDIA_BOX"
    assert (page.width, page.height) == (1000.0, 700.0)


def test_mixed_sizes_and_negative_rotation_are_normalized(tmp_path: Path) -> None:
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


def test_unreadable_pdf_has_explicit_reason(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"not-a-pdf")
    with pytest.raises(ValueError, match="PAGE_DIMENSIONS_UNAVAILABLE"):
        read_pdf_page_geometries(source)
```

- [ ] **Step 3: Run the tests and confirm RED**

```powershell
python -m pytest tests/unit/parsing/test_pdf_page_geometry.py -v
```

Expected: collection fails with `ModuleNotFoundError: ansim_review.parsing.pdf_page_geometry`.

- [ ] **Step 4: Implement the resolver**

Create `src/ansim_review/parsing/pdf_page_geometry.py`:

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

The `/CropBox` presence test is required because pypdf's `page.cropbox` accessor itself falls back to MediaBox.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
python -m pytest tests/unit/parsing/test_pdf_page_geometry.py -v
python -m ruff check src/ansim_review/parsing/pdf_page_geometry.py tests/helpers/pdf_fixtures.py tests/unit/parsing/test_pdf_page_geometry.py
python -m mypy src/ansim_review/parsing/pdf_page_geometry.py
git add src/ansim_review/parsing/pdf_page_geometry.py tests/helpers/pdf_fixtures.py tests/unit/parsing/test_pdf_page_geometry.py
git commit -m "feat: resolve canonical PDF page geometry"
```

Expected: tests/static checks PASS before the commit.

---

### Task 2: Remove A4 fallback and classify parser dimensions

**Files:**
- Modify: `src/ansim_review/parsing/odl_source.py`
- Modify: `tests/unit/parsing/test_odl_adapter.py`

**Interfaces:**
- Produces `ParserDimensionState = Literal["ABSENT", "VALID", "INVALID"]`.
- Produces `ParserPageDimensionsResult(state, width, height)`.
- Changes `parser_page_dimensions(payload, page_number) -> ParserPageDimensionsResult`.
- Preserves `parser_bbox(element, width, height) -> list[float] | None`.

- [ ] **Step 1: Add failing state tests**

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
def test_invalid_parser_dimensions_are_not_missing(
    width: object,
    height: object,
) -> None:
    payload = {"pages": [{"page_number": 1, "width": width, "height": height}]}
    assert parser_page_dimensions(payload, 1).state == "INVALID"


def test_partial_parser_dimensions_are_invalid() -> None:
    payload = {"pages": [{"page_number": 1, "width": 1000.0}]}
    assert parser_page_dimensions(payload, 1).state == "INVALID"
```

- [ ] **Step 2: Run and confirm RED**

```powershell
python -m pytest tests/unit/parsing/test_odl_adapter.py -v
```

Expected: import/expectation failures because the result type does not exist and the current implementation returns an A4 tuple.

- [ ] **Step 3: Implement the state result and delete A4 constants**

In `src/ansim_review/parsing/odl_source.py`, replace the runtime `RawElement` import with `TYPE_CHECKING`, import `isfinite`, and replace `parser_page_dimensions()`:

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

Delete `_DEFAULT_PAGE_WIDTH` and `_DEFAULT_PAGE_HEIGHT`. Keep `from __future__ import annotations` so `RawElement` remains valid in annotations.

- [ ] **Step 4: Verify GREEN, verify no fallback constants, and commit**

```powershell
python -m pytest tests/unit/parsing/test_odl_adapter.py -v
git grep -n "_DEFAULT_PAGE_WIDTH\|_DEFAULT_PAGE_HEIGHT" -- src/ansim_review/parsing
python -m ruff check src/ansim_review/parsing/odl_source.py tests/unit/parsing/test_odl_adapter.py
git add src/ansim_review/parsing/odl_source.py tests/unit/parsing/test_odl_adapter.py
git commit -m "fix: remove silent A4 parser fallback"
```

Expected: pytest/Ruff PASS; both `git grep` patterns return no matches.

---

### Task 3: Reconcile OpenDataLoader page geometry with the source PDF

**Files:**
- Modify: `src/ansim_review/parsing/odl_adapter.py`
- Modify: `tests/unit/parsing/test_odl_adapter.py`

**Interfaces:**
- Consumes `read_pdf_page_geometries()` from Task 1.
- Consumes `parser_page_dimensions()` from Task 2.
- Produces `_reconcile_page_dimensions(payload: Mapping[str, Any], page_count: int, pdf_pages: tuple[PdfPageGeometry, ...]) -> tuple[PageDimensions, ...]`.
- Raises `PARSER_PDF_PAGE_COUNT_MISMATCH`, `PARSER_PAGE_DIMENSIONS_INVALID`, or `PARSER_PDF_PAGE_DIMENSIONS_MISMATCH`.

- [ ] **Step 1: Add parser/PDF integration helpers and failing tests**

Extend `tests/unit/parsing/test_odl_adapter.py`:

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
            {"page_number": 1, "width": dimensions[0], "height": dimensions[1]}
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _parse(source: Path, parser: Path):
    return OpenDataLoaderJsonAdapter().parse(
        ParserContext(source_path=source, parser_artifact_path=parser, options={})
    )


@pytest.mark.parametrize(
    "page_size",
    [
        (595.0, 842.0),
        (842.0, 1191.0),
        (1191.0, 842.0),
        (1000.0, 700.0),
    ],
)
def test_missing_parser_dimensions_follow_source_pdf(
    tmp_path: Path,
    page_size: tuple[float, float],
) -> None:
    source = write_pdf_fixture(tmp_path / "source.pdf", page_sizes=(page_size,))
    parser = _write_parser(
        tmp_path / "source.json",
        file_name=source.name,
        page_count=1,
        bbox=(10.0, 20.0, 100.0, 40.0),
    )
    contribution = _parse(source, parser)
    assert (contribution.page_dimensions[0].width, contribution.page_dimensions[0].height) == page_size


def test_a3_landscape_bbox_is_not_rejected_by_a4_bounds(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "drawing.pdf", page_sizes=((1191.0, 842.0),))
    parser = _write_parser(
        tmp_path / "drawing.json",
        file_name=source.name,
        page_count=1,
        bbox=(100.0, 100.0, 1100.0, 700.0),
    )
    contribution = _parse(source, parser)
    assert contribution.elements[0].bbox == (100.0, 100.0, 1100.0, 700.0)


def test_parser_dimensions_within_half_point_use_pdf_values(tmp_path: Path) -> None:
    source = write_pdf_fixture(tmp_path / "custom.pdf", page_sizes=((1000.0, 700.0),))
    parser = _write_parser(
        tmp_path / "custom.json",
        file_name=source.name,
        page_count=1,
        bbox=(10.0, 20.0, 100.0, 40.0),
        dimensions=(999.6, 700.4),
    )
    contribution = _parse(source, parser)
    assert (contribution.page_dimensions[0].width, contribution.page_dimensions[0].height) == (1000.0, 700.0)


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


def test_invalid_parser_dimension_is_rejected(tmp_path: Path) -> None:
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

- [ ] **Step 2: Run and confirm RED**

```powershell
python -m pytest tests/unit/parsing/test_odl_adapter.py -v
```

Expected: new parse-path tests fail because the adapter still expects `(width, height)` from parser metadata and does not read the PDF.

- [ ] **Step 3: Implement deterministic reconciliation**

In `src/ansim_review/parsing/odl_adapter.py`, remove the function-local `odl_source` import block and add module imports plus the helper:

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
            PageDimensions(pdf_page.page_number, pdf_page.width, pdf_page.height)
        )
    return tuple(dimensions)
```

Replace the old dimensions tuple comprehension in `parse()`:

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

Keep filename binding before `read_pdf_page_geometries()` so `PARSER_SOURCE_MISMATCH` remains deterministic.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
python -m pytest tests/unit/parsing/test_odl_adapter.py tests/unit/parsing/test_coordinate_normalization.py tests/unit/parsing/test_pdf_page_geometry.py -v
python -m ruff check src/ansim_review/parsing tests/unit/parsing/test_odl_adapter.py
python -m mypy src/ansim_review/parsing
git add src/ansim_review/parsing/odl_adapter.py tests/unit/parsing/test_odl_adapter.py
git commit -m "fix: reconcile parser geometry with source PDF"
```

Expected: all tests/static checks PASS.

---

### Task 4: Verify source-batch DB geometry and failure atomicity

**Files:**
- Modify: `tests/unit/parsing/test_source_batch_importer.py`

**Interfaces:**
- Consumes the Task 3 adapter through `import_source_batch()`.
- Verifies `pages.width`/`pages.height` equal canonical PDF geometry.
- Verifies geometry failures leave no output DB.

- [ ] **Step 1: Replace the ingest-path fake PDF with a valid custom-size PDF**

Add:

```python
from tests.helpers.pdf_fixtures import write_pdf_fixture
```

In `test_arbitrary_pdf_and_parser_create_searchable_evidence_database`, replace synthetic PDF bytes with:

```python
write_pdf_fixture(source, page_sizes=((1000.0, 700.0),))
```

Extend the query/assertions:

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

- [ ] **Step 2: Add mismatch/unreadable failure-atomicity tests**

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

Prepare/hash/dedup-only tests keep arbitrary bytes because they intentionally do not parse geometry.

- [ ] **Step 3: Verify and commit**

```powershell
python -m pytest tests/unit/parsing/test_source_batch_importer.py -v
git add tests/unit/parsing/test_source_batch_importer.py
git commit -m "test: verify canonical geometry during source import"
```

Expected: PASS.

---

### Task 5: Add canonical page dimensions to resolved citations

**Files:**
- Modify: `src/ansim_review/review_packet/builder.py`
- Modify: `tests/unit/review_packet/test_builder.py`

**Interfaces:**
- Produces citation fields `page_width: float` and `page_height: float`.
- Source is `pages`, joined with `retrieval_records.page_id = pages.id`.
- These fields are DB-resolved metadata and remain outside `_citation_identity()`.

- [ ] **Step 1: Add failing builder assertions**

In `test_view_model_resolves_all_required_sections_and_blank_decision`:

```python
assert citation["page_width"] == 120.0
assert citation["page_height"] == 200.0
```

- [ ] **Step 2: Run and confirm RED**

```powershell
python -m pytest tests/unit/review_packet/test_builder.py::test_view_model_resolves_all_required_sections_and_blank_decision -v
```

Expected: missing-key failure.

- [ ] **Step 3: Join `pages` in `_resolve_citation()`**

Use:

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

Return:

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

Do not add `page_width`/`page_height` to `_citation_identity()`; packet identity verification remains unchanged.

- [ ] **Step 4: Verify and commit**

```powershell
python -m pytest tests/unit/review_packet/test_builder.py -v
python -m ruff check src/ansim_review/review_packet/builder.py tests/unit/review_packet/test_builder.py
python -m mypy src/ansim_review/review_packet/builder.py
git add src/ansim_review/review_packet/builder.py tests/unit/review_packet/test_builder.py
git commit -m "feat: attach canonical page geometry to citations"
```

Expected: all PASS.

---

### Task 6: Cross-check DB geometry against verified page-image metadata

**Files:**
- Modify: `src/ansim_review/review_packet/html_renderer.py`
- Modify: `tests/integration/review_packet/test_html_renderer.py`

**Interfaces:**
- Consumes citation `page_width`/`page_height` from Task 5.
- Consumes `_PageAsset.pdf_width`/`pdf_height` from verified metadata.
- Produces `_verify_page_geometry(citation, page_asset) -> None`.
- Raises `PAGE_RENDER_GEOMETRY_MISMATCH` beyond `0.5 pt`.

- [ ] **Step 1: Update renderer fixtures to include citation geometry and parameterized page-image geometry**

Add to the citation in `_model()`:

```python
"page_width": 120.0,
"page_height": 200.0,
```

Replace `_write_page_assets()` with the complete function:

```python
def _write_page_assets(
    root: Path,
    *,
    pdf_width: float = 120.0,
    pdf_height: float = 200.0,
) -> bytes:
    images = root / "REV1"
    images.mkdir(parents=True)
    page = images / "page-0003.png"
    page_bytes = b"\x89PNG\r\n\x1a\nverified-fixture"
    page.write_bytes(page_bytes)
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
    (images / "page-0003.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    return page_bytes
```

- [ ] **Step 2: Add failing mismatch and large-page tests**

```python
def test_page_image_geometry_mismatch_is_rejected(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages", pdf_width=121.0, pdf_height=200.0)
    with pytest.raises(ValueError, match="PAGE_RENDER_GEOMETRY_MISMATCH"):
        render_review_html(_model(), tmp_path / "pages")


def test_a3_landscape_overlay_uses_canonical_geometry(tmp_path: Path) -> None:
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


def test_cached_page_rejects_inconsistent_second_citation_geometry(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    model = _model()
    claims = model["claims"]
    assert isinstance(claims, list)
    first_claim = claims[0]
    assert isinstance(first_claim, dict)
    first_citation = first_claim["citations"][0]
    second_claim = dict(first_claim)
    second_claim["claim_id"] = "C2"
    second_claim["citations"] = [
        {
            **first_citation,
            "citation_id": "CIT-E2",
            "evidence_id": "E2",
            "page_width": 130.0,
        }
    ]
    model["claims"] = [first_claim, second_claim]

    with pytest.raises(ValueError, match="PAGE_RENDER_GEOMETRY_MISMATCH"):
        render_review_html(model, tmp_path / "pages")
```

- [ ] **Step 3: Run and confirm RED**

```powershell
python -m pytest tests/integration/review_packet/test_html_renderer.py -v
```

Expected: mismatch tests fail because the renderer currently trusts page-image metadata.

- [ ] **Step 4: Implement the cross-check and preserve one-read-per-page caching**

In `src/ansim_review/review_packet/html_renderer.py`:

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

Replace the body of the citation loop in `_page_assets()` with:

```python
citation = _mapping(citation_value, "citation")
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

Every citation is checked; page image bytes/metadata remain loaded once per identity.

- [ ] **Step 5: Verify and commit**

```powershell
python -m pytest tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_html_renderer.py -v
python -m ruff check src/ansim_review/review_packet tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_html_renderer.py
python -m mypy src/ansim_review/review_packet
git add src/ansim_review/review_packet/html_renderer.py tests/integration/review_packet/test_html_renderer.py
git commit -m "fix: verify review overlay page geometry"
```

Expected: all PASS, including existing shared-page, bbox-bounds, offline, and print tests.

---

### Task 7: Lock coordinate and paper-size regression invariants

**Files:**
- Modify: `tests/unit/parsing/test_coordinate_normalization.py`

**Interfaces:**
- Preserves `normalize_bbox(...) -> BBox`.
- Verifies large valid coordinates are not subjected to A4 assumptions.
- Verifies the existing bbox boundary tolerance remains exactly `0.5 pt`.

- [ ] **Step 1: Add regression tests**

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

- [ ] **Step 3: Verify no production A4 fallback remains**

```powershell
git grep -n "_DEFAULT_PAGE_WIDTH\|_DEFAULT_PAGE_HEIGHT" -- src/ansim_review/parsing
git grep -n "595\.0.*842\.0\|595.*842" -- src/ansim_review/parsing
```

Expected: no matches. A4 values may remain only in explicit tests/fixtures and print CSS.

- [ ] **Step 4: Run diff/static checks and commit**

```powershell
git diff --check
python -m ruff check src tests
python -m mypy src
git add tests/unit/parsing/test_coordinate_normalization.py
git commit -m "test: lock page geometry regression invariants"
```

Expected: all checks PASS before commit.

---

### Task 8: Full repository verification and handoff

**Files:**
- No planned source changes.
- Verify the exact final implementation HEAD after Tasks 1–7.

**Interfaces:**
- Produces validation evidence for the PR and Issue #63.
- Do not create an empty verification commit.

- [ ] **Step 1: Run repository documentation validation**

```powershell
evidence-review documentation validate --repository-root . --config documentation-integrity.json --output build/documentation-integrity-report.json
```

Expected: exit code 0. Record the report's exact error and warning counts.

- [ ] **Step 2: Run full tests**

```powershell
python -m pytest -v
```

Expected: exit code 0 and no new failures.

- [ ] **Step 3: Run repository static/bytecode checks**

```powershell
python -m ruff check src tests
python -m mypy src
python -m compileall -q src scripts web_runtime tests
git diff --check
```

Expected: all exit code 0.

- [ ] **Step 4: Build the wheel**

```powershell
python -m pip install build
python -m build --wheel
```

Expected: wheel build succeeds. No `pyproject.toml` package-data change is required because the new resolver is a Python module under an already discovered package.

- [ ] **Step 5: Re-run the exact Issue #63 subset at final HEAD**

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

Expected: all PASS at the same SHA proposed for review.

- [ ] **Step 6: Publish the verification summary with exact observed results**

The PR/Issue handoff must explicitly report:

- final commit SHA;
- A4 silent fallback removal result;
- CropBox/MediaBox canonical geometry result;
- A4, A3 portrait, A3 landscape, and custom-size parser-dimensions-missing results;
- A3 landscape bbox result;
- parser/PDF dimensions mismatch result;
- parser/PDF page-count mismatch result;
- invalid parser dimension result;
- `PAGE_DIMENSIONS_UNAVAILABLE` failure-path result;
- evidence DB page geometry result;
- Review Workspace DB/page-image cross-check result;
- exact targeted pytest summary;
- exact full pytest summary;
- exact documentation validation error/warning counts;
- Ruff, mypy, compileall, and wheel-build results;
- actual GitHub Actions state. Manual validation must never be labeled as an Actions PASS.

Do not close Issue #63 solely because the branch tests pass. Close it after the implementation PR is merged and the merged `main` HEAD is rechecked, or when the repository's established manual-acceptance policy explicitly permits closure from the verified PR HEAD.
