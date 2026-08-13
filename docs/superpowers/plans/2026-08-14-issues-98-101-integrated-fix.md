# Issues #98–#101 Integrated Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix runtime provenance, bounded Korean deterministic retrieval, Track B run-local finalization semantics, and formal-review result/PDF synchronization in one auditable PR without weakening evidence authority or fail-closed behavior.

**Architecture:** Establish a dependency-safe CLI provenance gate first, then implement #100 Korean lexical retrieval and #101 Track B artifact ownership as independent subsystems. Finish by integrating #98 with the completed #92 protected-server lifecycle and the #100 retrieval behavior, then run combined Windows/browser acceptance.

**Tech Stack:** Python 3.11/3.13, argparse, importlib.metadata, pathlib, subprocess, SQLite FTS5, pytest, vanilla JavaScript, existing Evidence Review contracts and protected loopback server.

## Global Constraints

- Base branch: `main`; planning baseline: `820fff52c568ec860cc2d92459e4502fccfc14e3`.
- Keep the PR Draft until all issue-level acceptance criteria pass at one exact HEAD.
- Do not add LLM/API query rewriting or an external Korean morphology dependency.
- Do not change citation IDs, evidence/source hashes, snapshot hash, page/bbox authority, or final packet authority to satisfy retrieval tests.
- Do not weaken Track A/Track B validation, create-only artifact safety, stale-index checks, offline/network guard, or #92 protected-server security.
- Existing English/numeric retrieval behavior must remain compatible.
- Windows Python 3.11 and 3.13 are required acceptance environments.
- Real-browser acceptance must include 1366×768, 200% zoom, and print.

---

## File map

### New files

- `src/evidence_review/diagnostics.py` — stdlib-only runtime provenance/dependency diagnostics used before heavy runtime imports.
- `tests/unit/test_cli_diagnostics.py` — pure diagnostic contract tests.
- `tests/integration/packaging/test_cli_runtime_provenance.py` — subprocess/bootstrap provenance tests.

### Primary modified files

- `src/evidence_review/cli.py` — dependency-safe bootstrap and lazy runtime dispatch.
- `src/ansim_review/cli_parser.py` — `doctor`/`--version` or compatible parser surface; `review-question submit-track-b --open`.
- `src/ansim_review/cli.py` — review-question handoff output/error mapping.
- `src/ansim_review/retrieval/korean_variants.py` — bounded Korean compound/search variants.
- `src/ansim_review/retrieval/index.py` — Korean compound lexical channel.
- `src/ansim_review/retrieval/bundle.py` — provenance-preserving channel integration and zero-hit attempted-term trace.
- `src/ansim_review/review_run.py` — Track B validated-input ownership and same-path publish behavior.
- `src/ansim_review/review_question.py` — Track B retry identity/recovery and formal-review handoff integration.
- `src/ansim_review/review_packet/assets/review.js` — review-item -> first citation -> existing PDF focus path.

### Primary existing tests to extend

- `tests/integration/retrieval/test_fts_lexical_channels.py`
- `tests/integration/retrieval/test_fts_retrieval.py`
- `tests/integration/retrieval/test_korean_formal_review_retrieval.py`
- `tests/integration/retrieval/test_hybrid_fusion.py`
- `tests/integration/review_run/test_review_run.py`
- `tests/integration/review_run/test_review_run_cli.py`
- `tests/integration/review_question/test_review_question_cli.py`
- `tests/integration/review_packet/test_review_workspace_ui.py`
- `tests/integration/review_packet/test_review_visual_contract.py`

---

### Task 1: Characterize the four failures at the current baseline

**Files:**
- Modify: `tests/integration/retrieval/test_fts_lexical_channels.py`
- Modify: `tests/integration/review_run/test_review_run.py`
- Modify: `tests/integration/review_question/test_review_question_cli.py`
- Modify: `tests/integration/review_packet/test_review_workspace_ui.py`

**Interfaces:**
- Consumes: current `search_fts_phrase`, `search_fts_token_and`, `submit_question_track_b`, `finalize_review_run`, rendered review workspace.
- Produces: failing regression tests that precisely distinguish #98, #100, and #101 before implementation; #99 tests are added in Task 2 because they require the diagnostic interface.

- [ ] **Step 1: Add a Korean lexical RED case using authoritative indexed text**

Add a fixture record whose indexed text contains the representative Korean term and assert that the current exact/token channels reproduce the miss that #100 describes. The assertion must also prove the source record exists in `retrieval_records` so the test cannot be satisfied by changing ingest behavior.

```python
def test_korean_compound_term_present_in_record_is_retrievable(connection):
    row = connection.execute(
        "SELECT evidence_id, normalized_text FROM retrieval_records "
        "WHERE normalized_text LIKE ? LIMIT 1",
        ("%주차구획선%",),
    ).fetchone()
    assert row is not None
    assert "주차구획선" in row["normalized_text"]

    hits = search_fts_phrase(connection, "주차구획선")
    assert {hit.evidence_id for hit in hits} == {row["evidence_id"]}
```

- [ ] **Step 2: Run the focused retrieval test and record the exact failure mode**

Run:

```bash
pytest tests/integration/retrieval/test_fts_lexical_channels.py -v
```

Expected before #100 implementation: the new representative assertion fails because the authoritative record exists but the required lexical query does not return it.

- [ ] **Step 3: Add a run-local Track B RED case**

In `tests/integration/review_run/test_review_run.py`, prepare/validate Track A and write the valid Track B document directly to `<run-dir>/track-b-output.json`, then submit that exact path.

```python
run_local_b = prepared.run_directory / "track-b-output.json"
run_local_b.write_bytes(dump_bytes(valid_track_b_document))
result = submit_question_track_b(workspace, prepared.run_id, run_local_b)
assert result.packet_path.is_file()
```

Expected before #101 implementation: normal same-path submission raises `FileExistsError` or equivalent collision.

- [ ] **Step 4: Add a review-item/PDF synchronization RED assertion**

Extend the review workspace UI contract fixture so item 1 and item 2 cite different pages/bboxes. Assert that the generated JS contract routes item selection through the evidence-focus path rather than only changing the selected rail item.

If the existing UI tests execute JavaScript, assert the selected item's page/bbox state. If they are static-contract tests, assert that `selectReviewItem` invokes the same evidence-focus helper used by `.evidence-link`.

- [ ] **Step 5: Add a `review-question submit-track-b --open` RED subprocess test**

In `tests/integration/review_question/test_review_question_cli.py`, invoke the current parser with `--open` and require a bounded JSON response containing `run_id`, final status, `review_html`, and either `url` or an explicit display-failure status.

- [ ] **Step 6: Run all characterization tests and confirm RED for the intended reasons only**

Run:

```bash
pytest \
  tests/integration/retrieval/test_fts_lexical_channels.py \
  tests/integration/review_run/test_review_run.py \
  tests/integration/review_question/test_review_question_cli.py \
  tests/integration/review_packet/test_review_workspace_ui.py -v
```

- [ ] **Step 7: Commit the characterization tests**

```bash
git add \
  tests/integration/retrieval/test_fts_lexical_channels.py \
  tests/integration/review_run/test_review_run.py \
  tests/integration/review_question/test_review_question_cli.py \
  tests/integration/review_packet/test_review_workspace_ui.py
git commit -m "test: reproduce issues 98 100 and 101"
```

---

### Task 2: Add dependency-safe CLI provenance diagnostics (#99)

**Files:**
- Create: `src/evidence_review/diagnostics.py`
- Modify: `src/evidence_review/cli.py`
- Modify: `src/ansim_review/cli_parser.py`
- Create: `tests/unit/test_cli_diagnostics.py`
- Create: `tests/integration/packaging/test_cli_runtime_provenance.py`

**Interfaces:**
- Produces: `collect_runtime_diagnostics(repository_root: Path | None) -> RuntimeDiagnostics`; `preflight_runtime(repository_root: Path | None) -> RuntimeDiagnostics`; dependency-safe `doctor` command.
- Later tasks depend on: trusted current-checkout execution and structured diagnostic statuses.

- [ ] **Step 1: Write the diagnostic model RED tests**

Define the expected immutable model contract in `tests/unit/test_cli_diagnostics.py`:

```python
from pathlib import Path

from evidence_review.diagnostics import RuntimeDiagnostics


def test_runtime_diagnostics_document_is_stable() -> None:
    diagnostics = RuntimeDiagnostics(
        status="OK",
        executable=Path("C:/Python313/python.exe"),
        command_path=None,
        distribution_version="0.1.0",
        working_directory=Path("C:/repo"),
        repository_root=Path("C:/repo"),
        repository_head="a" * 40,
        package_root=Path("C:/repo/src/ansim_review"),
        package_checkout_match=True,
        dependencies=(("pypdf", "OK", "5.0"),),
    )
    document = diagnostics.to_document()
    assert document["status"] == "OK"
    assert document["package_checkout_match"] is True
```

- [ ] **Step 2: Write SOURCE_MISMATCH and DEPENDENCY_MISSING RED tests**

Mock Git/path discovery so a repository root points to checkout A while `ansim_review` resolves under checkout B. Separately mock missing `pypdfium2` metadata/import availability. Assert `SOURCE_MISMATCH` and `DEPENDENCY_MISSING` respectively.

- [ ] **Step 3: Implement `src/evidence_review/diagnostics.py` using stdlib only**

Use `dataclasses`, `importlib.metadata`, `importlib.util`, `pathlib`, `shutil`, `subprocess`, and `sys`. Do not import `ansim_review.cli`, parser modules, PDF libraries, or other heavy runtime modules.

Required behavior:

```python
@dataclass(frozen=True, slots=True)
class RuntimeDiagnostics:
    status: Literal["OK", "SOURCE_MISMATCH", "DEPENDENCY_MISSING", "NOT_A_CHECKOUT"]
    executable: Path
    command_path: Path | None
    distribution_version: str | None
    working_directory: Path
    repository_root: Path | None
    repository_head: str | None
    package_root: Path | None
    package_checkout_match: bool | None
    dependencies: tuple[tuple[str, str, str | None], ...]

    def to_document(self) -> dict[str, object]: ...
```

Dependency inventory must include the runtime dependencies declared by `pyproject.toml`: `pypdf`, `pypdfium2`, and `Pillow`/`PIL`.

- [ ] **Step 4: Refactor `src/evidence_review/cli.py` into a lazy bootstrap**

The module import path used by the console script must not eagerly import `ansim_review.entrypoint` before diagnostics run.

Pseudo-structure:

```python
def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if _is_doctor(arguments):
        return _run_doctor(arguments)
    diagnostics = preflight_runtime(_repository_root_from_arguments(arguments))
    if diagnostics.status in {"SOURCE_MISMATCH", "DEPENDENCY_MISSING"}:
        _write_diagnostic_error(diagnostics)
        return 2
    from ansim_review.entrypoint import main as runtime_main
    return runtime_main(arguments)
```

- [ ] **Step 5: Add `doctor` and version parser coverage**

Support:

```bash
python -m evidence_review doctor --repository-root <repo>
python -m evidence_review --version
```

`doctor` prints canonical JSON and does not require the heavy runtime dependency import path to succeed.

- [ ] **Step 6: Add subprocess tests for current checkout, stale source, and missing dependency**

`tests/integration/packaging/test_cli_runtime_provenance.py` must assert:

- current checkout -> `status=OK`, exit 0;
- different package root while inside the repo -> `SOURCE_MISMATCH`, exit 2, business command not entered;
- missing `pypdfium2` -> doctor still runs and reports `DEPENDENCY_MISSING` rather than raw traceback.

- [ ] **Step 7: Run focused provenance tests**

```bash
pytest tests/unit/test_cli_diagnostics.py tests/integration/packaging/test_cli_runtime_provenance.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit #99 implementation**

```bash
git add src/evidence_review/diagnostics.py src/evidence_review/cli.py \
  src/ansim_review/cli_parser.py tests/unit/test_cli_diagnostics.py \
  tests/integration/packaging/test_cli_runtime_provenance.py
git commit -m "fix: add CLI runtime provenance diagnostics"
```

---

### Task 3: Implement bounded Korean compound retrieval (#100)

**Files:**
- Modify: `src/ansim_review/retrieval/korean_variants.py`
- Modify: `src/ansim_review/retrieval/index.py`
- Modify: `src/ansim_review/retrieval/bundle.py`
- Modify: `tests/unit/retrieval/test_korean_variants.py`
- Modify: `tests/integration/retrieval/test_fts_lexical_channels.py`
- Modify: `tests/integration/retrieval/test_fts_retrieval.py`
- Modify: `tests/integration/retrieval/test_hybrid_fusion.py`

**Interfaces:**
- Produces: bounded Korean compound variant derivation and a traceable `fts_korean_compound` retrieval channel.
- Consumes: existing `normalize_text`, `search_fts_*`, `RetrievalHit`, fusion logic.
- Task 7 consumes the resulting formal-review behavior.

- [ ] **Step 1: Add unit RED tests for spacing and suffix variants**

Required examples:

```python
variants = derive_korean_compound_variants("소방차 전용구역")
assert variants == ("소방차 전용구역", "소방차전용구역")

variants = derive_korean_compound_variants("피난안전구역에서")
assert "피난안전구역" in variants
```

Also cover zero-width format removal and stable ordered de-duplication.

- [ ] **Step 2: Characterize the FTS token boundary using the existing SQLite fixture**

In the integration test, confirm the authoritative `retrieval_records` row and inspect FTS behavior. Use `fts5vocab` only inside the test if needed; production code must not depend on it.

- [ ] **Step 3: Implement bounded Korean variant derivation**

Extend `korean_variants.py` with a function such as:

```python
def derive_korean_compound_variants(primary: str) -> tuple[str, ...]:
    """Return ordered, bounded Korean lexical variants for deterministic fallback."""
```

Rules:

- NFC normalize;
- collapse whitespace/newlines;
- remove only explicitly handled zero-width format characters;
- reuse existing bounded suffix stripping;
- include original spaced term;
- include compact Hangul spacing form only when at least two Hangul-bearing lexical tokens participate;
- never emit an empty or one-character broad token;
- deterministic order and de-duplication.

- [ ] **Step 4: Add `fts_korean_compound` search support**

Extend `src/ansim_review/retrieval/index.py` without changing existing `fts_phrase`, `fts_token_and`, or grouped channels. Keep the query origin/channel visible in `ChannelScore`.

If exact FTS tokenization still blocks a compound match, build the additional searchable representation at FTS index-build time while leaving `retrieval_records.raw_text` and `normalized_text` unchanged. Only add a schema migration if the focused characterization proves this impossible in the existing table.

- [ ] **Step 5: Integrate the channel into `bundle.py` after exact/token channels**

Order must remain:

```text
origin phrase/token channels
-> bounded Korean compound fallback
-> existing grouped entity/numeric/concept channels
-> fusion
```

Use trace details that preserve origin and derived term, e.g. `derived:korean_compound:소방차전용구역`.

- [ ] **Step 6: Verify authoritative citation invariants**

For representative hits, assert unchanged `evidence_id`, `document_id`, `revision_id`, `page_number`, `bbox`, and `source_hash` versus the indexed record.

- [ ] **Step 7: Verify English/numeric regressions**

Run:

```bash
pytest \
  tests/unit/retrieval/test_korean_variants.py \
  tests/integration/retrieval/test_fts_lexical_channels.py \
  tests/integration/retrieval/test_fts_retrieval.py \
  tests/integration/retrieval/test_hybrid_fusion.py -v
```

Expected: PASS, including existing English and numeric tests.

- [ ] **Step 8: Commit #100 implementation**

```bash
git add src/ansim_review/retrieval/korean_variants.py \
  src/ansim_review/retrieval/index.py src/ansim_review/retrieval/bundle.py \
  tests/unit/retrieval/test_korean_variants.py \
  tests/integration/retrieval/test_fts_lexical_channels.py \
  tests/integration/retrieval/test_fts_retrieval.py \
  tests/integration/retrieval/test_hybrid_fusion.py
git commit -m "fix: retrieve bounded Korean compound terms"
```

---

### Task 4: Make Track B a validated run artifact with deterministic retry (#101)

**Files:**
- Modify: `src/ansim_review/review_run.py`
- Modify: `src/ansim_review/review_question.py`
- Modify: `tests/integration/review_run/test_review_run.py`
- Modify: `tests/integration/review_question/test_review_question_cli.py`

**Interfaces:**
- Produces: same-path Track B reuse, external-path create-or-identical publish, retry hash enforcement, finalizer-output-only recovery.
- Consumes: existing canonical JSON bytes, workflow event journal, Track B validators.

- [ ] **Step 1: Add a Track B publish helper symmetric with Track A**

Implement a focused helper, preferably sharing the existing create-or-identical primitive:

```python
def _publish_validated_track_b(
    source: Path,
    destination: Path,
    document: object,
) -> None:
    if source.resolve() == destination.resolve():
        if not destination.is_file():
            raise FileNotFoundError(destination)
        if destination.read_bytes() != dump_bytes(document):
            raise ValueError("TRACK_B_INPUT_MISMATCH")
        return
    _write_json_or_identical(destination, document)
```

Use the repository's preferred typed/contract error pattern if one already exists; do not introduce raw overwrite semantics.

- [ ] **Step 2: Separate validated inputs from generated collision checks**

In `finalize_review_run()`, do not include run-local `track-b-output.json` in the set whose mere existence is considered a generated-output collision.

Generated collision targets remain:

```python
generated = (
    run_directory / "run-manifest.json",
    run_directory / "final-review-packet.json",
    run_directory / "review.html",
)
```

Validate Track B first, then publish/reuse the validated run-local artifact, then build the manifest/final packet.

- [ ] **Step 3: Bind retry identity to the workflow journal**

When `WAITING_TRACK_B -> FINALIZING` is appended, retain the submitted Track B SHA-256 as the event payload hash. On `FINALIZING` retry, compare the new input hash with the journaled hash before recovery/finalizer execution.

Required behavior:

```python
if retry_hash != journaled_hash:
    raise ValueError("TRACK_B_RETRY_MISMATCH")
```

- [ ] **Step 4: Preserve validated Track B during incomplete-finalization recovery**

Update `_recover_incomplete_finalization()` so it removes only:

- `run-manifest.json`
- `final-review-packet.json`
- `review.html`

Do not delete validated `track-a-output.json` or `track-b-output.json`.

- [ ] **Step 5: Add retry and mismatch regressions**

Tests must cover:

1. external Track B -> run-local publish -> success;
2. run-local same path -> success without rewrite;
3. identical FINALIZING retry -> success/idempotent;
4. modified Track B after journal entry -> `TRACK_B_RETRY_MISMATCH` before finalizer;
5. malformed Track B -> validation failure before generated artifacts;
6. partial generated artifacts -> safe recovery while validated Track B remains.

- [ ] **Step 6: Map user-facing CLI errors distinctly**

`review-question submit-track-b` must not present a normal same-path case as `FileExistsError`. Preserve distinct stderr/status messages for validation failure, input mismatch, retry mismatch, and generated artifact collision.

- [ ] **Step 7: Run focused review tests**

```bash
pytest \
  tests/integration/review_run/test_review_run.py \
  tests/integration/review_question/test_review_question_cli.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit #101 implementation**

```bash
git add src/ansim_review/review_run.py src/ansim_review/review_question.py \
  tests/integration/review_run/test_review_run.py \
  tests/integration/review_question/test_review_question_cli.py
git commit -m "fix: make Track B run-local submission idempotent"
```

---

### Task 5: Synchronize review-item selection with PDF evidence focus (#98 UI)

**Files:**
- Modify: `src/ansim_review/review_packet/assets/review.js`
- Modify: `tests/integration/review_packet/test_review_workspace_ui.py`
- Modify: `tests/integration/review_packet/test_review_visual_contract.py`

**Interfaces:**
- Consumes: existing `selectReviewItem()` and `focusEvidence()` behavior.
- Produces: one selection path for mouse and keyboard; first-citation default focus; no duplicated PDF page/bbox logic.

- [ ] **Step 1: Strengthen the RED fixture for multiple review items/citations**

The test fixture must contain:

- item A -> citation page 1 / bbox A;
- item B -> citation page 3 / bbox B;
- item C -> two citations on different pages;
- optional item D -> no citation.

- [ ] **Step 2: Refactor item selection to reuse the existing evidence-focus helper**

Keep PDF positioning inside `focusEvidence()`. Add only a helper that finds the first valid evidence link for the selected item if necessary.

Conceptual JS:

```javascript
function focusFirstEvidenceForItem(itemElement) {
  const link = itemElement.querySelector(".evidence-link");
  if (!link) return;
  focusEvidence(link);
}

function selectReviewItem(itemElement) {
  // existing selected/detail state updates
  focusFirstEvidenceForItem(itemElement);
}
```

Adapt to the actual DOM structure; do not duplicate page-number or bbox parsing already owned by `focusEvidence()`.

- [ ] **Step 3: Route keyboard activation through the same selection function**

Arrow navigation and Enter/Space activation must call the same `selectReviewItem()` path as mouse clicks. Remove any alternate code path that only changes visual selection.

- [ ] **Step 4: Preserve multiple-citation behavior**

Item selection focuses citation 1. Clicking citation 2 subsequently calls `focusEvidence()` for citation 2 and must not be overridden by the rail selection state.

- [ ] **Step 5: Handle citation-less items safely**

Selecting an item with no citation updates the detail panel but leaves the current PDF/page overlay unchanged and throws no error.

- [ ] **Step 6: Run workspace UI tests**

```bash
pytest \
  tests/integration/review_packet/test_review_workspace_ui.py \
  tests/integration/review_packet/test_review_visual_contract.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit #98 UI implementation**

```bash
git add src/ansim_review/review_packet/assets/review.js \
  tests/integration/review_packet/test_review_workspace_ui.py \
  tests/integration/review_packet/test_review_visual_contract.py
git commit -m "fix: synchronize review items with PDF evidence"
```

---

### Task 6: Return a protected result handoff from formal review (#98 CLI)

**Files:**
- Modify: `src/ansim_review/cli_parser.py`
- Modify: `src/ansim_review/cli.py`
- Modify: `src/ansim_review/review_question.py` only if a small orchestration helper is required
- Modify: `tests/integration/review_question/test_review_question_cli.py`
- Modify: `tests/integration/review_run/test_review_run_cli.py` only for shared protected-server contract coverage

**Interfaces:**
- Consumes: completed #92 `open_review_run()`/detached protected loopback lifecycle.
- Produces: `review-question submit-track-b --open` bounded result with `review_html`, protected URL when available, and explicit display failure when browser dispatch fails.

- [ ] **Step 1: Add `--open` to `review-question submit-track-b` parser**

Match the existing `review-run finalize --open` semantics where possible. Do not introduce a second `serve` implementation.

- [ ] **Step 2: Extend successful review-question stdout**

Without `--open`, preserve existing fields and add `review_html` if compatible with the CLI format contract. With `--open`, output a structured document containing at least:

```json
{
  "format": "evidence-review/review-question-status",
  "version": 1,
  "stage": "submit-track-b",
  "status": "READY_FOR_HUMAN_REVIEW",
  "run_id": "RUN-...",
  "review_html": ".../review.html",
  "display_status": "OPENED",
  "url": "http://127.0.0.1:.../..."
}
```

If browser dispatch fails after finalization, use `display_status="OPEN_FAILED"`, retain `status`, `run_id`, and `review_html`, and report the display error separately. Do not relabel the finalized packet as failed.

- [ ] **Step 3: Reuse #92 bounded server lifecycle**

Call the existing detached protected opening function. Do not join/wait indefinitely. Preserve loopback-only binding, tokenized route, idle timeout, process-identity checks, and token non-persistence.

- [ ] **Step 4: Add subprocess timing and URL reachability tests**

The test must use a real subprocess path where the repository already has one for #92, not only a mocked wait. Assert the command returns within the existing bounded contract and the returned URL is immediately reachable when `display_status=OPENED`.

- [ ] **Step 5: Add browser-launch failure coverage**

Mock only the external browser dispatch boundary while allowing packet/HTML creation and server startup. Assert successful finalization plus `OPEN_FAILED`/`review_html` visibility.

- [ ] **Step 6: Run focused CLI/server tests**

```bash
pytest \
  tests/integration/review_question/test_review_question_cli.py \
  tests/integration/review_run/test_review_run_cli.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit #98 protected-handoff implementation**

```bash
git add src/ansim_review/cli_parser.py src/ansim_review/cli.py \
  src/ansim_review/review_question.py \
  tests/integration/review_question/test_review_question_cli.py \
  tests/integration/review_run/test_review_run_cli.py
git commit -m "fix: return protected review handoff from review-question"
```

---

### Task 7: Add combined Korean formal-review and zero-hit guidance regressions (#98 + #100)

**Files:**
- Modify: `src/ansim_review/retrieval/bundle.py` if attempted-term trace is not yet exported
- Modify: `src/ansim_review/review_question.py` if the handoff needs to expose deterministic suggestions
- Modify: `tests/integration/retrieval/test_korean_formal_review_retrieval.py`
- Modify: `tests/integration/review_question/test_review_question_cli.py`

**Interfaces:**
- Consumes: Task 3 bounded Korean retrieval and Task 6 review-question status output.
- Produces: real user-query regressions without manual `--expansion`; auditable no-hit guidance without fabricated evidence.

- [ ] **Step 1: Add the three representative formal-review questions**

Parameterize:

```python
@pytest.mark.parametrize(
    "question",
    [
        "청소년 문화의집 설치기준",
        "청소년문화의집 설치기준",
        "청소년수련관 설치기준",
    ],
)
def test_korean_spacing_variants_retrieve_authoritative_evidence(question, workspace):
    ...
```

Assert relevant evidence/citations, not merely non-empty hits.

- [ ] **Step 2: Assert no user expansion is required**

Build the review question with `expansions=()` and verify the bundle origin trace contains deterministic derived terms rather than `origin=user` expansions.

- [ ] **Step 3: Add a true no-hit case**

Use a query that is absent from the fixture and assert:

- no fabricated citation;
- fail-closed review semantics remain;
- the bundle/handoff may report the bounded normalized/derived terms that were attempted;
- original query text and origins remain intact.

- [ ] **Step 4: Run combined formal-review tests**

```bash
pytest \
  tests/integration/retrieval/test_korean_formal_review_retrieval.py \
  tests/integration/review_question/test_review_question_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit integrated retrieval/formal-review regressions**

```bash
git add src/ansim_review/retrieval/bundle.py src/ansim_review/review_question.py \
  tests/integration/retrieval/test_korean_formal_review_retrieval.py \
  tests/integration/review_question/test_review_question_cli.py
git commit -m "test: cover Korean formal review integration"
```

---

### Task 8: Run subsystem regression gates before full acceptance

**Files:**
- No required source changes unless a regression is discovered.

**Interfaces:**
- Consumes: Tasks 2–7.
- Produces: evidence that each subsystem works independently before full-suite cost is paid.

- [ ] **Step 1: Run CLI provenance/packaging tests**

```bash
pytest tests/unit/test_cli_diagnostics.py tests/integration/packaging -v
```

- [ ] **Step 2: Run retrieval tests**

```bash
pytest tests/unit/retrieval tests/integration/retrieval -v
```

- [ ] **Step 3: Run review-run/question tests**

```bash
pytest tests/integration/review_run tests/integration/review_question -v
```

- [ ] **Step 4: Run review-packet tests**

```bash
pytest tests/unit/review_packet tests/integration/review_packet -v
```

- [ ] **Step 5: If a regression is found, fix it in the owning task's files and add a targeted test before continuing**

Do not paper over failures by weakening assertions or broadening exception catches.

- [ ] **Step 6: Commit only if regression fixes were required**

Use a narrowly scoped message that identifies the corrected subsystem.

---

### Task 9: Run repository-wide quality gates

**Files:**
- No source changes expected.

- [ ] **Step 1: Run full pytest**

```bash
pytest -v
```

Expected: all tests pass; existing intentional skips remain explainable.

- [ ] **Step 2: Run Ruff**

```bash
ruff check .
```

Expected: PASS.

- [ ] **Step 3: Run mypy**

```bash
mypy
```

Expected: PASS.

- [ ] **Step 4: Run compileall**

```bash
python -m compileall -q src tests
```

Expected: PASS.

- [ ] **Step 5: Run documentation integrity using the repository's current documented command**

Use the same interpreter that passed `python -m evidence_review doctor --repository-root .`. Record the report path and error/warning counts.

- [ ] **Step 6: Record the exact HEAD used for all gates**

```bash
git rev-parse HEAD
git status --short
git diff --check
```

Expected: clean worktree and no whitespace errors.

---

### Task 10: Windows Python 3.11/3.13 and real-browser acceptance

**Files:**
- Create or modify the repository's existing acceptance evidence document location used for recent issue verification.
- Update PR body/checklist with exact results.

**Interfaces:**
- Consumes: final candidate HEAD.
- Produces: merge-ready acceptance evidence for all four issues.

- [ ] **Step 1: Python 3.11 provenance smoke**

From the intended checkout/venv:

```powershell
python -m evidence_review doctor --repository-root .
```

Assert `status=OK`, correct checkout/package path, and required dependencies present.

- [ ] **Step 2: Python 3.13 provenance smoke**

Repeat with the 3.13 acceptance interpreter and record the same fields.

- [ ] **Step 3: Intentional stale-source negative smoke**

Arrange PATH/interpreter selection to reproduce the former stale-install case without modifying evidence data. Assert `SOURCE_MISMATCH` before source-batch/parser business logic.

- [ ] **Step 4: Source-batch dependency-negative smoke**

Use a Python environment missing one required runtime dependency and assert `doctor` remains usable and reports `DEPENDENCY_MISSING` clearly.

- [ ] **Step 5: Track B run-local E2E**

Execute a prepared formal-review run where Track B writes directly to `<run-dir>/track-b-output.json`; submit that exact path and verify final packet/HTML creation with no `FileExistsError` and no unnecessary retry.

- [ ] **Step 6: Protected review handoff E2E**

Run `review-question submit-track-b ... --open`. Record stdout `status`, `run_id`, `review_html`, `display_status`, and protected URL. Confirm the command returns within the bounded #92 lifecycle and the URL loads.

- [ ] **Step 7: Browser review-item/PDF focus acceptance**

At 1366×768:

1. select review item 1 and record focused citation/page;
2. select review item 2 and confirm page/bbox changes;
3. select a multi-citation item and confirm citation 1 is the default;
4. click citation 2 and confirm the second page/bbox;
5. repeat item navigation with keyboard;
6. zoom browser to 200% and repeat the critical transitions;
7. print/print-preview and verify the review content remains usable.

- [ ] **Step 8: Korean formal-review E2E**

Run without manual expansions:

```text
청소년 문화의집 설치기준
청소년문화의집 설치기준
청소년수련관 설치기준
```

Record returned authoritative citations and confirm spacing variants do not require user-provided expansion.

- [ ] **Step 9: Verify authority invariants on the final candidate**

Compare representative citation ID, document/revision IDs, page/bbox, source hash, snapshot hash, and final packet semantics against the source evidence. Search convenience must not have changed authority.

- [ ] **Step 10: Commit acceptance evidence**

```bash
git add docs
# use the exact acceptance evidence path created/updated above
git commit -m "docs: record issues 98 through 101 acceptance"
```

---

### Task 11: Final PR gate and issue closure readiness

**Files:**
- Update: pull request description/checklist through GitHub.
- Update: issues #98, #99, #100, #101 with final exact-HEAD evidence only after implementation verification.

- [ ] **Step 1: Compare the PR head with latest `main`**

```bash
git fetch origin
git rev-list --left-right --count origin/main...HEAD
```

If `main` moved in relevant files, rebase/merge according to repository policy and rerun affected focused tests plus the final quality gates.

- [ ] **Step 2: Verify no unintended files are in the PR**

```bash
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD
```

The diff must remain scoped to diagnostics, retrieval, review Track B orchestration, review workspace JS, tests, and acceptance docs.

- [ ] **Step 3: Update the Draft PR checklist with exact results**

Include:

- exact HEAD;
- focused test results;
- full pytest count;
- Ruff/mypy/compileall/documentation integrity;
- Windows 3.11/3.13 diagnostics;
- protected URL handoff timing/result;
- browser 1366×768 / 200% / print result;
- authority invariant check.

- [ ] **Step 4: Only then mark the PR Ready for review**

Do not mark Ready based solely on unit/integration tests if Windows/browser acceptance is missing.

- [ ] **Step 5: Close #98–#101 only after the final candidate is merged or the repository's normal issue-closing policy is satisfied**

The PR body may reference all four issues, but comments on each issue should state which exact acceptance evidence proves its own criteria.

---

## Self-review coverage matrix

| Requirement | Owning task |
|---|---|
| #99 stale CLI provenance | Task 2, Task 10 |
| #99 missing-dependency diagnostics | Task 2, Task 10 |
| #100 Korean compound/exact retrieval | Task 3, Task 7 |
| #100 authority preservation | Task 3, Task 10 |
| #101 run-local Track B | Task 4, Task 10 |
| #101 identical/differing retry semantics | Task 4 |
| #101 partial finalizer recovery | Task 4 |
| #98 protected result handoff | Task 6, Task 10 |
| #98 review item -> PDF page/bbox | Task 5, Task 10 |
| #98 keyboard/multiple citations | Task 5, Task 10 |
| #98 Korean spacing E2E | Task 7, Task 10 |
| Full regression/quality | Tasks 8–9 |
| Windows/browser acceptance | Task 10 |
| PR finalization | Task 11 |

No task requires unrelated parser/rule/release redesign, model-based query rewriting, or authority mutation.
