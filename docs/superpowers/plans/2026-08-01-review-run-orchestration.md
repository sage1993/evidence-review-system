# Review Run Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic staged `review-run` CLI that prepares immutable Track A inputs, imports external Track A/B outputs, finalizes and renders a review packet, and explicitly publishes the packet used by the release builder.

**Architecture:** A focused `ansim_review.review_run` module owns request decoding, run-directory creation, exclusive artifact writes, manifest hashing, finalizer invocation, reviewer HTML rendering, and publication. The existing CLI gains nested `review-run prepare` and `review-run finalize` commands; project code never invokes a model or network service.

**Tech Stack:** Python 3.11+, argparse, pathlib, hashlib, sqlite3-backed reviewer view model, canonical JSON, pytest, Ruff, Mypy.

## Global Constraints

- Project code performs no model or API calls.
- Track A and Track B are externally generated untrusted JSON files.
- JSON outputs use `dump_bytes` canonical UTF-8 bytes.
- Run directories, artifacts, HTML, and published packets are exclusive-create only.
- `human_decision` remains `null` in machine packets.
- The implementation must pass on Windows and Linux.

---

### Task 1: Add failing staged-workflow integration tests

**Files:**
- Create: `tests/integration/review_run/test_review_run.py`

**Interfaces:**
- Consumes: existing `CalculationResult`, `RuleResult`, `Citation`, `dump_bytes`, and finalizer-compatible Track A/B documents.
- Produces: executable expectations for `prepare_review_run(...)` and `finalize_review_run(...)`.

- [ ] **Step 1: Write the request and fixture helpers**

Create a minimal evidence SQLite database with one `retrieval_records` row, a valid cited calculation result, a valid cited rule result, all ten confidence factors, and valid Track A/B outputs.

- [ ] **Step 2: Write the failing prepare test**

```python
def test_prepare_is_deterministic_and_refuses_overwrite(tmp_path: Path) -> None:
    first = prepare_review_run(workspace_a, request_a)
    second = prepare_review_run(workspace_b, request_b)
    assert first.run_id == second.run_id
    assert (first.run_directory / "track-a-bundle.json").read_bytes() == (
        second.run_directory / "track-a-bundle.json"
    ).read_bytes()
    with pytest.raises(FileExistsError):
        prepare_review_run(workspace_a, request_a)
```

- [ ] **Step 3: Write the failing finalize and publish test**

```python
def test_finalize_writes_packet_html_manifest_and_published_packet(tmp_path: Path) -> None:
    prepared = prepare_review_run(workspace, request_path)
    result = finalize_review_run(
        workspace,
        prepared.run_id,
        track_a_path,
        track_b_path,
        publish=True,
    )
    assert result.packet.status == "READY_FOR_HUMAN_REVIEW"
    assert result.packet.human_decision is None
    assert result.review_html.is_file()
    assert (prepared.run_directory / "run-manifest.json").is_file()
    assert (workspace / "runs/final-review-packet.json").read_bytes() == (
        prepared.run_directory / "final-review-packet.json"
    ).read_bytes()
```

- [ ] **Step 4: Write overwrite and invalid-request tests**

Test that a second publication raises `FileExistsError`, an unsupported format/version raises `ValueError`, and missing prepared artifacts raise `FileNotFoundError`.

- [ ] **Step 5: Run the tests and verify RED**

Run:

```bash
pytest tests/integration/review_run/test_review_run.py -v
```

Expected: collection failure because `ansim_review.review_run` does not exist.

- [ ] **Step 6: Commit the failing tests**

```bash
git add tests/integration/review_run/test_review_run.py
git commit -m "test: define staged review-run workflow"
```

---

### Task 2: Implement deterministic preparation

**Files:**
- Create: `src/ansim_review/review_run.py`
- Test: `tests/integration/review_run/test_review_run.py`

**Interfaces:**
- Consumes: `compute_run_id`, `create_run_directory`, `decode_citation`, `decode_calculation_result`, `decode_rule_result`, `build_track_a_bundle`, and `track_a_bundle_document`.
- Produces:

```python
@dataclass(frozen=True, slots=True)
class PreparedReviewRun:
    run_id: str
    run_directory: Path
    track_a_bundle: Path
    confidence_input: Path


def prepare_review_run(workspace_root: Path, request_path: Path) -> PreparedReviewRun:
    ...
```

- [ ] **Step 1: Decode the request before creating output**

Require exactly these top-level fields:

```python
{
    "format",
    "version",
    "question",
    "inputs",
    "evidence",
    "calculations",
    "rules",
    "approved_rule_result_ids",
    "confidence_input",
}
```

Require `format == "ansim/review-run-request"` and `version == 1`. Decode evidence citations, calculations, and rules through existing contract decoders. Validate confidence input by calling `score_confidence` on decoded factor inputs without persisting the score.

- [ ] **Step 2: Compute the deterministic run ID**

Use:

```python
run_id = compute_run_id(
    question,
    inputs,
    evidence_hash=sha256_json(evidence_documents),
    rule_hash=sha256_json(rule_documents),
    formula_hash=sha256_json(calculation_documents),
)
```

- [ ] **Step 3: Create the run directory and canonical artifacts**

Exclusively create `workspace_root / "runs" / run_id`, then write:

- `review-request.json`
- `track-a-bundle.json`
- `confidence-input.json`
- `TRACK_A_INSTRUCTIONS.md`
- `TRACK_B_INSTRUCTIONS.md`
- `prepare-status.json`

Use package template files for the two instruction documents and `dump_bytes` for JSON.

- [ ] **Step 4: Run the prepare tests and verify GREEN**

Run:

```bash
pytest tests/integration/review_run/test_review_run.py::test_prepare_is_deterministic_and_refuses_overwrite -v
```

Expected: PASS.

- [ ] **Step 5: Commit preparation**

```bash
git add src/ansim_review/review_run.py tests/integration/review_run/test_review_run.py
git commit -m "feat: prepare immutable review runs"
```

---

### Task 3: Implement finalization, rendering, and publication

**Files:**
- Modify: `src/ansim_review/review_run.py`
- Test: `tests/integration/review_run/test_review_run.py`

**Interfaces:**
- Consumes: `finalize_run`, `build_review_view_model`, `write_review_html`, and the prepared run directory.
- Produces:

```python
@dataclass(frozen=True, slots=True)
class FinalizedReviewRun:
    run_id: str
    run_directory: Path
    packet: ReviewPacket
    packet_path: Path
    review_html: Path
    published_packet: Path | None


def finalize_review_run(
    workspace_root: Path,
    run_id: str,
    track_a_output: Path,
    track_b_output: Path,
    *,
    publish: bool = False,
) -> FinalizedReviewRun:
    ...
```

- [ ] **Step 1: Validate the prepared run**

Require the run directory name to match `RUN-[0-9A-F]{20}` and require `track-a-bundle.json` plus `confidence-input.json` to exist.

- [ ] **Step 2: Exclusively import Track A and Track B outputs**

Parse both source files as JSON before copying. Write canonical bytes to `track-a-output.json` and `track-b-output.json` using exclusive mode.

- [ ] **Step 3: Write the finalizer manifest**

Hash exactly:

```python
(
    "track-a-bundle.json",
    "track-a-output.json",
    "track-b-output.json",
    "confidence-input.json",
)
```

Write canonical `run-manifest.json` containing `run_id` and the artifact hash mapping.

- [ ] **Step 4: Finalize and render**

Call `finalize_run(run_directory)`, resolve the view model against `workspace_root / "evidence/ansim-evidence.sqlite"`, and exclusively write `review.html`. Use `workspace_root / "page-images"` as the page-image root; missing images remain acceptable because the renderer supports text-only citations.

- [ ] **Step 5: Publish explicitly**

When `publish=True`, exclusively write `workspace_root / "runs/final-review-packet.json"` with the exact bytes from the run-specific packet. Never overwrite an existing published packet.

- [ ] **Step 6: Run finalization tests and verify GREEN**

Run:

```bash
pytest tests/integration/review_run/test_review_run.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit finalization**

```bash
git add src/ansim_review/review_run.py tests/integration/review_run/test_review_run.py
git commit -m "feat: finalize and publish review runs"
```

---

### Task 4: Expose nested CLI commands

**Files:**
- Modify: `src/ansim_review/cli.py`
- Create: `tests/integration/review_run/test_review_run_cli.py`

**Interfaces:**
- Consumes: `prepare_review_run` and `finalize_review_run`.
- Produces:

```text
ansim-review review-run prepare --workspace PATH --request PATH
ansim-review review-run finalize --workspace PATH --run-id RUN-ID --track-a-output PATH --track-b-output PATH [--publish]
```

- [ ] **Step 1: Write failing CLI tests**

Invoke `python -m ansim_review review-run prepare ...` and `python -m ansim_review review-run finalize ...` in subprocesses. Assert exit code `0` and canonical JSON stdout for success, exit code `1` for an existing target, and exit code `2` for invalid input.

- [ ] **Step 2: Run CLI tests and verify RED**

Run:

```bash
pytest tests/integration/review_run/test_review_run_cli.py -v
```

Expected: FAIL because the parser does not recognize `review-run`.

- [ ] **Step 3: Add nested argparse parsers**

Add `review-run`, then nested `prepare` and `finalize` subparsers. Route exceptions as follows:

```python
except FileExistsError as error:
    print(str(error), file=sys.stderr)
    return 1
except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError, sqlite3.Error) as error:
    print(str(error), file=sys.stderr)
    return 2
```

Write success output through `sys.stdout.buffer.write(dump_bytes(status_document))`.

- [ ] **Step 4: Run CLI tests and verify GREEN**

Run:

```bash
pytest tests/integration/review_run/test_review_run_cli.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit CLI support**

```bash
git add src/ansim_review/cli.py tests/integration/review_run/test_review_run_cli.py
git commit -m "feat: expose staged review-run cli"
```

---

### Task 5: Document the API-less Track handoff

**Files:**
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `docs/CHATGPT_WEB_WORKFLOW.md`
- Modify: `docs/REVIEWER_WORKFLOW.md`
- Test: `tests/integration/docs/test_documented_commands.py`

**Interfaces:**
- Consumes: final CLI syntax.
- Produces: copyable commands and explicit human/model authority boundaries.

- [ ] **Step 1: Add staged workflow commands**

Document prepare, saving Track A/B JSON, finalize with `--publish`, reviewing `review.html`, and running the release builder only after publication.

- [ ] **Step 2: Preserve safety language**

State that project code never invokes a model, Track A cannot calculate or decide, Track B cannot rewrite Track A, and the reviewer decision remains separate.

- [ ] **Step 3: Extend documented-command tests**

Assert the docs mention `review-run prepare`, `review-run finalize`, and `human_decision` separation without claiming an AI decision.

- [ ] **Step 4: Run documentation tests**

Run:

```bash
pytest tests/integration/docs/test_documented_commands.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit documentation**

```bash
git add docs tests/integration/docs/test_documented_commands.py
git commit -m "docs: add staged review-run workflow"
```

---

### Task 6: Full verification

**Files:**
- Verify all changed files.

**Interfaces:**
- Consumes: completed implementation.
- Produces: release-quality verification evidence.

- [ ] **Step 1: Run the focused suite**

```bash
pytest tests/integration/review_run -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run the full suite**

```bash
pytest -v
```

Expected: zero failures.

- [ ] **Step 3: Run static checks**

```bash
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

Expected: all commands exit `0`.

- [ ] **Step 4: Verify CLI help**

```bash
python -m ansim_review review-run --help
python -m ansim_review review-run prepare --help
python -m ansim_review review-run finalize --help
```

Expected: all commands exit `0` and show the documented flags.

- [ ] **Step 5: Review the branch diff**

Confirm no network client imports, no generated human decision, no overwrite flags, and no change to release acceptance semantics.

- [ ] **Step 6: Push and confirm GitHub Actions**

Push the branch and require the PR workflow to complete successfully before reporting completion.
