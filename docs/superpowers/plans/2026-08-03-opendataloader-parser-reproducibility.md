# OpenDataLoader Parser Warning and Reproducibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic OpenDataLoader parser warning collection and two-run JSON/Markdown reproducibility validation with fail-closed mismatch detection and canonical create-only reports.

**Architecture:** Add an isolated `parser_reproducibility` package that strictly decodes repository-owned configuration, builds immutable run manifests from source and parser artifacts, extracts warnings, applies a closed normalization profile in memory, compares raw and canonical forms, and emits stable reports and review queues. Integrate the package through the existing shared CLI parser and canonical JSON writer without changing source PDFs, raw parser outputs, downstream evidence ingestion, rules, calculations, or release-wide golden behavior.

**Tech Stack:** Python 3.11+, frozen dataclasses, `pathlib`, `hashlib`, strict JSON decoding, existing `ansim_review.canonical_json`, existing source-batch contracts, pytest, Ruff, strict mypy, compileall, isolated wheel builds for Python 3.11 and 3.13.

## Global Constraints

- Support only parser kind `opendataloader` in version 1.
- Original PDFs and raw OpenDataLoader JSON, Markdown, logs, and images are immutable inputs.
- Normalization is comparison-only and must never write normalized replacements beside raw artifacts.
- The normalization allowlist is repository-owned, versioned, closed, and contains no wildcards or user executable code.
- Unexpected text, table, image, coordinate, page, relationship, warning, or ordering differences are `MISMATCH`.
- Parser version, adapter version, parser configuration SHA-256, or normalization profile differences are `ENVIRONMENT_MISMATCH`.
- Parser warnings are preserved and queued as `REVIEW_REQUIRED`; warning presence alone is not `PARSER_FAILED`.
- Canonical outputs use UTF-8 without BOM, LF endings, sorted keys, stable list ordering, relative POSIX paths, no equality-sensitive timestamps, and a trailing newline.
- Every CLI output is create-only. Multi-output commands preflight all destinations and must not leave partial outputs.
- Runtime code remains offline and must not call OpenDataLoader, remote APIs, or external services during validation.
- GitHub Actions is not an acceptance dependency. Local manual acceptance records exact HEAD, platform, Python versions, commands, exit codes, and artifact hashes.
- Implementation begins from branch `agent/issue-52-opendataloader-reproducibility` after confirming it contains spec commit `b31113479a02e63aa22277f1c7354e00fe26c274` and a clean worktree.

---

## Planned File Structure

```text
parser-reproducibility.json
src/ansim_review/parser_reproducibility/
├─ __init__.py
├─ contract.py
├─ paths.py
├─ run_manifest.py
├─ opendataloader.py
├─ normalization.py
├─ warnings.py
├─ comparison.py
├─ queue.py
├─ report.py
└─ cli.py
src/ansim_review/contracts/schemas/
├─ parser-reproducibility-config.schema.json
├─ parser-run-manifest.schema.json
├─ parser-reproducibility-report.schema.json
├─ parser-warning-report.schema.json
└─ parser-review-queue.schema.json
tests/unit/parser_reproducibility/
├─ test_contract.py
├─ test_paths.py
├─ test_run_manifest.py
├─ test_opendataloader.py
├─ test_normalization.py
├─ test_warnings.py
├─ test_comparison.py
├─ test_queue.py
└─ test_report.py
tests/integration/parser_reproducibility/
├─ test_cli.py
├─ test_reproducibility_matrix.py
├─ test_warning_collection.py
└─ fixtures/
   ├─ text/
   ├─ table/
   └─ warning/
docs/acceptance/issue-52/
└─ README.md
```

Existing files to modify:

```text
src/ansim_review/cli_parser.py
src/ansim_review/cli.py
src/ansim_review/contracts/schemas/__init__.py
src/ansim_review/parsing/odl_adapter.py
tests/unit/contracts/test_schema_documents.py
tests/unit/test_cli_parser.py
tests/integration/parsing/test_source_batch_cli.py
documentation-integrity.json
README.md
AGENTS.md
skills/01-preserving-and-parsing-pdfs/SKILL.md
pyproject.toml
```

---

### Task 1: Register current authority and strict configuration contract

**Files:**
- Create: `parser-reproducibility.json`
- Create: `src/ansim_review/parser_reproducibility/__init__.py`
- Create: `src/ansim_review/parser_reproducibility/contract.py`
- Create: `src/ansim_review/contracts/schemas/parser-reproducibility-config.schema.json`
- Modify: `src/ansim_review/contracts/schemas/__init__.py`
- Modify: `tests/unit/contracts/test_schema_documents.py`
- Create: `tests/unit/parser_reproducibility/test_contract.py`
- Modify: `documentation-integrity.json`

**Interfaces:**
- Produces: `ReproducibilityConfig`, `decode_reproducibility_config(data: bytes) -> ReproducibilityConfig`
- Produces: `NormalizationProfileName = Literal["opendataloader-v1"]`
- Produces: `ParserKind = Literal["opendataloader"]`
- Consumes later: Tasks 2 through 9 use the decoded immutable configuration.

- [ ] **Step 1: Write failing strict-decoder tests**

```python
from __future__ import annotations

import json

import pytest

from ansim_review.parser_reproducibility.contract import (
    ReproducibilityConfig,
    decode_reproducibility_config,
)


def valid_payload() -> dict[str, object]:
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


def decode(payload: dict[str, object]) -> ReproducibilityConfig:
    return decode_reproducibility_config(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )


def test_decodes_exact_v1_contract() -> None:
    config = decode(valid_payload())
    assert config.parser_kind == "opendataloader"
    assert config.adapter_version == 1
    assert config.json_artifact_names == ("document.json",)
    assert config.allowed_nondeterministic_fields == (
        "$.metadata.parsed_at",
        "$.metadata.output_directory",
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"extra": True}, "unknown field"),
        ({"parser_kind": "other"}, "unsupported parser kind"),
        ({"normalization_profile": "other-v1"}, "unsupported normalization profile"),
        ({"json_artifact_names": ["C:\\absolute.json"]}, "backslash"),
        ({"warning_sources": ["../parser.log"]}, "unsafe path"),
        ({"allowed_nondeterministic_fields": ["$..parsed_at"]}, "recursive"),
        ({"allowed_nondeterministic_fields": ["$.pages[*].id"]}, "wildcard"),
    ],
)
def test_rejects_invalid_contract(mutation: dict[str, object], message: str) -> None:
    payload = valid_payload()
    payload.update(mutation)
    with pytest.raises(ValueError, match=message):
        decode(payload)
```

- [ ] **Step 2: Run the decoder tests and confirm failure**

Run:

```powershell
python -m pytest tests/unit/parser_reproducibility/test_contract.py -v
```

Expected: collection fails because `ansim_review.parser_reproducibility.contract` does not exist.

- [ ] **Step 3: Implement immutable config models and duplicate-key rejection**

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


def decode_reproducibility_config(data: bytes) -> ReproducibilityConfig:
    payload = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique_object)
    if not isinstance(payload, dict):
        raise ValueError("configuration must be an object")
    _require_exact_keys(payload, _CONFIG_KEYS)
    _require_literal(payload, "format", "evidence-review/parser-reproducibility-config")
    _require_literal(payload, "version", 1)
    return ReproducibilityConfig(
        parser_kind=_decode_parser_kind(payload["parser_kind"]),
        adapter_version=_decode_adapter_version(payload["adapter_version"]),
        json_artifact_names=_decode_artifact_names(payload["json_artifact_names"]),
        markdown_artifact_names=_decode_artifact_names(payload["markdown_artifact_names"]),
        warning_sources=_decode_artifact_names(payload["warning_sources"]),
        normalization_profile=_decode_profile(payload["normalization_profile"]),
        allowed_nondeterministic_fields=_decode_allowlist(
            payload["allowed_nondeterministic_fields"]
        ),
    )
```

Implement the closed v1 allowlist as a constant containing only:

```python
OPENDATALOADER_V1_ALLOWED_FIELDS = frozenset(
    {
        "$.metadata.parsed_at",
        "$.metadata.output_directory",
    }
)
```

- [ ] **Step 4: Add the repository config and schema**

Write `parser-reproducibility.json` with the exact payload used by `valid_payload()` and LF line endings. Add the schema name to `SCHEMA_FILENAMES` and the schema-document test expected set.

- [ ] **Step 5: Register the active spec and plan as current documentation**

Add these exact paths to `current_overrides` in `documentation-integrity.json`:

```json
"docs/superpowers/specs/2026-08-03-opendataloader-parser-reproducibility-design.md",
"docs/superpowers/plans/2026-08-03-opendataloader-parser-reproducibility.md"
```

Keep the array sorted with the repository's existing ordering rule.

- [ ] **Step 6: Run focused tests and documentation validation**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_contract.py tests/unit/contracts/test_schema_documents.py -v
python -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output build/issue52-task1-documentation.json
```

Expected: all tests pass; documentation report has `status=PASS` and `error_count=0`.

- [ ] **Step 7: Commit the contract**

```powershell
git add parser-reproducibility.json documentation-integrity.json src/ansim_review/parser_reproducibility src/ansim_review/contracts/schemas tests/unit/parser_reproducibility/test_contract.py tests/unit/contracts/test_schema_documents.py
git commit -m "feat: define parser reproducibility contracts"
```

---

### Task 2: Safe relative paths and parser run manifest construction

**Files:**
- Create: `src/ansim_review/parser_reproducibility/paths.py`
- Create: `src/ansim_review/parser_reproducibility/run_manifest.py`
- Create: `src/ansim_review/contracts/schemas/parser-run-manifest.schema.json`
- Create: `tests/unit/parser_reproducibility/test_paths.py`
- Create: `tests/unit/parser_reproducibility/test_run_manifest.py`

**Interfaces:**
- Consumes: `ReproducibilityConfig`
- Produces: `resolve_run_artifact(root: Path, relative_name: str) -> Path`
- Produces: `canonical_relative_path(root: Path, path: Path) -> str`
- Produces: `ParserRunManifest`
- Produces: `build_parser_run_manifest(source_pdf: Path, run_root: Path, config: ReproducibilityConfig) -> ParserRunManifest`

- [ ] **Step 1: Write path-safety tests**

```python
from pathlib import Path

import pytest

from ansim_review.parser_reproducibility.paths import (
    canonical_relative_path,
    resolve_run_artifact,
)


def test_resolves_regular_file_under_root(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    artifact = root / "document.json"
    artifact.write_text("{}", encoding="utf-8")
    assert resolve_run_artifact(root, "document.json") == artifact.resolve()
    assert canonical_relative_path(root, artifact) == "document.json"


@pytest.mark.parametrize("value", ["../x", "/x", "C:/x", "a\\b", "a/./b"])
def test_rejects_unsafe_relative_names(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError):
        resolve_run_artifact(tmp_path, value)
```

Add a Windows junction/symlink escape test when the platform permits symlink creation; skip only on `OSError` from insufficient privilege, not on assertion failure.

- [ ] **Step 2: Write run-manifest characterization tests**

Use a minimal PDF fixture created from checked-in bytes and an OpenDataLoader JSON object with these required metadata fields:

```json
{
  "metadata": {
    "parser": "opendataloader",
    "parser_version": "1.2.3",
    "parser_configuration": {"markdown_with_html": true},
    "page_count": 1
  },
  "pages": [{"page_number": 1, "elements": []}]
}
```

Test that `configuration_sha256` equals the SHA-256 of `dump_bytes(parser_configuration)` and that source/artifact hashes, sizes, page counts, relative paths, warning counts, and sorted warning codes are stable.

- [ ] **Step 3: Run tests and confirm failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_paths.py tests/unit/parser_reproducibility/test_run_manifest.py -v
```

Expected: missing modules or functions.

- [ ] **Step 4: Implement safe path resolution**

`resolve_run_artifact` must:

```python
candidate = (root.resolve() / PurePosixPath(relative_name)).resolve()
try:
    candidate.relative_to(root.resolve())
except ValueError as exc:
    raise ValueError("artifact path escapes run root") from exc
if not candidate.is_file():
    raise ValueError("required parser artifact is missing")
return candidate
```

Reject absolute paths, drive letters, empty components, `.`/`..`, and backslashes before filesystem resolution.

- [ ] **Step 5: Implement run manifest construction**

`build_parser_run_manifest` must:

1. Hash the source PDF without modifying it.
2. Resolve exactly one configured JSON and Markdown artifact. Zero or multiple matches are invalid.
3. Decode JSON as UTF-8 with optional BOM.
4. Read `metadata.parser`, `metadata.parser_version`, `metadata.parser_configuration`, and parser page count through the OpenDataLoader adapter helper introduced in Task 3; until Task 3 lands, define a private strict extractor in `run_manifest.py` and move it in Task 3 without changing behavior.
5. Hash parser configuration using `dump_bytes`.
6. Count warnings using the warning extractor introduced in Task 3; until then return an empty tuple and keep the test fixture warning-free.
7. Build a frozen manifest with no timestamp or absolute path.

- [ ] **Step 6: Add canonical schema and round-trip test**

Add `ParserRunManifest.as_dict()` returning:

```python
{
    "format": "evidence-review/parser-run-manifest",
    "version": 1,
    "source_sha256": self.source_sha256,
    "source_size": self.source_size,
    "source_page_count": self.source_page_count,
    "parser_kind": self.parser_kind,
    "parser_version": self.parser_version,
    "adapter_version": self.adapter_version,
    "configuration_sha256": self.configuration_sha256,
    "platform_family": self.platform_family,
    "json_relative_path": self.json_relative_path,
    "json_sha256": self.json_sha256,
    "json_size": self.json_size,
    "markdown_relative_path": self.markdown_relative_path,
    "markdown_sha256": self.markdown_sha256,
    "markdown_size": self.markdown_size,
    "warning_source_relative_paths": list(self.warning_source_relative_paths),
    "warning_count": self.warning_count,
    "warning_codes": list(self.warning_codes),
    "parser_page_count": self.parser_page_count,
}
```

- [ ] **Step 7: Run focused tests**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_paths.py tests/unit/parser_reproducibility/test_run_manifest.py -v
```

Expected: pass on Windows and Linux path forms.

- [ ] **Step 8: Commit run authority**

```powershell
git add src/ansim_review/parser_reproducibility/paths.py src/ansim_review/parser_reproducibility/run_manifest.py src/ansim_review/contracts/schemas/parser-run-manifest.schema.json tests/unit/parser_reproducibility/test_paths.py tests/unit/parser_reproducibility/test_run_manifest.py
git commit -m "feat: build immutable parser run manifests"
```

---

### Task 3: Decode OpenDataLoader artifacts and extract warnings without loss

**Files:**
- Create: `src/ansim_review/parser_reproducibility/opendataloader.py`
- Create: `src/ansim_review/parser_reproducibility/warnings.py`
- Modify: `src/ansim_review/parser_reproducibility/run_manifest.py`
- Modify: `src/ansim_review/parsing/odl_adapter.py`
- Create: `src/ansim_review/contracts/schemas/parser-warning-report.schema.json`
- Create: `tests/unit/parser_reproducibility/test_opendataloader.py`
- Create: `tests/unit/parser_reproducibility/test_warnings.py`

**Interfaces:**
- Produces: `OpenDataLoaderArtifact`
- Produces: `decode_opendataloader_json(data: bytes) -> OpenDataLoaderArtifact`
- Produces: `extract_opendataloader_warnings(artifact: OpenDataLoaderArtifact, log_text: str | None, context: WarningContext) -> tuple[ParserWarning, ...]`
- Produces: `ParserWarning`, `ParserWarningReport`, `WarningContext`
- Consumes later: Tasks 4 through 9 compare decoded values and warning identities.

- [ ] **Step 1: Add real-shape characterization fixtures**

Check in bounded JSON fragments under `tests/integration/parser_reproducibility/fixtures/` that preserve actual OpenDataLoader field names from existing repository parser artifacts. Remove extracted document text longer than 200 characters per element, but keep metadata, page, element type, IDs, bbox, table rows/cells, image references, links, and warning structures intact.

Document the source artifact hash and OpenDataLoader version in `fixtures/README.md` without adding the original proprietary PDF when it cannot be redistributed.

- [ ] **Step 2: Write strict decoder tests**

```python
def test_decodes_metadata_pages_elements_tables_and_images() -> None:
    artifact = decode_opendataloader_json(FIXTURE.read_bytes())
    assert artifact.parser_kind == "opendataloader"
    assert artifact.parser_version == "1.2.3"
    assert artifact.page_numbers == (1, 2)
    assert artifact.page_count == 2
    assert artifact.raw_payload["pages"][0]["page_number"] == 1


def test_rejects_duplicate_json_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        decode_opendataloader_json(b'{"pages":[],"pages":[]}')
```

- [ ] **Step 3: Write warning preservation and taxonomy tests**

```python
def test_unknown_warning_preserves_raw_message() -> None:
    warnings = extract_opendataloader_warnings(
        artifact=minimal_artifact(),
        log_text="page 4: strange parser condition at C:\\tmp\\run-a\\image.png",
        context=warning_context(page_count=4),
    )
    assert warnings[0].code == "PARSER_WARNING_UNKNOWN"
    assert warnings[0].raw_message == (
        "page 4: strange parser condition at C:\\tmp\\run-a\\image.png"
    )
    assert warnings[0].page_number == 4


def test_table_warning_uses_explicit_taxonomy() -> None:
    warning = warning_from_json("TABLE_EXTRACTION_FAILED", page_number=2)
    assert warning.code == "PARSER_WARNING_TABLE_EXTRACTION"
```

- [ ] **Step 4: Run tests and confirm failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_opendataloader.py tests/unit/parser_reproducibility/test_warnings.py -v
```

- [ ] **Step 5: Implement a read-only adapter model**

The decoder must retain the full JSON value as immutable comparison input while exposing typed metadata accessors. Do not reuse `ParserContribution` as the comparison model because ingestion intentionally discards operational metadata and may reorder records.

```python
@dataclass(frozen=True, slots=True)
class OpenDataLoaderArtifact:
    raw_payload: JsonObject
    parser_kind: str
    parser_version: str
    parser_configuration: JsonObject
    page_numbers: tuple[int, ...]
    page_count: int
```

Share only bounded helper functions with `parsing/odl_adapter.py`, such as metadata lookup and page-number extraction. Do not make the ingestion adapter depend on reproducibility reports.

- [ ] **Step 6: Implement warning classification from explicit forms**

Define an exact mapping table for observed machine codes:

```python
WARNING_CODE_MAP = {
    "TEXT_EXTRACTION_FAILED": "PARSER_WARNING_TEXT_EXTRACTION",
    "TABLE_EXTRACTION_FAILED": "PARSER_WARNING_TABLE_EXTRACTION",
    "IMAGE_EXTRACTION_FAILED": "PARSER_WARNING_IMAGE_EXTRACTION",
    "LAYOUT_WARNING": "PARSER_WARNING_LAYOUT",
    "PAGE_WARNING": "PARSER_WARNING_PAGE",
}
```

For log-only warnings, recognize page numbers only with tested patterns such as `page 4`, `page=4`, or `[page 4]`. Do not infer a page from unrelated numbers.

- [ ] **Step 7: Implement stable warning identity**

```python
def warning_id_for(warning: ParserWarning) -> str:
    identity = {
        "source_sha256": warning.source_sha256,
        "parser_kind": warning.parser_kind,
        "parser_version": warning.parser_version,
        "configuration_sha256": warning.configuration_sha256,
        "page_number": warning.page_number,
        "code": warning.code,
        "normalized_message_sha256": warning.normalized_message_sha256,
    }
    return "PWRN-" + hashlib.sha256(dump_bytes(identity)).hexdigest()[:24].upper()
```

Normalize only CRLF/LF, approved run-root replacement, and path separators for the identity hash. Preserve `raw_message` unchanged in the report.

- [ ] **Step 8: Update run manifest warning summaries and run tests**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_opendataloader.py tests/unit/parser_reproducibility/test_warnings.py tests/unit/parser_reproducibility/test_run_manifest.py -v
```

Expected: warning count and sorted codes match extracted warnings.

- [ ] **Step 9: Commit adapter and warning extraction**

```powershell
git add src/ansim_review/parser_reproducibility/opendataloader.py src/ansim_review/parser_reproducibility/warnings.py src/ansim_review/parser_reproducibility/run_manifest.py src/ansim_review/parsing/odl_adapter.py src/ansim_review/contracts/schemas/parser-warning-report.schema.json tests/unit/parser_reproducibility tests/integration/parser_reproducibility/fixtures
git commit -m "feat: preserve OpenDataLoader parser warnings"
```

---

### Task 4: Closed normalization profile and canonical artifact hashing

**Files:**
- Create: `src/ansim_review/parser_reproducibility/normalization.py`
- Create: `tests/unit/parser_reproducibility/test_normalization.py`

**Interfaces:**
- Consumes: decoded OpenDataLoader JSON, raw Markdown bytes, `ReproducibilityConfig`, run root
- Produces: `NormalizedArtifact`
- Produces: `normalize_json_artifact(payload: JsonValue, config: ReproducibilityConfig, run_root: Path) -> NormalizedJson`
- Produces: `normalize_markdown_artifact(data: bytes, run_root: Path) -> NormalizedMarkdown`
- Produces: `AppliedNormalization(path: str, kind: str)`

- [ ] **Step 1: Write failing allowlist tests**

```python
def test_normalizes_only_approved_metadata_fields(tmp_path: Path) -> None:
    payload = {
        "metadata": {
            "parsed_at": "2026-08-03T01:02:03Z",
            "output_directory": str(tmp_path / "run-a"),
            "title": "Evidence title",
        },
        "pages": [{"page_number": 1, "text": "A  B"}],
    }
    normalized = normalize_json_artifact(payload, config(), tmp_path / "run-a")
    assert normalized.value["metadata"]["parsed_at"] == "<NONDETERMINISTIC>"
    assert normalized.value["metadata"]["output_directory"] == "<RUN_ROOT>"
    assert normalized.value["metadata"]["title"] == "Evidence title"
    assert normalized.value["pages"][0]["text"] == "A  B"


def test_does_not_normalize_bbox_or_element_id(tmp_path: Path) -> None:
    payload = {"pages": [{"elements": [{"id": "A", "bbox": [1, 2, 3, 4]}]}]}
    normalized = normalize_json_artifact(payload, config(), tmp_path)
    assert normalized.value == payload
```

- [ ] **Step 2: Write Markdown normalization tests**

Verify only UTF-8 BOM removal, CRLF-to-LF conversion, approved run-root replacement, and path-separator conversion within approved run-local references. Assert that trailing spaces, blank lines, table spacing, headings, body whitespace, and image ordering remain unchanged.

- [ ] **Step 3: Run tests and confirm failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_normalization.py -v
```

- [ ] **Step 4: Implement JSON path replacement without wildcard evaluation**

Parse each allowlist entry into exact object-key components. Refuse list indices and wildcard syntax in v1. Deep-copy into tuples/dicts used only for canonical serialization; do not mutate the decoded raw payload.

```python
@dataclass(frozen=True, slots=True)
class NormalizedJson:
    value: JsonValue
    canonical_bytes: bytes
    sha256: str
    applied: tuple[AppliedNormalization, ...]
```

- [ ] **Step 5: Implement bounded Markdown normalization**

```python
def normalize_markdown_artifact(data: bytes, run_root: Path) -> NormalizedMarkdown:
    text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    root_forms = _approved_root_forms(run_root)
    for root_form in root_forms:
        text = text.replace(root_form, "<RUN_ROOT>")
    canonical = text.encode("utf-8")
    return NormalizedMarkdown(
        text=text,
        canonical_bytes=canonical,
        sha256=hashlib.sha256(canonical).hexdigest().upper(),
        applied=_applied_markdown_normalizations(data, text),
    )
```

Do not call `.strip()`, split/join whitespace, normalize Unicode, sort sections, or rewrite Markdown tables.

- [ ] **Step 6: Run tests and verify raw objects remain unchanged**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_normalization.py -v
```

- [ ] **Step 7: Commit normalization**

```powershell
git add src/ansim_review/parser_reproducibility/normalization.py tests/unit/parser_reproducibility/test_normalization.py
git commit -m "feat: add closed parser normalization profile"
```

---

### Task 5: Structural difference engine and reproducibility status

**Files:**
- Create: `src/ansim_review/parser_reproducibility/comparison.py`
- Create: `src/ansim_review/contracts/schemas/parser-reproducibility-report.schema.json`
- Create: `tests/unit/parser_reproducibility/test_comparison.py`

**Interfaces:**
- Consumes: two `ParserRunManifest` values, decoded artifacts, normalized artifacts, warning tuples
- Produces: `StructuralDifference`
- Produces: `ComparisonResult`
- Produces: `compare_parser_runs(left: ParsedRun, right: ParsedRun, config: ReproducibilityConfig) -> ComparisonResult`

- [ ] **Step 1: Write status precedence tests**

```python
def test_byte_identical_precedes_semantic_comparison() -> None:
    result = compare_parser_runs(run_pair(raw_equal=True), config())
    assert result.status == "BYTE_IDENTICAL"
    assert result.differences == ()


def test_environment_mismatch_makes_no_semantic_claim() -> None:
    pair = run_pair(parser_versions=("1.2.3", "1.2.4"))
    result = compare_parser_runs(pair, config())
    assert result.status == "ENVIRONMENT_MISMATCH"
    assert result.canonical_equivalent is None


def test_allowed_timestamp_difference_is_semantically_identical() -> None:
    result = compare_parser_runs(run_pair(parsed_at_differs=True), config())
    assert result.status == "SEMANTICALLY_IDENTICAL"
    assert {item.path for item in result.applied_normalizations} == {
        "$.metadata.parsed_at"
    }
```

- [ ] **Step 2: Write meaningful mismatch matrix tests**

Parametrize mutations and expected difference kinds:

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
        (change_markdown_body, "MARKDOWN_CONTENT_CHANGED"),
        (add_warning, "WARNING_ADDED"),
        (move_warning_page, "WARNING_CHANGED"),
    ],
)
def test_detects_meaningful_difference(mutation, kind: str) -> None:
    result = compare_parser_runs(mutation(run_pair()), config())
    assert result.status == "MISMATCH"
    assert kind in {item.kind for item in result.differences}
```

- [ ] **Step 3: Run tests and confirm failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_comparison.py -v
```

- [ ] **Step 4: Implement deterministic recursive JSON comparison**

Rules:

- Dictionaries compare by sorted key.
- Lists compare by position; no set conversion or ID-based reordering.
- Numeric types compare exactly after JSON decode; do not apply tolerances to coordinates.
- Difference records use canonical JSON paths and SHA-256 of bounded values.
- Large strings are not copied into reports; use hashes and a maximum 120-character summary with control characters escaped.

- [ ] **Step 5: Map structural paths to stable difference kinds**

Implement pure mapping logic:

```python
def difference_kind(path: str, left: JsonValue, right: JsonValue) -> str:
    if path.endswith(".bbox") or ".bbox[" in path:
        return "BOUNDING_BOX_CHANGED"
    if ".rows[" in path and ".cells[" in path and path.endswith(".content"):
        return "TABLE_CELL_VALUE_CHANGED"
    if path.endswith(".content") or path.endswith(".text"):
        return "TEXT_CONTENT_CHANGED"
    if path.endswith(".previous") or path.endswith(".next") or ".kids[" in path:
        return "RELATIONSHIP_CHANGED"
    return "UNAPPROVED_NONDETERMINISM"
```

Use explicit tests for every mapping branch.

- [ ] **Step 6: Implement status selection**

Exact precedence:

```text
PARSER_FAILED
ENVIRONMENT_MISMATCH
BYTE_IDENTICAL
SEMANTICALLY_IDENTICAL
MISMATCH
```

`BYTE_IDENTICAL` requires raw JSON bytes, raw Markdown bytes, and normalized warning collections to match. A warning mismatch prevents byte-identical status even when artifact bytes match.

- [ ] **Step 7: Run focused tests**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_comparison.py tests/unit/parser_reproducibility/test_normalization.py tests/unit/parser_reproducibility/test_warnings.py -v
```

- [ ] **Step 8: Commit comparison engine**

```powershell
git add src/ansim_review/parser_reproducibility/comparison.py src/ansim_review/contracts/schemas/parser-reproducibility-report.schema.json tests/unit/parser_reproducibility/test_comparison.py
git commit -m "feat: compare parser artifacts deterministically"
```

---

### Task 6: Deterministic parser warning review queue

**Files:**
- Create: `src/ansim_review/parser_reproducibility/queue.py`
- Create: `src/ansim_review/contracts/schemas/parser-review-queue.schema.json`
- Create: `tests/unit/parser_reproducibility/test_queue.py`

**Interfaces:**
- Consumes: current warning tuples and optional previous queue artifact
- Produces: `ParserReviewQueue`, `ParserReviewQueueEntry`
- Produces: `build_review_queue(warnings: Sequence[ParserWarning], run_id: str, previous: ParserReviewQueue | None = None) -> ParserReviewQueue`

- [ ] **Step 1: Write duplicate and history tests**

```python
def test_repeated_warning_produces_one_queue_entry() -> None:
    warning = parser_warning(page_number=3)
    first = build_review_queue((warning,), run_id="PRUN-A")
    second = build_review_queue((warning, warning), run_id="PRUN-B", previous=first)
    assert len(second.entries) == 1
    assert second.entries[0].status == "REVIEW_REQUIRED"
    assert second.entries[0].first_seen_run_id == "PRUN-A"
    assert second.entries[0].last_seen_run_id == "PRUN-B"
    assert second.entries[0].occurrence_count == 3


def test_warning_disappearance_does_not_delete_previous_history() -> None:
    previous = build_review_queue((parser_warning(),), run_id="PRUN-A")
    current = build_review_queue((), run_id="PRUN-B", previous=previous)
    assert current.entries == previous.entries
```

- [ ] **Step 2: Write stable key tests**

Assert that file name, absolute root, execution timestamp, and warning source line number do not alter queue ID, while source hash, parser version, config hash, page, warning code, or normalized message hash do alter it.

- [ ] **Step 3: Run tests and confirm failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_queue.py -v
```

- [ ] **Step 4: Implement immutable merge behavior**

```python
def build_review_queue(
    warnings: Sequence[ParserWarning],
    run_id: str,
    previous: ParserReviewQueue | None = None,
) -> ParserReviewQueue:
    entries = {entry.queue_id: entry for entry in (() if previous is None else previous.entries)}
    for warning in sorted(warnings, key=_warning_sort_key):
        queue_id = queue_id_for(warning)
        current = entries.get(queue_id)
        entries[queue_id] = _new_entry(warning, run_id) if current is None else replace(
            current,
            last_seen_run_id=run_id,
            occurrence_count=current.occurrence_count + 1,
        )
    return ParserReviewQueue(entries=tuple(sorted(entries.values(), key=_queue_sort_key)))
```

Reject malformed prior queue artifacts instead of silently resetting history.

- [ ] **Step 5: Add canonical schema and serialization tests**

The queue format is `evidence-review/parser-review-queue`, version 1. Verify two serializations produce identical bytes and SHA-256.

- [ ] **Step 6: Run tests**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_queue.py -v
```

- [ ] **Step 7: Commit queue support**

```powershell
git add src/ansim_review/parser_reproducibility/queue.py src/ansim_review/contracts/schemas/parser-review-queue.schema.json tests/unit/parser_reproducibility/test_queue.py
git commit -m "feat: add parser warning review queue"
```

---

### Task 7: Orchestrate reports and canonical serialization

**Files:**
- Create: `src/ansim_review/parser_reproducibility/report.py`
- Modify: `src/ansim_review/parser_reproducibility/__init__.py`
- Create: `tests/unit/parser_reproducibility/test_report.py`

**Interfaces:**
- Produces: `validate_opendataloader_reproducibility(source_pdf: Path, run_a_root: Path, run_b_root: Path, config: ReproducibilityConfig) -> ParserReproducibilityReport`
- Produces: `collect_opendataloader_warnings(source_pdf: Path, run_root: Path, config: ReproducibilityConfig, previous_queue: ParserReviewQueue | None = None) -> WarningCollectionResult`
- Produces: `report_bytes(report: ReportProtocol) -> bytes`

- [ ] **Step 1: Write orchestration tests**

```python
def test_validation_does_not_modify_inputs(tmp_path: Path) -> None:
    source, run_a, run_b = write_equal_runs(tmp_path)
    before = tree_hashes(tmp_path)
    report = validate_opendataloader_reproducibility(source, run_a, run_b, config())
    after = tree_hashes(tmp_path)
    assert report.status == "BYTE_IDENTICAL"
    assert before == after


def test_report_contains_no_absolute_paths(tmp_path: Path) -> None:
    source, run_a, run_b = write_semantically_equal_runs(tmp_path)
    encoded = report_bytes(
        validate_opendataloader_reproducibility(source, run_a, run_b, config())
    )
    assert str(tmp_path).encode("utf-8") not in encoded
    assert b"\\\\" not in encoded
```

- [ ] **Step 2: Write deterministic report tests**

Run the same validation twice into in-memory report objects and assert `report_bytes(first) == report_bytes(second)`. Verify stable difference ordering, warning ordering, normalization path ordering, counts, and summary text.

- [ ] **Step 3: Run tests and confirm failure**

```powershell
python -m pytest tests/unit/parser_reproducibility/test_report.py -v
```

- [ ] **Step 4: Implement pure orchestration**

The public functions read inputs and return frozen models only. They do not create output directories or files. Convert exceptions into deterministic `PARSER_FAILED` findings at the orchestration boundary; do not catch `KeyboardInterrupt` or `SystemExit`.

- [ ] **Step 5: Implement canonical report dictionaries**

`ParserReproducibilityReport.as_dict()` includes exact format/version, status, source identity, both run summaries, raw/canonical hashes, normalization profile, applied normalization paths, warning summaries, differences, counts, and stable summary. No field may use `datetime.now()`, temp paths, object repr, exception repr containing paths, or unordered sets.

- [ ] **Step 6: Export public interfaces**

Update `__init__.py` to expose only the supported contracts and public functions. Keep private normalization and adapter helpers unexported.

- [ ] **Step 7: Run all unit tests for the package**

```powershell
python -m pytest tests/unit/parser_reproducibility -v
```

- [ ] **Step 8: Commit report orchestration**

```powershell
git add src/ansim_review/parser_reproducibility/__init__.py src/ansim_review/parser_reproducibility/report.py tests/unit/parser_reproducibility/test_report.py
git commit -m "feat: emit canonical parser reproducibility reports"
```

---

### Task 8: Add canonical CLI commands and atomic create-only output

**Files:**
- Create: `src/ansim_review/parser_reproducibility/cli.py`
- Modify: `src/ansim_review/cli_parser.py`
- Modify: `src/ansim_review/cli.py`
- Modify: `tests/unit/test_cli_parser.py`
- Create: `tests/integration/parser_reproducibility/test_cli.py`

**Interfaces:**
- Produces CLI: `evidence-review parser reproducibility validate`
- Produces CLI: `evidence-review parser warnings collect`
- Produces: `write_create_only(path: Path, data: bytes) -> None`
- Produces exit codes: 0 success/equivalent, 1 mismatch, 2 usage/config/environment/existing output, 3 parser failure.

- [ ] **Step 1: Write parser-shape tests**

```python
def test_parser_reproducibility_validate_arguments() -> None:
    args = build_parser().parse_args(
        [
            "parser",
            "reproducibility",
            "validate",
            "--source",
            "source.pdf",
            "--run-a",
            "run-a",
            "--run-b",
            "run-b",
            "--config",
            "parser-reproducibility.json",
            "--output",
            "report.json",
        ]
    )
    assert args.command == "parser"
    assert args.parser_stage == "reproducibility"
    assert args.parser_action == "validate"
```

Add an equivalent test for `parser warnings collect` with both output paths and optional `--previous-queue`.

- [ ] **Step 2: Write create-only integration tests**

Test all of the following:

1. Existing `--output` returns 2 and leaves bytes unchanged.
2. If either warning or queue output exists, neither output is created or changed.
3. Mismatch writes a complete report then returns 1.
4. Environment mismatch writes a complete report then returns 2.
5. Parser failure writes a complete report when the destination is valid then returns 3.
6. Temporary files are absent after a simulated replace/write failure.
7. Concurrent exclusive creation allows one writer and rejects the other without corruption.

- [ ] **Step 3: Run tests and confirm failure**

```powershell
python -m pytest tests/unit/test_cli_parser.py tests/integration/parser_reproducibility/test_cli.py -v
```

- [ ] **Step 4: Extend the shared parser without dispatch during parser construction**

Add nested subparsers through the existing `build_parser()` function. Do not import heavy parser reproducibility modules in `cli_parser.py`; parser construction must remain dependency-safe for documentation static command validation.

- [ ] **Step 5: Implement atomic create-only writer**

Use exclusive temporary creation in the destination directory and an exclusive final destination reservation. For multi-output warning collection, reserve both final paths before computing reports; on any failure, close and remove both reservations.

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

Write bytes directly to reserved descriptors, flush, `os.fsync`, and close. Do not overwrite through `Path.write_bytes` after preflight.

- [ ] **Step 6: Dispatch commands from `cli.py`**

Lazy-import `ansim_review.parser_reproducibility.cli` only after the parser command is selected. Print a concise stable summary to stdout and errors to stderr. Do not print absolute paths in canonical summary lines.

- [ ] **Step 7: Run CLI tests**

```powershell
python -m pytest tests/unit/test_cli_parser.py tests/integration/parser_reproducibility/test_cli.py -v
```

- [ ] **Step 8: Commit CLI support**

```powershell
git add src/ansim_review/parser_reproducibility/cli.py src/ansim_review/cli_parser.py src/ansim_review/cli.py tests/unit/test_cli_parser.py tests/integration/parser_reproducibility/test_cli.py
git commit -m "feat: expose parser reproducibility CLI"
```

---

### Task 9: Build text, table, and warning fixture matrix

**Files:**
- Create: `tests/integration/parser_reproducibility/fixtures/text/source.pdf`
- Create: `tests/integration/parser_reproducibility/fixtures/text/run-a/*`
- Create: `tests/integration/parser_reproducibility/fixtures/text/run-b/*`
- Create: `tests/integration/parser_reproducibility/fixtures/table/source.pdf`
- Create: `tests/integration/parser_reproducibility/fixtures/table/run-a/*`
- Create: `tests/integration/parser_reproducibility/fixtures/table/run-b/*`
- Create: `tests/integration/parser_reproducibility/fixtures/warning/source.pdf`
- Create: `tests/integration/parser_reproducibility/fixtures/warning/run-a/*`
- Create: `tests/integration/parser_reproducibility/fixtures/warning/run-b/*`
- Create: `tests/integration/parser_reproducibility/fixtures/manifest.json`
- Create: `tests/integration/parser_reproducibility/test_reproducibility_matrix.py`
- Create: `tests/integration/parser_reproducibility/test_warning_collection.py`

**Interfaces:**
- Consumes: public Python APIs and CLI from Tasks 7 and 8
- Produces: deterministic acceptance fixtures with recorded source/artifact SHA-256 and expected status.

- [ ] **Step 1: Define fixture manifest contract in the test module**

Each fixture entry contains:

```json
{
  "id": "TEXT-BYTE-IDENTICAL",
  "source": "text/source.pdf",
  "run_a": "text/run-a",
  "run_b": "text/run-b",
  "expected_status": "BYTE_IDENTICAL",
  "expected_difference_kinds": [],
  "source_sha256": "64 uppercase hexadecimal characters"
}
```

Decode it strictly in tests and verify every referenced file exists and every recorded hash matches.

- [ ] **Step 2: Generate or add redistributable PDF fixtures**

Use a deterministic repository script inside the test module or checked-in minimal PDF bytes. PDFs must have stable bytes and contain:

- text fixture: two pages with headings and plain text;
- table fixture: one page with a 2x3 table and explicit cell coordinates;
- warning fixture: a simple source paired with a captured stable warning artifact.

Do not add proprietary source documents.

- [ ] **Step 3: Add expected run pairs**

Include cases for:

```text
BYTE_IDENTICAL
SEMANTICALLY_IDENTICAL timestamp
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

Use copy-on-write fixture setup in `tmp_path`; never mutate checked-in fixture directories during tests.

- [ ] **Step 4: Write matrix test**

```python
@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case.id)
def test_reproducibility_matrix(case: FixtureCase, tmp_path: Path) -> None:
    prepared = copy_case(case, tmp_path)
    report = validate_opendataloader_reproducibility(
        prepared.source,
        prepared.run_a,
        prepared.run_b,
        repository_config(),
    )
    assert report.status == case.expected_status
    assert {item.kind for item in report.differences} == set(
        case.expected_difference_kinds
    )
```

- [ ] **Step 5: Write warning collection tests**

Verify text/table/layout/unknown taxonomy, raw message preservation, page association, queue deduplication, deterministic IDs, and byte-identical report/queue regeneration.

- [ ] **Step 6: Run integration matrix twice**

```powershell
python -m pytest tests/integration/parser_reproducibility -v
python -m pytest tests/integration/parser_reproducibility -v
```

Expected: both runs report identical test counts and all pass.

- [ ] **Step 7: Commit fixtures and matrix**

```powershell
git add tests/integration/parser_reproducibility
git commit -m "test: add OpenDataLoader reproducibility matrix"
```

---

### Task 10: Document the current parser validation workflow

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `skills/01-preserving-and-parsing-pdfs/SKILL.md`
- Modify: `documentation-integrity.json` only if new current paths are added during implementation
- Modify: `tests/integration/documentation_integrity/test_repository_acceptance.py`

**Interfaces:**
- Produces: current, executable documentation for parser reproducibility and warning collection.
- Consumes: exact CLI commands from Task 8.

- [ ] **Step 1: Write documentation acceptance assertions first**

Assert current docs contain the exact supported commands:

```text
evidence-review parser reproducibility validate
evidence-review parser warnings collect
```

Assert they state:

- raw parser artifacts are immutable;
- warnings create `REVIEW_REQUIRED`, not automatic parser failure;
- `MISMATCH` blocks reproducibility acceptance;
- `ENVIRONMENT_MISMATCH` makes no equivalence claim;
- output paths are create-only;
- validation is offline and does not invoke OpenDataLoader.

- [ ] **Step 2: Run documentation tests and confirm failure**

```powershell
python -m pytest tests/integration/documentation_integrity/test_repository_acceptance.py -v
```

- [ ] **Step 3: Update README and AGENTS**

Add concise command examples using repository-relative paths. Do not add legacy wrapper commands or machine-specific drive paths. Keep GitHub Actions out of required acceptance language.

- [ ] **Step 4: Update Stage 1 skill**

Extend verification with:

1. record parser version and parser configuration;
2. preserve raw JSON/Markdown/log outputs;
3. compare two runs when reproducibility acceptance is required;
4. submit parser warning report and review queue;
5. never resolve parser warnings by deleting or editing raw output.

- [ ] **Step 5: Run canonical documentation validation twice**

```powershell
python -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output build/issue52-doc-a.json
python -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output build/issue52-doc-b.json
python -c "from pathlib import Path; import hashlib; a=Path('build/issue52-doc-a.json').read_bytes(); b=Path('build/issue52-doc-b.json').read_bytes(); assert a == b; print(hashlib.sha256(a).hexdigest().upper())"
```

Expected: both reports PASS with zero errors and identical bytes.

- [ ] **Step 6: Run documentation tests**

```powershell
python -m pytest tests/integration/documentation_integrity tests/unit/documentation_integrity -v
```

- [ ] **Step 7: Commit documentation**

```powershell
git add README.md AGENTS.md skills/01-preserving-and-parsing-pdfs/SKILL.md documentation-integrity.json tests/integration/documentation_integrity/test_repository_acceptance.py
git commit -m "docs: document parser reproducibility workflow"
```

---

### Task 11: Package schemas and validate isolated wheels

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/unit/contracts/test_schema_documents.py`
- Create: `tests/integration/parser_reproducibility/test_wheel_resources.py`

**Interfaces:**
- Produces: installed wheels containing all five parser reproducibility schemas and canonical package imports.
- Consumes: CLI and contracts from prior tasks.

- [ ] **Step 1: Write installed-resource tests**

Use `importlib.resources.files("ansim_review.contracts.schemas")` and assert all five schema files are readable in an installed environment. Assert `evidence_review.parser_reproducibility` and `ansim_review.parser_reproducibility` resolve to the same public class/function identities under the repository compatibility contract.

- [ ] **Step 2: Run tests and confirm any packaging gap**

```powershell
python -m pytest tests/integration/parser_reproducibility/test_wheel_resources.py tests/unit/contracts/test_schema_documents.py -v
```

- [ ] **Step 3: Update package-data configuration only when required**

Ensure `pyproject.toml` includes the existing schema package glob covering `*.json`. Do not add root `parser-reproducibility.json` as package data; users pass a repository-owned config path. Add only missing schema-package rules.

- [ ] **Step 4: Build and test Python 3.11 wheel**

```powershell
py -3.11 -m venv build/issue52-wheel-build-311
build/issue52-wheel-build-311/Scripts/python.exe -m pip install --upgrade pip build
build/issue52-wheel-build-311/Scripts/python.exe -m build --wheel --outdir build/issue52-dist-311
py -3.11 -m venv build/issue52-wheel-test-311
$Wheel311 = (Get-ChildItem build/issue52-dist-311/*.whl | Select-Object -First 1).FullName
build/issue52-wheel-test-311/Scripts/python.exe -m pip install $Wheel311
build/issue52-wheel-test-311/Scripts/python.exe -m pip check
build/issue52-wheel-test-311/Scripts/evidence-review.exe parser reproducibility validate --help
build/issue52-wheel-test-311/Scripts/evidence-review.exe parser warnings collect --help
build/issue52-wheel-test-311/Scripts/python.exe -m evidence_review parser reproducibility validate --help
build/issue52-wheel-test-311/Scripts/python.exe -m ansim_review parser warnings collect --help
```

- [ ] **Step 5: Build and test Python 3.13 wheel**

Repeat Step 4 with `py -3.13`, directories ending in `313`, and the Python 3.13 executable.

- [ ] **Step 6: Execute an installed-wheel fixture validation**

Copy the text fixture and config to a temporary directory outside the repository checkout. Run the installed `evidence-review` executable with `PYTHONPATH` cleared. Assert status `BYTE_IDENTICAL`, exit 0, report format/version, and no checkout imports.

- [ ] **Step 7: Record wheel SHA-256 values in the local verification notes**

```powershell
Get-FileHash $Wheel311 -Algorithm SHA256
Get-FileHash $Wheel313 -Algorithm SHA256
```

Do not commit built wheel files or virtual environments.

- [ ] **Step 8: Commit packaging changes**

```powershell
git add pyproject.toml tests/unit/contracts/test_schema_documents.py tests/integration/parser_reproducibility/test_wheel_resources.py
git commit -m "test: verify parser contracts in installed wheels"
```

---

### Task 12: Full manual acceptance, ledger, Draft PR, and Issue #27 handoff

**Files:**
- Create: `docs/acceptance/issue-52/README.md`
- Modify: `documentation-integrity.json` to classify the acceptance ledger according to repository policy
- No implementation files should change during this task unless a reproduced defect requires returning to its owning task.

**Interfaces:**
- Produces: exact manual acceptance evidence for Issue #52.
- Produces: Draft PR linked to #52 and completion update linked to #27.

- [ ] **Step 1: Confirm exact branch and clean starting state**

```powershell
git fetch origin
git switch agent/issue-52-opendataloader-reproducibility
git pull --ff-only origin agent/issue-52-opendataloader-reproducibility
git status --short
git rev-parse HEAD
git rev-parse origin/agent/issue-52-opendataloader-reproducibility
```

Stop if local and remote HEAD differ or the worktree is not clean.

- [ ] **Step 2: Run targeted parser reproducibility tests**

```powershell
python -m pytest tests/unit/parser_reproducibility tests/integration/parser_reproducibility -v
```

Record passed/skipped/failed counts and exit code.

- [ ] **Step 3: Run repository-wide gates**

```powershell
python -m pytest -v
python -m ruff check src tests
python -m mypy src
python -m compileall -q src scripts web_runtime tests
git diff --check origin/main...HEAD
```

Every command must exit 0. Do not waive a failing test, Ruff finding, mypy error, compile failure, or whitespace error.

- [ ] **Step 4: Run canonical documentation validation twice**

Use fresh output paths, assert PASS/errors 0, assert byte identity, and record SHA-256.

- [ ] **Step 5: Run the real fixture acceptance matrix through the CLI**

Execute the exact CLI commands for the text, table, and warning fixtures into fresh output paths. Confirm expected statuses, warning counts, queue deduplication, create-only rejection, and report byte identity.

- [ ] **Step 6: Repeat isolated Python 3.11 and 3.13 wheel acceptance**

Use fresh build/install environments, `pip check`, both parser subcommand help trees through all canonical module entry points, and actual installed-wheel fixture validation. Record both wheel SHA-256 values.

- [ ] **Step 7: Write the acceptance ledger**

`docs/acceptance/issue-52/README.md` must include:

```text
Verdict
Repository / branch / exact implementation HEAD
Windows version
Python 3.11 and 3.13 versions
Configuration SHA-256
Fixture source and artifact hashes
Targeted and full pytest results
Ruff / mypy / compileall / diff check
Documentation report counts and SHA-256
Reproducibility status matrix
Warning report and queue hashes
Create-only and concurrency results
Python 3.11 and 3.13 wheel hashes
GitHub Actions excluded from acceptance
Human review still required
Ready / merge / issue closure not performed
```

Mark the ledger as a current manual acceptance record while it is active. After final evidence commit, follow the same post-ledger recheck discipline used by Issue #50 and convert it to historical only when the branch process requires that transition.

- [ ] **Step 8: Commit the ledger and re-run post-ledger gates**

```powershell
git add docs/acceptance/issue-52/README.md documentation-integrity.json
git commit -m "docs: record issue 52 manual acceptance"
python -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output build/issue52-post-ledger-documentation.json
python -m pytest -v
python -m ruff check src tests
python -m mypy src
python -m compileall -q src scripts web_runtime tests
git diff --check origin/main...HEAD
git status --short
```

- [ ] **Step 9: Push and open a Draft PR**

Push only after all post-ledger gates pass. Open a Draft PR titled:

```text
feat: validate OpenDataLoader parser reproducibility
```

The PR body must state manual acceptance results, exact implementation/evidence HEADs, wheel hashes, documentation report hash, GitHub Actions exclusion, and that Ready transition, merge, Issue #52 closure, and Issue #27 closure were not performed.

- [ ] **Step 10: Update Issue #52 and parent Issue #27**

Add the same factual summary to Issue #52. Add a concise parent update to #27 stating that its final P2 implementation unit is in Draft review, listing the exact HEAD and remaining human-review/merge conditions. Do not close either issue.

- [ ] **Step 11: Commit nothing else**

Verify the final changed-file set contains only Issue #52 implementation, tests, current documentation, schemas, configuration, and acceptance evidence. Remove untracked wheels, virtual environments, temporary reports, and copied fixtures outside tracked test paths.

---

## Plan Self-Review Results

### Spec coverage

- OpenDataLoader-only scope: Tasks 1, 3, 9.
- Raw byte comparison: Tasks 2, 5, 7.
- Closed allowlist semantic comparison: Task 4.
- Text/table/image/coordinate/page/relationship/warning mismatch detection: Tasks 3, 5, 9.
- Warning preservation and taxonomy: Task 3.
- Stable `REVIEW_REQUIRED` queue and deduplication: Task 6.
- Canonical create-only reports and all-or-nothing multi-output: Tasks 7 and 8.
- Windows/POSIX path normalization and path safety: Tasks 2 and 4.
- Text/table/warning fixture minimum: Task 9.
- Documentation and installed-wheel support: Tasks 10 and 11.
- Manual acceptance without GitHub Actions dependency: Task 12.

### Placeholder scan

The plan contains no `TBD`, `TODO`, deferred implementation instructions, wildcard ignore rules, or unspecified error-handling steps.

### Type and interface consistency

- `ReproducibilityConfig` originates in Task 1 and is consumed unchanged by Tasks 2 through 9.
- `ParserRunManifest` originates in Task 2 and is consumed by Tasks 5 and 7.
- `OpenDataLoaderArtifact` and `ParserWarning` originate in Task 3 and are consumed by Tasks 4 through 7.
- `NormalizedJson` and `NormalizedMarkdown` originate in Task 4 and are consumed by Task 5.
- `ComparisonResult` originates in Task 5 and is converted to the public report in Task 7.
- `ParserReviewQueue` originates in Task 6 and is emitted by Tasks 7 and 8.
- CLI entry points in Task 8 match the approved spec and documentation work in Task 10.
