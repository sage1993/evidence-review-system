# Evidence Review System

Evidence Review System (ERS) is an **offline, evidence-first document review runtime** for turning user-provided PDFs into traceable local evidence and running every question through a formal review pipeline.

The project is designed for cases where a result must remain tied to the original document, page, coordinates, deterministic calculations/rules, and an explicit human decision rather than a free-form model answer.

## What it does

```text
PDF
→ immutable parser artifacts
→ source/hash binding
→ evidence.sqlite
→ deterministic retrieval
→ formal review request
→ Track A
→ independent Track B audit
→ immutable final-review-packet.json
→ Review Workspace
→ separate append-only human decision
```

The runtime does not make the final human decision. `READY_FOR_HUMAN_REVIEW` means that the evidence package is ready to inspect; it does **not** mean approved, compliant, or correct.

## Core design principles

- **Evidence first:** preserve the original source bytes, source hash, document/revision/page identity, and bbox/geometry provenance.
- **Deterministic authority:** parser records, retrieval, Math Engine results, and approved Rule Engine results are validated before review output is accepted.
- **Independent review tracks:** Track A explains the evidence; Track B audits the validated Track A claims.
- **Human final decision:** machine output remains immutable and human decisions are stored separately as append-only packet-bound records.
- **Fail closed:** missing parser output, stale artifacts, unsafe paths, hash mismatches, invalid rule authority, or release-validation failures stop the workflow.
- **Offline runtime:** project/runtime code requires no remote model/API service. The protected Review Workspace uses loopback communication only.

## Requirements

- Python `>=3.13,<3.14`
- Windows is the primary acceptance platform for protected-browser and Review Workspace behavior.
- Codex Desktop is the intended assisted workflow for `$ERS_PDF` / `$ERS_REVIEW`, but the deterministic runtime and CLI are ordinary local Python code.
- A supported local parser such as OpenDataLoader PDF is required before parser-dependent evidence can be evaluated.

Runtime dependencies are declared in `pyproject.toml`.

## Installation

```powershell
git clone https://github.com/sage1993/evidence-review-system.git
Set-Location evidence-review-system
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

For development and validation:

```powershell
python -m pip install -e ".[dev]"
```

Runtime dependencies are pinned to pypdf>=5,<6, pypdfium2>=5.12,<6, and Pillow>=12,<13.

Canonical entrypoints:

```text
evidence-review --help
python -m evidence_review --help
```

The legacy `ansim-review` name may remain temporarily as a compatibility entrypoint during the `v0.2.0` transition, but `evidence_review` is the canonical public namespace.

## Quick start

Codex Desktop users normally use two shortcuts:

```text
$ERS_PDF 이 PDF 파싱해줘
$ERS_REVIEW <검토 질문>
```

### 1. Prepare PDF evidence

`$ERS_PDF` preserves the source, validates parser/source binding, checks parser warnings/reproducibility, builds source-batch v2, creates searchable `evidence.sqlite`, and prepares verified revision page-image cache artifacts.

Source preparation is not considered successful while required parser output or drawing confirmation is missing.

### 2. Run a formal question

All questions use the formal review flow; there is no separate quick-answer mode.

```text
question
→ local evidence retrieval
→ review request
→ Track A output + validation
→ Track B audit + validation
→ final review packet
→ Review Workspace
→ human decision
```

Lower-level CLI commands are documented in [Codex Workflow](docs/CODEX_WORKFLOW.md) and [Reviewer Workflow](docs/REVIEWER_WORKFLOW.md).

## Review Workspace

The default reviewer surface prioritizes non-developer information:

1. **검토 결과** — status and concise conclusion
2. **판단 근거** — source text/page/bbox and verified page image
3. **추가 확인** — only when missing/conflicting/exception items exist
4. **검토자 의견** — decision and notes

Internal IDs, hashes, confidence factors, and other audit details are retained but should not dominate the default UI.

`review.html` is the standalone archival presentation. Protected localhost mode additionally allows packet-bound append-only human decision persistence.

## Trust and security boundaries

ERS separates:

- application-level offline guard;
- optional OS-level network isolation;
- source/evidence integrity;
- protected loopback browser security;
- human review decisions;
- release process attestation and release-output validation.

Passing one boundary does not imply another. For example, a human release attestation cannot override a failed release ZIP/hash validation.

See [Offline Execution Boundary](docs/OFFLINE_EXECUTION.md) and [Security Policy](SECURITY.md).

## Repository structure

The active tree is intended to contain only current runtime/product/developer material or clearly scoped deterministic fixtures.

```text
src/               Python runtime
web_runtime/       installation-free web runtime bootstrap
schemas/           machine-readable contracts
tests/fixtures/    deterministic ANSIM compatibility and rule fixtures
tests/             unit/integration/golden fixtures
skills/            ERS Codex workflow skills
docs/              current architecture/workflow/governance docs
scripts/           current operational/developer scripts only
```

Historical issue-specific acceptance output does not need to remain in the active tree because Git history and GitHub Issue/PR history already preserve it.

## Development

Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.

Minimum exact-HEAD validation for the current Python 3.13 support policy:

```powershell
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
py -3.13 -m evidence_review documentation validate --repository-root .
```

Packaging/release changes also require wheel/runtime smoke tests. Review Workspace changes require real-browser acceptance; static tests are not a substitute for UI/interaction validation.

If a validation step was not executed, report it as `NOT_RUN` rather than inferring PASS. GitHub Actions availability is tracked separately from reproducible local/manual validation.

## Documentation

- [Codex workflow](docs/CODEX_WORKFLOW.md)
- [Reviewer workflow](docs/REVIEWER_WORKFLOW.md)
- [Offline execution boundary](docs/OFFLINE_EXECUTION.md)
- [Manual acceptance policy](docs/MANUAL_ACCEPTANCE_POLICY.md)
- [Source Batch v2](docs/SOURCE_BATCH_V2.md)
- [Rule activation governance](docs/RULE_ACTIVATION_GOVERNANCE.md)
- [Parser reproducibility](docs/PARSER_REPRODUCIBILITY.md)
- [ERS skills](skills/README.md)
- [Changelog](CHANGELOG.md)

## Contributing and security

- Contributions: [CONTRIBUTING.md](CONTRIBUTING.md)
- Vulnerability reporting: [SECURITY.md](SECURITY.md)

Do not commit proprietary/customer PDFs, parser output derived from restricted documents, user evidence databases, page-image caches, human-decision records, credentials, tokens, private URLs, or private keys.

## Releases

`v0.1.0` is the historical sanitized source-only release. The current public-readiness work targets `v0.2.0`, including repository cleanup, Python 3.13-only support, namespace/CLI consolidation, Review Workspace fixes, runtime-manifest hardening, and reproducible release artifacts.

Release assets should be produced from an accepted exact HEAD and published with SHA-256 values. Generated user workspaces and historical acceptance artifacts are not release assets.

## License

Evidence Review System is licensed under the [Apache License 2.0](LICENSE). Third-party notices remain subject to their own applicable licenses.
