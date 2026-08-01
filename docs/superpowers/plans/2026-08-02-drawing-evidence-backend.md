# Drawing Evidence Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a contract-first backend that stores drawing sources immutably, records extractor or reviewer-created evidence, persists append-only confirmations, and binds only hash-verified confirmed inputs to deterministic engines.

**Architecture:** Reuse the M0 drawing, attachment, workflow, and canonical JSON contracts. Add small parsing services for case manifests, intake, quality, candidates, confirmations, confirmed inputs, binding, and workflow projection; each service performs deterministic validation and create-only persistence without introducing OCR or automatic boundary recognition.

**Tech Stack:** Python 3.11+, standard library only, dataclasses, pathlib, hashlib, json, pytest, ruff, mypy.

## Global Constraints

- Branch: `agent/m1-drawing-evidence-backend`.
- No OpenAI API, external model API, network access, OCR dependency, PDF dependency, or image dependency.
- Reuse `ansim_review.contracts.drawing`, `ansim_review.contracts.attachments`, and `ansim_review.contracts.workflow`; do not duplicate their enums.
- Default intake policy: 262,144,000 bytes per file, 200 PDF pages, 150,000,000 pixels per image, 500,000,000 image pixels per case.
- Supported signatures: PDF, PNG, TIFF, JPEG; `.tiff` and `.jpeg` normalize to `.tif` and `.jpg`.
- Reject directories, symlinks, Windows reparse points, path escapes, extension/MIME mismatches, unsupported signatures, and overwrite attempts.
- `METADATA_ONLY` physical-size trust cannot produce quality `PASS`.
- Candidate IDs cannot depend on timestamps, arrival order, or filesystem enumeration order.
- Candidate and confirmation files are create-only and immutable.
- Only `ACCEPTED`, `EDITED`, or `CREATED` candidates may produce confirmed inputs.
- Workflow reason codes appear only on `BLOCKED` or `FAILED`, as required by M0.
- All JSON output uses `ansim_review.canonical_json.dumps`, `dump_bytes`, or `sha256_json`.

---

## File Structure

### New production files

- `schemas/case-manifest.schema.json` — versioned JSON Schema for deterministic case indexes.
- `src/ansim_review/parsing/drawing_case.py` — identifier validation, case paths, case-manifest codec, create-only canonical JSON writes.
- `src/ansim_review/parsing/drawing_source.py` — intake policy, signature detection, safe streaming copy, immutable attachment creation.
- `src/ansim_review/parsing/drawing_quality.py` — trusted metadata result and quality assessment.
- `src/ansim_review/parsing/drawing_candidates.py` — stable candidate IDs, neutral parser conversion, manual candidate creation, candidate persistence.
- `src/ansim_review/parsing/drawing_confirmation.py` — append-only confirmation validation, persistence, and hash verification.
- `src/ansim_review/parsing/drawing_inputs.py` — confirmed-input construction, set-level conflict detection, canonical document persistence.
- `src/ansim_review/parsing/drawing_binding.py` — source/confirmation revalidation and deterministic engine-input mapping.
- `src/ansim_review/parsing/drawing_workflow.py` — M0-compliant workflow projection.

### New tests

- `tests/unit/parsing/test_drawing_case.py`
- `tests/unit/parsing/test_drawing_source.py`
- `tests/unit/parsing/test_drawing_quality.py`
- `tests/unit/parsing/test_drawing_candidates.py`
- `tests/unit/parsing/test_drawing_confirmation.py`
- `tests/unit/parsing/test_drawing_inputs.py`
- `tests/unit/parsing/test_drawing_binding.py`
- `tests/unit/parsing/test_drawing_workflow.py`
- `tests/integration/drawing/test_manual_annotation_flow.py`
- `tests/integration/drawing/test_drawing_tamper_detection.py`
- `tests/golden/drawing/manual-confirmed-inputs.json`

### Existing files to consume without changing their public enums

- `src/ansim_review/contracts/drawing.py`
- `src/ansim_review/contracts/attachments.py`
- `src/ansim_review/contracts/workflow.py`
- `src/ansim_review/canonical_json.py`
- `src/ansim_review/parsing/source_manifest.py`
- `src/ansim_review/parsing/odl_adapter.py`

---

### Task 1: Case workspace, identifiers, and manifest contract

**Files:**
- Create: `schemas/case-manifest.schema.json`
- Create: `src/ansim_review/parsing/drawing_case.py`
- Create: `tests/unit/parsing/test_drawing_case.py`

**Interfaces:**
- Consumes: `ImmutableAttachment`, `DrawingQualityAssessment`, canonical JSON utilities.
- Produces:
  - `validate_artifact_id(value: str, field: str) -> str`
  - `case_root(cases_root: Path, case_id: str) -> Path`
  - `case_artifact_path(case_dir: Path, relative_path: str) -> Path`
  - `write_canonical_create_only(path: Path, document: object) -> str`
  - `CaseManifestEntry`
  - `CaseManifest`
  - `case_manifest_document(manifest: CaseManifest) -> dict[str, object]`
  - `decode_case_manifest(value: object) -> CaseManifest`

- [ ] **Step 1: Write failing identifier and path tests**

```python
from pathlib import Path

import pytest

from ansim_review.parsing.drawing_case import (
    case_artifact_path,
    case_root,
    validate_artifact_id,
)


def test_artifact_ids_accept_ascii_safe_tokens() -> None:
    assert validate_artifact_id("CASE-001_A", "case_id") == "CASE-001_A"


@pytest.mark.parametrize("value", ["", "../CASE", "C:/CASE", "한글", "A" * 129])
def test_artifact_ids_reject_unsafe_tokens(value: str) -> None:
    with pytest.raises(ValueError):
        validate_artifact_id(value, "case_id")


def test_case_artifact_path_rejects_escape(tmp_path: Path) -> None:
    root = case_root(tmp_path, "CASE-001")
    with pytest.raises(ValueError, match="safe relative path"):
        case_artifact_path(root, "../outside.json")
```

- [ ] **Step 2: Run the focused tests and observe RED**

Run: `pytest tests/unit/parsing/test_drawing_case.py -v`

Expected: collection error because `ansim_review.parsing.drawing_case` does not exist.

- [ ] **Step 3: Implement identifier and path primitives**

```python
_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def validate_artifact_id(value: str, field: str) -> str:
    if not _ID_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be an ASCII artifact identifier")
    return value


def case_root(cases_root: Path, case_id: str) -> Path:
    validate_artifact_id(case_id, "case_id")
    return cases_root.resolve() / case_id


def case_artifact_path(case_dir: Path, relative_path: str) -> Path:
    if "\\" in relative_path:
        raise ValueError("artifact path must be a safe relative path")
    parsed = PurePosixPath(relative_path)
    if parsed.is_absolute() or not parsed.parts or ".." in parsed.parts:
        raise ValueError("artifact path must be a safe relative path")
    target = case_dir.joinpath(*parsed.parts)
    if not target.resolve(strict=False).is_relative_to(case_dir.resolve()):
        raise ValueError("artifact path must stay inside the case root")
    return target
```

- [ ] **Step 4: Add create-only canonical write tests**

```python
def test_write_canonical_create_only_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    digest = write_canonical_create_only(path, {"b": 2, "a": 1})
    assert path.read_text(encoding="utf-8") == '{"a":1,"b":2}'
    assert len(digest) == 64
    with pytest.raises(FileExistsError):
        write_canonical_create_only(path, {"a": 1})
```

- [ ] **Step 5: Implement create-only canonical writes**

```python
def write_canonical_create_only(path: Path, document: object) -> str:
    payload = dump_bytes(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 6: Add manifest codec tests**

```python
def test_case_manifest_round_trips_explicit_empty_collections() -> None:
    manifest = CaseManifest(
        format="ansim/case-manifest",
        version=1,
        case_id="CASE-001",
        policy_id="DRAWING-INTAKE-1",
        sources=(),
        quality_assessments=(),
        candidates=(),
        confirmations=(),
        confirmed_inputs_path=None,
        confirmed_inputs_sha256=None,
    )
    document = case_manifest_document(manifest)
    assert decode_case_manifest(document) == manifest
    assert document["sources"] == []
```

- [ ] **Step 7: Implement manifest dataclasses, codec, and schema**

The manifest entry indexes immutable artifacts without embedding their complete payload:

```python
@dataclass(frozen=True, slots=True)
class CaseManifestEntry:
    artifact_id: str
    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class CaseManifest:
    format: Literal["ansim/case-manifest"]
    version: Literal[1]
    case_id: str
    policy_id: str
    sources: tuple[CaseManifestEntry, ...]
    quality_assessments: tuple[CaseManifestEntry, ...]
    candidates: tuple[CaseManifestEntry, ...]
    confirmations: tuple[CaseManifestEntry, ...]
    confirmed_inputs_path: str | None
    confirmed_inputs_sha256: str | None
```

`schemas/case-manifest.schema.json` must use JSON Schema Draft 2020-12, require every field, reject unknown fields, constrain hashes to lowercase 64-character hexadecimal strings, and constrain relative paths to forward-slash paths without `..`.

- [ ] **Step 8: Run focused tests and schema-document regression**

Run: `pytest tests/unit/parsing/test_drawing_case.py tests/unit/contracts/test_schema_documents.py -v`

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add schemas/case-manifest.schema.json src/ansim_review/parsing/drawing_case.py tests/unit/parsing/test_drawing_case.py
git commit -m "feat: define drawing case workspace"
```

---

### Task 2: Immutable drawing source intake

**Files:**
- Create: `src/ansim_review/parsing/drawing_source.py`
- Create: `tests/unit/parsing/test_drawing_source.py`

**Interfaces:**
- Consumes: `validate_artifact_id`, `case_artifact_path`, `ImmutableAttachment`, `sha256_file`.
- Produces:
  - `DrawingIntakePolicy`
  - `TrustedSourceMetadata`
  - `sniff_drawing_mime(header: bytes) -> tuple[str, str]`
  - `validate_source_path(path: Path) -> None`
  - `ingest_drawing_source(source_path: Path, case_dir: Path, attachment_id: str, role: AttachmentRole, policy: DrawingIntakePolicy) -> ImmutableAttachment`
  - `verify_immutable_attachment(case_dir: Path, attachment: ImmutableAttachment) -> tuple[str, ...]`

- [ ] **Step 1: Write failing MIME and policy tests**

```python
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
```

- [ ] **Step 2: Run tests and observe RED**

Run: `pytest tests/unit/parsing/test_drawing_source.py -v`

Expected: import failure for `drawing_source`.

- [ ] **Step 3: Implement policy and signature detection**

```python
@dataclass(frozen=True, slots=True)
class DrawingIntakePolicy:
    policy_id: str = "DRAWING-INTAKE-1"
    max_file_bytes: int = 262_144_000
    max_pdf_pages: int = 200
    max_image_pixels: int = 150_000_000
    max_case_image_pixels: int = 500_000_000
```

`sniff_drawing_mime` must inspect only known signatures and return canonical MIME and extension.

- [ ] **Step 4: Add source path, extension, and byte-limit tests**

```python
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
    with pytest.raises(ValueError, match="FILE_SIZE_LIMIT_EXCEEDED"):
        ingest_drawing_source(
            source,
            tmp_path / "case",
            "ATT-001",
            "CASE_DRAWING",
            DrawingIntakePolicy(max_file_bytes=16),
        )
    assert not list((tmp_path / "case").rglob("*.tmp"))
```

- [ ] **Step 5: Implement source-path rejection and streaming intake**

Implementation requirements:

```python
def validate_source_path(path: Path) -> None:
    stat_result = path.lstat()
    if stat.S_ISLNK(stat_result.st_mode) or not stat.S_ISREG(stat_result.st_mode):
        raise ValueError("source must be a regular non-link file")
    if os.name == "nt" and getattr(stat_result, "st_file_attributes", 0) & 0x400:
        raise ValueError("source cannot be a Windows reparse point")
```

Stream in 1 MiB chunks to `case_dir/.intake/<attachment_id>.tmp`, enforce the byte limit during the copy, sniff copied bytes, normalize extension aliases, publish to `sources/drawings/<attachment_id><canonical_extension>` with create-only mode, and return:

```python
ImmutableAttachment(
    attachment_id=attachment_id,
    original_name=source_path.name,
    stored_path=f"inputs/original/{attachment_id}{canonical_extension}",
    sha256=source_hash,
    byte_size=byte_size,
    mime=mime,
    role=role,
)
```

The contract path remains `inputs/original/...`; `drawing_source.py` maps it deterministically to physical `sources/drawings/...` within the case directory through a private helper.

- [ ] **Step 6: Add success, overwrite, and tamper tests**

```python
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
    source.write_bytes(b"changed")
    assert stored.read_bytes() == payload
    with pytest.raises(FileExistsError):
        ingest_drawing_source(
            source, case_dir, "ATT-001", "CASE_DRAWING", DrawingIntakePolicy()
        )


def test_verify_attachment_reports_hash_tampering(tmp_path: Path) -> None:
    # ingest, change immutable test file, verify deterministic error code
    assert verify_immutable_attachment(case_dir, attachment) == (
        "SOURCE_HASH_MISMATCH",
        "SOURCE_SIZE_MISMATCH",
    )
```

- [ ] **Step 7: Run Task 2 tests**

Run: `pytest tests/unit/parsing/test_drawing_source.py -v`

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/ansim_review/parsing/drawing_source.py tests/unit/parsing/test_drawing_source.py
git commit -m "feat: ingest immutable drawing sources"
```

---

### Task 3: Trusted metadata and drawing quality gate

**Files:**
- Create: `src/ansim_review/parsing/drawing_quality.py`
- Create: `tests/unit/parsing/test_drawing_quality.py`

**Interfaces:**
- Consumes: `DrawingIntakePolicy`, `ImmutableAttachment`, `DrawingQualityAssessment`.
- Produces:
  - `ParserOutcome = Literal["SUCCESS", "TIMEOUT", "MEMORY_LIMIT", "INVALID_OUTPUT", "UNAVAILABLE"]`
  - `TrustedSourceMetadata`
  - `DrawingQualityResult`
  - `assess_drawing_quality(attachment: ImmutableAttachment, metadata: TrustedSourceMetadata, policy: DrawingIntakePolicy, existing_case_image_pixels: int = 0) -> DrawingQualityResult`
  - `workflow_reason_for_quality(result: DrawingQualityResult) -> ReasonCode | None`

- [ ] **Step 1: Write failing trust and policy tests**

```python
def test_metadata_only_cannot_pass() -> None:
    result = assess_drawing_quality(
        png_attachment(),
        TrustedSourceMetadata(
            source_sha256=png_attachment().sha256,
            adapter="fixture",
            adapter_version="1",
            parser_outcome="SUCCESS",
            page_count=None,
            width=4000,
            height=3000,
            physical_size_trust="METADATA_ONLY",
            lossy_or_screen_capture=False,
        ),
        DrawingIntakePolicy(),
    )
    assert result.assessment.quality == "REVIEW_REQUIRED"
    assert "METADATA_ONLY_PHYSICAL_SIZE" in result.detailed_reasons


def test_pdf_page_limit_rejects_source() -> None:
    result = assess_drawing_quality(
        pdf_attachment(),
        pdf_metadata(page_count=201),
        DrawingIntakePolicy(max_pdf_pages=200),
    )
    assert result.assessment.quality == "REJECTED"
    assert result.detailed_reasons == ("PDF_PAGE_LIMIT_EXCEEDED",)
```

- [ ] **Step 2: Run focused tests and observe RED**

Run: `pytest tests/unit/parsing/test_drawing_quality.py -v`

Expected: missing module.

- [ ] **Step 3: Implement immutable metadata and result types**

```python
@dataclass(frozen=True, slots=True)
class TrustedSourceMetadata:
    source_sha256: str
    adapter: str
    adapter_version: str
    parser_outcome: ParserOutcome
    page_count: int | None
    width: int | None
    height: int | None
    physical_size_trust: PhysicalSizeTrust
    lossy_or_screen_capture: bool


@dataclass(frozen=True, slots=True)
class DrawingQualityResult:
    assessment: DrawingQualityAssessment
    detailed_reasons: tuple[str, ...]
    policy_id: str
```

- [ ] **Step 4: Implement deterministic assessment order**

Evaluation order:

1. source hash mismatch
2. parser failure
3. file-byte limit
4. PDF page limit or unknown page count
5. image dimensions and multiplication overflow-safe pixel count
6. per-image and per-case pixel limits
7. lossy/screen-capture source
8. physical-size trust

Any resource/security failure produces `REJECTED`. Unknown metadata, lossy source, `METADATA_ONLY`, or `UNKNOWN` produces `REVIEW_REQUIRED`. `PASS` is allowed only for trusted non-lossy input with no reasons.

Detailed reasons must be sorted by this declared evaluation order, not alphabetically.

- [ ] **Step 5: Add parser-failure and workflow-reason mapping tests**

```python
@pytest.mark.parametrize(
    ("outcome", "detail"),
    [
        ("TIMEOUT", "PARSER_TIMEOUT"),
        ("MEMORY_LIMIT", "PARSER_MEMORY_LIMIT"),
        ("INVALID_OUTPUT", "PARSER_OUTPUT_INVALID"),
    ],
)
def test_parser_failures_are_quality_data(outcome: str, detail: str) -> None:
    result = assess_drawing_quality(
        pdf_attachment(), pdf_metadata(parser_outcome=outcome), DrawingIntakePolicy()
    )
    assert result.assessment.quality == "REVIEW_REQUIRED"
    assert result.detailed_reasons == (detail,)
    assert workflow_reason_for_quality(result) == "DRAWING_CONFIRMATION_REQUIRED"


def test_rejected_quality_maps_to_m0_reason() -> None:
    assert workflow_reason_for_quality(rejected_result()) == "DRAWING_QUALITY_REJECTED"
```

- [ ] **Step 6: Run Task 3 tests**

Run: `pytest tests/unit/parsing/test_drawing_quality.py tests/unit/contracts/test_drawing_contracts.py -v`

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/ansim_review/parsing/drawing_quality.py tests/unit/parsing/test_drawing_quality.py
git commit -m "feat: assess drawing source quality"
```

---

### Task 4: Candidate creation and create-only repository

**Files:**
- Create: `src/ansim_review/parsing/drawing_candidates.py`
- Create: `tests/unit/parsing/test_drawing_candidates.py`

**Interfaces:**
- Consumes: `DrawingCandidate`, `Geometry`, `RawElement`, `drawing_candidate_document`, Task 1 writer.
- Produces:
  - `extractor_candidate_id(case_id: str, source_sha256: str, page: int, extractor: str, extractor_version: str, element_id: str) -> str`
  - `manual_candidate_id(case_id: str, annotation_id: str) -> str`
  - `candidate_from_raw_element(...) -> DrawingCandidate`
  - `create_manual_candidate(...) -> DrawingCandidate`
  - `persist_candidate(case_dir: Path, candidate: DrawingCandidate) -> CaseManifestEntry`
  - `load_candidate(case_dir: Path, candidate_id: str) -> DrawingCandidate`

- [ ] **Step 1: Write failing stable-ID tests**

```python
def test_extractor_candidate_id_is_stable_and_order_independent() -> None:
    first = extractor_candidate_id(
        "CASE-001", "a" * 64, 1, "opendataloader", "1", "E-17"
    )
    second = extractor_candidate_id(
        "CASE-001", "a" * 64, 1, "opendataloader", "1", "E-17"
    )
    assert first == second
    assert first.startswith("CAND-")


def test_manual_id_uses_annotation_identity() -> None:
    assert manual_candidate_id("CASE-001", "ANN-ROAD-01") == manual_candidate_id(
        "CASE-001", "ANN-ROAD-01"
    )
```

- [ ] **Step 2: Run focused tests and observe RED**

Run: `pytest tests/unit/parsing/test_drawing_candidates.py -v`

Expected: missing module.

- [ ] **Step 3: Implement stable IDs**

Use canonical JSON hashing:

```python
def _stable_id(prefix: str, payload: dict[str, object]) -> str:
    return f"{prefix}-{sha256_json(payload)[:24].upper()}"
```

Every input string is validated before hashing.

- [ ] **Step 4: Add neutral parser conversion tests**

```python
def test_raw_text_element_becomes_neutral_extractor_candidate() -> None:
    candidate = candidate_from_raw_element(
        case_id="CASE-001",
        source_sha256="a" * 64,
        raw=RawElement(..., element_type="text", raw_bbox=(1, 2, 3, 4), raw_text="8M"),
        extractor="opendataloader",
        extractor_version="1.0",
    )
    assert candidate.candidate_type == "TEXT_ELEMENT"
    assert candidate.origin == "EXTRACTOR"
    assert candidate.status == "UNCONFIRMED"
    assert candidate.geometry.type == "BBOX"
    assert candidate.normalized_candidate is None
```

Parser types map only through an explicit dictionary:

```python
_NEUTRAL_TYPES = {
    "text": "TEXT_ELEMENT",
    "table": "TABLE_ELEMENT",
    "path": "VECTOR_ELEMENT",
    "line": "VECTOR_ELEMENT",
}
```

Unknown types or elements without bbox raise `ValueError`; no domain-specific candidate is inferred.

- [ ] **Step 5: Add manual candidate tests for all geometry types**

```python
@pytest.mark.parametrize("geometry", [point(), bbox(), linestring(), polygon()])
def test_manual_candidates_support_m0_geometry(geometry: Geometry) -> None:
    candidate = create_manual_candidate(
        case_id="CASE-001",
        source_sha256="a" * 64,
        page=1,
        annotation_id="ANN-001",
        candidate_type="VEHICLE_ENTRANCE",
        geometry=geometry,
        raw_value=None,
        normalized_candidate=None,
    )
    assert candidate.origin == "REVIEWER_MANUAL"
    assert candidate.status == "CREATED"
    assert candidate.annotation_id == "ANN-001"
```

- [ ] **Step 6: Implement manual construction and persistence**

`persist_candidate` writes `candidates/<candidate_id>.json` through `write_canonical_create_only`, then returns a `CaseManifestEntry`. `load_candidate` reads JSON, calls `decode_drawing_candidate`, and verifies the document candidate ID matches the filename.

- [ ] **Step 7: Add overwrite and file-ID mismatch tests**

```python
def test_candidate_repository_is_create_only(tmp_path: Path) -> None:
    entry = persist_candidate(tmp_path, manual_candidate())
    assert entry.relative_path.startswith("candidates/")
    with pytest.raises(FileExistsError):
        persist_candidate(tmp_path, manual_candidate())
```

- [ ] **Step 8: Run Task 4 tests**

Run: `pytest tests/unit/parsing/test_drawing_candidates.py tests/unit/contracts/test_drawing_contracts.py -v`

Expected: PASS.

- [ ] **Step 9: Commit Task 4**

```bash
git add src/ansim_review/parsing/drawing_candidates.py tests/unit/parsing/test_drawing_candidates.py
git commit -m "feat: persist drawing candidates"
```

---

### Task 5: Append-only drawing confirmations

**Files:**
- Create: `src/ansim_review/parsing/drawing_confirmation.py`
- Create: `tests/unit/parsing/test_drawing_confirmation.py`

**Interfaces:**
- Consumes: `DrawingCandidate`, `DrawingConfirmation`, Task 1 path/writer helpers.
- Produces:
  - `parse_confirmation_time(value: str) -> datetime`
  - `validate_confirmation_for_candidate(candidate: DrawingCandidate, confirmation: DrawingConfirmation) -> CandidateStatus`
  - `persist_confirmation(case_dir: Path, reviewer_token: str, candidate: DrawingCandidate, confirmation: DrawingConfirmation) -> CaseManifestEntry`
  - `load_and_verify_confirmation(case_dir: Path, entry: CaseManifestEntry) -> DrawingConfirmation`

- [ ] **Step 1: Write failing timestamp and relation tests**

```python
def test_confirmation_timestamp_requires_explicit_offset() -> None:
    with pytest.raises(ValueError, match="explicit UTC offset"):
        parse_confirmation_time("2026-08-02T01:00:00")


def test_rejected_confirmation_is_not_bindable() -> None:
    assert validate_confirmation_for_candidate(
        extractor_candidate(), confirmation(action="REJECTED")
    ) == "REJECTED"


def test_edited_confirmation_requires_value_or_geometry() -> None:
    with pytest.raises(ValueError, match="confirmed value or geometry"):
        validate_confirmation_for_candidate(
            extractor_candidate(), confirmation(action="EDITED", confirmed_value=None, geometry=None)
        )
```

- [ ] **Step 2: Run focused tests and observe RED**

Run: `pytest tests/unit/parsing/test_drawing_confirmation.py -v`

Expected: missing module.

- [ ] **Step 3: Implement timestamp and action/status validation**

Rules:

```text
ACCEPTED -> effective status ACCEPTED; candidate cannot already be REJECTED or CONFLICT
EDITED   -> effective status EDITED; confirmed_value or geometry required
CREATED  -> effective status CREATED; candidate origin must be REVIEWER_MANUAL and status CREATED
REJECTED -> effective status REJECTED; never bindable
```

The confirmation candidate ID and source hash must equal the candidate. Replacement geometry must use the same coordinate system as the candidate geometry.

- [ ] **Step 4: Add persistence and tamper tests**

```python
def test_confirmation_is_append_only_and_hash_bound(tmp_path: Path) -> None:
    entry = persist_confirmation(
        tmp_path,
        "kim-sh",
        manual_candidate(),
        confirmation(action="CREATED", confirmed_value="8.0", unit="m"),
    )
    loaded = load_and_verify_confirmation(tmp_path, entry)
    assert loaded.action == "CREATED"
    with pytest.raises(FileExistsError):
        persist_confirmation(
            tmp_path,
            "kim-sh",
            manual_candidate(),
            confirmation(action="CREATED", confirmed_value="8.0", unit="m"),
        )


def test_confirmation_tamper_is_detected(tmp_path: Path) -> None:
    entry = persist_confirmation(...)
    path = tmp_path / entry.relative_path
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="confirmation hash mismatch"):
        load_and_verify_confirmation(tmp_path, entry)
```

- [ ] **Step 5: Implement append-only filename and loading**

Filename format:

```python
filename = (
    f"{timestamp.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
    f"{reviewer_token}-{confirmation.confirmation_id}.json"
)
```

`persist_confirmation` validates the reviewer token and confirmation ID, writes canonical JSON create-only, and returns the hash entry. `load_and_verify_confirmation` hashes bytes before JSON decoding and rejects any mismatch.

- [ ] **Step 6: Run Task 5 tests**

Run: `pytest tests/unit/parsing/test_drawing_confirmation.py tests/unit/contracts/test_drawing_contracts.py -v`

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add src/ansim_review/parsing/drawing_confirmation.py tests/unit/parsing/test_drawing_confirmation.py
git commit -m "feat: append drawing confirmations"
```

---

### Task 6: Confirmed-input builder and conflict detection

**Files:**
- Create: `src/ansim_review/parsing/drawing_inputs.py`
- Create: `tests/unit/parsing/test_drawing_inputs.py`
- Create: `tests/golden/drawing/manual-confirmed-inputs.json`

**Interfaces:**
- Consumes: `DrawingCandidate`, `DrawingConfirmation`, `ConfirmedInput`, confirmation entry and hash.
- Produces:
  - `ConfirmedInputBuildRequest`
  - `ConfirmedInputConflict`
  - `build_confirmed_input(request: ConfirmedInputBuildRequest) -> ConfirmedInput`
  - `validate_confirmed_input_set(inputs: Sequence[ConfirmedInput]) -> tuple[ConfirmedInputConflict, ...]`
  - `confirmed_inputs_document(inputs: Sequence[ConfirmedInput]) -> dict[str, object]`
  - `persist_confirmed_inputs(case_dir: Path, inputs: Sequence[ConfirmedInput]) -> CaseManifestEntry`

- [ ] **Step 1: Write failing build tests**

```python
def test_manual_created_candidate_builds_confirmed_input() -> None:
    confirmed = build_confirmed_input(
        ConfirmedInputBuildRequest(
            input_id="INPUT-ROAD-WIDTH",
            field="road_width_m",
            value="8.0",
            unit="m",
            candidate=manual_candidate(),
            effective_status="CREATED",
            confirmation=confirmation(action="CREATED", confirmed_value="8.0", unit="m"),
            confirmation_entry=confirmation_entry(),
        )
    )
    assert confirmed.status == "CONFIRMED"
    assert confirmed.candidate_status == "CREATED"
    assert confirmed.value == "8.0"


@pytest.mark.parametrize("status", ["UNCONFIRMED", "REJECTED", "CONFLICT"])
def test_non_bindable_candidate_status_is_rejected(status: str) -> None:
    with pytest.raises(ValueError, match="cannot bind"):
        build_confirmed_input(request(effective_status=status))
```

- [ ] **Step 2: Run focused tests and observe RED**

Run: `pytest tests/unit/parsing/test_drawing_inputs.py -v`

Expected: missing module.

- [ ] **Step 3: Implement build request and confirmed-input construction**

`build_confirmed_input` must call `validate_confirmation_for_candidate`, require the passed effective status to match the computed one, use replacement geometry when present, require a finite decimal string and non-empty unit, and create the M0 `ConfirmedInput` with:

```python
confirmation_record=confirmation_entry.relative_path
confirmation_sha256=confirmation_entry.sha256
evidence_id=candidate.candidate_id
```

- [ ] **Step 4: Add deterministic conflict tests**

```python
def test_conflicting_field_values_are_reported_without_winner() -> None:
    conflicts = validate_confirmed_input_set(
        [confirmed_input("A", "road_width_m", "8.0", "m"),
         confirmed_input("B", "road_width_m", "10.0", "m")]
    )
    assert conflicts == (
        ConfirmedInputConflict(
            field="road_width_m",
            input_ids=("A", "B"),
            reason="DIFFERENT_VALUE_OR_UNIT",
        ),
    )


def test_duplicate_identical_values_are_also_rejected() -> None:
    conflicts = validate_confirmed_input_set(
        [confirmed_input("A", "road_width_m", "8.0", "m"),
         confirmed_input("B", "road_width_m", "8.0", "m")]
    )
    assert conflicts[0].reason == "DUPLICATE_ACTIVE_FIELD"
```

One active input per field is allowed. Sort conflicts by field and input IDs.

- [ ] **Step 5: Implement canonical collection document and golden fixture**

Document format:

```json
{
  "format": "ansim/confirmed-input-set",
  "version": 1,
  "inputs": []
}
```

Sort inputs by `(field, input_id)`. Reject persistence when conflicts exist. Write `confirmed-inputs.json` create-only and return a manifest entry. Add `tests/golden/drawing/manual-confirmed-inputs.json` for one manual `CREATED` road-width input.

- [ ] **Step 6: Run Task 6 tests and golden comparison**

Run: `pytest tests/unit/parsing/test_drawing_inputs.py -v`

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

```bash
git add src/ansim_review/parsing/drawing_inputs.py tests/unit/parsing/test_drawing_inputs.py tests/golden/drawing/manual-confirmed-inputs.json
git commit -m "feat: build confirmed drawing inputs"
```

---

### Task 7: Engine binding and M0 workflow projection

**Files:**
- Create: `src/ansim_review/parsing/drawing_binding.py`
- Create: `src/ansim_review/parsing/drawing_workflow.py`
- Create: `tests/unit/parsing/test_drawing_binding.py`
- Create: `tests/unit/parsing/test_drawing_workflow.py`

**Interfaces:**
- Consumes: `ConfirmedInput`, case paths, attachment verifier, confirmation verifier, M0 `WorkflowStateRecord`.
- Produces:
  - `EngineInputValue`
  - `bind_confirmed_inputs(case_dir: Path, inputs: Sequence[ConfirmedInput], source_attachments: Mapping[str, ImmutableAttachment]) -> dict[str, EngineInputValue]`
  - `DrawingWorkflowFacts`
  - `project_drawing_workflow(run_id: str, facts: DrawingWorkflowFacts) -> WorkflowStateRecord`

- [ ] **Step 1: Write failing binding tests**

```python
def test_binding_reverifies_confirmation_hash(tmp_path: Path) -> None:
    # persist complete fixture, then tamper with confirmation
    with pytest.raises(ValueError, match="confirmation hash mismatch"):
        bind_confirmed_inputs(case_dir, [confirmed], {confirmed.source_sha256: attachment})


def test_binding_returns_deterministic_decimal_strings() -> None:
    result = bind_confirmed_inputs(case_dir, [confirmed_road_width()], attachments())
    assert result == {
        "road_width_m": EngineInputValue(value="8.0", unit="m", input_id="INPUT-ROAD-WIDTH")
    }
```

- [ ] **Step 2: Run binding tests and observe RED**

Run: `pytest tests/unit/parsing/test_drawing_binding.py -v`

Expected: missing module.

- [ ] **Step 3: Implement binding revalidation**

For every input:

1. Decode through `confirmed_input_document` and `decode_confirmed_input` to enforce M0.
2. Locate immutable attachment by source SHA-256.
3. Run `verify_immutable_attachment`; reject any error.
4. Read confirmation record under the case root.
5. Verify confirmation byte hash equals `confirmation_sha256`.
6. Reject duplicate fields.
7. Return a field-sorted dictionary of immutable `EngineInputValue` objects.

- [ ] **Step 4: Write failing workflow projection tests**

```python
def test_missing_source_projects_pending_ingestion() -> None:
    record = project_drawing_workflow("RUN-001", DrawingWorkflowFacts(has_source=False))
    assert record.workflow_state == "PENDING_DRAWING_INGESTION"
    assert record.reason_codes == ()
    assert record.resumable is False


def test_rejected_quality_projects_resumable_block() -> None:
    record = project_drawing_workflow(
        "RUN-001",
        DrawingWorkflowFacts(has_source=True, quality_rejected=True),
    )
    assert record.workflow_state == "BLOCKED"
    assert record.reason_codes == ("DRAWING_QUALITY_REJECTED",)
    assert record.resumable is True


def test_conflict_projects_confirmation_required_without_reason_codes() -> None:
    record = project_drawing_workflow(
        "RUN-001",
        DrawingWorkflowFacts(has_source=True, has_conflict=True),
    )
    assert record.workflow_state == "INPUT_CONFIRMATION_REQUIRED"
    assert record.reason_codes == ()
```

- [ ] **Step 5: Implement workflow precedence**

Precedence:

```text
terminal_integrity_failure -> FAILED / SOURCE_HASH_MISMATCH / resumable false
quality_rejected           -> BLOCKED / DRAWING_QUALITY_REJECTED / resumable true
no source                  -> PENDING_DRAWING_INGESTION
conflict or missing input  -> INPUT_CONFIRMATION_REQUIRED
validated inputs           -> READY_TO_EVALUATE
otherwise                  -> INPUT_CONFIRMATION_REQUIRED
```

Construct `WorkflowStateRecord` then round-trip through `workflow_state_document` and `decode_workflow_state_record` before returning it.

- [ ] **Step 6: Run Task 7 tests**

Run: `pytest tests/unit/parsing/test_drawing_binding.py tests/unit/parsing/test_drawing_workflow.py tests/unit/contracts/test_workflow_contracts.py -v`

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```bash
git add src/ansim_review/parsing/drawing_binding.py src/ansim_review/parsing/drawing_workflow.py tests/unit/parsing/test_drawing_binding.py tests/unit/parsing/test_drawing_workflow.py
git commit -m "feat: bind confirmed drawing inputs"
```

---

### Task 8: End-to-end manual annotation, tamper detection, and release verification

**Files:**
- Create: `tests/integration/drawing/test_manual_annotation_flow.py`
- Create: `tests/integration/drawing/test_drawing_tamper_detection.py`
- Modify: `docs/superpowers/plans/2026-08-01-evidence-review-system-master-roadmap.md`
- Modify: `docs/CODEX_WORKFLOW.md`

**Interfaces:**
- Consumes: every Task 1–7 public interface.
- Produces: verified manual-annotation backend flow and documentation for downstream UI/orchestration.

- [ ] **Step 1: Write the complete manual annotation integration test**

```python
def test_manual_annotation_reaches_ready_to_evaluate(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    source = tmp_path / "site-plan.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fixture")

    attachment = ingest_drawing_source(
        source, case_dir, "ATT-001", "CASE_DRAWING", DrawingIntakePolicy()
    )
    quality = assess_drawing_quality(
        attachment,
        TrustedSourceMetadata(
            source_sha256=attachment.sha256,
            adapter="fixture",
            adapter_version="1",
            parser_outcome="SUCCESS",
            page_count=None,
            width=4000,
            height=3000,
            physical_size_trust="USER_CONFIRMED",
            lossy_or_screen_capture=False,
        ),
        DrawingIntakePolicy(),
    )
    assert quality.assessment.quality == "PASS"

    candidate = create_manual_candidate(
        case_id="CASE-001",
        source_sha256=attachment.sha256,
        page=1,
        annotation_id="ANN-ROAD-WIDTH",
        candidate_type="ROAD_WIDTH_TEXT",
        geometry=Geometry(
            type="LINESTRING",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=((100.0, 200.0), (900.0, 200.0)),
        ),
        raw_value=None,
        normalized_candidate=None,
    )
    persist_candidate(case_dir, candidate)

    confirmation = DrawingConfirmation(
        confirmation_id="CONF-001",
        candidate_id=candidate.candidate_id,
        action="CREATED",
        source_sha256=attachment.sha256,
        reviewer="김성현",
        confirmed_at="2026-08-02T01:30:00+09:00",
        confirmed_value="8.0",
        unit="m",
        geometry=None,
    )
    confirmation_entry = persist_confirmation(
        case_dir, "kim-sh", candidate, confirmation
    )
    confirmed = build_confirmed_input(
        ConfirmedInputBuildRequest(
            input_id="INPUT-ROAD-WIDTH",
            field="road_width_m",
            value="8.0",
            unit="m",
            candidate=candidate,
            effective_status="CREATED",
            confirmation=confirmation,
            confirmation_entry=confirmation_entry,
        )
    )
    persist_confirmed_inputs(case_dir, [confirmed])
    bound = bind_confirmed_inputs(
        case_dir, [confirmed], {attachment.sha256: attachment}
    )
    assert bound["road_width_m"].value == "8.0"
    workflow = project_drawing_workflow(
        "RUN-001",
        DrawingWorkflowFacts(has_source=True, has_validated_inputs=True),
    )
    assert workflow.workflow_state == "READY_TO_EVALUATE"
```

- [ ] **Step 2: Run the integration test and fix only wiring defects**

Run: `pytest tests/integration/drawing/test_manual_annotation_flow.py -v`

Expected: PASS after correcting imports or interface mismatches; do not add automatic recognition.

- [ ] **Step 3: Write and run tamper integration test**

```python
def test_tampered_confirmation_blocks_engine_binding(tmp_path: Path) -> None:
    fixture = build_complete_case(tmp_path)
    confirmation_path = fixture.case_dir / fixture.confirmation_entry.relative_path
    confirmation_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="confirmation hash mismatch"):
        bind_confirmed_inputs(
            fixture.case_dir,
            [fixture.confirmed_input],
            {fixture.attachment.sha256: fixture.attachment},
        )
```

Run: `pytest tests/integration/drawing/test_drawing_tamper_detection.py -v`

Expected: PASS.

- [ ] **Step 4: Run the complete drawing test slice**

Run:

```bash
pytest tests/unit/parsing/test_drawing_case.py \
  tests/unit/parsing/test_drawing_source.py \
  tests/unit/parsing/test_drawing_quality.py \
  tests/unit/parsing/test_drawing_candidates.py \
  tests/unit/parsing/test_drawing_confirmation.py \
  tests/unit/parsing/test_drawing_inputs.py \
  tests/unit/parsing/test_drawing_binding.py \
  tests/unit/parsing/test_drawing_workflow.py \
  tests/integration/drawing -v
```

Expected: PASS.

- [ ] **Step 5: Update roadmap and Codex workflow documentation**

Document:

- M1 backend consumes M0 contracts from #15.
- Browser UI, calibration, and automatic candidate recognition remain future milestones.
- Codex may create manual candidate and confirmation JSON only when acting as the reviewer interface with explicit user confirmation; it may not independently confirm a value.
- Runtime project code never calls a model API.

- [ ] **Step 6: Run full verification**

Run:

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

Expected:

- all tests pass, including the previous 158-test baseline
- ruff reports `All checks passed!`
- mypy reports no issues
- compileall exits 0

- [ ] **Step 7: Perform contract self-review**

Verify with repository search:

```bash
rg 'Literal\[.*(POINT|BBOX|LINESTRING|POLYGON)' src/ansim_review/parsing
rg 'REVIEW_COMPLETED|ABSTAIN|CONDITIONAL' src/ansim_review/parsing/drawing_*.py
rg 'openai|anthropic|requests|httpx' src/ansim_review/parsing/drawing_*.py
```

Expected:

- parsing modules import M0 drawing literals rather than redefining them
- no finalizer or human-decision values are reused as quality/workflow states
- no network/model dependency is introduced

- [ ] **Step 8: Commit Task 8**

```bash
git add tests/integration/drawing docs/superpowers/plans/2026-08-01-evidence-review-system-master-roadmap.md docs/CODEX_WORKFLOW.md
git commit -m "test: verify manual drawing evidence flow"
```

- [ ] **Step 9: Open a draft pull request**

Title:

```text
feat: add drawing evidence backend
```

Body must include:

- scope completed for Tasks 1–8
- explicit exclusions: OCR, automatic drawing recognition, browser UI, calibration
- full verification results
- manual review gate for source security, append-only confirmation behavior, and engine-binding provenance
- `Closes #6` only after all issue completion criteria covered by this PR are genuinely complete; otherwise use `Refs #6` and create follow-up issues for remaining #6 scope
