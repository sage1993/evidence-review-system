# Repository-wide Documentation Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, offline documentation-integrity gate that validates every in-scope repository Markdown document and registered generated Markdown, emits a canonical report, and blocks release on documentation errors.

**Architecture:** Implement an isolated `ansim_review.documentation_integrity` package with strict contracts, path classification, Markdown extraction, link/path checks, static command validation, generated-document rendering, deterministic report construction, and a thin CLI writer. Reuse one validation function from the user-facing CLI, release workspace validator, repository acceptance test, and wheel checks so all gates apply the same policy.

**Tech Stack:** Python 3.11+ standard library only, `argparse`, frozen dataclasses, `pathlib`, `json`, `importlib`, `re`, `shlex`, existing canonical JSON utilities, pytest, Ruff, strict mypy, GitHub Actions.

## Global Constraints

- Do not restore missing legacy wrapper scripts.
- Do not add runtime dependencies.
- Do not make network requests while validating URLs.
- Do not execute commands extracted from Markdown.
- Scan `README.md`, `AGENTS.md`, `docs/**/*.md`, `skills/**/SKILL.md`, and registered generated Markdown.
- Treat `docs/acceptance/**`, `docs/superpowers/plans/**`, and `docs/superpowers/specs/**` as historical by default, with explicit overrides.
- Invalid external URL syntax is always a `WARNING` and never fails validation by itself.
- `ERROR` findings produce report status `FAIL`; warning-only reports remain `PASS`.
- Reports are canonical, deterministic, create-only JSON.
- Historical records are not rewritten to current command, branch, or artifact semantics.
- Machine-specific absolute paths in prose are not repository references; only Markdown targets and recognized repository-local command arguments receive repository path checks.
- Preserve rule golden artifacts, activation approvals, active manifests, Grist QA artifacts, lineage artifacts, and human attestation contracts unchanged.

---

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

### Task 1: Extract the CLI parser without changing command behavior

**Files:**
- Create: `src/ansim_review/cli_parser.py`
- Modify: `src/ansim_review/cli.py`
- Modify: `src/evidence_review/cli.py`
- Test: `tests/unit/test_cli_parser.py`

**Interfaces:**
- Produces: `build_parser() -> argparse.ArgumentParser` in `ansim_review.cli_parser`.
- Preserves: `ansim_review.cli.build_parser` as a re-export for `entrypoint.py` and existing imports.
- Later consumed by: `documentation_integrity.commands.validate_cli_tokens()`.

- [ ] **Step 1: Write a failing parser identity and command-freeze test**

```python
from ansim_review.cli import build_parser as legacy_build_parser
from ansim_review.cli_parser import build_parser
from evidence_review.cli import build_parser as canonical_build_parser


def test_parser_builder_is_shared_without_command_loss() -> None:
    parser = build_parser()
    assert legacy_build_parser is build_parser
    assert canonical_build_parser is build_parser
    assert parser.parse_args(["source-batch", "prepare", "--root", ".", "--manifest", "m.json"]).command == "source-batch"
    assert parser.parse_args(["rules", "select", "--repository-root", ".", "--manifest", "a.json", "--context", "c.json"]).rules_stage == "select"
```

- [ ] **Step 2: Run the test and verify the new module is missing**

Run:

```bash
pytest -v tests/unit/test_cli_parser.py
```

Expected: collection fails with `ModuleNotFoundError: ansim_review.cli_parser`.

- [ ] **Step 3: Move only `build_parser()` into `cli_parser.py`**

`cli_parser.py` must import only `argparse` and `Path`. `cli.py` must import and re-export the function:

```python
from ansim_review.cli_parser import build_parser

__all__ = ["build_parser", "main"]
```

Do not move handlers or change argument names, destinations, required flags, help text, or command dispatch in this task.

- [ ] **Step 4: Run parser and existing CLI tests**

```bash
pytest -v tests/unit/test_cli_parser.py tests/unit/test_cli.py tests/integration/test_cli.py
```

If either existing test path does not exist, run `pytest -v tests -k "cli and not documentation"` instead and record the collected test count.

Expected: PASS with no output differences in existing commands.

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
- Produces:
  - `GeneratedDocumentConfig`
  - `DocumentationIntegrityConfig`
  - `DocumentationFinding`
  - `DocumentationIntegrityReport`
  - `decode_config_bytes(data: bytes) -> DocumentationIntegrityConfig`
  - `report_document(report: DocumentationIntegrityReport) -> dict[str, object]`
  - `report_bytes(report: DocumentationIntegrityReport) -> bytes`
  - `finding_sort_key(finding: DocumentationFinding) -> tuple[object, ...]`
- Adds format constants:
  - `DOCUMENTATION_INTEGRITY_CONFIG_FORMAT`
  - `DOCUMENTATION_INTEGRITY_REPORT_FORMAT`

- [ ] **Step 1: Write failing strict-decoder tests**

Cover exact valid decoding and rejection of unknown fields, duplicate JSON keys, duplicate roots, invalid generator IDs, invalid classifications, absolute paths, `.`/`..`, empty components, and backslashes.

```python
VALID_CONFIG = b'''{
  "format":"evidence-review/documentation-integrity-config",
  "version":1,
  "current_roots":["README.md","docs"],
  "historical_roots":["docs/acceptance"],
  "current_overrides":[],
  "historical_overrides":[],
  "generated_documents":[{
    "id":"CODEX_VALIDATE",
    "generator":"ansim_review.packaging.codex_bundle:render_validation_document",
    "virtual_path":"codex-workspace/VALIDATE.md",
    "classification":"CURRENT"
  }]
}'''


def test_config_rejects_duplicate_json_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        decode_config_bytes(VALID_CONFIG.replace(b'"version":1', b'"version":1,"version":1'))
```

- [ ] **Step 2: Run contract tests and verify failure**

```bash
pytest -v tests/unit/documentation_integrity/test_contract.py
```

Expected: import or attribute failures.

- [ ] **Step 3: Implement frozen slot dataclasses and exact-key decoding**

Use `json.loads(..., object_pairs_hook=...)` with a hook that raises on duplicate keys. Validate path strings component-by-component using `PurePosixPath`; do not use platform-native separator normalization.

The finding model must have exactly:

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

The report constructor must derive counts from supplied documents and findings rather than trusting caller-provided counts.

- [ ] **Step 4: Add deterministic report-byte tests**

```python
def test_report_bytes_are_stable_and_errors_sort_before_warnings() -> None:
    first = report_bytes(make_report(findings=(warning, error, error)))
    second = report_bytes(make_report(findings=(error, warning)))
    assert first == second
    payload = json.loads(first)
    assert payload["status"] == "FAIL"
    assert payload["error_count"] == 1
    assert payload["warning_count"] == 1
```

- [ ] **Step 5: Run tests and static checks**

```bash
pytest -v tests/unit/documentation_integrity/test_contract.py
ruff check src/ansim_review/documentation_integrity/contract.py src/ansim_review/contracts/formats.py tests/unit/documentation_integrity/test_contract.py
mypy src/ansim_review/documentation_integrity/contract.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ansim_review/contracts/formats.py src/ansim_review/documentation_integrity tests/unit/documentation_integrity/test_contract.py
git commit -m "feat: define documentation integrity contracts"
```

---

### Task 3: Implement deterministic path classification and discovery

**Files:**
- Create: `src/ansim_review/documentation_integrity/classification.py`
- Create: `src/ansim_review/documentation_integrity/discovery.py`
- Test: `tests/unit/documentation_integrity/test_classification.py`
- Test: `tests/unit/documentation_integrity/test_discovery.py`

**Interfaces:**
- Produces:
  - `classify_document(path: str, config: DocumentationIntegrityConfig) -> Literal["CURRENT", "HISTORICAL"]`
  - `DiscoveredDocument(path: str, filesystem_path: Path, classification: DocumentClassification)`
  - `discover_repository_documents(repository_root: Path, config: DocumentationIntegrityConfig) -> tuple[DiscoveredDocument, ...]`
- Raises `DocumentClassificationError(code, path)` for conflict or missing classification.

- [ ] **Step 1: Write classification precedence tests**

```python
def test_more_specific_historical_root_beats_current_docs_root() -> None:
    config = make_config(
        current_roots=("docs",),
        historical_roots=("docs/acceptance",),
    )
    assert classify_document("docs/README.md", config) == "CURRENT"
    assert classify_document("docs/acceptance/issue-48/README.md", config) == "HISTORICAL"


def test_current_override_beats_historical_spec_root() -> None:
    config = make_config(
        current_roots=("docs",),
        historical_roots=("docs/superpowers/specs",),
        current_overrides=("docs/superpowers/specs/2026-08-03-documentation-integrity-design.md",),
    )
    assert classify_document("docs/superpowers/specs/2026-08-03-documentation-integrity-design.md", config) == "CURRENT"
```

Also test equal-specificity current/historical matches as `CONFIG_CLASSIFICATION_CONFLICT` and unmatched Markdown as `DOCUMENT_CLASSIFICATION_MISSING`.

- [ ] **Step 2: Write discovery safety tests**

Create a temporary repository containing `README.md`, `AGENTS.md`, nested docs, skill files, unrelated Markdown outside scope, non-Markdown files, and a symlink escaping the root. Assert bytewise POSIX path ordering and fail-closed handling of the escaping symlink.

- [ ] **Step 3: Run tests and verify failures**

```bash
pytest -v tests/unit/documentation_integrity/test_classification.py tests/unit/documentation_integrity/test_discovery.py
```

- [ ] **Step 4: Implement scope matching**

A scope path matches itself and descendants by POSIX path components. Select the match with the greatest component count. Overrides are evaluated before roots. Do not infer file-versus-directory semantics from whether a path currently exists.

- [ ] **Step 5: Implement repository discovery**

Discover exactly:

```python
candidates = [repository_root / "README.md", repository_root / "AGENTS.md"]
candidates.extend((repository_root / "docs").rglob("*.md"))
candidates.extend((repository_root / "skills").glob("*/SKILL.md"))
```

Skip missing top-level optional directories, reject non-regular discovered entries, and reject symlinks whose resolved path is outside `repository_root.resolve()`.

- [ ] **Step 6: Run tests and commit**

```bash
pytest -v tests/unit/documentation_integrity/test_classification.py tests/unit/documentation_integrity/test_discovery.py
ruff check src/ansim_review/documentation_integrity tests/unit/documentation_integrity
mypy src/ansim_review/documentation_integrity

git add src/ansim_review/documentation_integrity/classification.py src/ansim_review/documentation_integrity/discovery.py tests/unit/documentation_integrity/test_classification.py tests/unit/documentation_integrity/test_discovery.py
git commit -m "feat: classify and discover documentation"
```

---

### Task 4: Parse Markdown structures and define project anchor normalization

**Files:**
- Create: `src/ansim_review/documentation_integrity/markdown.py`
- Test: `tests/unit/documentation_integrity/test_markdown.py`

**Interfaces:**
- Produces:
  - `MarkdownHeading(text, anchor, line, column)`
  - `MarkdownLink(label, target, is_image, line, column)`
  - `CommandBlock(language, text, start_line)`
  - `ParsedMarkdown(headings, links, command_blocks, raw_urls, first_non_empty_line)`
  - `parse_markdown(text: str) -> ParsedMarkdown`
  - `normalize_heading_anchor(text: str) -> str`
  - `assign_heading_anchors(headings: Sequence[str]) -> tuple[str, ...]`

- [ ] **Step 1: Write structural extraction tests**

Include ATX headings, Setext headings, inline links, images, reference-style links, same-file fragments, cross-file fragments, fenced PowerShell/bash/text blocks, code spans containing fake links, and escaped Markdown.

- [ ] **Step 2: Freeze anchor policy with Unicode and duplicates**

Use this exact policy:

1. Unicode NFKC normalization.
2. `casefold()`.
3. Keep Unicode alphanumeric characters, `_`, `-`, and whitespace.
4. Remove other punctuation.
5. Convert each whitespace run to one `-`.
6. Collapse repeated `-` and strip leading/trailing `-`.
7. Empty result becomes `section`.
8. Duplicate anchors receive `-1`, `-2`, and so on in source order.

```python
def test_anchor_normalization_is_unicode_stable() -> None:
    assert normalize_heading_anchor("검토 Run") == "검토-run"
    assert assign_heading_anchors(["Title", "Title", "TITLE"]) == (
        "title",
        "title-1",
        "title-2",
    )
```

- [ ] **Step 3: Run tests and verify failure**

```bash
pytest -v tests/unit/documentation_integrity/test_markdown.py
```

- [ ] **Step 4: Implement a bounded standard-library parser**

Use line-oriented state tracking for fenced blocks and Setext headings, then regular expressions for links and reference definitions. Do not treat inline code or non-command fenced contents as commands. Resolve reference-style link uses after collecting definitions. Preserve 1-based line and column positions.

- [ ] **Step 5: Run tests and commit**

```bash
pytest -v tests/unit/documentation_integrity/test_markdown.py
ruff check src/ansim_review/documentation_integrity/markdown.py tests/unit/documentation_integrity/test_markdown.py
mypy src/ansim_review/documentation_integrity/markdown.py

git add src/ansim_review/documentation_integrity/markdown.py tests/unit/documentation_integrity/test_markdown.py
git commit -m "feat: parse documentation structures"
```

---

### Task 5: Validate internal links, safe repository paths, and URL schemes

**Files:**
- Create: `src/ansim_review/documentation_integrity/links.py`
- Test: `tests/unit/documentation_integrity/test_links.py`

**Interfaces:**
- Produces:
  - `validate_links(document: DiscoveredDocument, parsed: ParsedMarkdown, index: DocumentationIndex) -> tuple[DocumentationFinding, ...]`
  - `DocumentationIndex` containing classifications, headings by path, and registered virtual paths.
- Consumes: Task 3 discovery/classification and Task 4 parsed structures.

- [ ] **Step 1: Write current-document failure tests**

Cover missing target, missing anchor, repository escape, absolute Markdown target, backslash Markdown target, existing directory, image target, query string plus fragment, virtual generated target, and current-to-historical link labeling.

The explicit historical label rule is:

```text
The link label starts with "Historical:" or "과거 기록:".
```

Anything else linking from a current document to a historical document emits `CURRENT_TO_HISTORICAL_REFERENCE_UNMARKED` as `ERROR`.

- [ ] **Step 2: Write historical-document boundary tests**

Historical documents must not fail because a safe old target no longer exists. They must still emit errors for Markdown targets such as `../../../../outside.md`, `C:/repo/file.md`, `/repo/file.md`, or `docs\\file.md`. A plain prose line containing `F:\old-worktree` must not be interpreted as a repository reference.

Missing first-line marker emits:

```python
DocumentationFinding(
    severity="WARNING",
    code="HISTORICAL_MARKER_MISSING",
    ...,
)
```

- [ ] **Step 3: Write external URL warning tests**

`https://example.com/path` is valid. `http://`, `ftp://`, `//host/path`, and `https:///missing-host` emit `EXTERNAL_URL_SCHEME_INVALID` as `WARNING` for both current and historical documents.

- [ ] **Step 4: Run tests and verify failures**

```bash
pytest -v tests/unit/documentation_integrity/test_links.py
```

- [ ] **Step 5: Implement link resolution**

Resolve file links relative to the containing document directory. Percent-decode only for target resolution; preserve the original target in findings. Strip query and fragment before file lookup. Resolve fragments through the target document's parsed heading anchors.

A path is a repository reference only when it appears as a Markdown link/image target or has already been identified by the command checker as repository-local. Do not scan arbitrary prose or JSON samples for absolute paths.

- [ ] **Step 6: Run tests and commit**

```bash
pytest -v tests/unit/documentation_integrity/test_links.py
ruff check src/ansim_review/documentation_integrity/links.py tests/unit/documentation_integrity/test_links.py
mypy src/ansim_review/documentation_integrity/links.py

git add src/ansim_review/documentation_integrity/links.py tests/unit/documentation_integrity/test_links.py
git commit -m "feat: validate documentation links and paths"
```

---

### Task 6: Statistically validate documented commands without execution

**Files:**
- Create: `src/ansim_review/documentation_integrity/commands.py`
- Test: `tests/unit/documentation_integrity/test_commands.py`

**Interfaces:**
- Produces:
  - `normalize_command_block(block: CommandBlock) -> tuple[CommandLine, ...]`
  - `validate_command_lines(lines: Sequence[CommandLine], repository_root: Path, document: DiscoveredDocument) -> tuple[DocumentationFinding, ...]`
  - `validate_cli_tokens(tokens: Sequence[str]) -> str | None`, returning a stable error message or `None`.
- Consumes: `ansim_review.cli_parser.build_parser` without dispatching handlers.

- [ ] **Step 1: Write command normalization tests**

Cover PowerShell backtick continuation, POSIX backslash continuation, prompt prefixes (`PS>`, `$`), comments, quoted paths, multiple independent commands, and `text` blocks that do not start with a recognized executable.

- [ ] **Step 2: Write actual argparse validation tests**

```python
@pytest.mark.parametrize(
    "command",
    [
        "evidence-review source-batch prepare --root <path> --manifest <path>",
        "python -m ansim_review rules select --repository-root . --manifest <path> --context <path>",
        "python -m evidence_review documentation validate --help",
    ],
)
def test_valid_project_commands_are_accepted(command: str) -> None:
    assert validate_text_command(command, repository_root=Path(".")) == ()


def test_unknown_subcommand_is_error() -> None:
    findings = validate_text_command("evidence-review source-batch explode --root .")
    assert [item.code for item in findings] == ["COMMAND_CLI_INVALID"]
```

Before Task 8 adds `documentation`, mark the future command in the test with `pytest.mark.xfail(strict=True, reason="Task 8 registers command")`, then remove the marker in Task 8. Do not add a fake parser branch here.

- [ ] **Step 3: Define the bounded tool option registry**

Support these option forms initially:

```python
TOOL_OPTIONS = {
    "pytest": {"-v": 0, "-q": 0, "-k": 1, "-m": 1, "--maxfail": 1, "--tb": 1, "--strict-markers": 0, "--strict-config": 0},
    "ruff check": {"--fix": 0, "--diff": 0, "--output-format": 1, "--select": 1, "--ignore": 1, "--extend-select": 1, "--extend-ignore": 1, "--exclude": 1, "--target-version": 1, "--no-cache": 0},
    "mypy": {"--strict": 0, "--config-file": 1, "--python-version": 1, "--show-error-codes": 0, "--no-incremental": 0, "--cache-dir": 1, "--exclude": 1},
    "compileall": {"-q": 0, "-f": 0, "-j": 1, "-x": 1, "-b": 0, "-d": 1, "-s": 1, "-p": 1, "--invalidation-mode": 1, "--hardlink-dupes": 0, "--stripdir": 1, "--prependdir": 1, "--legacy": 0},
}
```

Accept `--name=value` when the registry says the option takes one value.

- [ ] **Step 4: Implement placeholder substitution and parser capture**

Recognize exactly:

```text
<path> <output> <SHA256> ${WORKSPACE} $WORKSPACE $env:WORKSPACE %WORKSPACE%
```

Replace recognized placeholders with inert sentinel strings before `argparse` parsing. Capture `stdout`, `stderr`, and `SystemExit`; code `0` from `--help` is valid, code `2` is `COMMAND_CLI_INVALID`. Never call `args.func`, `main()`, or any command handler.

Unknown angle-bracket or variable-looking values produce `COMMAND_PLACEHOLDER_AMBIGUOUS` as `WARNING` while still satisfying value presence.

- [ ] **Step 5: Validate repository-local script invocations**

Check only clear script forms:

```text
python scripts/name.py
python ./scripts/name.py
./scripts/name.sh
.\scripts\name.ps1
pwsh scripts/name.ps1
powershell -File scripts/name.ps1
```

Current documents referencing a missing script emit `COMMAND_SCRIPT_MISSING`. Absolute user workspace values such as `F:\evidence-review-workspace\input.pdf` are argument data, not repository script references.

- [ ] **Step 6: Run tests and commit**

```bash
pytest -v tests/unit/documentation_integrity/test_commands.py
ruff check src/ansim_review/documentation_integrity/commands.py tests/unit/documentation_integrity/test_commands.py
mypy src/ansim_review/documentation_integrity/commands.py

git add src/ansim_review/documentation_integrity/commands.py tests/unit/documentation_integrity/test_commands.py
git commit -m "feat: validate documented commands statically"
```

---

### Task 7: Render and validate generated Markdown

**Files:**
- Create: `src/ansim_review/documentation_integrity/generated.py`
- Modify: `src/ansim_review/packaging/codex_bundle.py`
- Modify: `src/ansim_review/packaging/project_instructions.py`
- Test: `tests/unit/documentation_integrity/test_generated.py`
- Test: `tests/unit/release/test_output_verifier_documentation.py`

**Interfaces:**
- Produces:
  - `GeneratedDocument(path: str, classification: DocumentClassification, text: str, generator_id: str)`
  - `render_generated_documents(config: DocumentationIntegrityConfig) -> tuple[GeneratedDocument, ...]`
  - `render_validation_document() -> str` in `codex_bundle.py`.
- Preserves: `render_project_instructions() -> str`.

- [ ] **Step 1: Write generator failure tests**

Cover missing module, missing callable, callable exception, non-string return, duplicate virtual path, and successful in-memory render. Assert stable finding codes rather than exception repr text.

- [ ] **Step 2: Write the failing Codex validation-document test**

```python
def test_codex_validation_document_contains_full_offline_sequence() -> None:
    text = render_validation_document()
    assert "python -m ansim_review --help" in text
    assert "python -m ansim_review rules --help" in text
    assert "python -m ansim_review source-batch --help" in text
    assert "python -m ansim_review documentation validate --help" in text
    assert "python -m compileall -q src" in text
```

Expected initially: import or assertion failure because the bundle writes an inline one-command string.

- [ ] **Step 3: Implement `render_validation_document()` and use it verbatim**

The generated document must be stable UTF-8 Markdown with LF newlines and this command order:

```powershell
python -m ansim_review --help
python -m ansim_review source-batch --help
python -m ansim_review rules --help
python -m ansim_review documentation validate --help
python -m compileall -q src
```

`build_codex_bundle()` must write exactly `render_validation_document()` to `VALIDATE.md`; do not duplicate the text in the builder.

- [ ] **Step 4: Implement safe registered generator loading**

Split `package.module:function` once at `:`. Import the module, resolve the named attribute, require it to be callable, call with no arguments, and require `str`. Convert all failures to stable findings in the orchestrator; do not include absolute paths or exception messages in report messages.

- [ ] **Step 5: Run tests and commit**

```bash
pytest -v tests/unit/documentation_integrity/test_generated.py tests/unit/release/test_output_verifier_documentation.py
ruff check src/ansim_review/documentation_integrity/generated.py src/ansim_review/packaging/codex_bundle.py src/ansim_review/packaging/project_instructions.py tests/unit/documentation_integrity/test_generated.py
mypy src/ansim_review/documentation_integrity/generated.py src/ansim_review/packaging/codex_bundle.py

git add src/ansim_review/documentation_integrity/generated.py src/ansim_review/packaging/codex_bundle.py src/ansim_review/packaging/project_instructions.py tests/unit/documentation_integrity/test_generated.py tests/unit/release/test_output_verifier_documentation.py
git commit -m "feat: validate generated documentation"
```

---

### Task 8: Build the orchestration engine and create-only CLI

**Files:**
- Create: `src/ansim_review/documentation_integrity/validator.py`
- Create: `src/ansim_review/documentation_integrity/cli.py`
- Modify: `src/ansim_review/cli_parser.py`
- Modify: `src/ansim_review/cli.py`
- Test: `tests/unit/documentation_integrity/test_validator.py`
- Test: `tests/integration/documentation_integrity/test_cli.py`
- Modify: `tests/unit/documentation_integrity/test_commands.py`

**Interfaces:**
- Produces:
  - `validate_documentation(repository_root: Path, config_path: Path) -> DocumentationIntegrityReport`
  - `run_documentation_validation(repository_root: Path, config_path: Path, output_path: Path) -> int`
- Registers:

```text
evidence-review documentation validate
  --repository-root PATH
  --config PATH
  --output PATH
```

- [ ] **Step 1: Write a failing end-to-end validator test**

Create a minimal repository with valid current/historical docs and one generated document. Assert exact counts, stable ordering, warning-only PASS, error FAIL, and byte-identical `report_bytes()` across two validations.

- [ ] **Step 2: Write CLI exit-code and create-only tests**

Required behavior:

```text
0 = report PASS
1 = report FAIL due to ERROR findings
2 = invocation error, missing/unreadable authority config, or existing output path
```

Assert concise stdout exactly:

```text
Documentation integrity: PASS
Documents: 4 current=2 historical=1 generated=1
Findings: errors=0 warnings=1
Report: build/documentation-integrity-report.json
```

Normalize the displayed report path relative to the explicit repository root when possible; never print a machine-specific resolved absolute path.

- [ ] **Step 3: Implement two-pass orchestration**

Pass 1 discovers and renders documents, parses headings, and builds the index. Pass 2 validates links and commands. Convert discovery, classification, render, parse, and config-schema failures into findings. Deduplicate and sort only once when constructing the final report.

Missing or unreadable config authority must raise `DocumentationAuthorityError`; malformed but readable config produces a canonical FAIL report with `CONFIG_*` findings.

- [ ] **Step 4: Register the CLI parser branch**

Add:

```python
documentation = subparsers.add_parser("documentation", help="validate repository documentation integrity")
documentation_stages = documentation.add_subparsers(dest="documentation_stage", required=True)
documentation_validate = documentation_stages.add_parser("validate", help="write a canonical documentation integrity report")
documentation_validate.add_argument("--repository-root", required=True, type=Path)
documentation_validate.add_argument("--config", required=True, type=Path)
documentation_validate.add_argument("--output", required=True, type=Path)
```

Dispatch through `_documentation_validate()` in `ansim_review.cli`. Remove the strict xfail marker from Task 6 and require the new command to pass static validation.

- [ ] **Step 5: Implement create-only output**

Use `output_path.open("xb")`; do not pre-delete or overwrite. Create parent directories only after config authority is readable and invocation arguments are valid.

- [ ] **Step 6: Run tests and commit**

```bash
pytest -v tests/unit/documentation_integrity/test_validator.py tests/integration/documentation_integrity/test_cli.py tests/unit/documentation_integrity/test_commands.py
ruff check src/ansim_review/documentation_integrity src/ansim_review/cli.py src/ansim_review/cli_parser.py tests/unit/documentation_integrity tests/integration/documentation_integrity
mypy src/ansim_review/documentation_integrity src/ansim_review/cli.py src/ansim_review/cli_parser.py

git add src/ansim_review/documentation_integrity src/ansim_review/cli.py src/ansim_review/cli_parser.py tests/unit/documentation_integrity/test_validator.py tests/integration/documentation_integrity/test_cli.py tests/unit/documentation_integrity/test_commands.py
git commit -m "feat: expose documentation integrity validation"
```

---

### Task 9: Add repository authority configuration and repair current documentation

**Files:**
- Create: `documentation-integrity.json`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/OFFLINE_EXECUTION.md`
- Modify: current Markdown files reported by the validator
- Test: `tests/integration/documentation_integrity/test_repository_acceptance.py`

**Interfaces:**
- Produces the repository-owned v1 config consumed by CLI and release validation.
- Establishes current-document acceptance: zero `ERROR` findings on the repository branch.

- [ ] **Step 1: Add the exact authority config**

```json
{
  "format": "evidence-review/documentation-integrity-config",
  "version": 1,
  "current_roots": ["README.md", "AGENTS.md", "docs", "skills"],
  "historical_roots": ["docs/acceptance", "docs/superpowers/plans", "docs/superpowers/specs"],
  "current_overrides": ["docs/superpowers/specs/2026-08-03-documentation-integrity-design.md"],
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

- [ ] **Step 2: Write the repository acceptance test before document repair**

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

Run it and preserve the first FAIL report as the task's baseline evidence.

- [ ] **Step 3: Remove known obsolete script instructions from `AGENTS.md`**

Replace the review-only and changed-source command blocks that invoke missing `repair_grist_document.py`, `export_grist_csv.py`, `rebuild_visuals_and_grist.py`, or `validate_workspace.py` with current canonical commands:

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

For legacy Grist UI evidence, document only the existing command:

```powershell
evidence-review legacy validate-grist-qa `
  --artifact <artifact> `
  --root <workspace>
```

State explicitly that direct legacy repair/export wrappers are not shipped by the current runtime.

- [ ] **Step 4: Apply the approved legacy-reference mapping across current docs**

Run:

```bash
git grep -n -E "migrate_ansim_workspace\.py|build_ansim_release\.py|repair_grist_document\.py|export_grist_csv\.py|rebuild_visuals_and_grist\.py|validate_workspace\.py|CHATGPT_WEB_WORKFLOW\.md" -- README.md AGENTS.md docs skills
```

For CURRENT documents only, apply this mapping:

| Obsolete reference | Required current treatment |
|---|---|
| `migrate_ansim_workspace.py` | Replace with `evidence-review source-batch prepare` plus `source-batch ingest`. |
| `build_ansim_release.py` | Remove executable claim and link to `docs/OFFLINE_EXECUTION.md` for release gates. |
| `repair_grist_document.py` | Remove executable claim; state that legacy direct repair is not a current runtime command. |
| `export_grist_csv.py` | Remove executable claim; do not invent an export CLI. |
| `rebuild_visuals_and_grist.py` | Replace with the current source-batch workflow where the document describes current ingestion; otherwise mark the section historical. |
| `validate_workspace.py` | Replace current release-validation guidance with the documentation CLI plus the repository test/static-check sequence. Do not claim documentation validation replaces SQLite or release-output validation. |
| `CHATGPT_WEB_WORKFLOW.md` | Replace with `README.md#8-검토-run` when the context is review orchestration, or `docs/OFFLINE_EXECUTION.md` when the context is offline/release policy. |

Do not edit historical content merely to remove an old name.

- [ ] **Step 5: Fix remaining current-document errors from the canonical report**

Run the CLI to a new output path after each pass:

```bash
evidence-review documentation validate --repository-root . --config documentation-integrity.json --output build/documentation-integrity-pass-1.json
```

For every remaining `ERROR`, make only the change dictated by its rule code:

- missing target: correct or remove the link;
- missing anchor: link to an existing normalized heading;
- missing command/script: replace with an existing canonical command or remove the executable claim;
- classification conflict: fix config, not document prose;
- current-to-historical link: prefix the link label with `Historical:` or `과거 기록:`;
- path escape/absolute/backslash Markdown target: replace with a safe repository-relative POSIX target.

Use a new report filename for every rerun because reports are create-only.

- [ ] **Step 6: Run repository acceptance and commit**

```bash
pytest -v tests/integration/documentation_integrity/test_repository_acceptance.py
ruff check README.md AGENTS.md docs/OFFLINE_EXECUTION.md src tests
mypy src

git add documentation-integrity.json README.md AGENTS.md docs skills tests/integration/documentation_integrity/test_repository_acceptance.py
git commit -m "docs: align repository guidance with canonical cli"
```

Expected: repository report status PASS; warnings are allowed and preserved.

---

### Task 10: Integrate documentation integrity into workspace and release gates

**Files:**
- Modify: `src/ansim_review/release/validator.py`
- Modify: `src/ansim_review/release/builder.py`
- Modify: `tests/unit/release/test_release_output_gate.py`
- Modify: `tests/integration/release/test_release_builder.py`
- Create: `tests/integration/release/test_documentation_gate.py`

**Interfaces:**
- `validate_release_workspace()` embeds `documentation` report payload.
- Workspace errors include `DOCUMENTATION_INTEGRITY_FAILED` when documentation status is FAIL.
- `_automated_reason_codes()` returns `AUTOMATED_VALIDATION_FAILED` and then `DOCUMENTATION_INTEGRITY_FAILED` when the workspace error list contains that code.

- [ ] **Step 1: Write the failing workspace-gate integration test**

Create a valid synthetic release workspace with one broken current link and a valid config. Assert:

```python
report = validate_release_workspace(root)
assert report["status"] == "FAIL"
assert "DOCUMENTATION_INTEGRITY_FAILED" in report["errors"]
assert report["documentation"]["status"] == "FAIL"
```

Also assert that a warning-only external URL leaves workspace status PASS.

- [ ] **Step 2: Expand the release reason-code unit matrix**

Add cases proving this exact order:

```python
assert _automated_reason_codes(
    {"status": "FAIL", "errors": ["DOCUMENTATION_INTEGRITY_FAILED"]},
    {"status": "PASS"},
) == ["AUTOMATED_VALIDATION_FAILED", "DOCUMENTATION_INTEGRITY_FAILED"]
```

When output validation also fails, the order is:

```text
AUTOMATED_VALIDATION_FAILED
DOCUMENTATION_INTEGRITY_FAILED
RELEASE_OUTPUT_VALIDATION_FAILED
```

- [ ] **Step 3: Update synthetic release workspaces**

In `tests/integration/release/test_release_builder.py`, add a helper that writes:

```text
README.md
AGENTS.md
docs/OFFLINE_EXECUTION.md
documentation-integrity.json
```

Use a minimal config with current roots for those three files and no historical/generated documents unless the test explicitly exercises generated documents. This keeps release tests focused and prevents them from depending on the full repository tree.

- [ ] **Step 4: Implement pure validator integration**

Call `validate_documentation()` without writing a report file. Embed `report_document(documentation_report)` under `documentation`. A missing/unreadable config is a documentation failure with stable summary data in the workspace report, not an uncaught exception.

- [ ] **Step 5: Prove process attestation cannot bypass the gate**

Build a release from a workspace with a valid attestation and broken current documentation. Assert:

```python
assert manifest["status"] == "BLOCKED"
assert manifest["reason_codes"] == [
    "AUTOMATED_VALIDATION_FAILED",
    "DOCUMENTATION_INTEGRITY_FAILED",
]
assert manifest["tag_allowed"] is False
```

- [ ] **Step 6: Run release tests and commit**

```bash
pytest -v tests/unit/release/test_release_output_gate.py tests/integration/release/test_release_builder.py tests/integration/release/test_documentation_gate.py
ruff check src/ansim_review/release tests/unit/release tests/integration/release
mypy src/ansim_review/release

git add src/ansim_review/release/validator.py src/ansim_review/release/builder.py tests/unit/release/test_release_output_gate.py tests/integration/release/test_release_builder.py tests/integration/release/test_documentation_gate.py
git commit -m "feat: block release on documentation errors"
```

---

### Task 11: Add CI, wheel, reproducibility, and acceptance evidence

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `docs/acceptance/issue-50/README.md`
- Test: `tests/integration/documentation_integrity/test_repository_acceptance.py`

**Interfaces:**
- CI runs repository documentation validation before wheel build.
- Installed Python 3.11 and 3.13 wheels expose `documentation validate --help`.
- Acceptance document records exact source commit, commands, exit codes, report SHA-256, counts, and Actions limitation/status.

- [ ] **Step 1: Add CI repository validation**

In the Ubuntu `validate` job, insert after installation and before full pytest:

```yaml
- name: Validate repository documentation
  run: |
    evidence-review documentation validate \
      --repository-root . \
      --config documentation-integrity.json \
      --output build/documentation-integrity-report.json
```

Do not enable online link checking.

- [ ] **Step 2: Add installed-wheel parser checks**

Add to both Python 3.11 and 3.13 wheel verification blocks:

```bash
.wheel-venv/bin/evidence-review documentation validate --help
.wheel-venv/bin/python -m evidence_review documentation validate --help
.wheel-venv/bin/python -m ansim_review documentation validate --help
```

The wheel need not contain repository Markdown or the authority config; only parser and importability are required in isolated wheel checks.

- [ ] **Step 3: Strengthen deterministic report acceptance**

Extend the repository acceptance test to copy the repository's in-scope Markdown and config into two separate temporary roots, run validation, and assert `report_bytes(first) == report_bytes(second)`. Exclude generated build outputs and `.git` from the copies.

- [ ] **Step 4: Create the acceptance record**

Start the file with:

```markdown
> Document status: HISTORICAL RECORD

# Issue #50 Documentation Integrity Acceptance
```

Record these exact sections:

```text
A. Basis
B. Automated result
C. Repository document counts
D. Error and warning counts
E. Generated Markdown result
F. CLI static-semantic result
G. Release fail-closed result
H. Determinism result
I. Python 3.11/3.13 wheel result
J. Limitations
```

State that external URL availability was not checked, Markdown commands were not executed, warnings do not block by default, and historical content was not rewritten to current semantics.

- [ ] **Step 5: Run the complete local gate**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
python -m build --wheel
```

Then run the create-only CLI twice with separate paths:

```bash
evidence-review documentation validate --repository-root . --config documentation-integrity.json --output build/documentation-integrity-final-a.json
evidence-review documentation validate --repository-root . --config documentation-integrity.json --output build/documentation-integrity-final-b.json
python -c "from pathlib import Path; assert Path('build/documentation-integrity-final-a.json').read_bytes() == Path('build/documentation-integrity-final-b.json').read_bytes()"
```

Expected: every command exits 0; both report files are byte-identical; report status PASS.

- [ ] **Step 6: Commit acceptance and CI**

```bash
git add .github/workflows/ci.yml docs/acceptance/issue-50/README.md tests/integration/documentation_integrity/test_repository_acceptance.py
git commit -m "test: verify documentation integrity release gate"
```

---

### Task 12: Final review, PR preparation, and manual validation handoff

**Files:**
- Review all files changed in Tasks 1-11.
- Update: `docs/acceptance/issue-50/README.md` only with final immutable command ledger and commit IDs.
- Update: Issue #50 and parent Issue #27 comments.

**Interfaces:**
- Produces a draft PR from `agent/issue-50-documentation-integrity` to `main`.
- Does not mark Ready or merge until the final Windows/Linux result is accepted.

- [ ] **Step 1: Run diff-scope review**

```bash
git diff --stat main...HEAD
git diff --check main...HEAD
git status --short
```

Reject unrelated runtime, rule, golden, Grist, lineage, or attestation changes.

- [ ] **Step 2: Run targeted regression groups**

```bash
pytest -v tests/unit/documentation_integrity tests/integration/documentation_integrity
pytest -v tests/unit/release tests/integration/release
pytest -v tests/unit/rule_engine tests/integration/rule_engine
```

Expected: PASS; rule-governance artifacts remain byte-identical.

- [ ] **Step 3: Verify canonical output safety**

Test each of these manually or through automated tests:

```text
existing output path -> exit 2, file unchanged
broken current link -> exit 1, canonical FAIL report
warning-only external URL -> exit 0, canonical PASS report
missing config -> exit 2, no report
historical missing marker -> warning only
current missing script -> error
valid process attestation plus documentation error -> release BLOCKED
```

- [ ] **Step 4: Update acceptance ledger**

Record final branch HEAD, OS, Python versions, test counts, report SHA-256, report counts, wheel results, and whether GitHub Actions ran or remained billing-blocked. Do not describe manual validation as GitHub Actions PASS.

- [ ] **Step 5: Open a draft PR**

Use title:

```text
feat: validate repository-wide documentation integrity
```

PR body must include:

```text
Implements #50
Parent #27
Status: DRAFT
Documentation report: PASS/FAIL
GitHub Actions: PASS or ACTIONS_BILLING_BLOCKED, based on observed run only
```

- [ ] **Step 6: Request review and stop before merge**

Do not mark Ready, merge, or close Issue #50 until review confirms:

- repository report has zero errors;
- full pytest/Ruff/mypy/compileall pass;
- Python 3.11 and 3.13 wheel parser checks pass;
- release fail-closed integration passes;
- acceptance evidence matches the exact remote HEAD.

---

## Plan Self-Review

- **Spec coverage:** Every approved requirement maps to Tasks 2-11: strict versioned config/report, complete scope discovery, current/historical classification, offline URL syntax, static command semantics, generated Markdown, create-only CLI, release blocking, full Codex `VALIDATE.md`, repository repair, deterministic bytes, wheel/platform checks.
- **No implementation gaps:** The plan defines parser-cycle avoidance, exact anchor normalization, explicit historical labeling, placeholder forms, tool option registry, exit codes, release reason order, and synthetic workspace updates.
- **No scope expansion:** No online crawler, command executor, legacy wrapper restoration, Markdown formatter, or unrelated artifact migration is included.
- **Type consistency:** `DocumentationIntegrityConfig`, `DocumentationFinding`, `DocumentationIntegrityReport`, `DiscoveredDocument`, `ParsedMarkdown`, and `validate_documentation()` names are fixed and used consistently across tasks.
- **Historical preservation:** Missing markers are warnings; old safe targets are not required to exist; current documents alone are repaired to match canonical runtime behavior.
