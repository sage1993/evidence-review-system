# Repository-wide Documentation Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline, deterministic documentation-integrity gate for repository Markdown and generated Markdown, emit a canonical report, and block release when documentation contains errors.

**Architecture:** Add an isolated `ansim_review.documentation_integrity` package for strict contracts, document discovery/classification, Markdown extraction, link/path checks, static command validation, generated-document rendering, and report orchestration. Extract CLI parser construction into a dependency-safe module so the documentation checker can validate real argparse commands without importing command handlers. Reuse one pure validation function from the CLI, repository acceptance test, workspace validator, and release builder.

**Tech Stack:** Python 3.11+ standard library only, frozen dataclasses, `argparse`, `pathlib`, `json`, `importlib`, `re`, `shlex`, existing canonical JSON utilities, pytest, Ruff, strict mypy, GitHub Actions.

## Global Constraints

- No runtime dependency additions.
- No network requests or external URL availability checks.
- No execution of commands extracted from Markdown.
- No restoration of missing legacy wrapper scripts.
- Scan `README.md`, `AGENTS.md`, `docs/**/*.md`, `skills/**/SKILL.md`, and registered generated Markdown.
- Historical defaults: `docs/acceptance/**`, `docs/superpowers/plans/**`, `docs/superpowers/specs/**`.
- Invalid external URL syntax is always `WARNING`; warnings alone never fail validation.
- `ERROR` findings produce report status `FAIL` and CLI exit code `1`.
- Reports use create-only canonical JSON.
- Machine-specific paths in prose are not repository references. Path safety applies to Markdown targets and recognized repository-local command arguments.
- Preserve rule, golden, activation, Grist QA, lineage, and attestation artifacts unchanged.

## File Map

### Create

```text
documentation-integrity.json
src/ansim_review/cli_parser.py
src/ansim_review/documentation_integrity/__init__.py
src/ansim_review/documentation_integrity/contract.py
src/ansim_review/documentation_integrity/classification.py
src/ansim_review/documentation_integrity/discovery.py
src/ansim_review/documentation_integrity/markdown.py
src/ansim_review/documentation_integrity/links.py
src/ansim_review/documentation_integrity/commands.py
src/ansim_review/documentation_integrity/generated.py
src/ansim_review/documentation_integrity/validator.py
src/ansim_review/documentation_integrity/cli.py
tests/unit/test_cli_parser.py
tests/unit/documentation_integrity/test_contract.py
tests/unit/documentation_integrity/test_classification.py
tests/unit/documentation_integrity/test_discovery.py
tests/unit/documentation_integrity/test_markdown.py
tests/unit/documentation_integrity/test_links.py
tests/unit/documentation_integrity/test_commands.py
tests/unit/documentation_integrity/test_generated.py
tests/unit/documentation_integrity/test_validator.py
tests/integration/documentation_integrity/test_cli.py
tests/integration/documentation_integrity/test_repository_acceptance.py
tests/integration/release/test_documentation_gate.py
docs/acceptance/issue-50/README.md
```

### Modify

```text
src/ansim_review/cli.py
src/evidence_review/cli.py
src/ansim_review/contracts/formats.py
src/ansim_review/packaging/codex_bundle.py
src/ansim_review/packaging/project_instructions.py
src/ansim_review/release/validator.py
src/ansim_review/release/builder.py
tests/unit/release/test_release_output_gate.py
tests/integration/release/test_release_builder.py
README.md
AGENTS.md
docs/OFFLINE_EXECUTION.md
.github/workflows/ci.yml
```

---

### Task 1: Extract parser construction without changing CLI behavior

**Files:**
- Create: `src/ansim_review/cli_parser.py`
- Modify: `src/ansim_review/cli.py`
- Modify: `src/evidence_review/cli.py`
- Test: `tests/unit/test_cli_parser.py`

**Interfaces:**
- Produces `build_parser() -> argparse.ArgumentParser` in `ansim_review.cli_parser`.
- `ansim_review.cli.build_parser` remains a re-export.
- `evidence_review.cli.build_parser` imports the same function object.

- [ ] **Step 1: Write the failing parser-sharing test**

```python
from ansim_review.cli import build_parser as legacy_build_parser
from ansim_review.cli_parser import build_parser
from evidence_review.cli import build_parser as canonical_build_parser


def test_parser_builder_is_shared_and_existing_commands_remain() -> None:
    assert legacy_build_parser is build_parser
    assert canonical_build_parser is build_parser
    parser = build_parser()
    prepared = parser.parse_args(
        ["source-batch", "prepare", "--root", ".", "--manifest", "m.json"]
    )
    selected = parser.parse_args(
        [
            "rules",
            "select",
            "--repository-root",
            ".",
            "--manifest",
            "a.json",
            "--context",
            "c.json",
        ]
    )
    assert prepared.command == "source-batch"
    assert selected.rules_stage == "select"
```

- [ ] **Step 2: Verify RED**

```bash
pytest -v tests/unit/test_cli_parser.py
```

Expected: `ModuleNotFoundError: ansim_review.cli_parser`.

- [ ] **Step 3: Move only `build_parser()`**

`cli_parser.py` imports only `argparse` and `Path`. `cli.py` imports the function and keeps handlers/dispatch unchanged:

```python
from ansim_review.cli_parser import build_parser

__all__ = ["build_parser", "main"]
```

- [ ] **Step 4: Verify parser regression**

```bash
pytest -v tests/unit/test_cli_parser.py
pytest -v tests -k "cli and not documentation_integrity"
ruff check src/ansim_review/cli.py src/ansim_review/cli_parser.py src/evidence_review/cli.py tests/unit/test_cli_parser.py
mypy src/ansim_review/cli.py src/ansim_review/cli_parser.py src/evidence_review/cli.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ansim_review/cli_parser.py src/ansim_review/cli.py src/evidence_review/cli.py tests/unit/test_cli_parser.py
git commit -m "refactor: share cli parser construction"
```

---

### Task 2: Define strict config, finding, and report contracts

**Files:**
- Create: `src/ansim_review/documentation_integrity/__init__.py`
- Create: `src/ansim_review/documentation_integrity/contract.py`
- Modify: `src/ansim_review/contracts/formats.py`
- Test: `tests/unit/documentation_integrity/test_contract.py`

**Interfaces:**
- `GeneratedDocumentConfig`
- `DocumentationIntegrityConfig`
- `DocumentationFinding`
- `DocumentationIntegrityReport`
- `decode_config_bytes(data: bytes) -> DocumentationIntegrityConfig`
- `report_document(report: DocumentationIntegrityReport) -> dict[str, object]`
- `report_bytes(report: DocumentationIntegrityReport) -> bytes`
- Constants `DOCUMENTATION_INTEGRITY_CONFIG_FORMAT` and `DOCUMENTATION_INTEGRITY_REPORT_FORMAT`.

- [ ] **Step 1: Write strict decoder tests**

```python
VALID_CONFIG = b'''{
  "format":"evidence-review/documentation-integrity-config",
  "version":1,
  "current_roots":["README.md","docs"],
  "historical_roots":["docs/acceptance"],
  "current_overrides":[],
  "historical_overrides":[],
  "generated_documents":[]
}'''


def test_config_rejects_duplicate_json_keys() -> None:
    invalid = VALID_CONFIG.replace(
        b'"version":1',
        b'"version":1,"version":1',
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        decode_config_bytes(invalid)
```

Also test unknown fields, unsupported format/version, duplicate paths, invalid generator IDs, absolute paths, backslashes, `.`/`..`, and classifications outside `CURRENT|HISTORICAL`.

- [ ] **Step 2: Verify RED**

```bash
pytest -v tests/unit/documentation_integrity/test_contract.py
```

- [ ] **Step 3: Implement exact-key decoding and frozen dataclasses**

Use `json.loads(..., object_pairs_hook=...)`. Validate repository paths with `PurePosixPath` and explicit component checks. The finding model has exactly:

```python
@dataclass(frozen=True, slots=True)
class DocumentationFinding:
    severity: Literal["ERROR", "WARNING"]
    code: str
    document_path: str
    line: int
    column: int
    target: str
    message: str
```

Deduplicate findings by the complete tuple. Sort with `ERROR` before `WARNING`, then path, line, column, code, target, message.

- [ ] **Step 4: Freeze canonical report behavior**

```python
def test_report_is_deduplicated_and_byte_stable() -> None:
    first = make_report(findings=(warning, error, error))
    second = make_report(findings=(error, warning))
    assert report_bytes(first) == report_bytes(second)
    payload = json.loads(report_bytes(first))
    assert payload["status"] == "FAIL"
    assert payload["error_count"] == 1
    assert payload["warning_count"] == 1
```

- [ ] **Step 5: Verify GREEN and commit**

```bash
pytest -v tests/unit/documentation_integrity/test_contract.py
ruff check src/ansim_review/documentation_integrity/contract.py src/ansim_review/contracts/formats.py tests/unit/documentation_integrity/test_contract.py
mypy src/ansim_review/documentation_integrity/contract.py

git add src/ansim_review/contracts/formats.py src/ansim_review/documentation_integrity tests/unit/documentation_integrity/test_contract.py
git commit -m "feat: define documentation integrity contracts"
```

---

### Task 3: Implement classification and repository discovery

**Files:**
- Create: `src/ansim_review/documentation_integrity/classification.py`
- Create: `src/ansim_review/documentation_integrity/discovery.py`
- Test: `tests/unit/documentation_integrity/test_classification.py`
- Test: `tests/unit/documentation_integrity/test_discovery.py`

**Interfaces:**
- `classify_document(path: str, config: DocumentationIntegrityConfig) -> Literal["CURRENT", "HISTORICAL"]`
- `DiscoveredDocument(path: str, filesystem_path: Path, classification: DocumentClassification)`
- `discover_repository_documents(repository_root: Path, config: DocumentationIntegrityConfig) -> tuple[DiscoveredDocument, ...]`
- `DocumentClassificationError(code: str, path: str)`.

- [ ] **Step 1: Write precedence tests**

```python
def test_more_specific_historical_root_wins() -> None:
    config = make_config(
        current_roots=("docs",),
        historical_roots=("docs/acceptance",),
    )
    assert classify_document("docs/guide.md", config) == "CURRENT"
    assert classify_document("docs/acceptance/issue-48/README.md", config) == "HISTORICAL"


def test_current_override_wins_over_historical_default() -> None:
    config = make_config(
        current_roots=("docs",),
        historical_roots=("docs/superpowers/specs",),
        current_overrides=("docs/superpowers/specs/current.md",),
    )
    assert classify_document("docs/superpowers/specs/current.md", config) == "CURRENT"
```

Test equal-specificity conflicts and missing classification.

- [ ] **Step 2: Write discovery tests**

The temporary repository includes `README.md`, `AGENTS.md`, `docs/**/*.md`, `skills/*/SKILL.md`, unrelated Markdown outside scope, non-Markdown files, and a symlink escaping the root. Assert POSIX bytewise sorting and fail-closed handling of the escaping symlink.

- [ ] **Step 3: Verify RED**

```bash
pytest -v tests/unit/documentation_integrity/test_classification.py tests/unit/documentation_integrity/test_discovery.py
```

- [ ] **Step 4: Implement deterministic matching and discovery**

Scope paths match themselves and descendants by components. Overrides are evaluated first; within each group the greatest component count wins. Discover exactly the approved roots and reject discovered non-regular files or symlinks resolving outside `repository_root.resolve()`.

- [ ] **Step 5: Verify GREEN and commit**

```bash
pytest -v tests/unit/documentation_integrity/test_classification.py tests/unit/documentation_integrity/test_discovery.py
ruff check src/ansim_review/documentation_integrity tests/unit/documentation_integrity
mypy src/ansim_review/documentation_integrity

git add src/ansim_review/documentation_integrity/classification.py src/ansim_review/documentation_integrity/discovery.py tests/unit/documentation_integrity/test_classification.py tests/unit/documentation_integrity/test_discovery.py
git commit -m "feat: classify and discover documentation"
```

---

### Task 4: Parse Markdown and freeze heading-anchor policy

**Files:**
- Create: `src/ansim_review/documentation_integrity/markdown.py`
- Test: `tests/unit/documentation_integrity/test_markdown.py`

**Interfaces:**
- `MarkdownHeading(text, anchor, line, column)`
- `MarkdownLink(label, target, is_image, line, column)`
- `CommandBlock(language, text, start_line)`
- `ParsedMarkdown(headings, links, command_blocks, raw_urls, first_non_empty_line)`
- `parse_markdown(text: str) -> ParsedMarkdown`
- `normalize_heading_anchor(text: str) -> str`
- `assign_heading_anchors(headings: Sequence[str]) -> tuple[str, ...]`.

- [ ] **Step 1: Write extraction tests**

Cover ATX/Setext headings, inline links, images, reference-style links, same-file/cross-file fragments, fenced PowerShell/bash/text blocks, inline code containing fake links, escaped Markdown, and source positions.

- [ ] **Step 2: Freeze anchor normalization**

Exact policy:

1. Unicode NFKC.
2. `casefold()`.
3. Keep Unicode alphanumeric characters, `_`, `-`, and whitespace.
4. Remove other punctuation.
5. Convert whitespace runs to one `-`.
6. Collapse repeated `-`; strip leading/trailing `-`.
7. Empty result becomes `section`.
8. Duplicates receive `-1`, `-2`, and so on.

```python
def test_anchor_normalization_is_stable() -> None:
    assert normalize_heading_anchor("검토 Run") == "검토-run"
    assert assign_heading_anchors(["Title", "Title", "TITLE"]) == (
        "title",
        "title-1",
        "title-2",
    )
```

- [ ] **Step 3: Verify RED, implement the bounded parser, verify GREEN**

```bash
pytest -v tests/unit/documentation_integrity/test_markdown.py
ruff check src/ansim_review/documentation_integrity/markdown.py tests/unit/documentation_integrity/test_markdown.py
mypy src/ansim_review/documentation_integrity/markdown.py
```

Use line-oriented fenced-block and Setext state plus regular expressions for links/reference definitions. Do not interpret inline code or non-command fences as commands.

- [ ] **Step 4: Commit**

```bash
git add src/ansim_review/documentation_integrity/markdown.py tests/unit/documentation_integrity/test_markdown.py
git commit -m "feat: parse documentation structures"
```

---

### Task 5: Validate links, anchors, repository paths, and URL schemes

**Files:**
- Create: `src/ansim_review/documentation_integrity/links.py`
- Test: `tests/unit/documentation_integrity/test_links.py`

**Interfaces:**
- `DocumentationIndex(classifications, headings_by_path, virtual_paths)`
- `validate_links(document, parsed, index) -> tuple[DocumentationFinding, ...]`.

- [ ] **Step 1: Write CURRENT-document tests**

Cover missing targets/anchors, path escape, absolute Markdown targets, backslash Markdown targets, valid directory/image targets, query plus fragment, and generated virtual targets.

A current-to-historical link is explicitly labeled only when its label starts with `Historical:` or `과거 기록:`. Otherwise emit `CURRENT_TO_HISTORICAL_REFERENCE_UNMARKED` as `ERROR`.

- [ ] **Step 2: Write HISTORICAL-document tests**

Safe old targets may be missing. Still reject link targets such as `../../../../outside.md`, `C:/repo/file.md`, `/repo/file.md`, or a target containing backslashes. Plain prose such as a recorded Windows worktree path is not a repository reference.

The missing first-line marker emits `HISTORICAL_MARKER_MISSING` as `WARNING`.

- [ ] **Step 3: Write URL tests**

`https://example.com/path` is valid. `http://`, `ftp://`, protocol-relative URLs, and `https:///missing-host` emit `EXTERNAL_URL_SCHEME_INVALID` as `WARNING` in both classifications.

- [ ] **Step 4: Verify RED, implement, verify GREEN**

```bash
pytest -v tests/unit/documentation_integrity/test_links.py
ruff check src/ansim_review/documentation_integrity/links.py tests/unit/documentation_integrity/test_links.py
mypy src/ansim_review/documentation_integrity/links.py
```

Resolve links from the containing document directory. Strip query/fragment for file lookup; validate fragments against parsed target headings. Preserve original target text in findings.

- [ ] **Step 5: Commit**

```bash
git add src/ansim_review/documentation_integrity/links.py tests/unit/documentation_integrity/test_links.py
git commit -m "feat: validate documentation links and paths"
```

---

### Task 6: Validate documented commands statically

**Files:**
- Create: `src/ansim_review/documentation_integrity/commands.py`
- Test: `tests/unit/documentation_integrity/test_commands.py`

**Interfaces:**
- `CommandLine(tokens, line, raw)`
- `normalize_command_block(block: CommandBlock) -> tuple[CommandLine, ...]`
- `validate_cli_tokens(tokens: Sequence[str]) -> str | None`
- `validate_command_lines(lines, repository_root, document) -> tuple[DocumentationFinding, ...]`.

- [ ] **Step 1: Write normalization tests**

Cover PowerShell backtick continuation, POSIX continuation, prompt prefixes, comments, quoted values, multiple commands, and `text` blocks not beginning with recognized executables.

- [ ] **Step 2: Write real argparse tests**

```python
@pytest.mark.parametrize(
    "command",
    [
        "evidence-review source-batch prepare --root <path> --manifest <path>",
        "python -m ansim_review rules select --repository-root . --manifest <path> --context <path>",
    ],
)
def test_valid_project_commands_are_accepted(command: str) -> None:
    assert validate_text_command(command) == ()


def test_unknown_subcommand_is_error() -> None:
    findings = validate_text_command(
        "evidence-review source-batch explode --root ."
    )
    assert [item.code for item in findings] == ["COMMAND_CLI_INVALID"]
```

Add the future documentation command as strict xfail until Task 8 registers it.

- [ ] **Step 3: Add a bounded tool-option registry**

Support repository-used options for `pytest`, `ruff check`, `mypy`, and `python -m compileall`. Include at minimum:

```python
TOOL_OPTIONS = {
    "pytest": {"-v": 0, "-q": 0, "-k": 1, "-m": 1, "--maxfail": 1, "--tb": 1},
    "ruff check": {"--fix": 0, "--diff": 0, "--output-format": 1, "--select": 1, "--ignore": 1, "--exclude": 1, "--target-version": 1, "--no-cache": 0},
    "mypy": {"--strict": 0, "--config-file": 1, "--python-version": 1, "--show-error-codes": 0, "--no-incremental": 0, "--cache-dir": 1, "--exclude": 1},
    "compileall": {"-q": 0, "-f": 0, "-j": 1, "-x": 1, "-b": 0, "-d": 1, "-s": 1, "-p": 1, "--invalidation-mode": 1},
}
```

Accept `--name=value` when one value is required.

- [ ] **Step 4: Implement parser capture without dispatch**

Recognize exactly `<path>`, `<output>`, `<SHA256>`, `${WORKSPACE}`, `$WORKSPACE`, `$env:WORKSPACE`, and `%WORKSPACE%`. Replace recognized placeholders with inert sentinels. Capture argparse stdout/stderr and `SystemExit`; help exit `0` is valid, parse exit `2` becomes `COMMAND_CLI_INVALID`. Never call `main()` or handlers.

Unknown placeholder-like values emit `COMMAND_PLACEHOLDER_AMBIGUOUS` as `WARNING`.

- [ ] **Step 5: Check only clear repository-local script invocations**

Validate forms such as `python scripts/name.py`, `python ./scripts/name.py`, `bash scripts/name.sh`, `pwsh scripts/name.ps1`, and `powershell -File scripts/name.ps1`. Current missing scripts emit `COMMAND_SCRIPT_MISSING`. Absolute user workspace values remain ordinary argument data.

- [ ] **Step 6: Verify and commit**

```bash
pytest -v tests/unit/documentation_integrity/test_commands.py
ruff check src/ansim_review/documentation_integrity/commands.py tests/unit/documentation_integrity/test_commands.py
mypy src/ansim_review/documentation_integrity/commands.py

git add src/ansim_review/documentation_integrity/commands.py tests/unit/documentation_integrity/test_commands.py
git commit -m "feat: validate documented commands statically"
```

---

### Task 7: Render registered generated Markdown and expand Codex validation instructions

**Files:**
- Create: `src/ansim_review/documentation_integrity/generated.py`
- Modify: `src/ansim_review/packaging/codex_bundle.py`
- Modify: `src/ansim_review/packaging/project_instructions.py`
- Test: `tests/unit/documentation_integrity/test_generated.py`
- Modify: `tests/unit/release/test_output_verifier_documentation.py`

**Interfaces:**
- `GeneratedDocument(path, classification, text, generator_id)`
- `render_generated_documents(config) -> tuple[GeneratedDocument, ...]`
- `render_validation_document() -> str`.

- [ ] **Step 1: Write generator failure tests**

Cover missing module, missing callable, callable exception, non-string return, duplicate virtual path, and successful render. Findings use stable project messages, not exception repr.

- [ ] **Step 2: Write the failing Codex document test**

```python
def test_codex_validation_document_contains_full_offline_sequence() -> None:
    text = render_validation_document()
    assert "python -m ansim_review --help" in text
    assert "python -m ansim_review source-batch --help" in text
    assert "python -m ansim_review rules --help" in text
    assert "python -m ansim_review documentation validate --help" in text
    assert "python -m compileall -q src" in text
```

- [ ] **Step 3: Implement stable rendering**

`build_codex_bundle()` writes exactly `render_validation_document()` with LF newlines. The generator reference format is `package.module:function`; import, resolve, call without arguments, and require `str`.

- [ ] **Step 4: Verify and commit**

```bash
pytest -v tests/unit/documentation_integrity/test_generated.py tests/unit/release/test_output_verifier_documentation.py
ruff check src/ansim_review/documentation_integrity/generated.py src/ansim_review/packaging/codex_bundle.py src/ansim_review/packaging/project_instructions.py tests/unit/documentation_integrity/test_generated.py
mypy src/ansim_review/documentation_integrity/generated.py src/ansim_review/packaging/codex_bundle.py

git add src/ansim_review/documentation_integrity/generated.py src/ansim_review/packaging/codex_bundle.py src/ansim_review/packaging/project_instructions.py tests/unit/documentation_integrity/test_generated.py tests/unit/release/test_output_verifier_documentation.py
git commit -m "feat: validate generated documentation"
```

---

### Task 8: Build the validator and create-only CLI

**Files:**
- Create: `src/ansim_review/documentation_integrity/validator.py`
- Create: `src/ansim_review/documentation_integrity/cli.py`
- Modify: `src/ansim_review/cli_parser.py`
- Modify: `src/ansim_review/cli.py`
- Test: `tests/unit/documentation_integrity/test_validator.py`
- Test: `tests/integration/documentation_integrity/test_cli.py`
- Modify: `tests/unit/documentation_integrity/test_commands.py`

**Interfaces:**
- `validate_documentation(repository_root: Path, config_path: Path) -> DocumentationIntegrityReport`
- `run_documentation_validation(repository_root: Path, config_path: Path, output_path: Path) -> int`
- CLI: `evidence-review documentation validate --repository-root PATH --config PATH --output PATH`.

- [ ] **Step 1: Write orchestration tests**

Use a minimal repository with current, historical, and generated documents. Assert exact counts, warning-only PASS, error FAIL, deterministic findings, and byte-identical reports.

- [ ] **Step 2: Write CLI behavior tests**

Exit codes:

```text
0 = PASS report
1 = FAIL report containing ERROR
2 = invocation error, missing/unreadable config, or existing output
```

Stdout is stable and relative-path based:

```text
Documentation integrity: PASS
Documents: 4 current=2 historical=1 generated=1
Findings: errors=0 warnings=1
Report: build/documentation-integrity-report.json
```

- [ ] **Step 3: Implement two-pass validation**

Pass 1 discovers/renders/parses and builds the classification/heading index. Pass 2 validates links and commands. Convert readable config schema failures into canonical `CONFIG_*` findings. Missing/unreadable authority config raises `DocumentationAuthorityError` and produces exit `2` without a report.

- [ ] **Step 4: Register and dispatch the command**

```python
documentation = subparsers.add_parser(
    "documentation",
    help="validate repository documentation integrity",
)
documentation_stages = documentation.add_subparsers(
    dest="documentation_stage",
    required=True,
)
documentation_validate = documentation_stages.add_parser(
    "validate",
    help="write a canonical documentation integrity report",
)
documentation_validate.add_argument("--repository-root", required=True, type=Path)
documentation_validate.add_argument("--config", required=True, type=Path)
documentation_validate.add_argument("--output", required=True, type=Path)
```

Remove the Task 6 xfail and require this command to validate through the real parser.

- [ ] **Step 5: Implement create-only output and verify**

Use `output_path.open("xb")`. Create parent directories only after authority/config validation. Never overwrite.

```bash
pytest -v tests/unit/documentation_integrity/test_validator.py tests/integration/documentation_integrity/test_cli.py tests/unit/documentation_integrity/test_commands.py
ruff check src/ansim_review/documentation_integrity src/ansim_review/cli.py src/ansim_review/cli_parser.py tests/unit/documentation_integrity tests/integration/documentation_integrity
mypy src/ansim_review/documentation_integrity src/ansim_review/cli.py src/ansim_review/cli_parser.py
```

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/documentation_integrity src/ansim_review/cli.py src/ansim_review/cli_parser.py tests/unit/documentation_integrity tests/integration/documentation_integrity
git commit -m "feat: expose documentation integrity validation"
```

---

### Task 9: Add repository authority config and repair CURRENT documentation

**Files:**
- Create: `documentation-integrity.json`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/OFFLINE_EXECUTION.md`
- Modify: other CURRENT files identified by the canonical report
- Test: `tests/integration/documentation_integrity/test_repository_acceptance.py`

**Interfaces:**
- Repository-owned v1 authority config.
- Repository acceptance requires zero `ERROR` findings.

- [ ] **Step 1: Add the exact config**

```json
{
  "format": "evidence-review/documentation-integrity-config",
  "version": 1,
  "current_roots": ["README.md", "AGENTS.md", "docs", "skills"],
  "historical_roots": ["docs/acceptance", "docs/superpowers/plans", "docs/superpowers/specs"],
  "current_overrides": [
    "docs/superpowers/specs/2026-08-03-documentation-integrity-design.md",
    "docs/superpowers/plans/2026-08-03-documentation-integrity.md"
  ],
  "historical_overrides": [],
  "generated_documents": [
    {
      "id": "CODEX_VALIDATE",
      "generator": "ansim_review.packaging.codex_bundle:render_validation_document",
      "virtual_path": "codex-workspace/VALIDATE.md",
      "classification": "CURRENT"
    },
    {
      "id": "WEB_PROJECT_INSTRUCTIONS",
      "generator": "ansim_review.packaging.project_instructions:render_project_instructions",
      "virtual_path": "chatgpt-web-runtime/PROJECT_INSTRUCTIONS.md",
      "classification": "CURRENT"
    }
  ]
}
```

- [ ] **Step 2: Write repository acceptance before repairs**

```python
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_repository_documentation_has_no_errors() -> None:
    report = validate_documentation(
        REPOSITORY_ROOT,
        REPOSITORY_ROOT / "documentation-integrity.json",
    )
    assert report.status == "PASS", report_bytes(report).decode("utf-8")
    assert report.error_count == 0
```

Run once and preserve the first FAIL report as baseline evidence.

- [ ] **Step 3: Replace known obsolete current instructions**

Run:

```bash
git grep -n -E "migrate_ansim_workspace\.py|build_ansim_release\.py|repair_grist_document\.py|export_grist_csv\.py|rebuild_visuals_and_grist\.py|validate_workspace\.py|CHATGPT_WEB_WORKFLOW\.md" -- README.md AGENTS.md docs skills
```

For CURRENT files only:

| Obsolete reference | Required treatment |
|---|---|
| `migrate_ansim_workspace.py` | Replace with `evidence-review source-batch prepare` and `source-batch ingest`. |
| `build_ansim_release.py` | Remove executable claim; link to `docs/OFFLINE_EXECUTION.md`. |
| `repair_grist_document.py` | Remove executable claim; state that legacy direct repair is not shipped. |
| `export_grist_csv.py` | Remove executable claim; do not invent an export CLI. |
| `rebuild_visuals_and_grist.py` | Replace current ingestion guidance with source-batch commands, or classify the section as historical. |
| `validate_workspace.py` | Replace current documentation checks with the documentation CLI plus pytest/Ruff/mypy/compileall; do not claim this replaces SQLite or release-output validation. |
| `CHATGPT_WEB_WORKFLOW.md` | Use `README.md#8-검토-run` for orchestration context or `docs/OFFLINE_EXECUTION.md` for offline/release context. |

Do not rewrite historical records.

- [ ] **Step 4: Replace the known `AGENTS.md` command blocks**

Current workflows use:

```powershell
evidence-review source-batch prepare `
  --root <workspace> `
  --manifest <workspace>/manifests/source-batch.json

evidence-review source-batch ingest `
  --root <workspace> `
  --manifest <workspace>/manifests/source-batch.json `
  --output <workspace>/evidence/evidence.sqlite

evidence-review documentation validate `
  --repository-root . `
  --config documentation-integrity.json `
  --output <output>/documentation-integrity-report.json
```

Legacy Grist UI evidence uses only the existing `evidence-review legacy validate-grist-qa` command. State explicitly that direct repair/export wrappers are not current runtime commands.

- [ ] **Step 5: Resolve every remaining canonical ERROR**

Run the CLI with a fresh output filename on every pass. Apply only the action mapped to the finding code: correct/remove missing links, correct anchors, replace/remove missing commands, fix config classification, label links to historical records, or replace unsafe Markdown targets with safe POSIX repository-relative targets.

- [ ] **Step 6: Verify and commit**

```bash
pytest -v tests/integration/documentation_integrity/test_repository_acceptance.py
ruff check src tests
mypy src

git add documentation-integrity.json README.md AGENTS.md docs skills tests/integration/documentation_integrity/test_repository_acceptance.py
git commit -m "docs: align repository guidance with canonical cli"
```

Expected: report status PASS; warnings may remain.

---

### Task 10: Integrate workspace and release fail-closed gates

**Files:**
- Modify: `src/ansim_review/release/validator.py`
- Modify: `src/ansim_review/release/builder.py`
- Modify: `tests/unit/release/test_release_output_gate.py`
- Modify: `tests/integration/release/test_release_builder.py`
- Create: `tests/integration/release/test_documentation_gate.py`

**Interfaces:**
- `validate_release_workspace()` embeds `documentation` report payload.
- Workspace errors add `DOCUMENTATION_INTEGRITY_FAILED` on documentation FAIL.
- `_automated_reason_codes()` returns documentation reason immediately after `AUTOMATED_VALIDATION_FAILED`.

- [ ] **Step 1: Write failing workspace tests**

```python
report = validate_release_workspace(root)
assert report["status"] == "FAIL"
assert "DOCUMENTATION_INTEGRITY_FAILED" in report["errors"]
assert report["documentation"]["status"] == "FAIL"
```

A warning-only external URL must leave workspace status PASS.

- [ ] **Step 2: Freeze release reason ordering**

```python
assert _automated_reason_codes(
    {"status": "FAIL", "errors": ["DOCUMENTATION_INTEGRITY_FAILED"]},
    {"status": "PASS"},
) == ["AUTOMATED_VALIDATION_FAILED", "DOCUMENTATION_INTEGRITY_FAILED"]
```

With output failure, order is:

```text
AUTOMATED_VALIDATION_FAILED
DOCUMENTATION_INTEGRITY_FAILED
RELEASE_OUTPUT_VALIDATION_FAILED
```

- [ ] **Step 3: Update synthetic release fixtures**

Add minimal `README.md`, `AGENTS.md`, `docs/OFFLINE_EXECUTION.md`, and `documentation-integrity.json`. Synthetic configs may use no historical/generated documents unless the test targets those features.

- [ ] **Step 4: Implement pure integration**

Call `validate_documentation()` without writing a file. Embed `report_document(report)`. A missing/unreadable authority config becomes stable documentation failure data in workspace validation.

- [ ] **Step 5: Prove attestation cannot bypass documentation failure**

```python
assert manifest["status"] == "BLOCKED"
assert manifest["reason_codes"] == [
    "AUTOMATED_VALIDATION_FAILED",
    "DOCUMENTATION_INTEGRITY_FAILED",
]
assert manifest["tag_allowed"] is False
```

- [ ] **Step 6: Verify and commit**

```bash
pytest -v tests/unit/release/test_release_output_gate.py tests/integration/release/test_release_builder.py tests/integration/release/test_documentation_gate.py
ruff check src/ansim_review/release tests/unit/release tests/integration/release
mypy src/ansim_review/release

git add src/ansim_review/release/validator.py src/ansim_review/release/builder.py tests/unit/release/test_release_output_gate.py tests/integration/release/test_release_builder.py tests/integration/release/test_documentation_gate.py
git commit -m "feat: block release on documentation errors"
```

---

### Task 11: Add CI, wheel checks, reproducibility, and acceptance evidence

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `docs/acceptance/issue-50/README.md`
- Modify: `tests/integration/documentation_integrity/test_repository_acceptance.py`

**Interfaces:**
- CI validates repository documentation before full pytest.
- Python 3.11/3.13 installed wheels expose documentation CLI help.
- Acceptance evidence records exact HEAD and report identity.

- [ ] **Step 1: Add CI validation**

```yaml
- name: Validate repository documentation
  run: evidence-review documentation validate --repository-root . --config documentation-integrity.json --output build/documentation-integrity-report.json
```

- [ ] **Step 2: Add wheel parser checks for both versions**

```bash
.wheel-venv/bin/evidence-review documentation validate --help
.wheel-venv/bin/python -m evidence_review documentation validate --help
.wheel-venv/bin/python -m ansim_review documentation validate --help
```

The wheel does not need to package repository Markdown/config; this check covers parser/importability only.

- [ ] **Step 3: Add byte-reproducibility acceptance**

Copy the in-scope Markdown/config into two temporary roots, validate both, and assert `report_bytes(first) == report_bytes(second)`. Exclude `.git` and generated build outputs.

- [ ] **Step 4: Create the acceptance record**

First lines:

```markdown
> Document status: HISTORICAL RECORD

# Issue #50 Documentation Integrity Acceptance
```

Sections:

```text
A. Basis
B. Automated result
C. Repository document counts
D. Error and warning counts
E. Generated Markdown result
F. Static command result
G. Release fail-closed result
H. Determinism result
I. Python 3.11/3.13 wheel result
J. Limitations
```

State that external availability was not checked, Markdown commands were not executed, warnings do not block by default, and historical content was not rewritten.

- [ ] **Step 5: Run the complete local gate**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
python -m pip install build
python -m build --wheel
```

Run the documentation CLI twice with different output paths and assert the files are byte-identical.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml docs/acceptance/issue-50/README.md tests/integration/documentation_integrity/test_repository_acceptance.py
git commit -m "test: verify documentation integrity release gate"
```

---

### Task 12: Final review and draft PR handoff

**Files:**
- Review all Task 1-11 changes.
- Update only the final ledger in `docs/acceptance/issue-50/README.md`.
- Comment on Issues #50 and #27.

- [ ] **Step 1: Verify change scope**

```bash
git diff --stat main...HEAD
git diff --check main...HEAD
git status --short
```

Reject unrelated runtime, rule, golden, Grist, lineage, or attestation changes.

- [ ] **Step 2: Run targeted regressions**

```bash
pytest -v tests/unit/documentation_integrity tests/integration/documentation_integrity
pytest -v tests/unit/release tests/integration/release
pytest -v tests/unit/rule_engine tests/integration/rule_engine
```

- [ ] **Step 3: Verify boundary cases**

```text
existing output -> exit 2 and unchanged file
broken current link -> exit 1 and canonical FAIL report
warning-only external URL -> exit 0 and canonical PASS report
missing config -> exit 2 and no report
historical missing marker -> warning only
current missing script -> error
valid attestation plus documentation error -> release BLOCKED
```

- [ ] **Step 4: Finalize acceptance ledger**

Record remote HEAD, OS, Python versions, test counts, report SHA-256/counts, wheel results, and observed Actions state. Never equate manual PASS with GitHub Actions PASS.

- [ ] **Step 5: Open a draft PR**

Title:

```text
feat: validate repository-wide documentation integrity
```

Body includes `Implements #50`, `Parent #27`, exact validation status, and observed Actions status.

- [ ] **Step 6: Stop before Ready/merge**

Do not mark Ready, merge, or close #50 until repository report has zero errors; full pytest/Ruff/mypy/compileall pass; Python 3.11/3.13 wheel checks pass; release fail-closed tests pass; and acceptance evidence matches exact remote HEAD.

## Plan Self-Review

- Every approved requirement maps to Tasks 2-11.
- The parser dependency cycle is prevented by Task 1.
- Anchor normalization, historical labeling, URL severity, placeholder handling, exit codes, report ordering, and release reason ordering are explicit.
- No online crawler, command executor, legacy wrapper restoration, formatter, or unrelated migration is included.
- The names `DocumentationIntegrityConfig`, `DocumentationFinding`, `DocumentationIntegrityReport`, `DiscoveredDocument`, `ParsedMarkdown`, and `validate_documentation()` are consistent across tasks.
