# OpenDataLoader Parser Warning and Reproducibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic OpenDataLoader warning collection and two-run JSON/Markdown reproducibility validation with fail-closed mismatch detection, stable review queues, and canonical create-only reports.

**Architecture:** Build an isolated `parser_reproducibility` package. Each parser run contains immutable raw artifacts plus a strict `parser-run.json` sidecar that records parser execution identity; the validator builds canonical run manifests, compares raw bytes first, applies a closed in-memory normalization profile only when required, emits structural differences, and creates warning review evidence. The existing shared CLI parser exposes the feature without invoking OpenDataLoader or changing source-batch ingestion behavior.

**Tech Stack:** Python 3.11+, frozen dataclasses, `pathlib`, `hashlib`, strict JSON decoding, existing `ansim_review.canonical_json`, existing source-batch and OpenDataLoader helpers, pytest, Ruff, strict mypy, compileall, and isolated Python 3.11/3.13 wheel verification.

## Global Constraints

- Parser kind is exactly `opendataloader` in contract version 1.
- Original PDFs, raw parser JSON, Markdown, logs, images, and `parser-run.json` are immutable inputs.
- Runtime validation remains offline and never launches OpenDataLoader, OCR, a browser, or a network request.
- A parser run root must contain `document.json`, `document.md`, and `parser-run.json`; `parser.log` is optional.
- `parser-run.json` is strict authority for parser version, parser configuration, and adapter version. Missing or malformed authority produces `PARSER_FAILED`.
- Normalization occurs only in memory and uses a repository-owned closed allowlist. No wildcard paths, recursive paths, plugins, or user code are accepted.
- Any unexpected text, table, image, coordinate, page, order, relationship, Markdown, or warning difference is `MISMATCH`.
- Parser version, adapter version, parser configuration SHA-256, or normalization profile difference is `ENVIRONMENT_MISMATCH`; no equivalence claim is made.
- Warning presence does not itself fail parsing, but every warning produces or updates a `REVIEW_REQUIRED` queue entry.
- Canonical outputs use UTF-8 without BOM, LF, sorted object keys, deterministic list order, relative POSIX paths, no equality-sensitive timestamps, and one trailing newline.
- Every output is create-only. The two-output warning command reserves both destinations before writing either file.
- GitHub Actions is excluded from acceptance. Final evidence records exact HEAD, platform, Python versions, commands, exit codes, report hashes, and wheel hashes.
- Implementation begins on `agent/issue-52-opendataloader-reproducibility` with spec commit `b31113479a02e63aa22277f1c7354e00fe26c274` present and a clean worktree.

---

## File Map

Create:

```text
parser-reproducibility.json
src/ansim_review/parser_reproducibility/__init__.py
src/ansim_review/parser_reproducibility/contract.py
src/ansim_review/parser_reproducibility/paths.py
src/ansim_review/parser_reproducibility/opendataloader.py
src/ansim_review/parser_reproducibility/run_manifest.py
src/ansim_review/parser_reproducibility/normalization.py
src/ansim_review/parser_reproducibility/warnings.py
src/ansim_review/parser_reproducibility/comparison.py
src/ansim_review/parser_reproducibility/queue.py
src/ansim_review/parser_reproducibility/report.py
src/ansim_review/parser_reproducibility/cli.py
src/ansim_review/contracts/schemas/parser-reproducibility-config.schema.json
src/ansim_review/contracts/schemas/parser-run-metadata.schema.json
src/ansim_review/contracts/schemas/parser-run-manifest.schema.json
src/ansim_review/contracts/schemas/parser-reproducibility-report.schema.json
src/ansim_review/contracts/schemas/parser-warning-report.schema.json
src/ansim_review/contracts/schemas/parser-review-queue.schema.json
tests/unit/parser_reproducibility/*.py
tests/integration/parser_reproducibility/*.py
tests/integration/parser_reproducibility/fixtures/**
docs/acceptance/issue-52/README.md
```

Modify:

```text
src/ansim_review/cli_parser.py
src/ansim_review/cli.py
src/ansim_review/contracts/schemas/__init__.py
src/ansim_review/parsing/odl_adapter.py
src/ansim_review/parsing/odl_source.py
tests/unit/contracts/test_schema_documents.py
tests/unit/test_cli_parser.py
tests/integration/documentation_integrity/test_repository_acceptance.py
documentation-integrity.json
README.md
AGENTS.md
skills/01-preserving-and-parsing-pdfs/SKILL.md
pyproject.toml
```

---

### Task 1: Strict configuration and parser-run authority contracts

**Files:**
- Create: `parser-reproducibility.json`
- Create: `src/ansim_review/parser_reproducibility/__init__.py`
- Create: `src/ansim_review/parser_reproducibility/contract.py`
- Create: `src/ansim_review/contracts/schemas/parser-reproducibility-config.schema.json`
- Create: `src/ansim_review/contracts/schemas/parser-run-metadata.schema.json`
- Modify: `src/ansim_review/contracts/schemas/__init__.py`
- Modify: `tests/unit/contracts/test_schema_documents.py`
- Create: `tests/unit/parser_reproducibility/test_contract.py`
- Modify: `documentation-integrity.json`

**Interfaces:**
- Produces: `ReproducibilityConfig`
- Produces: `ParserRunMetadata`
- Produces: `decode_reproducibility_config(data: bytes) -> ReproducibilityConfig`
- Produces: `decode_parser_run_metadata(data: bytes) -> ParserRunMetadata`

- [ ] **Step 1: Write failing decoder tests**

```python
from __future__ import annotations

import json

import pytest

from ansim_review.parser_reproducibility.contract import (
    decode_parser_run_metadata,
    decode_reproducibility_config,
)


def config_payload() -> dict[str, object]:
    return {
        "format": "evidence-review/parser-reproducibility-config",
        "version": 1,
        "parser_kind": "opendataloader",
        "adapter_version": 1,
        "json_artifact_names": ["document.json"],
        "markdown_artifact_names": ["document.md"],
        "warning_sources": ["document.json", "parser.log"],
        "normalization_profile": "opendataloader-v1",
        "allowed_nondeterministic_fields": [
            "$.metadata.parsed_at",
            "$.metadata.output_directory",
        ],
    }


def run_payload() -> dict[str, object]:
    return {
        "format": "evidence-review/opendataloader-parser-run",
        "version": 1,
        "parser_kind": "opendataloader",
        "parser_version": "1.2.3",
        "adapter_version": 1,
        "parser_configuration": {"markdown_with_html": True},
        "platform_family": "windows",
    }


def encode(value: dict[str, object]) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def test_decodes_exact_config_and_run_authority() -> None:
    config = decode_reproducibility_config(encode(config_payload()))
    run = decode_parser_run_metadata(encode(run_payload()))
    assert config.parser_kind == "opendataloader"
    assert config.allowed_nondeterministic_fields == (
        "$.metadata.parsed_at",
        "$.metadata.output_directory",
    )
    assert run.parser_version == "1.2.3"
    assert run.parser_configuration == {"markdown_with_html": True}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("parser_kind", "other", "unsupported parser kind"),
        ("normalization_profile", "other-v1", "unsupported normalization profile"),
        ("json_artifact_names", ["a\\b.json"], "backslash"),
        ("warning_sources", ["../parser.log"], "unsafe path"),
        ("allowed_nondeterministic_fields", ["$..parsed_at"], "recursive"),
        ("allowed_nondeterministic_fields", ["$.pages[*].id"], "wildcard"),
    ],
)
def test_config_rejects_invalid_values(field: str, value: object, message: str) -> None:
    payload = config_payload()
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        decode_reproducibility_config(encode(payload))
```

Add duplicate-key, unknown-field, empty-version, Boolean-as-integer, duplicate-list-entry, and unsupported adapter-version cases.

- [ ] **Step 2: Run tests and verify the expected import failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_contract.py -v
```

Expected: collection fails because the package has not been created.

- [ ] **Step 3: Implement frozen models and strict JSON decoding**

```python
@dataclass(frozen=True, slots=True)
class ReproducibilityConfig:
    parser_kind: Literal["opendataloader"]
    adapter_version: int
    json_artifact_names: tuple[str, ...]
    markdown_artifact_names: tuple[str, ...]
    warning_sources: tuple[str, ...]
    normalization_profile: Literal["opendataloader-v1"]
    allowed_nondeterministic_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParserRunMetadata:
    parser_kind: Literal["opendataloader"]
    parser_version: str
    adapter_version: int
    parser_configuration: dict[str, JsonValue]
    platform_family: Literal["windows", "linux", "macos", "other"]
```

Use `json.loads(..., object_pairs_hook=_reject_duplicate_keys)`. Require exact key sets and reject absolute paths, drive-prefixed paths, backslashes, empty components, `.`/`..`, wildcard JSON paths, and recursive JSON paths.

- [ ] **Step 4: Add closed profile authority**

```python
OPENDATALOADER_V1_ALLOWED_FIELDS = frozenset(
    {
        "$.metadata.parsed_at",
        "$.metadata.output_directory",
    }
)
```

Configuration may select a subset of this set and may not introduce any other field.

- [ ] **Step 5: Add the root config and schemas**

Write `parser-reproducibility.json` using `config_payload()` exactly, with LF and one trailing newline. Add both schema names to the schema package and schema inventory test.

- [ ] **Step 6: Register active design and plan as current**

Add these exact entries to `documentation-integrity.json.current_overrides`:

```json
"docs/superpowers/plans/2026-08-03-opendataloader-parser-reproducibility.md",
"docs/superpowers/specs/2026-08-03-opendataloader-parser-reproducibility-design.md"
```

- [ ] **Step 7: Run focused verification**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_contract.py tests/unit/contracts/test_schema_documents.py -v
python -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output build/issue52-task1-documentation.json
```

Expected: tests pass; documentation status PASS with zero errors.

- [ ] **Step 8: Commit**

```powershell
git add parser-reproducibility.json documentation-integrity.json src/ansim_review/parser_reproducibility src/ansim_review/contracts/schemas tests/unit/parser_reproducibility/test_contract.py tests/unit/contracts/test_schema_documents.py
git commit -m "feat: define parser reproducibility authority"
```

---

### Task 2: Safe paths and immutable run manifests

**Files:**
- Create: `src/ansim_review/parser_reproducibility/paths.py`
- Create: `src/ansim_review/parser_reproducibility/run_manifest.py`
- Create: `src/ansim_review/contracts/schemas/parser-run-manifest.schema.json`
- Create: `tests/unit/parser_reproducibility/test_paths.py`
- Create: `tests/unit/parser_reproducibility/test_run_manifest.py`

**Interfaces:**
- Consumes: `ReproducibilityConfig`, `ParserRunMetadata`
- Produces: `ParserRunManifest`
- Produces: `resolve_run_artifact(root: Path, name: str) -> Path`
- Produces: `canonical_relative_path(root: Path, path: Path) -> str`
- Produces: `build_parser_run_manifest(source_pdf: Path, run_root: Path, config: ReproducibilityConfig) -> ParserRunManifest`

- [ ] **Step 1: Write path tests**

```python
@pytest.mark.parametrize("name", ["../x", "/x", "C:/x", "a\\b", "a/./b"])
def test_rejects_unsafe_artifact_name(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        resolve_run_artifact(tmp_path, name)


def test_resolves_regular_file_under_root(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    target = root / "document.json"
    target.write_text("{}", encoding="utf-8")
    assert resolve_run_artifact(root, "document.json") == target.resolve()
    assert canonical_relative_path(root, target) == "document.json"
```

Add a symlink/junction escape case that skips only when the operating system refuses link creation.

- [ ] **Step 2: Write manifest tests**

Create a run root with `document.json`, `document.md`, and `parser-run.json`. Assert source/run hashes, byte sizes, configuration SHA-256, platform family, relative paths, parser page count, warning count, and sorted warning codes. Assert source and raw artifact bytes are unchanged after manifest construction.

- [ ] **Step 3: Run tests and confirm missing implementation**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_paths.py tests/unit/parser_reproducibility/test_run_manifest.py -v
```

- [ ] **Step 4: Implement safe resolution**

```python
def resolve_run_artifact(root: Path, name: str) -> Path:
    relative = validate_posix_relative_name(name)
    resolved_root = root.resolve()
    candidate = (resolved_root / relative).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ValueError("artifact path escapes run root")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate
```

- [ ] **Step 5: Implement manifest construction**

Use existing `ansim_review.parsing.source_manifest.sha256_file`. Read run metadata strictly from `parser-run.json`. Read parser page count through the OpenDataLoader helper introduced in Task 3; initially use a private exact extractor for `number of pages` or `page_count`, then replace it with the shared helper in the same Task 3 commit.

```python
@dataclass(frozen=True, slots=True)
class ParserRunManifest:
    source_sha256: str
    source_size: int
    parser_kind: str
    parser_version: str
    adapter_version: int
    configuration_sha256: str
    platform_family: str
    json_relative_path: str
    json_sha256: str
    json_size: int
    markdown_relative_path: str
    markdown_sha256: str
    markdown_size: int
    warning_source_relative_paths: tuple[str, ...]
    warning_count: int
    warning_codes: tuple[str, ...]
    parser_page_count: int
```

The config hash is `sha256(dump_bytes(run_metadata.parser_configuration))` in uppercase hexadecimal.

- [ ] **Step 6: Add schema and deterministic serialization tests**

The format is `evidence-review/parser-run-manifest`, version 1. Serialize twice and assert byte equality and identical SHA-256.

- [ ] **Step 7: Run tests and commit**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_paths.py tests/unit/parser_reproducibility/test_run_manifest.py -v
git add src/ansim_review/parser_reproducibility/paths.py src/ansim_review/parser_reproducibility/run_manifest.py src/ansim_review/contracts/schemas/parser-run-manifest.schema.json tests/unit/parser_reproducibility/test_paths.py tests/unit/parser_reproducibility/test_run_manifest.py
git commit -m "feat: build immutable parser run manifests"
```

---

### Task 3: OpenDataLoader decoding and lossless warning extraction

**Files:**
- Create: `src/ansim_review/parser_reproducibility/opendataloader.py`
- Create: `src/ansim_review/parser_reproducibility/warnings.py`
- Modify: `src/ansim_review/parser_reproducibility/run_manifest.py`
- Modify: `src/ansim_review/parsing/odl_adapter.py`
- Modify: `src/ansim_review/parsing/odl_source.py`
- Create: `src/ansim_review/contracts/schemas/parser-warning-report.schema.json`
- Create: `tests/unit/parser_reproducibility/test_opendataloader.py`
- Create: `tests/unit/parser_reproducibility/test_warnings.py`

**Interfaces:**
- Produces: `OpenDataLoaderArtifact`
- Produces: `ParserWarning`, `ParserWarningReport`, `WarningContext`
- Produces: `decode_opendataloader_json(data: bytes) -> OpenDataLoaderArtifact`
- Produces: `extract_opendataloader_warnings(artifact: OpenDataLoaderArtifact, log_text: str | None, context: WarningContext) -> tuple[ParserWarning, ...]`

- [ ] **Step 1: Add bounded real-shape fixtures**

Create fixture fragments preserving actual OpenDataLoader keys used by the repository: `file name`, `number of pages`, `kids`, `type`, `page number`, `bounding box`, `content`, table row/cell structures, image references, and warning fields. Remove proprietary long text while preserving structure and hashes documented in `fixtures/README.md`.

- [ ] **Step 2: Write decoder tests**

```python
def test_decoder_preserves_raw_payload_and_page_order() -> None:
    artifact = decode_opendataloader_json(FIXTURE.read_bytes())
    assert artifact.page_count == 2
    assert artifact.page_numbers == (1, 2)
    assert artifact.raw_payload["kids"][0]["page number"] == 1


def test_decoder_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        decode_opendataloader_json(b'{"kids":[],"kids":[]}')
```

- [ ] **Step 3: Write warning taxonomy and preservation tests**

```python
def test_unknown_warning_preserves_exact_message() -> None:
    message = "page 4: strange condition at C:\\tmp\\run-a\\image.png"
    warnings = extract_opendataloader_warnings(
        minimal_artifact(), message, warning_context(page_count=4)
    )
    assert warnings[0].code == "PARSER_WARNING_UNKNOWN"
    assert warnings[0].raw_message == message
    assert warnings[0].page_number == 4
```

Add explicit forms for text, table, image, layout, and page warnings. Do not classify based on broad keyword guesses.

- [ ] **Step 4: Run tests and verify failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_opendataloader.py tests/unit/parser_reproducibility/test_warnings.py -v
```

- [ ] **Step 5: Implement read-only artifact model**

```python
@dataclass(frozen=True, slots=True)
class OpenDataLoaderArtifact:
    raw_payload: JsonObject
    page_numbers: tuple[int, ...]
    page_count: int
```

Reuse or extract pure metadata helpers from `odl_source.py`. Ingestion may use shared decoding helpers, but must not depend on reproducibility reports or warning queues.

- [ ] **Step 6: Implement exact warning mapping**

```python
WARNING_CODE_MAP = {
    "TEXT_EXTRACTION_FAILED": "PARSER_WARNING_TEXT_EXTRACTION",
    "TABLE_EXTRACTION_FAILED": "PARSER_WARNING_TABLE_EXTRACTION",
    "IMAGE_EXTRACTION_FAILED": "PARSER_WARNING_IMAGE_EXTRACTION",
    "LAYOUT_WARNING": "PARSER_WARNING_LAYOUT",
    "PAGE_WARNING": "PARSER_WARNING_PAGE",
}
```

Log page recognition supports only tested forms `page 4`, `page=4`, and `[page 4]`. Other numbers remain document-level.

- [ ] **Step 7: Implement stable warning identity**

```python
def warning_id_for(warning: ParserWarning) -> str:
    authority = {
        "source_sha256": warning.source_sha256,
        "parser_kind": warning.parser_kind,
        "parser_version": warning.parser_version,
        "configuration_sha256": warning.configuration_sha256,
        "page_number": warning.page_number,
        "code": warning.code,
        "normalized_message_sha256": warning.normalized_message_sha256,
    }
    return "PWRN-" + hashlib.sha256(dump_bytes(authority)).hexdigest()[:24].upper()
```

Raw warning text remains unchanged. Identity normalization is limited to line endings, an approved run-root token, and separators inside approved run-local paths.

- [ ] **Step 8: Replace Task 2 private page/warning extraction and run tests**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_opendataloader.py tests/unit/parser_reproducibility/test_warnings.py tests/unit/parser_reproducibility/test_run_manifest.py -v
```

- [ ] **Step 9: Commit**

```powershell
git add src/ansim_review/parser_reproducibility/opendataloader.py src/ansim_review/parser_reproducibility/warnings.py src/ansim_review/parser_reproducibility/run_manifest.py src/ansim_review/parsing/odl_adapter.py src/ansim_review/parsing/odl_source.py src/ansim_review/contracts/schemas/parser-warning-report.schema.json tests/unit/parser_reproducibility tests/integration/parser_reproducibility/fixtures
git commit -m "feat: preserve OpenDataLoader parser warnings"
```

---

### Task 4: Closed normalization profile

**Files:**
- Create: `src/ansim_review/parser_reproducibility/normalization.py`
- Create: `tests/unit/parser_reproducibility/test_normalization.py`

**Interfaces:**
- Produces: `NormalizedJson`, `NormalizedMarkdown`, `AppliedNormalization`
- Produces: `normalize_json_artifact(payload: JsonValue, config: ReproducibilityConfig, run_root: Path) -> NormalizedJson`
- Produces: `normalize_markdown_artifact(data: bytes, run_root: Path) -> NormalizedMarkdown`

- [ ] **Step 1: Write exact allowlist tests**

```python
def test_only_approved_metadata_is_replaced(tmp_path: Path) -> None:
    payload = {
        "metadata": {
            "parsed_at": "2026-08-03T00:00:00Z",
            "output_directory": str(tmp_path / "run-a"),
            "title": "Title",
        },
        "kids": [{"content": "A  B", "bounding box": [1, 2, 3, 4]}],
    }
    result = normalize_json_artifact(payload, config(), tmp_path / "run-a")
    assert result.value["metadata"]["parsed_at"] == "<NONDETERMINISTIC>"
    assert result.value["metadata"]["output_directory"] == "<RUN_ROOT>"
    assert result.value["metadata"]["title"] == "Title"
    assert result.value["kids"][0]["content"] == "A  B"
    assert result.value["kids"][0]["bounding box"] == [1, 2, 3, 4]
```

- [ ] **Step 2: Write Markdown boundary tests**

Verify UTF-8 BOM removal, CRLF-to-LF conversion, approved run-root replacement, and separator normalization. Assert trailing spaces, blank-line count, table spacing, heading order, body whitespace, and image order remain meaningful.

- [ ] **Step 3: Run tests and verify failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_normalization.py -v
```

- [ ] **Step 4: Implement exact JSON path replacement**

Parse allowlist paths into object-key components only. Do not support array indices, wildcards, recursion, predicates, or missing-field insertion. Deep-copy comparison values and leave the original decoded object unchanged.

- [ ] **Step 5: Implement bounded Markdown normalization**

```python
def normalize_markdown_artifact(data: bytes, run_root: Path) -> NormalizedMarkdown:
    text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    for root_form in approved_root_forms(run_root):
        text = text.replace(root_form, "<RUN_ROOT>")
    encoded = text.encode("utf-8")
    return NormalizedMarkdown(
        text=text,
        canonical_bytes=encoded,
        sha256=hashlib.sha256(encoded).hexdigest().upper(),
        applied=applied_markdown_normalizations(data, text),
    )
```

Do not use `.strip()`, whitespace split/join, Unicode normalization, Markdown re-rendering, or section sorting.

- [ ] **Step 6: Run tests and commit**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_normalization.py -v
git add src/ansim_review/parser_reproducibility/normalization.py tests/unit/parser_reproducibility/test_normalization.py
git commit -m "feat: add closed parser normalization profile"
```

---

### Task 5: Structural comparison and status selection

**Files:**
- Create: `src/ansim_review/parser_reproducibility/comparison.py`
- Create: `src/ansim_review/contracts/schemas/parser-reproducibility-report.schema.json`
- Create: `tests/unit/parser_reproducibility/test_comparison.py`

**Interfaces:**
- Produces: `ParsedRun`, `ParsedRunPair`, `StructuralDifference`, `ComparisonResult`
- Produces: `compare_parser_runs(pair: ParsedRunPair, config: ReproducibilityConfig) -> ComparisonResult`

- [ ] **Step 1: Write status tests using one consistent signature**

```python
def test_raw_equality_is_byte_identical() -> None:
    result = compare_parser_runs(run_pair(raw_equal=True), config())
    assert result.status == "BYTE_IDENTICAL"
    assert result.differences == ()


def test_environment_difference_makes_no_equivalence_claim() -> None:
    result = compare_parser_runs(run_pair(parser_versions=("1.2.3", "1.2.4")), config())
    assert result.status == "ENVIRONMENT_MISMATCH"
    assert result.canonical_equivalent is None


def test_approved_timestamp_difference_is_semantically_identical() -> None:
    result = compare_parser_runs(run_pair(parsed_at_differs=True), config())
    assert result.status == "SEMANTICALLY_IDENTICAL"
```

- [ ] **Step 2: Write mutation matrix**

```python
@pytest.mark.parametrize(
    ("mutation", "kind"),
    [
        (change_text, "TEXT_CONTENT_CHANGED"),
        (change_table_cell, "TABLE_CELL_VALUE_CHANGED"),
        (change_bbox, "BOUNDING_BOX_CHANGED"),
        (swap_pages, "PAGE_ORDER_CHANGED"),
        (remove_element, "ELEMENT_REMOVED"),
        (change_relationship, "RELATIONSHIP_CHANGED"),
        (change_markdown, "MARKDOWN_CONTENT_CHANGED"),
        (add_warning, "WARNING_ADDED"),
        (move_warning_page, "WARNING_CHANGED"),
    ],
)
def test_meaningful_changes_fail_closed(mutation, kind: str) -> None:
    result = compare_parser_runs(mutation(run_pair()), config())
    assert result.status == "MISMATCH"
    assert kind in {difference.kind for difference in result.differences}
```

- [ ] **Step 3: Run tests and verify failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_comparison.py -v
```

- [ ] **Step 4: Implement recursive comparison**

Dictionaries compare by sorted key. Lists compare by position. Numbers compare exactly with no coordinate tolerance. Differences contain canonical paths, bounded summaries, and SHA-256 values rather than large extracted text.

```python
@dataclass(frozen=True, slots=True)
class ParsedRunPair:
    left: ParsedRun
    right: ParsedRun
```

- [ ] **Step 5: Implement stable difference taxonomy**

Use explicit mapping for page count/order, element add/remove/type, text, table structure/cell, image occurrence, bbox, relationship, Markdown, warning add/remove/change, and unapproved nondeterminism. Tests cover every mapping branch.

- [ ] **Step 6: Implement exact status precedence**

```text
PARSER_FAILED
ENVIRONMENT_MISMATCH
BYTE_IDENTICAL
SEMANTICALLY_IDENTICAL
MISMATCH
```

`BYTE_IDENTICAL` requires raw JSON, raw Markdown, and normalized warning collections to match.

- [ ] **Step 7: Run tests and commit**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_comparison.py tests/unit/parser_reproducibility/test_normalization.py tests/unit/parser_reproducibility/test_warnings.py -v
git add src/ansim_review/parser_reproducibility/comparison.py src/ansim_review/contracts/schemas/parser-reproducibility-report.schema.json tests/unit/parser_reproducibility/test_comparison.py
git commit -m "feat: compare parser artifacts deterministically"
```

---

### Task 6: Stable warning review queue

**Files:**
- Create: `src/ansim_review/parser_reproducibility/queue.py`
- Create: `src/ansim_review/contracts/schemas/parser-review-queue.schema.json`
- Create: `tests/unit/parser_reproducibility/test_queue.py`

**Interfaces:**
- Produces: `ParserReviewQueue`, `ParserReviewQueueEntry`
- Produces: `build_review_queue(warnings: Sequence[ParserWarning], run_id: str, previous: ParserReviewQueue | None = None) -> ParserReviewQueue`

- [ ] **Step 1: Write deduplication and history tests**

```python
def test_repeated_warning_updates_one_entry() -> None:
    warning = parser_warning(page_number=3)
    first = build_review_queue((warning,), "PRUN-A")
    second = build_review_queue((warning, warning), "PRUN-B", first)
    assert len(second.entries) == 1
    assert second.entries[0].status == "REVIEW_REQUIRED"
    assert second.entries[0].first_seen_run_id == "PRUN-A"
    assert second.entries[0].last_seen_run_id == "PRUN-B"
    assert second.entries[0].occurrence_count == 3


def test_absent_warning_does_not_delete_history() -> None:
    previous = build_review_queue((parser_warning(),), "PRUN-A")
    current = build_review_queue((), "PRUN-B", previous)
    assert current.entries == previous.entries
```

- [ ] **Step 2: Test stable key inputs**

Changing source hash, parser version, configuration hash, page, warning code, or normalized message hash changes queue ID. Changing absolute run root, timestamp, file name, or log line number does not.

- [ ] **Step 3: Run tests and verify failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_queue.py -v
```

- [ ] **Step 4: Implement immutable merge**

```python
def build_review_queue(
    warnings: Sequence[ParserWarning],
    run_id: str,
    previous: ParserReviewQueue | None = None,
) -> ParserReviewQueue:
    entries = {entry.queue_id: entry for entry in (() if previous is None else previous.entries)}
    for warning in sorted(warnings, key=warning_sort_key):
        queue_id = queue_id_for(warning)
        existing = entries.get(queue_id)
        entries[queue_id] = new_entry(warning, run_id) if existing is None else replace(
            existing,
            last_seen_run_id=run_id,
            occurrence_count=existing.occurrence_count + 1,
        )
    return ParserReviewQueue(entries=tuple(sorted(entries.values(), key=queue_sort_key)))
```

Strictly decode prior queue artifacts; malformed history is an error rather than an empty reset.

- [ ] **Step 5: Add schema, deterministic byte tests, and commit**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_queue.py -v
git add src/ansim_review/parser_reproducibility/queue.py src/ansim_review/contracts/schemas/parser-review-queue.schema.json tests/unit/parser_reproducibility/test_queue.py
git commit -m "feat: add parser warning review queue"
```

---

### Task 7: Public reports and pure orchestration

**Files:**
- Create: `src/ansim_review/parser_reproducibility/report.py`
- Modify: `src/ansim_review/parser_reproducibility/__init__.py`
- Create: `tests/unit/parser_reproducibility/test_report.py`

**Interfaces:**
- Produces: `validate_opendataloader_reproducibility(source_pdf: Path, run_a_root: Path, run_b_root: Path, config: ReproducibilityConfig) -> ParserReproducibilityReport`
- Produces: `collect_opendataloader_warnings(source_pdf: Path, run_root: Path, config: ReproducibilityConfig, previous_queue: ParserReviewQueue | None = None) -> WarningCollectionResult`
- Produces: `report_bytes(report: CanonicalReport) -> bytes`

- [ ] **Step 1: Write immutability and path-leak tests**

```python
def test_validation_does_not_modify_inputs(tmp_path: Path) -> None:
    source, run_a, run_b = write_equal_runs(tmp_path)
    before = tree_hashes(tmp_path)
    report = validate_opendataloader_reproducibility(source, run_a, run_b, config())
    assert report.status == "BYTE_IDENTICAL"
    assert tree_hashes(tmp_path) == before


def test_report_has_no_machine_absolute_path(tmp_path: Path) -> None:
    source, run_a, run_b = write_semantically_equal_runs(tmp_path)
    encoded = report_bytes(validate_opendataloader_reproducibility(source, run_a, run_b, config()))
    assert str(tmp_path).encode("utf-8") not in encoded
```

- [ ] **Step 2: Write deterministic report tests**

Create the same report twice and assert identical bytes and SHA-256. Verify deterministic sorting of run summaries, normalizations, warnings, differences, counts, and summary text.

- [ ] **Step 3: Run tests and verify failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_report.py -v
```

- [ ] **Step 4: Implement orchestration**

Public functions read inputs and return frozen models only. Convert expected validation exceptions into deterministic `PARSER_FAILED` findings. Do not catch `KeyboardInterrupt` or `SystemExit`.

- [ ] **Step 5: Implement canonical report dictionaries**

Use existing `dump_bytes`. Do not include `datetime.now()`, temp paths, unordered sets, object repr, or raw exception repr. Difference and warning content uses bounded summaries and hashes.

- [ ] **Step 6: Export only public interfaces**

Keep normalization internals, raw adapter helpers, and queue key helpers private.

- [ ] **Step 7: Run package tests and commit**

```powershell
python -m pytest tests/unit/parser_reproducibility -v
git add src/ansim_review/parser_reproducibility/__init__.py src/ansim_review/parser_reproducibility/report.py tests/unit/parser_reproducibility/test_report.py
git commit -m "feat: emit canonical parser reproducibility reports"
```

---

### Task 8: CLI and atomic create-only outputs

**Files:**
- Create: `src/ansim_review/parser_reproducibility/cli.py`
- Modify: `src/ansim_review/cli_parser.py`
- Modify: `src/ansim_review/cli.py`
- Modify: `tests/unit/test_cli_parser.py`
- Create: `tests/integration/parser_reproducibility/test_cli.py`

**Interfaces:**
- Produces CLI: `evidence-review parser reproducibility validate`
- Produces CLI: `evidence-review parser warnings collect`
- Exit codes: 0 equivalent/collection success; 1 mismatch; 2 usage/config/environment/existing output; 3 parser failure.

- [ ] **Step 1: Write parser-shape tests**

```python
def test_reproducibility_cli_shape() -> None:
    args = build_parser().parse_args(
        [
            "parser", "reproducibility", "validate",
            "--source", "source.pdf",
            "--run-a", "run-a",
            "--run-b", "run-b",
            "--config", "parser-reproducibility.json",
            "--output", "report.json",
        ]
    )
    assert (args.command, args.parser_stage, args.parser_action) == (
        "parser", "reproducibility", "validate"
    )
```

Add the warning command with `--source`, `--run`, `--config`, `--warning-output`, `--queue-output`, and optional `--previous-queue`.

- [ ] **Step 2: Write create-only integration tests**

Cover existing single output, either existing multi-output destination, mismatch report with exit 1, environment report with exit 2, parser failure report with exit 3, simulated write failure cleanup, and two concurrent writers where exactly one succeeds.

- [ ] **Step 3: Run tests and verify failure**

```powershell
python -m pytest tests/unit/test_cli_parser.py tests/integration/parser_reproducibility/test_cli.py -v
```

- [ ] **Step 4: Extend dependency-safe parser construction**

Add nested subparsers in `cli_parser.py` without importing the parser reproducibility package. This preserves documentation static command validation.

- [ ] **Step 5: Implement destination reservation**

```python
def reserve_outputs(paths: Sequence[Path]) -> tuple[int, ...]:
    descriptors: list[int] = []
    try:
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptors.append(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        return tuple(descriptors)
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        for path in paths[: len(descriptors)]:
            path.unlink(missing_ok=True)
        raise
```

Write canonical bytes to reserved descriptors, flush, `os.fsync`, close, and remove every reserved path if a multi-output write fails.

- [ ] **Step 6: Add lazy dispatch and stable stdout**

Import `parser_reproducibility.cli` only after selecting the parser command. Stdout contains status and counts; stderr contains usage/config errors. Persistent reports contain no absolute paths.

- [ ] **Step 7: Run tests and commit**

```powershell
python -m pytest tests/unit/test_cli_parser.py tests/integration/parser_reproducibility/test_cli.py -v
git add src/ansim_review/parser_reproducibility/cli.py src/ansim_review/cli_parser.py src/ansim_review/cli.py tests/unit/test_cli_parser.py tests/integration/parser_reproducibility/test_cli.py
git commit -m "feat: expose parser reproducibility CLI"
```

---

### Task 9: Text, table, and warning acceptance matrix

**Files:**
- Create: `tests/integration/parser_reproducibility/fixtures/README.md`
- Create: `tests/integration/parser_reproducibility/fixtures/manifest.json`
- Create: `tests/integration/parser_reproducibility/fixtures/text/**`
- Create: `tests/integration/parser_reproducibility/fixtures/table/**`
- Create: `tests/integration/parser_reproducibility/fixtures/warning/**`
- Create: `tests/integration/parser_reproducibility/test_reproducibility_matrix.py`
- Create: `tests/integration/parser_reproducibility/test_warning_collection.py`

**Interfaces:**
- Consumes: public Python API and CLI
- Produces: redistributable deterministic fixtures with recorded source/artifact hashes and expected statuses.

- [ ] **Step 1: Define strict fixture manifest**

```json
{
  "format": "evidence-review/parser-reproducibility-fixtures",
  "version": 1,
  "cases": [
    {
      "id": "TEXT-BYTE-IDENTICAL",
      "source": "text/source.pdf",
      "run_a": "text/run-a",
      "run_b": "text/run-b",
      "expected_status": "BYTE_IDENTICAL",
      "expected_difference_kinds": [],
      "source_sha256": "uppercase SHA-256"
    }
  ]
}
```

The test decoder verifies exact fields, referenced paths, and recorded hashes.

- [ ] **Step 2: Add three legal fixtures**

Use deterministic generated minimal PDFs or redistributable samples:

- text: two pages and headings;
- table: one 2x3 table with cell coordinates;
- warning: captured stable layout/table/image/page warning.

Do not add proprietary PDFs. Every run directory includes `document.json`, `document.md`, `parser-run.json`, and optional `parser.log`.

- [ ] **Step 3: Add required cases**

```text
BYTE_IDENTICAL
SEMANTICALLY_IDENTICAL parsed_at
SEMANTICALLY_IDENTICAL run-root path
MISMATCH text
MISMATCH table cell
MISMATCH bbox
MISMATCH page order
MISMATCH warning added
MISMATCH warning page moved
ENVIRONMENT_MISMATCH parser version
ENVIRONMENT_MISMATCH parser configuration
PARSER_FAILED missing Markdown
```

Tests copy fixture trees to `tmp_path` before mutation.

- [ ] **Step 4: Write one consistent matrix test**

```python
@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case.id)
def test_reproducibility_matrix(case: FixtureCase, tmp_path: Path) -> None:
    prepared = copy_case(case, tmp_path)
    report = validate_opendataloader_reproducibility(
        prepared.source, prepared.run_a, prepared.run_b, repository_config()
    )
    assert report.status == case.expected_status
    assert {item.kind for item in report.differences} == set(case.expected_difference_kinds)
```

- [ ] **Step 5: Write warning queue tests**

Verify all taxonomy codes, unknown raw-message preservation, page association, queue deduplication, historical retention, stable IDs, report byte identity, and create-only behavior through the CLI.

- [ ] **Step 6: Run the matrix twice and commit**

```powershell
python -m pytest tests/integration/parser_reproducibility -v
python -m pytest tests/integration/parser_reproducibility -v
git add tests/integration/parser_reproducibility
git commit -m "test: add OpenDataLoader reproducibility matrix"
```

---

### Task 10: Current documentation, wheel verification, and manual acceptance

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `skills/01-preserving-and-parsing-pdfs/SKILL.md`
- Modify: `tests/integration/documentation_integrity/test_repository_acceptance.py`
- Modify: `pyproject.toml` only when schema package data requires it
- Create: `tests/integration/parser_reproducibility/test_wheel_resources.py`
- Create: `docs/acceptance/issue-52/README.md`
- Modify: `documentation-integrity.json`

**Interfaces:**
- Produces: executable current guidance, installed-wheel schema access, and exact manual acceptance evidence.

- [ ] **Step 1: Write documentation assertions first**

Require exact commands:

```text
evidence-review parser reproducibility validate --help
evidence-review parser warnings collect --help
```

Require statements that raw artifacts are immutable, warnings require review, mismatch blocks reproducibility acceptance, environment mismatch makes no equivalence claim, outputs are create-only, and validation does not invoke OpenDataLoader.

- [ ] **Step 2: Update README, AGENTS, and Stage 1 skill**

Document `parser-run.json` exact purpose and required fields. Use repository-relative examples only. Do not add deprecated wrappers, drive-specific paths, or GitHub Actions as an acceptance requirement.

- [ ] **Step 3: Validate documentation twice**

```powershell
python -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output build/issue52-doc-a.json
python -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output build/issue52-doc-b.json
python -c "from pathlib import Path; import hashlib; a=Path('build/issue52-doc-a.json').read_bytes(); b=Path('build/issue52-doc-b.json').read_bytes(); assert a == b; print(hashlib.sha256(a).hexdigest().upper())"
```

Expected: PASS, zero errors, byte-identical reports.

- [ ] **Step 4: Write installed-resource tests**

Use `importlib.resources.files("ansim_review.contracts.schemas")` to read all six new schemas from an installed wheel. Assert canonical and compatibility namespaces expose identical public objects.

- [ ] **Step 5: Run targeted and full gates**

```powershell
python -m pytest tests/unit/parser_reproducibility tests/integration/parser_reproducibility -v
python -m pytest -v
python -m ruff check src tests
python -m mypy src
python -m compileall -q src scripts web_runtime tests
git diff --check origin/main...HEAD
```

Every command exits 0.

- [ ] **Step 6: Build and install Python 3.11 wheel**

```powershell
py -3.11 -m venv build/issue52-build-311
build/issue52-build-311/Scripts/python.exe -m pip install --upgrade pip build
build/issue52-build-311/Scripts/python.exe -m build --wheel --outdir build/issue52-dist-311
py -3.11 -m venv build/issue52-test-311
$Wheel311 = (Get-ChildItem build/issue52-dist-311/*.whl | Select-Object -First 1).FullName
build/issue52-test-311/Scripts/python.exe -m pip install $Wheel311
build/issue52-test-311/Scripts/python.exe -m pip check
build/issue52-test-311/Scripts/evidence-review.exe parser reproducibility validate --help
build/issue52-test-311/Scripts/evidence-review.exe parser warnings collect --help
build/issue52-test-311/Scripts/python.exe -m evidence_review parser reproducibility validate --help
build/issue52-test-311/Scripts/python.exe -m ansim_review parser warnings collect --help
```

Run an actual text fixture comparison from outside the checkout with `PYTHONPATH` cleared and assert exit 0/`BYTE_IDENTICAL`.

- [ ] **Step 7: Repeat wheel acceptance with Python 3.13**

Use directories ending `313`, record both wheel SHA-256 values, and do not commit wheels or virtual environments.

- [ ] **Step 8: Write acceptance ledger**

Record repository, branch, implementation HEAD, platform, Python versions, config hash, fixture hashes, targeted/full pytest, Ruff, mypy, compileall, diff check, documentation report count/hash, status matrix, warning/queue hashes, create-only/concurrency results, wheel hashes, installed-wheel execution, GitHub Actions exclusion, and human review still required.

- [ ] **Step 9: Commit ledger and run post-ledger gates**

```powershell
git add README.md AGENTS.md skills/01-preserving-and-parsing-pdfs/SKILL.md pyproject.toml documentation-integrity.json tests/integration/documentation_integrity/test_repository_acceptance.py tests/integration/parser_reproducibility/test_wheel_resources.py docs/acceptance/issue-52/README.md
git commit -m "docs: record issue 52 manual acceptance"
python -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output build/issue52-post-ledger-doc.json
python -m pytest -v
python -m ruff check src tests
python -m mypy src
python -m compileall -q src scripts web_runtime tests
git diff --check origin/main...HEAD
git status --short
```

- [ ] **Step 10: Push and create Draft PR**

PR title:

```text
feat: validate OpenDataLoader parser reproducibility
```

PR body and Issue #52 comment contain exact implementation/evidence HEADs and all manual acceptance hashes. Parent Issue #27 receives a concise progress update. Do not mark Ready, merge, or close #52/#27 before explicit human review.

---

## Self-Review

- Every approved design requirement maps to a task.
- The comparison API is consistently `compare_parser_runs(pair, config)` in interfaces and tests.
- The immutable `parser-run.json` sidecar resolves parser version/configuration authority without modifying OpenDataLoader output.
- Warning presence and parser failure remain separate states.
- Evidence retrieval, calculation, rule execution, release-wide golden matrices, and OpenDataLoader algorithm changes remain outside scope.
- The plan contains no unresolved markers or deferred implementation steps.
