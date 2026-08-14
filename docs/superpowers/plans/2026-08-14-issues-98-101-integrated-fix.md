# Issues #98–#101 Integrated Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve #98, #99, #100, and #101 in one auditable PR by synchronizing with current `main`, proving each failure on the synchronized baseline, then fixing runtime provenance, Track B ownership/retry semantics, bounded Korean retrieval, and formal-review protected/UI integration without weakening evidence authority.

**Architecture:** Synchronize PR #102 to current `main` before production edits. Add a stdlib-only CLI provenance gate first, make Track B a validated run input second, characterize and fix Korean lexical retrieval with the smallest proven mechanism third, then integrate `review-question submit-track-b --open` and non-recursive review-item/PDF orchestration. Finish with an exact-HEAD combined E2E, Windows Python 3.11/3.13 gates, and real-browser acceptance.

**Tech Stack:** Python 3.11/3.13, argparse, dataclasses, importlib.metadata/importlib.util, pathlib, subprocess, SQLite FTS5, pytest, vanilla JavaScript + Node test harness, existing Evidence Review contracts and protected loopback server.

## Global Constraints

- PR #102 stays Draft until all issue-level acceptance criteria pass together at one exact HEAD.
- Before production edits, merge current `origin/main` into `agent/issues-98-101-integrated-fix` and record the synchronized HEAD.
- Do not add LLM/API query rewriting or an external Korean morphology/NLP dependency.
- Do not change citation IDs, page/bbox authority, evidence/source hashes, snapshot hash, or final packet authority to satisfy retrieval tests.
- Do not weaken Track A/Track B structural/integrity validation, create-only artifact safety, stale-index checks, offline/network guard, or #92 protected-server token/process-identity rules.
- Existing English/numeric retrieval behavior must remain compatible.
- A valid run-local `track-b-output.json` is an input artifact and must not be rewritten or deleted by normal finalization/retry.
- A malformed partial run-local Track B left by an interrupted external publish may be replaced only after the retry input hash matches the journaled `FINALIZING` hash; malformed same-path user input remains a validation failure.
- The Korean retrieval mechanism must be chosen only after the reported FTS miss is characterized; no schema migration unless the existing FTS representation is proven insufficient.
- Real-browser acceptance must include 1366×768, 200% zoom, keyboard activation, multiple citations, PDF page/bbox focus, and print.
- Use interpreter-pinned development/acceptance commands (`python -m evidence_review`) after provenance diagnostics rather than relying on a bare PATH console script.

---

## File map

### New files

- `src/evidence_review/diagnostics.py` — stdlib-only runtime provenance/dependency model and collectors.
- `tests/unit/test_cli_diagnostics.py` — diagnostic model, repository/package matching, dependency-state tests.
- `tests/integration/packaging/test_cli_runtime_provenance.py` — subprocess/bootstrap tests for doctor, version, stale source, and missing dependency.
- `scripts/build_issues_98_101_acceptance_workspace.py` — deterministic two-page evidence/page-image and Track fixture builder for reproducible browser acceptance.
- `tests/integration/test_issues_98_101_acceptance_fixture.py` — subprocess contract test for the browser-acceptance fixture builder.
- `test-results/issues-98-101/acceptance.md` — untracked exact-HEAD acceptance evidence generated after the final tracked commit; post the same evidence to PR #102 so recording it does not change the tested HEAD.
- `docs/acceptance/issues-98-101/fts-characterization.json` — checked-in non-sensitive characterization metadata for the failing Korean lexical shape; no source PDF or user workspace path.

### Primary modified files

- `src/evidence_review/cli.py` — stdlib-only bootstrap, `doctor`, `--version`, and normal-command preflight before lazy runtime import.
- `src/ansim_review/cli_parser.py` — `review-question submit-track-b --open`.
- `src/ansim_review/cli.py` — protected handoff result projection and stable Track B contract-error projection.
- `src/ansim_review/review_run.py` — validated Track B run-local binding and finalizer artifact ownership.
- `src/ansim_review/review_question.py` — FINALIZING Track B identity/retry gate and recovery that preserves Track B.
- `src/ansim_review/retrieval/korean_variants.py` — bounded compound variants independent of numeric/concept grouping.
- `src/ansim_review/retrieval/index.py` — `fts_korean_compound` prefix channel and, only if characterization requires it, FTS-only search shadow representation.
- `src/ansim_review/retrieval/bundle.py` — compound channel ordering, provenance trace, structural-context seeding, and attempted-term export.
- `src/ansim_review/review_packet/assets/review.js` — non-recursive `activateReviewItem` orchestration.
- `docs/CODEX_WORKFLOW.md` — interpreter-pinned provenance-first CLI workflow.
- `docs/OFFLINE_EXECUTION.md` — provenance diagnostics and stale-installation remediation.
- `docs/REVIEWER_WORKFLOW.md` — formal review `submit-track-b --open` behavior and display-failure semantics.

### Existing tests to extend

- `tests/integration/review_run/test_review_run.py`
- `tests/integration/review_question/test_review_question_cli.py`
- `tests/integration/review_packet/test_review_workspace_ui.py`
- `tests/integration/review_packet/test_review_visual_contract.py`
- `tests/unit/retrieval/test_korean_variants.py`
- `tests/integration/retrieval/test_fts_lexical_channels.py`
- `tests/integration/retrieval/test_fts_retrieval.py`
- `tests/integration/retrieval/test_hybrid_fusion.py`
- `tests/integration/retrieval/test_korean_formal_review_retrieval.py`

---

### Task 1: Synchronize PR #102 with current main and pin the RED baseline

**Files:**
- Modify: `tests/integration/packaging/test_cli_runtime_provenance.py` (create in this task)
- Modify: `tests/integration/review_run/test_review_run.py`
- Modify: `tests/integration/review_question/test_review_question_cli.py`
- Modify: `tests/integration/review_packet/test_review_workspace_ui.py`
- Modify: `tests/integration/retrieval/test_fts_lexical_channels.py`
- Create: `docs/acceptance/issues-98-101/fts-characterization.json`

**Interfaces:**
- Consumes: current `origin/main`, current `evidence_review.cli`, `submit_track_b`, `submit_question_track_b`, `search_fts_phrase`, `search_fts_token_and`, rendered review controller.
- Produces: synchronized branch plus failing/characterization tests that pin the remaining #99/#101/#100/#98 behavior before production edits.

- [ ] **Step 1: Fetch and merge current `main` before any production edit**

Run from `agent/issues-98-101-integrated-fix`:

```bash
git fetch origin
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git merge --no-ff origin/main
```

Requirements:

```text
branch = agent/issues-98-101-integrated-fix
tracked worktree clean before merge
merge conflicts resolved in favor of current-main behavior first
```

After merge:

```bash
git rev-parse HEAD
git merge-base --is-ancestor origin/main HEAD
git status --short
```

`git merge-base --is-ancestor` must exit `0`.

- [ ] **Step 2: Run current-main focused suites before adding new RED tests**

```bash
pytest \
  tests/integration/review_run/test_review_run.py \
  tests/integration/review_question/test_review_question_cli.py \
  tests/integration/review_packet/test_review_workspace_ui.py \
  tests/integration/review_packet/test_review_visual_contract.py \
  tests/integration/retrieval/test_fts_lexical_channels.py \
  tests/integration/retrieval/test_korean_formal_review_retrieval.py -v
```

Expected: existing tests PASS. Record any pre-existing failure separately; do not reinterpret it as a new issue regression.

- [ ] **Step 3: Add the #99 stale-bootstrap RED test surface**

Create `tests/integration/packaging/test_cli_runtime_provenance.py` with a first test requiring a dependency-safe command that does not yet exist:

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_doctor_reports_current_checkout(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evidence_review",
            "doctor",
            "--repository-root",
            str(repo),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    document = json.loads(completed.stdout)
    assert document["status"] == "OK"
    assert Path(document["repository_root"]).resolve() == repo.resolve()
    assert document["package_checkout_match"] is True
```

Expected before #99 implementation: FAIL because `doctor` is not a bootstrap command.

- [ ] **Step 4: Add the #101 run-local Track B RED test**

In `tests/integration/review_run/test_review_run.py`:

```python
def test_submit_track_b_accepts_valid_run_local_track_b_without_rewriting(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_run(
        workspace,
        _write_request(tmp_path / "request.json"),
    )
    track_a, _external_b = _write_tracks(tmp_path / "tracks", prepared.run_id)
    submit_track_a(workspace, prepared.run_id, track_a)

    run_local_b = prepared.run_directory / "track-b-output.json"
    original = dump_bytes(_track_b(prepared.run_id))
    run_local_b.write_bytes(original)

    result = submit_track_b(workspace, prepared.run_id, run_local_b)

    assert result.packet.status == "READY_FOR_HUMAN_REVIEW"
    assert run_local_b.read_bytes() == original
```

Expected before #101 implementation: FAIL with the current finalizer collision.

- [ ] **Step 5: Add the #98 `review-question submit-track-b --open` RED parser/CLI test**

In `tests/integration/review_question/test_review_question_cli.py`, use monkeypatches for finalization/open so the test isolates command projection:

```python
def test_review_question_submit_track_b_open_returns_review_html_and_protected_url(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    run_id = "RUN-0123456789ABCDEF0123"
    html_path = workspace / "runs" / run_id / "review.html"

    def fake_submit(*_args, **_kwargs):
        return SimpleNamespace(
            run_id=run_id,
            review_html=html_path,
            packet=SimpleNamespace(status="READY_FOR_HUMAN_REVIEW"),
            published_packet=None,
        )

    def fake_open(_workspace: Path, _run_id: str) -> str:
        return f"http://127.0.0.1:8123/runs/{run_id}/token/review"

    monkeypatch.setattr(cli, "submit_question_track_b", fake_submit)
    monkeypatch.setattr(cli, "open_review_run", fake_open)

    exit_code = cli.main(
        [
            "review-question",
            "submit-track-b",
            "--workspace",
            str(workspace),
            "--run-id",
            run_id,
            "--track-b-output",
            str(tmp_path / "track-b.json"),
            "--open",
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["review_html"] == str(html_path)
    assert document["display_status"] == "OPENED"
    assert document["url"].startswith("http://127.0.0.1:")
```

Expected before #98 implementation: parser rejects `--open`.

- [ ] **Step 6: Characterize the current-main review-item/PDF behavior before refactoring**

Extend the Node harness in `tests/integration/review_packet/test_review_workspace_ui.py` with two review items whose first citations point to different `assetKey` values. Invoke the current click handler for item 2 and assert page 2 becomes active and the matching overlay becomes focused.

The RED/GREEN outcome is part of characterization:

- if current main already passes mouse activation, keep the test GREEN and do not claim that mouse click remains broken;
- keyboard/multiple-citation gaps are pinned in Task 7 before the orchestration refactor.

Do not modify `review.js` in this task.

- [ ] **Step 7: Probe the actual #100 failing lexical shape before writing a production fix**

Use the reproduction evidence database that contains issue #100's reported evidence ID:

```text
DOC-2B5B95BDB86296510A4A-2b5b95bdb862-P0039-E00007
```

Run a one-off Python probe from the synchronized checkout, replacing `C:\acceptance\issue100\evidence.sqlite` with the local reproduction database path:

```powershell
@'
import json
import sqlite3
import unicodedata
from pathlib import Path

path = Path(r"C:\acceptance\issue100\evidence.sqlite")
connection = sqlite3.connect(path)
connection.row_factory = sqlite3.Row

evidence_id = "DOC-2B5B95BDB86296510A4A-2b5b95bdb862-P0039-E00007"
row = connection.execute(
    "SELECT normalized_text FROM retrieval_records WHERE evidence_id = ?",
    (evidence_id,),
).fetchone()
assert row is not None
normalized = row["normalized_text"]
document = {
    "evidence_id": evidence_id,
    "normalized_repr": repr(normalized),
    "codepoints": [
        {
            "char": char,
            "codepoint": f"U+{ord(char):04X}",
            "category": unicodedata.category(char),
            "name": unicodedata.name(char, "UNKNOWN"),
        }
        for char in normalized
    ],
    "contains_literal": "주차구획선" in normalized,
}
print(json.dumps(document, ensure_ascii=False, indent=2))
'@ | py -3.13 -
```

Then, in the same database, record:

```sql
SELECT evidence_id
FROM evidence_fts
WHERE evidence_fts MATCH '"주차구획선"';

CREATE VIRTUAL TABLE temp.issue100_vocab USING fts5vocab(evidence_fts, 'row');
SELECT term FROM temp.issue100_vocab WHERE term LIKE '%주차%';
```

Write only non-sensitive lexical metadata to `docs/acceptance/issues-98-101/fts-characterization.json`:

```json
{
  "format": "evidence-review/fts-characterization",
  "version": 1,
  "issue": 100,
  "evidence_id": "DOC-2B5B95BDB86296510A4A-2b5b95bdb862-P0039-E00007",
  "query": "주차구획선",
  "contains_literal": true,
  "observed_categories": ["Lo"],
  "fts_hit_count_before_fix": 0,
  "cause_class": "TOKEN_PREFIX_OR_SEARCH_REPRESENTATION"
}
```

`observed_categories` and `cause_class` must reflect the actual probe. Do not record a local absolute path, PDF contents beyond the minimal term, or source bytes.

- [ ] **Step 8: Turn the measured #100 lexical shape into a RED repository fixture**

In `tests/integration/retrieval/test_fts_lexical_channels.py`, add a fixture element whose `normalized_text` reproduces the exact lexical boundary/format shape observed in Step 7, and add:

```python
def test_reported_korean_compound_present_in_authority_is_retrievable(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        connection = store.require_connection()
        row = connection.execute(
            "SELECT evidence_id, normalized_text FROM retrieval_records "
            "WHERE evidence_id = 'E-PARKING-LINE'"
        ).fetchone()
        assert row is not None

        hits = search_fts_phrase(connection, "주차구획선")
        token_hits = search_fts_token_and(connection, "주차구획선")

    assert "주차" in row["normalized_text"]
    assert {hit.evidence_id for hit in (*hits, *token_hits)} == {"E-PARKING-LINE"}
```

Expected before #100 implementation: FAIL for the same lexical reason measured in Step 7. If the exact measured fixture unexpectedly passes, stop this task and correct the fixture; do not change production retrieval until the repository test reproduces the observed failure.

- [ ] **Step 9: Run the four RED groups and save the exact failure reasons**

```bash
pytest tests/integration/packaging/test_cli_runtime_provenance.py -v
pytest tests/integration/review_run/test_review_run.py::test_submit_track_b_accepts_valid_run_local_track_b_without_rewriting -v
pytest tests/integration/review_question/test_review_question_cli.py -k "submit_track_b_open" -v
pytest tests/integration/retrieval/test_fts_lexical_channels.py -k "reported_korean_compound" -v
```

Expected: #99, #101, #98 handoff, and #100 lexical tests are RED for their intended reasons. The current-main UI characterization may already be GREEN and must be recorded as such.

- [ ] **Step 10: Commit the synchronized characterization baseline**

```bash
git add \
  tests/integration/packaging/test_cli_runtime_provenance.py \
  tests/integration/review_run/test_review_run.py \
  tests/integration/review_question/test_review_question_cli.py \
  tests/integration/review_packet/test_review_workspace_ui.py \
  tests/integration/retrieval/test_fts_lexical_channels.py \
  docs/acceptance/issues-98-101/fts-characterization.json
git commit -m "test: recharacterize issues 98 through 101 on current main"
```

---

### Task 2: Add dependency-safe runtime provenance diagnostics (#99)

**Files:**
- Create: `src/evidence_review/diagnostics.py`
- Modify: `src/evidence_review/cli.py`
- Create: `tests/unit/test_cli_diagnostics.py`
- Modify: `tests/integration/packaging/test_cli_runtime_provenance.py`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `docs/OFFLINE_EXECUTION.md`

**Interfaces:**
- Produces: `collect_runtime_diagnostics(repository_root: Path | None = None) -> RuntimeDiagnostics`, `preflight_runtime(repository_root: Path | None = None) -> RuntimeDiagnostics`.
- Normal business commands depend on: preflight status before importing `ansim_review.entrypoint`.
- Stable statuses: `OK`, `SOURCE_MISMATCH`, `DEPENDENCY_MISSING`, `NOT_A_CHECKOUT`.

- [ ] **Step 1: Write unit RED tests for the immutable diagnostic document**

Create `tests/unit/test_cli_diagnostics.py`:

```python
from pathlib import Path

from evidence_review.diagnostics import DependencyDiagnostic, RuntimeDiagnostics


def test_runtime_diagnostics_to_document_is_stable() -> None:
    diagnostic = RuntimeDiagnostics(
        status="OK",
        executable=Path("C:/Python313/python.exe"),
        command_path=Path("C:/venv/Scripts/evidence-review.exe"),
        distribution_version="0.1.0",
        working_directory=Path("C:/repo"),
        repository_root=Path("C:/repo"),
        repository_head="a" * 40,
        package_root=Path("C:/repo/src/ansim_review"),
        package_checkout_match=True,
        dependencies=(
            DependencyDiagnostic("pypdf", "pypdf", "OK", "5.9.0"),
            DependencyDiagnostic("pypdfium2", "pypdfium2", "OK", "5.12.0"),
            DependencyDiagnostic("Pillow", "PIL", "OK", "12.0.0"),
        ),
    )

    document = diagnostic.to_document()

    assert document["status"] == "OK"
    assert document["repository_head"] == "a" * 40
    assert document["package_checkout_match"] is True
    assert [item["distribution"] for item in document["dependencies"]] == [
        "pypdf",
        "pypdfium2",
        "Pillow",
    ]
```

Expected: FAIL because `evidence_review.diagnostics` does not exist.

- [ ] **Step 2: Define the stdlib-only diagnostic model**

Implement the beginning of `src/evidence_review/diagnostics.py`:

```python
from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RuntimeStatus = Literal["OK", "SOURCE_MISMATCH", "DEPENDENCY_MISSING", "NOT_A_CHECKOUT"]
DependencyStatus = Literal["OK", "MISSING"]

_REQUIRED_DEPENDENCIES = (
    ("pypdf", "pypdf"),
    ("pypdfium2", "pypdfium2"),
    ("Pillow", "PIL"),
)


@dataclass(frozen=True, slots=True)
class DependencyDiagnostic:
    distribution: str
    import_name: str
    status: DependencyStatus
    version: str | None

    def to_document(self) -> dict[str, object]:
        return {
            "distribution": self.distribution,
            "import_name": self.import_name,
            "status": self.status,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class RuntimeDiagnostics:
    status: RuntimeStatus
    executable: Path
    command_path: Path | None
    distribution_version: str | None
    working_directory: Path
    repository_root: Path | None
    repository_head: str | None
    package_root: Path | None
    package_checkout_match: bool | None
    dependencies: tuple[DependencyDiagnostic, ...]

    def to_document(self) -> dict[str, object]:
        return {
            "status": self.status,
            "executable": str(self.executable),
            "command_path": None if self.command_path is None else str(self.command_path),
            "distribution_version": self.distribution_version,
            "working_directory": str(self.working_directory),
            "repository_root": None if self.repository_root is None else str(self.repository_root),
            "repository_head": self.repository_head,
            "package_root": None if self.package_root is None else str(self.package_root),
            "package_checkout_match": self.package_checkout_match,
            "dependencies": [item.to_document() for item in self.dependencies],
        }
```

- [ ] **Step 3: Add RED tests for source mismatch and dependency missing**

Use monkeypatch around helper boundaries, not business modules:

```python
def test_source_mismatch_has_priority(monkeypatch, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout-a"
    expected_package = checkout / "src" / "ansim_review"
    actual_package = tmp_path / "checkout-b" / "src" / "ansim_review"
    expected_package.mkdir(parents=True)
    (checkout / "src" / "evidence_review").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    actual_package.mkdir(parents=True)

    monkeypatch.setattr(diagnostics, "_package_root", lambda _name: actual_package)
    monkeypatch.setattr(diagnostics, "_dependency_diagnostics", lambda: ())

    result = diagnostics.collect_runtime_diagnostics(checkout)
    assert result.status == "SOURCE_MISMATCH"


def test_missing_dependency_is_structured(monkeypatch, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "src" / "ansim_review").mkdir(parents=True)
    (checkout / "src" / "evidence_review").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.setattr(diagnostics, "_package_root", lambda _name: checkout / "src" / "ansim_review")
    monkeypatch.setattr(
        diagnostics,
        "_dependency_diagnostics",
        lambda: (DependencyDiagnostic("pypdfium2", "pypdfium2", "MISSING", None),),
    )

    result = diagnostics.collect_runtime_diagnostics(checkout)
    assert result.status == "DEPENDENCY_MISSING"
```

- [ ] **Step 4: Implement repository, package, dependency, and version discovery without importing business modules**

Implement:

```python
def _detect_repository_root(start: Path) -> Path | None:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "src" / "ansim_review").is_dir()
            and (candidate / "src" / "evidence_review").is_dir()
        ):
            return candidate
    return None


def _package_root(import_name: str) -> Path | None:
    spec = importlib.util.find_spec(import_name)
    if spec is None:
        return None
    if spec.submodule_search_locations:
        location = next(iter(spec.submodule_search_locations), None)
        return None if location is None else Path(location).resolve()
    if spec.origin:
        return Path(spec.origin).resolve().parent
    return None


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _dependency_diagnostics() -> tuple[DependencyDiagnostic, ...]:
    result: list[DependencyDiagnostic] = []
    for distribution, import_name in _REQUIRED_DEPENDENCIES:
        available = importlib.util.find_spec(import_name) is not None
        result.append(
            DependencyDiagnostic(
                distribution=distribution,
                import_name=import_name,
                status="OK" if available else "MISSING",
                version=_distribution_version(distribution) if available else None,
            )
        )
    return tuple(result)
```

Repository HEAD:

```python
def _repository_head(repository_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and len(value) == 40 else None
```

Status precedence must be:

```text
SOURCE_MISMATCH
> DEPENDENCY_MISSING
> NOT_A_CHECKOUT
> OK
```

This ensures a development checkout never proceeds from a different source tree even if another dependency is also missing.

- [ ] **Step 5: Implement `collect_runtime_diagnostics` and `preflight_runtime`**

```python
def collect_runtime_diagnostics(
    repository_root: Path | None = None,
) -> RuntimeDiagnostics:
    working_directory = Path.cwd().resolve()
    detected = (
        repository_root.resolve()
        if repository_root is not None
        else _detect_repository_root(working_directory)
    )
    package_root = _package_root("ansim_review")
    dependencies = _dependency_diagnostics()

    package_checkout_match: bool | None = None
    if detected is not None:
        expected = (detected / "src" / "ansim_review").resolve()
        package_checkout_match = package_root == expected

    if detected is not None and package_checkout_match is False:
        status: RuntimeStatus = "SOURCE_MISMATCH"
    elif any(item.status == "MISSING" for item in dependencies):
        status = "DEPENDENCY_MISSING"
    elif detected is None:
        status = "NOT_A_CHECKOUT"
    else:
        status = "OK"

    return RuntimeDiagnostics(
        status=status,
        executable=Path(sys.executable).resolve(),
        command_path=(
            None
            if shutil.which("evidence-review") is None
            else Path(shutil.which("evidence-review") or "").resolve()
        ),
        distribution_version=_distribution_version("evidence-review-system"),
        working_directory=working_directory,
        repository_root=detected,
        repository_head=None if detected is None else _repository_head(detected),
        package_root=package_root,
        package_checkout_match=package_checkout_match,
        dependencies=dependencies,
    )


def preflight_runtime(repository_root: Path | None = None) -> RuntimeDiagnostics:
    return collect_runtime_diagnostics(repository_root)
```

A wheel outside a repository may return `NOT_A_CHECKOUT` and is not blocked solely for that state.

- [ ] **Step 6: Refactor `src/evidence_review/cli.py` into a stdlib-only bootstrap**

Remove top-level imports of `ansim_review.cli_parser` and `ansim_review.entrypoint`.

Implement a tiny bootstrap parser that recognizes only diagnostic surfaces before runtime import:

```python
def _doctor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--repository-root", type=Path)
    return parser


def _write_json(document: object) -> None:
    print(json.dumps(document, ensure_ascii=False, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)

    if arguments == ["--version"]:
        version = importlib.metadata.version("evidence-review-system")
        print(version)
        return 0

    if arguments and arguments[0] == "doctor":
        doctor = _doctor_parser().parse_args(arguments[1:])
        result = collect_runtime_diagnostics(doctor.repository_root)
        _write_json(result.to_document())
        return 0 if result.status in {"OK", "NOT_A_CHECKOUT"} else 2

    result = preflight_runtime()
    if result.status in {"SOURCE_MISMATCH", "DEPENDENCY_MISSING"}:
        _write_json(result.to_document())
        return 2

    from ansim_review.entrypoint import main as runtime_main

    return runtime_main(arguments)
```

If `importlib.metadata.version` is unavailable because the source checkout is not installed, print a stable fallback such as `0+source` instead of a traceback for `--version`.

Do not import `ansim_review.cli_parser` from this bootstrap module; `build_parser` is no longer part of the canonical public import surface of `evidence_review.cli` unless another existing test proves it is required. If required, expose it through a lazy function that imports only when called.

- [ ] **Step 7: Add subprocess proof that stale source is blocked before business import**

In `test_cli_runtime_provenance.py`, build a temporary fake package root:

```python
def test_stale_ansim_source_fails_before_business_runtime_import(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    stale_root = tmp_path / "stale"
    package = stale_root / "ansim_review"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entrypoint.py").write_text(
        'raise AssertionError("business runtime imported before source preflight")\n',
        encoding="utf-8",
    )

    env = {
        "PYTHONPATH": os.pathsep.join(
            [str(stale_root), str(repo / "src")]
        )
    }
    completed = _run_module(repo, "query", env=env)

    assert completed.returncode == 2
    document = json.loads(completed.stdout)
    assert document["status"] == "SOURCE_MISMATCH"
    assert "business runtime imported" not in completed.stderr
```

Use `PYTHONPATH` to put the stale `ansim_review` package ahead of the repository `src`, while keeping `evidence_review` imported from the repository. The fake `ansim_review/entrypoint.py` must contain the assertion above.

- [ ] **Step 8: Add missing-dependency subprocess coverage with a clean interpreter**

Do not try to hide an already-installed dependency with a fake module: `importlib.util.find_spec()` would still observe the real installation. Instead, create a temporary virtual environment without pip-installed project dependencies, expose only the repository `src` tree through `PYTHONPATH`, and run the bootstrap with that interpreter.

Add a helper to `tests/integration/packaging/test_cli_runtime_provenance.py`:

```python
import os
import subprocess
import sys
import venv
from pathlib import Path


def _dependency_empty_python(tmp_path: Path) -> Path:
    environment = tmp_path / "dependency-empty"
    venv.EnvBuilder(with_pip=False, clear=True).create(environment)
    if sys.platform == "win32":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def test_doctor_reports_missing_runtime_dependency_without_traceback(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[3]
    python = _dependency_empty_python(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")

    doctor = subprocess.run(
        [
            str(python),
            "-m",
            "evidence_review",
            "doctor",
            "--repository-root",
            str(repo),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert doctor.returncode == 2
    document = json.loads(doctor.stdout)
    assert document["status"] == "DEPENDENCY_MISSING"
    missing = {
        item["distribution"]
        for item in document["dependencies"]
        if item["status"] == "MISSING"
    }
    assert {"pypdf", "pypdfium2", "Pillow"} <= missing
    assert "Traceback" not in doctor.stderr

    version = subprocess.run(
        [str(python), "-m", "evidence_review", "--version"],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert version.returncode == 0
    assert version.stdout.strip()
    assert "Traceback" not in version.stderr
```

This test proves `doctor` and `--version` run through the stdlib-only bootstrap even when none of the declared heavy runtime dependencies are installed.

- [ ] **Step 9: Run #99 tests**

```bash
pytest tests/unit/test_cli_diagnostics.py tests/integration/packaging/test_cli_runtime_provenance.py -v
```

Expected: PASS.

Then run a representative normal command parser test to ensure lazy dispatch did not change CLI behavior:

```bash
pytest tests/integration/review_run/test_review_run_cli.py tests/integration/retrieval/test_query_cli.py -v
```

Expected: PASS.

- [ ] **Step 10: Update provenance-first developer documentation**

In `docs/CODEX_WORKFLOW.md` and `docs/OFFLINE_EXECUTION.md`, replace bare acceptance examples with this sequence:

```powershell
$Workspace = "C:\evidence-review-workspace"
py -3.11 -m evidence_review doctor --repository-root .
py -3.11 -m evidence_review review-question prepare --workspace $Workspace --question "피난안전구역 설치기준"

py -3.13 -m evidence_review doctor --repository-root .
py -3.13 -m evidence_review review-question prepare --workspace $Workspace --question "피난안전구역 설치기준"
```

Document `SOURCE_MISMATCH` remediation as: activate/use the intended interpreter and reinstall the current checkout editable with that interpreter if needed:

```powershell
py -3.11 -m pip install -e ".[dev]"
py -3.13 -m pip install -e ".[dev]"
```

- [ ] **Step 11: Commit #99**

```bash
git add \
  src/evidence_review/diagnostics.py \
  src/evidence_review/cli.py \
  tests/unit/test_cli_diagnostics.py \
  tests/integration/packaging/test_cli_runtime_provenance.py \
  docs/CODEX_WORKFLOW.md \
  docs/OFFLINE_EXECUTION.md
git commit -m "fix: add dependency-safe runtime provenance diagnostics"
```

---

### Task 3: Make Track B a validated run input with deterministic retry (#101)

**Files:**
- Modify: `src/ansim_review/review_run.py`
- Modify: `src/ansim_review/review_question.py`
- Modify: `src/ansim_review/cli.py`
- Modify: `tests/integration/review_run/test_review_run.py`
- Modify: `tests/integration/review_question/test_review_question_cli.py`

**Interfaces:**
- Produces:
  - `TrackBContractError(reason_code: str, message: str)`
  - `_publish_validated_track_b(source: Path, destination: Path, document: object) -> None`
  - retry identity check based on the `FINALIZING` workflow event payload hash.
- Later #98 handoff consumes a successfully finalized `FinalizedReviewRun`.

- [ ] **Step 1: Define RED tests for same-path, external-identical, and differing canonical Track B**

Extend `tests/integration/review_run/test_review_run.py`:

```python
def test_external_track_b_reuses_identical_run_local_validated_input(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_run(workspace, _write_request(tmp_path / "request.json"))
    track_a, track_b = _write_tracks(tmp_path / "tracks", prepared.run_id)
    submit_track_a(workspace, prepared.run_id, track_a)

    canonical = prepared.run_directory / "track-b-output.json"
    canonical.write_bytes(dump_bytes(_track_b(prepared.run_id)))

    result = submit_track_b(workspace, prepared.run_id, track_b)
    assert result.packet.status == "READY_FOR_HUMAN_REVIEW"
```

Add a mismatch case:

```python
def test_external_track_b_rejects_different_existing_run_local_input(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_run(workspace, _write_request(tmp_path / "request.json"))
    track_a, track_b = _write_tracks(tmp_path / "tracks", prepared.run_id)
    submit_track_a(workspace, prepared.run_id, track_a)

    canonical = prepared.run_directory / "track-b-output.json"
    different = _track_b(prepared.run_id)
    different["overall_disposition"] = "REJECT"
    canonical.write_bytes(dump_bytes(different))

    with pytest.raises(TrackBContractError) as caught:
        submit_track_b(workspace, prepared.run_id, track_b)
    assert caught.value.reason_code == "TRACK_B_INPUT_MISMATCH"
```

Keep Task 1's same-path non-rewrite test.

- [ ] **Step 2: Add a stable Track B contract error**

In `review_run.py`:

```python
class TrackBContractError(ValueError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
```

Use it only for Track B ownership/retry contract distinctions. Keep ordinary structural validation errors as validation errors.

- [ ] **Step 3: Implement `_publish_validated_track_b` with same-path and create-or-identical semantics**

```python
def _publish_validated_track_b(
    source: Path,
    destination: Path,
    document: object,
) -> None:
    if source.resolve() == destination.resolve():
        if not destination.is_file():
            raise FileNotFoundError(destination)
        return

    encoded = dump_bytes(document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(encoded)
    except FileExistsError:
        try:
            existing = dump_bytes(_json(destination))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise TrackBContractError(
                "TRACK_B_INPUT_MISMATCH",
                "existing run-local Track B is not a valid canonical JSON document",
            ) from error
        if existing != encoded:
            raise TrackBContractError(
                "TRACK_B_INPUT_MISMATCH",
                "existing run-local Track B differs from validated submission",
            ) from None
```

Important: for a valid same-path input, do not serialize and rewrite it. Validation happens before this helper.

- [ ] **Step 4: Bind validated Track B before finalizer output collision checks**

In `submit_track_b`:

```python
output = _json(track_b_output)
if not prevalidated:
    validate_track_b_submission(workspace_root, run_id, track_b_output)
run_directory = _require_prepared_run(workspace_root, run_id)
bound_track_b = run_directory / "track-b-output.json"
_publish_validated_track_b(track_b_output, bound_track_b, output)
```

Then call the finalizer with `bound_track_b` and an explicit flag indicating it is already a validated bound input:

```python
return finalize_review_run(
    workspace_root,
    run_id,
    run_directory / "track-a-output.json",
    bound_track_b,
    publish=publish,
    bound_track_b=True,
)
```

Add `bound_track_b: bool = False` to `finalize_review_run`.

- [ ] **Step 5: Separate bound input ownership from direct `review-run finalize` ownership**

In `finalize_review_run`:

```python
imported_b = run_directory / "track-b-output.json"

if bound_track_b:
    if track_b_output.resolve() != imported_b.resolve() or not imported_b.is_file():
        raise TrackBContractError(
            "TRACK_B_INPUT_MISMATCH",
            "bound Track B must be the validated run-local artifact",
        )
    generated = (
        run_directory / "run-manifest.json",
        run_directory / "final-review-packet.json",
        run_directory / "review.html",
    )
else:
    generated = (
        run_directory / "track-b-output.json",
        run_directory / "run-manifest.json",
        run_directory / "final-review-packet.json",
        run_directory / "review.html",
    )
```

For `bound_track_b=True`, do not call `_write_json(imported_b, track_b_document)` and do not put `imported_b` in cleanup.

For direct `review-run finalize`, retain the existing create-only behavior unless/until a separate issue changes that API.

- [ ] **Step 6: Add retry hash identity tests before recovery changes**

In `tests/integration/review_question/test_review_question_cli.py`:

```python
def test_finalizing_retry_rejects_different_track_b_before_finalizer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    first = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / first.run_id
    submit_question_track_a(workspace, first.run_id, _track_a(run_directory))

    original = _track_b(run_directory)
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    _append_event(run_directory, "FINALIZING", original_hash)

    changed = run_directory / "different-track-b.json"
    payload = json.loads(original.read_text(encoding="utf-8"))
    payload["claim_audits"][0]["notes"] = "different retry"
    changed.write_bytes(dump_bytes(payload))

    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("finalizer must not run for a retry hash mismatch")

    monkeypatch.setattr(review_question, "submit_track_b", fail_if_called)

    with pytest.raises(TrackBContractError) as caught:
        submit_question_track_b(workspace, first.run_id, changed)
    assert caught.value.reason_code == "TRACK_B_RETRY_MISMATCH"
    assert called is False
```

- [ ] **Step 7: Implement the FINALIZING hash gate**

Add:

```python
def _required_finalizing_track_b_hash(run_directory: Path) -> str:
    events = load_workflow_events(run_directory / "events")
    finalizing = [event for event in events if event.next_state == "FINALIZING"]
    if not finalizing:
        raise ValueError("FINALIZING state requires a Track B identity event")
    return finalizing[-1].payload_sha256


def _validate_finalizing_retry_identity(
    run_directory: Path,
    track_b_output: Path,
) -> None:
    expected = _required_finalizing_track_b_hash(run_directory)
    actual = _sha256(track_b_output)
    if actual != expected:
        raise TrackBContractError(
            "TRACK_B_RETRY_MISMATCH",
            "retry Track B does not match the artifact that entered FINALIZING",
        )
```

Call this before `_recover_incomplete_finalization` and before `submit_track_b` whenever `_resume_state` reports `FINALIZING`.

- [ ] **Step 8: Preserve valid Track B during interrupted-finalization recovery**

Replace `_recover_incomplete_finalization` with behavior that never deletes a valid canonical Track B:

```python
def _recover_incomplete_finalization(
    run_directory: Path,
    track_b_output: Path,
) -> None:
    canonical = run_directory / "track-b-output.json"
    if canonical.exists():
        try:
            canonical_document = _json(canonical)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            canonical_document = None

        if canonical_document is not None:
            incoming = dump_bytes(_json(track_b_output))
            if dump_bytes(canonical_document) != incoming:
                raise TrackBContractError(
                    "TRACK_B_INPUT_MISMATCH",
                    "validated run-local Track B differs from retry input",
                )
        elif track_b_output.resolve() == canonical.resolve():
            # A malformed same-path user input must fail validation before recovery.
            raise ValueError("malformed run-local Track B cannot be recovered as validated input")
        else:
            # Retry identity was already checked against the FINALIZING event.
            canonical.unlink()

    for name in ("run-manifest.json", "final-review-packet.json", "review.html"):
        (run_directory / name).unlink(missing_ok=True)
```

When the canonical file was a malformed partial left during an interrupted external publish, `submit_track_b` may recreate it from the already hash-validated external retry. A valid canonical Track B is never deleted.

- [ ] **Step 9: Keep current malformed-partial recovery as a regression**

Retain and adapt `test_track_b_recovers_malformed_import_while_finalizing` so:

- the retry source is external and hash-identical to the `FINALIZING` event;
- the run-local `track-b-output.json` is malformed partial JSON;
- recovery deletes only that malformed partial copy;
- finalization succeeds and the resulting canonical Track B is valid;
- a malformed same-path Track B still fails validation.

- [ ] **Step 10: Project stable Track B contract errors through CLI**

In `ansim_review.cli`, catch `TrackBContractError` before generic `ValueError`:

```python
except TrackBContractError as error:
    _write_stdout(
        {
            "format": "evidence-review/review-question-status",
            "version": 1,
            "stage": "submit-track-b",
            "status": "FAILED",
            "reason_code": error.reason_code,
            "run_id": run_id,
        }
    )
    return 2
```

Do not expose raw `FileExistsError` as the user contract for valid run-local Track B.

- [ ] **Step 11: Run #101 focused tests**

```bash
pytest \
  tests/integration/review_run/test_review_run.py \
  tests/integration/review_question/test_review_question_cli.py -v
```

Expected: PASS, including existing interrupted-finalization tests.

- [ ] **Step 12: Commit #101**

```bash
git add \
  src/ansim_review/review_run.py \
  src/ansim_review/review_question.py \
  src/ansim_review/cli.py \
  tests/integration/review_run/test_review_run.py \
  tests/integration/review_question/test_review_question_cli.py
git commit -m "fix: treat Track B as a validated run input"
```

---

### Task 4: Derive bounded Korean compound terms independent of numeric/concept grouping (#100)

**Files:**
- Modify: `src/ansim_review/retrieval/korean_variants.py`
- Modify: `tests/unit/retrieval/test_korean_variants.py`

**Interfaces:**
- Produces: `derive_korean_compound_variants(primary: str) -> tuple[str, ...]`.
- Task 5 consumes these variants to create a traceable FTS channel.

- [ ] **Step 1: Write RED unit tests for bounded compound derivation**

Add:

```python
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("청소년문화의집 설치기준", ("청소년문화의집",)),
        (
            "청소년 문화의집 설치기준",
            ("청소년 문화의집", "청소년문화의집"),
        ),
        (
            "소방차 전용구역",
            ("소방차 전용구역", "소방차전용구역"),
        ),
        ("피난안전구역에서", ("피난안전구역",)),
        ("설치기준", ()),
    ],
)
def test_derive_korean_compound_variants_is_bounded(
    query: str,
    expected: tuple[str, ...],
) -> None:
    assert derive_korean_compound_variants(query) == expected
```

Add zero-width handling:

```python
def test_compound_variants_remove_only_known_zero_width_markers() -> None:
    assert derive_korean_compound_variants("주차\u200b구획선 설치기준") == (
        "주차구획선",
    )
```

- [ ] **Step 2: Define generic trailing terms that must not become broad search entities**

In `korean_variants.py`:

```python
_GENERIC_TRAILING_TERMS = frozenset(
    {
        "기준",
        "설치기준",
        "관련기준",
        "요건",
        "여부",
        "규정",
        "조건",
    }
)
_ZERO_WIDTH = ("\u200b", "\u200c", "\u200d", "\u2060", "\ufeff")
_HANGUL = re.compile(r"[가-힣]")
```

These terms are excluded only from derived compound search terms; they remain in the original authoritative query.

- [ ] **Step 3: Implement bounded normalization helpers**

```python
def _search_normalized(value: str) -> str:
    normalized = normalize_text(value)
    for marker in _ZERO_WIDTH:
        normalized = normalized.replace(marker, "")
    return " ".join(normalized.split())


def _hangul_token(value: str) -> bool:
    return bool(value) and _HANGUL.search(value) is not None
```

Reuse `_strip_suffix` for the final lexical token.

- [ ] **Step 4: Implement `derive_korean_compound_variants` without token-OR expansion**

```python
def derive_korean_compound_variants(primary: str) -> tuple[str, ...]:
    normalized = _search_normalized(primary)
    if not normalized:
        raise ValueError("primary query must not be empty")

    tokens = [_strip_suffix(token) for token in normalized.split()]
    while tokens and tokens[-1] in _GENERIC_TRAILING_TERMS:
        tokens.pop()
    tokens = [token for token in tokens if token]
    if not tokens:
        return ()

    if len(tokens) == 1:
        token = tokens[0]
        if len(token) < 2 or not _hangul_token(token):
            return ()
        return (token,)

    if len(tokens) > 3 or not all(_hangul_token(token) for token in tokens):
        return ()

    spaced = " ".join(tokens)
    compact = "".join(tokens)
    return _ordered_unique([spaced, compact])
```

Do not emit each individual token from a multi-token phrase. The output is a bounded phrase/compound channel, not a broad OR channel.

- [ ] **Step 5: Run Korean variant unit tests**

```bash
pytest tests/unit/retrieval/test_korean_variants.py -v
```

Expected: PASS, including existing grouped entity/numeric/concept behavior.

- [ ] **Step 6: Commit the derivation layer**

```bash
git add \
  src/ansim_review/retrieval/korean_variants.py \
  tests/unit/retrieval/test_korean_variants.py
git commit -m "fix: derive bounded Korean compound terms"
```

---

### Task 5: Add the traceable Korean compound FTS channel and only the search representation proven necessary (#100)

**Files:**
- Modify: `src/ansim_review/retrieval/index.py`
- Modify: `src/ansim_review/retrieval/bundle.py`
- Modify: `tests/integration/retrieval/test_fts_lexical_channels.py`
- Modify: `tests/integration/retrieval/test_fts_retrieval.py`
- Modify: `tests/integration/retrieval/test_hybrid_fusion.py`
- Modify: `tests/integration/retrieval/test_korean_formal_review_retrieval.py`
- Modify only if proven necessary: evidence schema/migration files.

**Interfaces:**
- Produces: traceable `fts_korean_compound` retrieval hits and `query.derived_variants.compound`.
- Preserves: `retrieval_records.raw_text`, `retrieval_records.normalized_text`, citation fields, snapshot lineage.

- [ ] **Step 1: Add `fts_korean_compound` as an allowed literal channel**

In `index.py`:

```python
_GROUP_CHANNELS = frozenset(
    {"fts_entity", "fts_numeric", "fts_concept", "fts_korean_compound"}
)
```

No existing channel name or matching expression changes in this step.

- [ ] **Step 2: Add compound variants before existing grouped channels in `bundle.py`**

Import `derive_korean_compound_variants` and add:

```python
def _compound_variant_hits(
    connection: sqlite3.Connection,
    primary: str,
    limit: int,
) -> tuple[tuple[RetrievalHit, ...], ...]:
    channels: list[tuple[RetrievalHit, ...]] = []
    for term in derive_korean_compound_variants(primary):
        hits = search_fts_literal(
            connection,
            term,
            channel="fts_korean_compound",
            limit=limit,
        )
        channels.append(
            _trace_hits(
                hits,
                origin="derived:korean_compound",
                term=term,
            )
        )
    return tuple(channels)
```

Order in `build_evidence_bundle`:

```python
channels = list(_origin_hits(connection, query, limit))
channels.extend(_compound_variant_hits(connection, query.primary, limit))
channels.extend(_derived_variant_hits(connection, query.primary, limit))
```

Add `fts_korean_compound` to `_GROUPED_CONTEXT_CHANNELS` so separately cited adjacent-row context remains available for Korean label hits.

- [ ] **Step 3: Export attempted compound terms without changing query authority**

In `build_evidence_bundle`:

```python
compound_variants = derive_korean_compound_variants(query.primary)
```

Add:

```python
"derived_variants": {
    "compound": list(compound_variants),
    "entity": list(variants.entity),
    "numeric": list(variants.numeric),
    "concept": list(variants.concept),
},
```

The original `query.primary` and `query.terms[*].origin` remain unchanged.

- [ ] **Step 4: Make the measured issue-100 fixture GREEN using the smallest sufficient mechanism**

First run:

```bash
pytest tests/integration/retrieval/test_fts_lexical_channels.py -k "reported_korean_compound" -v
```

Decision table:

| Measured/fixture behavior | Implementation |
|---|---|
| Prefix literal channel alone returns the failing row | Stop here; do not alter FTS index representation. |
| Failure is caused only by known zero-width format characters | Normalize those characters in FTS-only search text before indexing. |
| Failure is caused by spacing split such as `소방차 전용구역` vs `소방차전용구역` | Add bounded compact Hangul n-gram aliases to FTS-only search text. |
| Existing FTS table cannot hold the required aliases without authority-field mutation | Only then create a schema migration; document why in the characterization JSON before editing schema. |

For the first three rows, no schema migration is allowed.

- [ ] **Step 5: If characterization requires an FTS-only shadow representation, implement it without changing `retrieval_records`**

Add to `index.py` only when Step 4 requires it:

```python
_HANGUL_TOKEN = re.compile(r"^[가-힣]+$")


def _fts_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join(value.split()))
    for marker in ("\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"):
        normalized = normalized.replace(marker, "")

    tokens = normalized.split()
    aliases: list[str] = []
    for size in (2, 3):
        for start in range(0, len(tokens) - size + 1):
            group = tokens[start : start + size]
            cleaned = [token.strip(".,!?;:()[]{}<>\"'“”‘’") for token in group]
            if all(_HANGUL_TOKEN.fullmatch(token) for token in cleaned):
                aliases.append("".join(cleaned))

    values = [normalized, *aliases]
    return " ".join(dict.fromkeys(value for value in values if value))
```

Change only the FTS insertion:

```python
connection.executemany(
    """
    INSERT INTO evidence_fts(evidence_id, title, raw_text, normalized_text)
    VALUES(?, ?, ?, ?)
    """,
    (
        (
            row[0],
            row[8],
            row[9],
            _fts_search_text(str(row[10])),
        )
        for row in rows
    ),
)
```

`retrieval_records` insertion remains `rows` unchanged.

- [ ] **Step 6: Add authority-preservation assertions**

In `test_fts_retrieval.py`, after index build:

```python
record = connection.execute(
    "SELECT raw_text, normalized_text, source_hash FROM retrieval_records WHERE evidence_id = ?",
    ("E-PARKING-LINE",),
).fetchone()

assert record["raw_text"] == expected_raw_text
assert record["normalized_text"] == expected_normalized_text
assert record["source_hash"] == "a" * 64
```

If an FTS shadow was required, separately assert the FTS searchable field may contain aliases while the authority record does not.

- [ ] **Step 7: Add required lexical fixtures and regressions**

Keep the measured `E-PARKING-LINE` element added during Task 1. In the same `_snapshot()` fixture, add deterministic authoritative elements for the other required terms:

```python
{
    "id": "E-FIRE-LANE",
    "revision_id": "LAW1-REV1",
    "page_id": "LAW1-P1",
    "page_number": 1,
    "element_type": "clause",
    "raw_json": {"text": "소방차 전용구역은 소방활동을 위해 확보한다."},
    "raw_text": "소방차 전용구역은 소방활동을 위해 확보한다.",
    "normalized_text": "소방차 전용구역은 소방활동을 위해 확보한다.",
    "raw_payload_hash": "7" * 64,
    "bbox": [10.0, 180.0, 500.0, 210.0],
    "parser_order": 4,
},
{
    "id": "E-EGRESS-SAFE",
    "revision_id": "LAW1-REV1",
    "page_id": "LAW1-P1",
    "page_number": 1,
    "element_type": "clause",
    "raw_json": {"text": "피난안전구역에서 피난 동선을 확보한다."},
    "raw_text": "피난안전구역에서 피난 동선을 확보한다.",
    "normalized_text": "피난안전구역에서 피난 동선을 확보한다.",
    "raw_payload_hash": "8" * 64,
    "bbox": [10.0, 220.0, 500.0, 250.0],
    "parser_order": 5,
},
```

Use unique `parser_order`, bbox, and payload-hash values if Task 1's measured fixture already occupies either numeric slot; do not change the authoritative text shown above.

Then parameterize `test_fts_lexical_channels.py` so the bundle returns the intended evidence for:

```python
@pytest.mark.parametrize(
    ("question", "expected_id"),
    [
        ("주차구획선", "E-PARKING-LINE"),
        ("소방차 전용구역", "E-FIRE-LANE"),
        ("소방차전용구역", "E-FIRE-LANE"),
        ("피난안전구역", "E-EGRESS-SAFE"),
    ],
)
def test_korean_compound_channel_retrieves_authoritative_element(
    tmp_path: Path,
    question: str,
    expected_id: str,
) -> None:
    with _store(tmp_path) as store:
        bundle = build_evidence_bundle(
            store.require_connection(),
            {
                "question": question,
                "synonym_manifest": {},
                "expansions": [],
                "limit": 20,
            },
        )

    hit = next(item for item in bundle["hits"] if item["evidence_id"] == expected_id)
    channels = {item["channel"] for item in hit["channel_scores"]}
    assert "fts_korean_compound" in channels or "fts_phrase" in channels
    assert hit["citation"]["evidence_id"] == expected_id
```

For a fallback hit, assert its detail contains:

```text
derived:korean_compound:
```

- [ ] **Step 8: Extend bare formal-review questions without user expansion**

In `tests/integration/retrieval/test_korean_formal_review_retrieval.py`, add label/criterion elements and tests for:

```python
@pytest.mark.parametrize(
    "question",
    [
        "청소년 문화의집 설치기준",
        "청소년문화의집 설치기준",
        "청소년수련관 설치기준",
    ],
)
def test_bare_korean_formal_review_question_retrieves_without_user_expansion(
    tmp_path: Path,
    question: str,
) -> None:
    with _store(tmp_path) as store:
        bundle = build_evidence_bundle(
            store.require_connection(),
            {
                "question": question,
                "synonym_manifest": {},
                "expansions": [],
                "limit": 20,
            },
        )

    assert bundle["hits"]
    assert all(term["origin"] != "user" for term in bundle["query"]["terms"])
```

Assert the expected label evidence ID for each question and its separately cited adjacent criterion where applicable.

- [ ] **Step 9: Preserve English/numeric and fusion behavior**

Run:

```bash
pytest \
  tests/integration/retrieval/test_fts_lexical_channels.py \
  tests/integration/retrieval/test_fts_retrieval.py \
  tests/integration/retrieval/test_hybrid_fusion.py \
  tests/integration/retrieval/test_korean_formal_review_retrieval.py -v
```

Expected: PASS. Existing exact phrase/token-and order and English/numeric results remain unchanged.

- [ ] **Step 10: Commit #100 retrieval**

```bash
git add \
  src/ansim_review/retrieval/index.py \
  src/ansim_review/retrieval/bundle.py \
  tests/integration/retrieval/test_fts_lexical_channels.py \
  tests/integration/retrieval/test_fts_retrieval.py \
  tests/integration/retrieval/test_hybrid_fusion.py \
  tests/integration/retrieval/test_korean_formal_review_retrieval.py
git commit -m "fix: retrieve bounded Korean compound terms"
```

If characterization proved a schema migration necessary, include only the migration files proven necessary by the Task 1 characterization and add their focused migration tests to this commit.

---

### Task 6: Add `review-question submit-track-b --open` protected handoff (#98 result display)

**Files:**
- Modify: `src/ansim_review/cli_parser.py`
- Modify: `src/ansim_review/cli.py`
- Modify: `tests/integration/review_question/test_review_question_cli.py`
- Modify: `docs/REVIEWER_WORKFLOW.md`

**Interfaces:**
- Consumes: `submit_question_track_b(...) -> FinalizedReviewRun`, existing `open_review_run(workspace, run_id) -> str` from #92.
- Produces: `review-question submit-track-b --open` JSON with `review_html`, `display_status`, and optional `url`/`display_error`.

- [ ] **Step 1: Keep Task 1's RED parser/projection test and add display-failure RED coverage**

Add:

```python
def test_review_question_submit_track_b_open_preserves_finalization_on_display_failure(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    run_id = "RUN-0123456789ABCDEF0123"
    html_path = workspace / "runs" / run_id / "review.html"

    monkeypatch.setattr(
        cli,
        "submit_question_track_b",
        lambda *_args, **_kwargs: SimpleNamespace(
            run_id=run_id,
            review_html=html_path,
            packet=SimpleNamespace(status="READY_FOR_HUMAN_REVIEW"),
            published_packet=None,
        ),
    )

    def fail_open(*_args, **_kwargs):
        raise RuntimeError("browser dispatch failed")

    monkeypatch.setattr(cli, "open_review_run", fail_open)

    exit_code = cli.main(
        [
            "review-question",
            "submit-track-b",
            "--workspace",
            str(workspace),
            "--run-id",
            run_id,
            "--track-b-output",
            str(tmp_path / "track-b.json"),
            "--open",
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "READY_FOR_HUMAN_REVIEW"
    assert document["review_html"] == str(html_path)
    assert document["display_status"] == "OPEN_FAILED"
    assert "browser dispatch failed" in document["display_error"]
    assert "url" not in document
```

A display failure after successful finalization is not a finalization failure. Return `0` so callers can inspect the completed review artifact; the JSON `display_status` carries the degraded display state.

- [ ] **Step 2: Add `--open` to the parser**

In `cli_parser.py`:

```python
question_track_b.add_argument(
    "--open",
    action="store_true",
    help="open the finalized formal-review workspace through its protected loopback route",
)
```

- [ ] **Step 3: Extend `_review_question_submit_track_b` signature**

```python
def _review_question_submit_track_b(
    workspace: Path,
    run_id: str,
    output: Path,
    *,
    publish: bool,
    open_browser: bool,
) -> int:
```

Call it from `main` with `open_browser=args.open`.

- [ ] **Step 4: Always include `review_html` on successful finalization**

Base success document:

```python
document: dict[str, object] = {
    "format": "evidence-review/review-question-status",
    "version": 1,
    "stage": "submit-track-b",
    "status": result.packet.status,
    "run_id": result.run_id,
    "review_html": str(result.review_html),
}
```

For `publish`, retain existing publication semantics but do not hide `review_html`.

- [ ] **Step 5: Reuse #92 `open_review_run` only after finalization succeeds**

```python
if open_browser:
    try:
        url = open_review_run(workspace, result.run_id)
    except (OSError, RuntimeError, ValueError) as error:
        document["display_status"] = "OPEN_FAILED"
        document["display_error"] = str(error)
    else:
        document["display_status"] = "OPENED"
        document["url"] = url
```

Do not wait for or close the detached protected server in this command.

- [ ] **Step 6: Write stdout exactly once and return finalization success**

```python
_write_stdout(document)
return 0
```

Track B validation/finalization errors still return the existing failure codes before any browser call.

- [ ] **Step 7: Run CLI handoff tests**

```bash
pytest tests/integration/review_question/test_review_question_cli.py -k "submit_track_b" -v
pytest tests/integration/review_run/test_review_run.py -k "open" -v
```

Expected: PASS and #92 detached lifecycle tests remain unchanged.

- [ ] **Step 8: Update reviewer workflow docs**

Document:

```powershell
py -3.13 -m evidence_review review-question submit-track-b `
  --workspace $Workspace `
  --run-id $RunId `
  --track-b-output $TrackB `
  --open
```

Explain:

- `display_status=OPENED` means the protected URL was dispatched;
- `display_status=OPEN_FAILED` means packet/HTML finalization succeeded but browser display failed;
- `review_html` is always returned on successful finalization;
- the command does not block for the server's full idle lifetime.

- [ ] **Step 9: Commit #98 protected handoff**

```bash
git add \
  src/ansim_review/cli_parser.py \
  src/ansim_review/cli.py \
  tests/integration/review_question/test_review_question_cli.py \
  docs/REVIEWER_WORKFLOW.md
git commit -m "fix: return protected formal-review handoff"
```

---

### Task 7: Unify review-item selection and PDF evidence focus without recursive ownership (#98 UI)

**Files:**
- Modify: `src/ansim_review/review_packet/assets/review.js`
- Modify: `tests/integration/review_packet/test_review_workspace_ui.py`
- Modify: `tests/integration/review_packet/test_review_visual_contract.py`

**Interfaces:**
- Produces: `resolveReviewItemEvidence(itemId, requestedEvidenceId) -> string`, `activateReviewItem(itemId, requestedEvidenceId) -> boolean`.
- `selectReviewItem` owns rail/detail state only.
- `focusEvidence` owns page/bbox state only.
- No cyclic calls between selection and focus functions.

- [ ] **Step 1: Add a Node RED test for first-citation focus across pages**

Extend the existing `_run_node_harness` setup with:

```javascript
const item1 = node(false, {itemId: "ITEM-1", evidenceId: "EV-1"});
const item2 = node(false, {itemId: "ITEM-2", evidenceId: "EV-2"});
const panel1 = node(false, {itemId: "ITEM-1"});
const panel2 = node(false, {itemId: "ITEM-2"});
const citation1 = node(false, {evidenceId: "EV-1", assetKey: "REV1-P1"});
const citation2 = node(false, {evidenceId: "EV-2", assetKey: "REV1-P2"});
const page1 = node(false, {assetKey: "REV1-P1"});
const page2 = node(false, {assetKey: "REV1-P2"});
const overlay1 = node(false, {evidenceId: "EV-1"});
const overlay2 = node(false, {evidenceId: "EV-2"});
```

Wire `panel.querySelectorAll(".citation")` and `panel.querySelector(".citation[data-evidence-id]")` to the matching citation.

After `eval(controller)`:

```javascript
item2.listeners.click();
if (!page2.classList.contains("is-active")) throw new Error("page 2 not activated");
if (!overlay2.classList.contains("is-focused")) throw new Error("bbox not focused");
if (!item2.classList.contains("is-selected")) throw new Error("rail item not selected");
```

Expected before refactor: characterize current main. If already GREEN, keep it as a regression and continue with Steps 2–3, which pin behavior current main does not explicitly own.

- [ ] **Step 2: Add a RED test that no-citation item activation preserves viewer state**

Create `ITEM-3` with a detail panel but no `.citation`. Set page 2 active first, activate item 3, then assert page 2 remains active and no overlay is newly focused.

```javascript
activateReviewItem("ITEM-3");
if (!page2.classList.contains("is-active")) {
  throw new Error("citation-free item changed the PDF page");
}
```

- [ ] **Step 3: Add keyboard RED tests for Enter and Space parity**

Require review items to handle both keys through the same orchestrator:

```javascript
item2.listeners.keydown({ key: "Enter", preventDefault() {} });
if (!page2.classList.contains("is-active")) throw new Error("Enter did not activate item 2 evidence");
item1.listeners.keydown({ key: " ", preventDefault() {} });
if (!page1.classList.contains("is-active")) throw new Error("Space did not activate item 1 evidence");
```

Assert the same page/bbox and rail state as mouse activation.

- [ ] **Step 4: Refactor `selectReviewItem` to selection state only**

Keep:

- `.review-item`/`.detail-panel` selected classes;
- `aria-pressed`;
- `updateTabControls`;
- detail tab activation.

Remove any evidence page/bbox movement from this function.

- [ ] **Step 5: Refactor `focusEvidence` to viewer state only**

Remove its internal `selectReviewItem(itemId, evidenceId)` call.

Use the provided item/evidence identity only to resolve the citation asset:

```javascript
function focusEvidence(itemId, evidenceId) {
  const citation = Array.from(document.querySelectorAll(".citation")).find((node) => {
    const panel = node.closest(".detail-panel");
    return panel &&
      panel.dataset.itemId === itemId &&
      node.dataset.evidenceId === evidenceId;
  });
  const assetKey = citation ? citation.dataset.assetKey : "";
  if (!assetKey) return false;

  setActivePage(assetKey);
  document.querySelectorAll(".citation-overlay").forEach((overlay) => {
    overlay.classList.toggle(
      "is-focused",
      overlay.dataset.evidenceId === evidenceId
    );
  });
  const page = Array.from(document.querySelectorAll(".evidence-page")).find(
    (node) => node.dataset.assetKey === assetKey
  );
  if (page) {
    page.scrollIntoView({ behavior: "smooth", block: "nearest" });
    page.focus({ preventScroll: true });
  }
  return true;
}
```

Return a boolean so orchestration tests can distinguish “no evidence target” without throwing.

- [ ] **Step 6: Add `resolveReviewItemEvidence` and `activateReviewItem`**

```javascript
function resolveReviewItemEvidence(itemId, requestedEvidenceId) {
  const panel = Array.from(document.querySelectorAll(".detail-panel")).find(
    (node) => node.dataset.itemId === itemId
  );
  if (!panel) return "";

  if (requestedEvidenceId) {
    const requested = Array.from(panel.querySelectorAll(".citation")).find(
      (node) => node.dataset.evidenceId === requestedEvidenceId
    );
    if (requested) return requestedEvidenceId;
  }

  const first = panel.querySelector(".citation[data-evidence-id]");
  return first ? first.dataset.evidenceId : "";
}


function activateReviewItem(itemId, requestedEvidenceId) {
  selectReviewItem(itemId, requestedEvidenceId);
  const evidenceId = resolveReviewItemEvidence(itemId, requestedEvidenceId);
  if (!evidenceId) return false;
  return focusEvidence(itemId, evidenceId);
}
```

`selectReviewItem` and `focusEvidence` must not call each other after this step.

- [ ] **Step 7: Route review-item mouse and keyboard events through `activateReviewItem`**

```javascript
document.querySelectorAll(".review-item").forEach((item) => {
  item.addEventListener("click", () => {
    activateReviewItem(item.dataset.itemId);
  });
  item.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    activateReviewItem(item.dataset.itemId);
  });
});
```

Do not separately call `focusEvidence` from the item handler.

- [ ] **Step 8: Route direct citation/evidence-link activation through the same item orchestration**

Citation click:

```javascript
const panel = citation.closest(".detail-panel");
if (panel) activateReviewItem(panel.dataset.itemId, citation.dataset.evidenceId);
```

Evidence-link click uses the same pattern.

Existing keydown-to-click handling for citation/evidence links may remain if it produces the same handler path.

- [ ] **Step 9: Export the orchestrator for the Node harness and assert non-recursion statically**

```javascript
window.activateReviewItem = activateReviewItem;
```

In `test_review_visual_contract.py`, inspect function bodies and assert:

```python
assert "focusEvidence(" not in select_review_item_body
assert "selectReviewItem(" not in focus_evidence_body
assert "activateReviewItem(" in controller
```

- [ ] **Step 10: Run UI focused tests**

```bash
pytest \
  tests/integration/review_packet/test_review_workspace_ui.py \
  tests/integration/review_packet/test_review_visual_contract.py -v
```

Expected: PASS.

- [ ] **Step 11: Commit #98 UI orchestration**

```bash
git add \
  src/ansim_review/review_packet/assets/review.js \
  tests/integration/review_packet/test_review_workspace_ui.py \
  tests/integration/review_packet/test_review_visual_contract.py
git commit -m "fix: unify review selection and evidence focus"
```

---

### Task 8: Add deterministic zero-hit guidance and Korean formal-review integration (#98 consuming #100)

**Files:**
- Modify: `src/ansim_review/retrieval/bundle.py`
- Modify: `src/ansim_review/review_question.py`
- Modify: `src/ansim_review/cli.py`
- Modify: `tests/integration/retrieval/test_fts_lexical_channels.py`
- Modify: `tests/integration/review_question/test_review_question_cli.py`

**Interfaces:**
- Produces: `query.attempted_terms` in evidence bundles and an immutable `retrieval-guidance.json` only for authoritative zero-hit formal-review prepares.
- Preserves: empty evidence remains empty; confidence/ABSTAIN semantics are not upgraded by guidance.

- [ ] **Step 1: Add RED bundle test for attempted-term trace on a true no-hit query**

Add:

```python
def test_zero_hit_bundle_reports_attempted_deterministic_terms_without_hits(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        bundle = build_evidence_bundle(
            store.require_connection(),
            {
                "question": "존재하지않는시설 설치기준",
                "synonym_manifest": {},
                "expansions": [],
                "limit": 20,
            },
        )

    assert bundle["hits"] == []
    assert bundle["query"]["primary"] == "존재하지않는시설 설치기준"
    assert bundle["query"]["attempted_terms"]
    assert all(
        item["origin"].startswith("derived:") or item["origin"] == "primary"
        for item in bundle["query"]["attempted_terms"]
    )
```

- [ ] **Step 2: Export deterministic attempted terms from `bundle.py`**

Create a stable ordered list containing:

1. original normalized query terms (`primary`, user/approved/LLM origin if present);
2. compound derived terms;
3. existing entity/numeric/concept terms.

Example:

```python
attempted_terms = [
    {"text": term.text, "origin": term.origin}
    for term in query.terms
]
attempted_terms.extend(
    {"text": term, "origin": "derived:korean_compound"}
    for term in compound_variants
)
```

Append entity/numeric/concept groups with `derived:<group>` origins and stable de-duplication by `(text, origin)`.

Add it under `bundle["query"]["attempted_terms"]`; do not modify `query.primary` or `query.terms`.

- [ ] **Step 3: Extend `PreparedReviewQuestion` with an optional guidance path**

```python
@dataclass(frozen=True, slots=True)
class PreparedReviewQuestion:
    run_id: str
    status: str
    next_action_path: Path | None
    resumed: bool
    retrieval_guidance_path: Path | None
```

Existing callers must be updated explicitly.

- [ ] **Step 4: Write immutable zero-hit guidance only when evidence is empty**

In `prepare_review_question`, after the bundle is built and the run directory exists:

```python
guidance_path: Path | None = None
if not bundle["hits"]:
    attempted = bundle["query"].get("attempted_terms", [])
    if attempted:
        guidance_path = run_directory / "retrieval-guidance.json"
        _write_or_identical(
            guidance_path,
            {
                "format": "evidence-review/retrieval-guidance",
                "version": 1,
                "query": bundle["query"]["primary"],
                "attempted_terms": attempted,
                "authoritative_hit_count": 0,
            },
        )
```

Return `retrieval_guidance_path=guidance_path`.

The review request still contains an empty `evidence` array; existing evidence-dependent confidence factors remain `0.0`.

- [ ] **Step 5: Add formal-review RED/GREEN test proving guidance does not fabricate evidence**

```python
def test_prepare_zero_hit_emits_guidance_but_keeps_authoritative_evidence_empty(
    tmp_path: Path,
) -> None:
    workspace = _korean_workspace(tmp_path / "workspace")[0]
    prepared = prepare_review_question(workspace, "존재하지않는시설 설치기준")
    run_directory = workspace / "runs" / prepared.run_id

    request = json.loads((run_directory / "review-request.json").read_text(encoding="utf-8"))
    guidance = json.loads(
        prepared.retrieval_guidance_path.read_text(encoding="utf-8")
    )

    assert request["evidence"] == []
    assert guidance["authoritative_hit_count"] == 0
    assert guidance["attempted_terms"]
```

Also assert evidence-dependent confidence factors remain `0.0`.

- [ ] **Step 6: Expose only the guidance path in prepare stdout**

Add:

```python
"retrieval_guidance_path": (
    None
    if result.retrieval_guidance_path is None
    else str(result.retrieval_guidance_path)
),
```

Do not dump the query/evidence text into stdout; preserve the existing privacy/minimal-output test.

- [ ] **Step 7: Add no-expansion formal-review regression for the three reported questions**

Parameterize `test_review_question_cli.py` using the Korean workspace:

```python
@pytest.mark.parametrize(
    "question",
    [
        "청소년 문화의집 설치기준",
        "청소년문화의집 설치기준",
        "청소년수련관 설치기준",
    ],
)
def test_reported_korean_question_prepares_with_authoritative_evidence_without_expansion(
    tmp_path: Path,
    question: str,
) -> None:
    workspace, snapshot_hash = _korean_workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, question)
    run_directory = workspace / "runs" / prepared.run_id
    request = json.loads((run_directory / "review-request.json").read_text(encoding="utf-8"))

    assert request["evidence"]
    assert request["inputs"]["snapshot_hash"] == snapshot_hash
    assert prepared.retrieval_guidance_path is None
```

No `expansions` argument is supplied.

- [ ] **Step 8: Run formal-review retrieval integration**

```bash
pytest \
  tests/integration/retrieval/test_fts_lexical_channels.py \
  tests/integration/retrieval/test_korean_formal_review_retrieval.py \
  tests/integration/review_question/test_review_question_cli.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit zero-hit/formal-review integration**

```bash
git add \
  src/ansim_review/retrieval/bundle.py \
  src/ansim_review/review_question.py \
  src/ansim_review/cli.py \
  tests/integration/retrieval/test_fts_lexical_channels.py \
  tests/integration/review_question/test_review_question_cli.py
git commit -m "fix: expose deterministic retrieval guidance"
```

---

### Task 9: Run combined exact-path E2E and add a reproducible browser-acceptance fixture

**Files:**
- Create: `scripts/build_issues_98_101_acceptance_workspace.py`
- Modify: `tests/integration/review_question/test_review_question_cli.py`
- Create: `tests/integration/test_issues_98_101_acceptance_fixture.py`

**Interfaces:**
- Consumes: all completed #99/#101/#100/#98 behavior.
- Produces:
  - one automated E2E proving the same run traverses provenance → retrieval → Track A → run-local Track B → protected handoff contract;
  - a deterministic two-page acceptance workspace builder used by Task 11 without relying on private user files or hand-authored Track JSON.

- [ ] **Step 1: Create a deterministic two-page acceptance-workspace builder**

Create `scripts/build_issues_98_101_acceptance_workspace.py` with two subcommands:

```text
seed --workspace PATH
tracks --workspace PATH --run-id RUN-...
```

The `seed` subcommand creates only deterministic evidence and verified page-image assets. Use these exact authoritative records:

```python
_ELEMENTS = (
    {
        "id": "E-CULTURE-PRIMARY",
        "revision_id": "REV-ACCEPT",
        "page_id": "REV-ACCEPT-P1",
        "page_number": 1,
        "element_type": "clause",
        "raw_json": {
            "text": "청소년문화의집 설치기준은 시설의 목적과 이용자 안전을 함께 검토한다."
        },
        "raw_text": "청소년문화의집 설치기준은 시설의 목적과 이용자 안전을 함께 검토한다.",
        "normalized_text": "청소년문화의집 설치기준은 시설의 목적과 이용자 안전을 함께 검토한다.",
        "raw_payload_hash": "7" * 64,
        "bbox": [40.0, 80.0, 520.0, 140.0],
        "parser_order": 10,
    },
    {
        "id": "E-CULTURE-SECONDARY",
        "revision_id": "REV-ACCEPT",
        "page_id": "REV-ACCEPT-P2",
        "page_number": 2,
        "element_type": "clause",
        "raw_json": {
            "text": "청소년문화의집 설치기준에는 독립된 활동공간의 확보가 포함된다."
        },
        "raw_text": "청소년문화의집 설치기준에는 독립된 활동공간의 확보가 포함된다.",
        "normalized_text": "청소년문화의집 설치기준에는 독립된 활동공간의 확보가 포함된다.",
        "raw_payload_hash": "8" * 64,
        "bbox": [50.0, 120.0, 530.0, 180.0],
        "parser_order": 20,
    },
)
```

Build the evidence database with:

```python
snapshot = EvidenceSnapshot(
    documents=({"id": "DOC-ACCEPT", "title": "청소년수련시설 기준"},),
    revisions=(
        {
            "id": "REV-ACCEPT",
            "document_id": "DOC-ACCEPT",
            "source_hash": "9" * 64,
            "byte_size": 100,
            "page_count": 2,
        },
    ),
    pages=(
        {
            "id": "REV-ACCEPT-P1",
            "revision_id": "REV-ACCEPT",
            "page_number": 1,
            "width": 595.0,
            "height": 842.0,
        },
        {
            "id": "REV-ACCEPT-P2",
            "revision_id": "REV-ACCEPT",
            "page_number": 2,
            "width": 595.0,
            "height": 842.0,
        },
    ),
    elements=_ELEMENTS,
)
```

Create `<workspace>/evidence/evidence.sqlite`, call `ingest_snapshot(...)`, then `build_fts_index(...)`.

Create real 595×842 PNG assets with Pillow:

```python
from PIL import Image

for page_number in (1, 2):
    directory = workspace / "page-images" / "REV-ACCEPT"
    directory.mkdir(parents=True, exist_ok=True)
    image_path = directory / f"page-{page_number:04d}.png"
    Image.new("RGB", (595, 842), "white").save(image_path, format="PNG")
    image_bytes = image_path.read_bytes()
    metadata = {
        "format": "ansim/page-image",
        "version": 1,
        "revision_id": "REV-ACCEPT",
        "page_number": page_number,
        "source_hash": "9" * 64,
        "pdf_width": 595.0,
        "pdf_height": 842.0,
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
    }
    (directory / f"page-{page_number:04d}.json").write_bytes(dump_bytes(metadata))
```

The `seed` command refuses to overwrite an existing `evidence.sqlite` or existing page-image asset.

- [ ] **Step 2: Implement deterministic Track A/B generation from the prepared run**

The `tracks` subcommand reads `<workspace>/runs/<run-id>/track-a-bundle.json`. Require at least two evidence entries on distinct page numbers:

```python
bundle = json.loads(
    (run_directory / "track-a-bundle.json").read_text(encoding="utf-8")
)
evidence = bundle["evidence"]
if len(evidence) < 2:
    raise ValueError("acceptance fixture requires at least two citations")
if evidence[0]["citation"]["page_number"] == evidence[1]["citation"]["page_number"]:
    raise ValueError("acceptance fixture requires citations on distinct pages")
```

Write canonical run-local Track A:

```python
first = evidence[0]
second = evidence[1]
first_id = first["citation"]["citation_id"]
second_id = second["citation"]["citation_id"]

track_a = {
    "run_id": run_id,
    "claims": [
        {
            "claim_id": "CL-PRIMARY",
            "text": first["text"],
            "citation_ids": [first_id],
            "numeric_tokens": [],
            "calculation_result_ids": [],
            "rule_references": [],
        },
        {
            "claim_id": "CL-SECONDARY",
            "text": second["text"],
            "citation_ids": [second_id],
            "numeric_tokens": [],
            "calculation_result_ids": [],
            "rule_references": [],
        },
        {
            "claim_id": "CL-MULTI",
            "text": "두 근거를 함께 검토한다.",
            "citation_ids": [first_id, second_id],
            "numeric_tokens": [],
            "calculation_result_ids": [],
            "rule_references": [],
        },
    ],
    "citations": [first_id, second_id],
    "missing_inputs": [],
    "exceptions": [],
    "conflicts": [],
    "explanation": "브라우저 수용성 검증을 위한 결정론 Track A fixture.",
}
(run_directory / "acceptance-track-a.json").write_bytes(dump_bytes(track_a))
```

Do not write run-local `track-b-output.json` yet. Print the Track A path as canonical JSON:

```python
print(json.dumps({"track_a": str(run_directory / "acceptance-track-a.json")}))
```

After Track A has been submitted through the public CLI, run `tracks` again with `--write-track-b`. In that mode require canonical `track-a-output.json` to exist, then write:

```python
track_b = {
    "run_id": run_id,
    "claim_audits": [
        {
            "claim_id": claim_id,
            "disposition": "ACCEPT",
            "finding_codes": [],
            "notes": "",
        }
        for claim_id in ("CL-PRIMARY", "CL-SECONDARY", "CL-MULTI")
    ],
    "overall_disposition": "ACCEPT",
}
(run_directory / "track-b-output.json").write_bytes(dump_bytes(track_b))
```

Use argparse so the exact command is:

```powershell
py -3.13 scripts\build_issues_98_101_acceptance_workspace.py tracks `
  --workspace $AcceptanceWorkspace `
  --run-id $RunId `
  --write-track-b
```

- [ ] **Step 3: Test the acceptance fixture builder through subprocesses**

Create `tests/integration/test_issues_98_101_acceptance_fixture.py`.

Run `seed` in a temporary workspace, then invoke the public CLI:

```python
prepare = subprocess.run(
    [
        sys.executable,
        "-m",
        "evidence_review",
        "review-question",
        "prepare",
        "--workspace",
        str(workspace),
        "--question",
        "청소년문화의집 설치기준",
    ],
    cwd=repo,
    text=True,
    capture_output=True,
    check=False,
)
assert prepare.returncode == 0
prepared = json.loads(prepare.stdout)
assert prepared["status"] == "WAITING_TRACK_A"
```

Run the builder's `tracks` mode, submit the emitted Track A with:

```python
submit_a = subprocess.run(
    [
        sys.executable,
        "-m",
        "evidence_review",
        "review-question",
        "submit-track-a",
        "--workspace",
        str(workspace),
        "--run-id",
        prepared["run_id"],
        "--track-a-output",
        str(run_directory / "acceptance-track-a.json"),
    ],
    cwd=repo,
    text=True,
    capture_output=True,
    check=False,
)
assert submit_a.returncode == 0
```

Run `tracks --write-track-b`, then assert the canonical run-local `track-b-output.json` validates and can finalize.

This test prevents the manual-browser fixture from drifting away from the public CLI contracts.

- [ ] **Step 4: Add one integrated formal-review test without opening a real browser**

In `tests/integration/review_question/test_review_question_cli.py`, use the existing Korean fixture helpers and monkeypatch `open_review_run` only at the final display boundary.

The test sequence must exercise:

```python
prepared = prepare_review_question(
    workspace,
    "청소년문화의집 설치기준",
)
assert prepared.status == "WAITING_TRACK_A"

submitted_a = submit_question_track_a(
    workspace,
    prepared.run_id,
    track_a_path,
)
assert submitted_a.next_action_path.is_file()

run_directory = workspace / "runs" / prepared.run_id
run_local_b = run_directory / "track-b-output.json"
run_local_b.write_bytes(track_b_bytes)

finalized = submit_question_track_b(
    workspace,
    prepared.run_id,
    run_local_b,
)
assert finalized.packet.status == "READY_FOR_HUMAN_REVIEW"
assert finalized.review_html.is_file()
```

Then exercise the CLI `--open` projection with `open_review_run` returning a protected loopback URL and assert `review_html`, `display_status="OPENED"`, and the URL are returned.

- [ ] **Step 5: Assert authority invariants from retrieval through final packet**

Capture before Track work:

```python
evidence_query = json.loads(
    (run_directory / "evidence-query.json").read_text(encoding="utf-8")
)
expected_snapshot = evidence_query["snapshot_hash"]
expected_citations = {
    hit["citation"]["citation_id"]: hit["citation"]
    for hit in evidence_query["hits"]
    if hit["citation"] is not None
}
```

After finalization:

```python
request = json.loads(
    (run_directory / "review-request.json").read_text(encoding="utf-8")
)
assert request["inputs"]["snapshot_hash"] == expected_snapshot

for item in request["evidence"]:
    citation = item["citation"]
    authoritative = expected_citations[citation["citation_id"]]
    assert citation["source_hash"] == authoritative["source_hash"]
    assert citation["page_number"] == authoritative["page_number"]
    assert citation["bbox"] == authoritative["bbox"]
    assert citation["evidence_id"] == authoritative["evidence_id"]
```

Also assert run-local `track-b-output.json` bytes are unchanged after successful finalization.

- [ ] **Step 6: Run the integrated test, acceptance-fixture test, and all four focused issue suites**

```bash
pytest \
  tests/unit/test_cli_diagnostics.py \
  tests/integration/packaging/test_cli_runtime_provenance.py \
  tests/unit/retrieval/test_korean_variants.py \
  tests/integration/retrieval/test_fts_lexical_channels.py \
  tests/integration/retrieval/test_fts_retrieval.py \
  tests/integration/retrieval/test_hybrid_fusion.py \
  tests/integration/retrieval/test_korean_formal_review_retrieval.py \
  tests/integration/review_run/test_review_run.py \
  tests/integration/review_question/test_review_question_cli.py \
  tests/integration/review_packet/test_review_workspace_ui.py \
  tests/integration/review_packet/test_review_visual_contract.py \
  tests/integration/test_issues_98_101_acceptance_fixture.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit integrated E2E and the reproducible acceptance fixture**

```bash
git add \
  scripts/build_issues_98_101_acceptance_workspace.py \
  tests/integration/review_question/test_review_question_cli.py \
  tests/integration/test_issues_98_101_acceptance_fixture.py
git commit -m "test: cover issues 98 through 101 end to end"
```

No tracked acceptance-result document is written after this point. Final test evidence is stored under ignored/untracked `test-results/` and posted to PR #102 so the evidence can name the exact tested HEAD without creating a new HEAD.

---

### Task 10: Run full repository validation on the exact final tracked HEAD

**Files:**
- Create untracked: `test-results/issues-98-101/acceptance.md`
- Do not modify tracked files after the candidate HEAD is frozen.

**Interfaces:**
- Consumes: candidate HEAD after Task 9's tracked commit.
- Produces: interpreter-specific automated acceptance evidence without changing git HEAD.

- [ ] **Step 1: Freeze and record the candidate HEAD**

PowerShell:

```powershell
$CandidateHead = (git rev-parse HEAD).Trim()
$StatusBefore = git status --short
if ($StatusBefore) { throw "Tracked/unignored worktree is not clean: $StatusBefore" }
New-Item -ItemType Directory -Force test-results\issues-98-101 | Out-Null
@"
PR: #102
Candidate HEAD: $CandidateHead
Automated status: RUNNING
"@ | Set-Content -Encoding utf8 test-results\issues-98-101\acceptance.md
```

`test-results/` must be ignored/untracked. Verify:

```powershell
git check-ignore test-results\issues-98-101\acceptance.md
if ($LASTEXITCODE -ne 0) { throw "acceptance output is not ignored" }
```

- [ ] **Step 2: Run `doctor` under Python 3.11 and record JSON**

```powershell
$Doctor311 = py -3.11 -m evidence_review doctor --repository-root .
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 doctor failed" }
$Doctor311 | Set-Content -Encoding utf8 test-results\issues-98-101\doctor-py311.json
$Doctor311Document = $Doctor311 | ConvertFrom-Json
if ($Doctor311Document.status -ne "OK") { throw "Python 3.11 provenance is not OK" }
if ($Doctor311Document.repository_head -ne $CandidateHead) { throw "Python 3.11 HEAD mismatch" }
if (-not $Doctor311Document.package_checkout_match) { throw "Python 3.11 package checkout mismatch" }
```

- [ ] **Step 3: Run `doctor` under Python 3.13 and record JSON**

```powershell
$Doctor313 = py -3.13 -m evidence_review doctor --repository-root .
if ($LASTEXITCODE -ne 0) { throw "Python 3.13 doctor failed" }
$Doctor313 | Set-Content -Encoding utf8 test-results\issues-98-101\doctor-py313.json
$Doctor313Document = $Doctor313 | ConvertFrom-Json
if ($Doctor313Document.status -ne "OK") { throw "Python 3.13 provenance is not OK" }
if ($Doctor313Document.repository_head -ne $CandidateHead) { throw "Python 3.13 HEAD mismatch" }
if (-not $Doctor313Document.package_checkout_match) { throw "Python 3.13 package checkout mismatch" }
```

Append both JSON documents to the acceptance evidence.

- [ ] **Step 4: Run full pytest under Python 3.11**

```powershell
py -3.11 -m pytest -v 2>&1 | Tee-Object test-results\issues-98-101\pytest-py311.log
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 pytest failed" }
```

Record exact passed/skipped counts from the log.

- [ ] **Step 5: Run full pytest under Python 3.13**

```powershell
py -3.13 -m pytest -v 2>&1 | Tee-Object test-results\issues-98-101\pytest-py313.log
if ($LASTEXITCODE -ne 0) { throw "Python 3.13 pytest failed" }
```

Record exact passed/skipped counts.

- [ ] **Step 6: Run Ruff**

```powershell
py -3.11 -m ruff check . 2>&1 | Tee-Object test-results\issues-98-101\ruff.log
if ($LASTEXITCODE -ne 0) { throw "Ruff failed" }
```

- [ ] **Step 7: Run mypy**

```powershell
py -3.11 -m mypy 2>&1 | Tee-Object test-results\issues-98-101\mypy.log
if ($LASTEXITCODE -ne 0) { throw "mypy failed" }
```

Record the source-file count reported by mypy.

- [ ] **Step 8: Run compileall on both interpreters**

```powershell
py -3.11 -m compileall -q src web_runtime
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 compileall failed" }

py -3.13 -m compileall -q src web_runtime
if ($LASTEXITCODE -ne 0) { throw "Python 3.13 compileall failed" }
```

- [ ] **Step 9: Run documentation integrity on both interpreters**

```powershell
py -3.11 -m evidence_review documentation validate `
  --repository-root . `
  --config documentation-integrity.json `
  --output test-results\issues-98-101\docs-py311.json
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 documentation integrity failed" }

py -3.13 -m evidence_review documentation validate `
  --repository-root . `
  --config documentation-integrity.json `
  --output test-results\issues-98-101\docs-py313.json
if ($LASTEXITCODE -ne 0) { throw "Python 3.13 documentation integrity failed" }
```

Expected for both:

- status PASS;
- errors `0`;
- warning count recorded exactly.

- [ ] **Step 10: Run intentional stale-source smoke on both interpreters through the committed subprocess tests**

```powershell
py -3.11 -m pytest tests/integration/packaging/test_cli_runtime_provenance.py -v `
  2>&1 | Tee-Object test-results\issues-98-101\provenance-py311.log
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 provenance smoke failed" }

py -3.13 -m pytest tests/integration/packaging/test_cli_runtime_provenance.py -v `
  2>&1 | Tee-Object test-results\issues-98-101\provenance-py313.log
if ($LASTEXITCODE -ne 0) { throw "Python 3.13 provenance smoke failed" }
```

These tests must include `SOURCE_MISMATCH` and `DEPENDENCY_MISSING` scenarios without modifying the installed developer environment.

- [ ] **Step 11: Confirm acceptance outputs did not dirty the repository**

```powershell
$HeadAfter = (git rev-parse HEAD).Trim()
if ($HeadAfter -ne $CandidateHead) { throw "HEAD changed during acceptance" }

$StatusAfter = git status --short
if ($StatusAfter) { throw "Acceptance generated tracked/unignored changes: $StatusAfter" }
```

- [ ] **Step 12: Write the automated result into the untracked acceptance evidence**

Append:

```text
Automated status: PASS
Python 3.11: PASS
Python 3.13: PASS
Full pytest counts: recorded from logs
Ruff: PASS
mypy: PASS
compileall: PASS
Documentation integrity: PASS, errors=0 for both interpreters
SOURCE_MISMATCH smoke: PASS
DEPENDENCY_MISSING smoke: PASS
Browser status: PENDING
```

Do not create a git commit after this step.

---

### Task 11: Perform real-browser acceptance and publish exact-HEAD evidence

**Files:**
- Modify untracked: `test-results/issues-98-101/acceptance.md`
- Do not modify tracked files.

**Interfaces:**
- Consumes: exact automated-PASS HEAD from Task 10, a fresh acceptance workspace outside tracked source paths, existing protected loopback server.
- Produces: final PASS/FAIL evidence posted to PR #102 without changing the tested HEAD.

- [ ] **Step 1: Create a deterministic acceptance workspace path outside the tracked repository content**

PowerShell:

```powershell
$CandidateHead = (git rev-parse HEAD).Trim()
$AcceptanceWorkspace = Join-Path $env:TEMP "evidence-review-issues-98-101-$CandidateHead"
if (Test-Path $AcceptanceWorkspace) {
    Remove-Item -Recurse -Force $AcceptanceWorkspace
}
New-Item -ItemType Directory -Force $AcceptanceWorkspace | Out-Null
```

Populate it only with the committed deterministic acceptance builder:

```powershell
py -3.13 scripts\build_issues_98_101_acceptance_workspace.py seed `
  --workspace $AcceptanceWorkspace
if ($LASTEXITCODE -ne 0) { throw "acceptance workspace seed failed" }

if (-not (Test-Path (Join-Path $AcceptanceWorkspace "evidence\evidence.sqlite"))) {
    throw "acceptance evidence database missing"
}
```

Do not copy generated workspace data into the repository.

- [ ] **Step 2: Run provenance immediately before the browser run**

```powershell
$Doctor = py -3.13 -m evidence_review doctor --repository-root .
if ($LASTEXITCODE -ne 0) { throw "doctor failed before browser acceptance" }
$DoctorDocument = $Doctor | ConvertFrom-Json
if ($DoctorDocument.status -ne "OK" -or $DoctorDocument.repository_head -ne $CandidateHead) {
    throw "browser acceptance is not using the candidate checkout"
}
```

- [ ] **Step 3: Prepare the real Korean formal-review question without user expansion**

Run:

```powershell
$PrepareJson = py -3.13 -m evidence_review review-question prepare `
  --workspace $AcceptanceWorkspace `
  --question "청소년문화의집 설치기준"
if ($LASTEXITCODE -ne 0) { throw "formal review prepare failed" }

$Prepare = $PrepareJson | ConvertFrom-Json
if ($Prepare.status -ne "WAITING_TRACK_A") { throw "unexpected prepare status" }
$RunId = $Prepare.run_id
```

Create deterministic Track A from the prepared bundle, submit it through the public CLI, then create Track B at the canonical run-local path:

```powershell
$RunDirectory = Join-Path (Join-Path $AcceptanceWorkspace "runs") $RunId

$TrackFixtureJson = py -3.13 scripts\build_issues_98_101_acceptance_workspace.py tracks `
  --workspace $AcceptanceWorkspace `
  --run-id $RunId
if ($LASTEXITCODE -ne 0) { throw "Track A fixture generation failed" }
$TrackFixture = $TrackFixtureJson | ConvertFrom-Json

$SubmitAJson = py -3.13 -m evidence_review review-question submit-track-a `
  --workspace $AcceptanceWorkspace `
  --run-id $RunId `
  --track-a-output $TrackFixture.track_a
if ($LASTEXITCODE -ne 0) { throw "Track A submission failed" }
$SubmitA = $SubmitAJson | ConvertFrom-Json
if ($SubmitA.status -ne "WAITING_TRACK_B") { throw "unexpected Track A status" }

py -3.13 scripts\build_issues_98_101_acceptance_workspace.py tracks `
  --workspace $AcceptanceWorkspace `
  --run-id $RunId `
  --write-track-b
if ($LASTEXITCODE -ne 0) { throw "Track B fixture generation failed" }

$RunLocalTrackB = Join-Path $RunDirectory "track-b-output.json"
if (-not (Test-Path $RunLocalTrackB)) { throw "run-local Track B missing" }
```

Do not use an external Track B path for this acceptance case.

- [ ] **Step 4: Finalize and open through the protected handoff**

```powershell
$OpenJson = py -3.13 -m evidence_review review-question submit-track-b `
  --workspace $AcceptanceWorkspace `
  --run-id $RunId `
  --track-b-output $RunLocalTrackB `
  --open
if ($LASTEXITCODE -ne 0) { throw "submit-track-b --open failed" }

$Open = $OpenJson | ConvertFrom-Json
if ($Open.status -ne "READY_FOR_HUMAN_REVIEW") { throw "unexpected final status" }
if ($Open.display_status -ne "OPENED") { throw "protected browser did not open" }
if (-not (Test-Path $Open.review_html)) { throw "review_html missing" }
if (-not $Open.url.StartsWith("http://127.0.0.1:")) { throw "non-loopback review URL" }
```

The command must return promptly; it must not wait for the detached server to terminate.

- [ ] **Step 5: Validate review-item → first citation → PDF page/bbox at 1366×768**

In a real headed browser:

1. set viewport/window to 1366×768;
2. activate review item 1 and record current page/evidence ID;
3. activate an item whose first citation is on another page;
4. verify the viewer changes to that page;
5. verify that citation's bbox overlay has focused styling;
6. verify rail selection/detail panel match the same item.

Record only run ID, item IDs, evidence IDs, and page numbers; do not copy source text into acceptance evidence.

- [ ] **Step 6: Validate multiple citations**

For the `CL-MULTI` item created by the acceptance fixture:

1. activate the item;
2. verify its first valid citation is focused by default;
3. activate the second citation directly;
4. verify the selected review item remains `CL-MULTI`;
5. verify page/bbox follows the second citation.

- [ ] **Step 7: Validate keyboard parity**

Using Tab/Shift+Tab and Enter/Space only:

- activate a review item;
- activate a citation/evidence link;
- verify the same page/bbox transitions as mouse input;
- verify visible focus remains present.

- [ ] **Step 8: Validate 200% zoom**

At browser zoom 200%:

- review rail remains usable;
- current detail remains reachable;
- evidence viewer controls remain reachable;
- activating a different item still changes page/bbox;
- no required control is clipped without a scroll path.

- [ ] **Step 9: Validate print**

Use print preview and verify:

- question/result/evidence/decision content is present;
- detail panels needed for print are revealed;
- protected-only controls that should not appear in the archive are excluded as intended;
- returning from print restores the pre-print tab visibility state.

- [ ] **Step 10: Validate display-failure semantics from the committed automated test evidence**

Confirm the Task 10 logs include the explicit opener-failure regression proving:

- packet and HTML remain finalized;
- `display_status = OPEN_FAILED`;
- `review_html` is returned;
- finalization status is not rewritten as failure.

Do not damage or disable the user's real browser installation to force this scenario manually.

- [ ] **Step 11: Reconfirm exact HEAD and clean tracked tree after browser acceptance**

```powershell
$HeadAfterBrowser = (git rev-parse HEAD).Trim()
if ($HeadAfterBrowser -ne $CandidateHead) { throw "HEAD changed during browser acceptance" }

$StatusAfterBrowser = git status --short
if ($StatusAfterBrowser) { throw "browser acceptance changed tracked/unignored files: $StatusAfterBrowser" }
```

- [ ] **Step 12: Finalize the untracked acceptance evidence**

If every gate passed, append:

```text
Final status: PASS — READY FOR REVIEW
1366×768: PASS
200% zoom: PASS
Keyboard activation: PASS
Multiple citations: PASS
PDF first-citation page/bbox focus: PASS
Print: PASS
Protected handoff: PASS
Run-local Track B: PASS
Korean no-expansion retrieval: PASS
Exact tested HEAD: unchanged from Task 10
```

If any gate failed, append:

```text
Final status: FAIL — DO NOT MARK READY
```

plus the exact failed gate and observable failure.

- [ ] **Step 13: Post the exact-HEAD acceptance evidence to PR #102**

Use the GitHub connector when executing interactively. If the execution environment only exposes `gh`, run:

```powershell
gh pr comment 102 --repo sage1993/evidence-review-system `
  --body-file test-results\issues-98-101\acceptance.md
```

The posted PR comment is the durable exact-HEAD acceptance record. Posting the comment does not alter git HEAD.

- [ ] **Step 14: Change PR #102 from Draft to Ready only after the PASS comment exists**

Verify:

- PR comment names the same `$CandidateHead`;
- repository HEAD remains unchanged;
- all four issues remain open until review/merge policy permits closure.

Then mark PR #102 Ready for review. Do not merge and do not close #98–#101 in this task unless separately instructed.

---

## Completion criteria

PR #102 may move from Draft to Ready for review only when all of the following are true at one exact HEAD:

- branch contains current `main`;
- `doctor` proves checkout/package/dependency provenance;
- stale source is blocked before business logic;
- missing dependencies produce `DEPENDENCY_MISSING` without traceback;
- valid run-local Track B finalizes without rewriting;
- identical retry succeeds;
- differing retry fails before finalizer execution;
- interrupted finalization preserves validated Track B;
- Korean compound/exact queries retrieve authoritative evidence without user expansion;
- original query origin and snapshot lineage remain intact;
- English/numeric retrieval remains compatible;
- `review-question submit-track-b --open` returns `review_html` and protected display outcome;
- review-item/citation/keyboard routes use non-recursive orchestration;
- item activation focuses first citation page/bbox;
- multiple citations behave coherently;
- zero-hit guidance does not fabricate authority or suppress legitimate ABSTAIN behavior;
- full pytest, Ruff, mypy, compileall, and documentation integrity pass;
- Windows Python 3.11 and 3.13 gates pass;
- real browser 1366×768, 200% zoom, keyboard, multiple citation, PDF page/bbox, and print gates pass;
- final acceptance record names the exact tested HEAD.

Do not close #98, #99, #100, or #101 and do not mark PR #102 Ready for review before these criteria pass.
