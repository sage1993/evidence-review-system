# Contributing to Evidence Review System

Evidence Review System is an evidence-first, offline review runtime. Contributions are welcome when they preserve deterministic provenance, fail-closed validation, and the separation between machine review output and final human decisions.

## Supported development environment

- Python `>=3.13,<3.14`
- Windows is the primary acceptance platform for browser/review-workspace behavior.
- Runtime behavior must not add a remote API, CDN, telemetry service, or model dependency.

Create an isolated environment and install the development dependencies:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Before changing code

1. Search existing issues and pull requests.
2. For behavior changes, add or update tests first.
3. Keep source PDFs, parser outputs, evidence databases, page-image caches, customer data, and human-decision records outside the repository.
4. Do not weaken source-hash, rule, page-image, manifest, release, or packet validation to make a test pass.
5. Keep the canonical public namespace and CLI under `evidence_review` / `evidence-review`.

## Development workflow

Use a focused branch and keep commits reviewable. A pull request should explain:

- the problem being solved;
- the relevant issue(s);
- the security/provenance implications;
- tests added or changed;
- exact validation commands actually executed;
- manual browser validation when UI behavior changes.

Do not report unexecuted validation as PASS. Use `NOT_RUN` with a reason.

## Validation

From a clean checkout at the exact candidate HEAD:

```powershell
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
py -3.13 -m evidence_review documentation validate --repository-root .
```

Changes to packaging/release behavior must also build and smoke-test the wheel and web runtime bundle. Changes to the Review Workspace require real-browser verification in addition to static tests.

GitHub Actions is useful when available, but it is not the sole release truth. Reproducible manual validation is acceptable when Actions is unavailable, provided the exact HEAD, Python version, OS, commands, and results are recorded.

## Test data

Tests must use deterministic, redistributable fixtures. Never commit:

- proprietary or customer PDFs;
- parser output derived from restricted source material;
- user evidence databases;
- extracted page images from restricted documents;
- credentials, tokens, private URLs, or private keys;
- real human-decision records.

If a fixture is necessary, minimize it and document why redistribution is permitted.

## Review architecture constraints

Contributions must preserve these boundaries:

1. preserved source bytes/hash are authoritative;
2. parser/evidence records are deterministic;
3. retrieval, Math Engine, and Rule Engine outputs are deterministic inputs to review;
4. Track A and Track B are validated handoffs, not authority to invent evidence;
5. `final-review-packet.json` is immutable machine output;
6. human decisions are separate append-only records.

`READY_FOR_HUMAN_REVIEW` never means approved or compliant.

## Pull requests

Keep one logical change per PR where practical. The public-readiness `v0.2.0` effort is intentionally integrated because repository cleanup, namespace migration, packaging, and release contracts overlap; that is not a precedent for unrelated mega-PRs.

Reviewers may request focused commits, additional regression tests, security hardening, or exact-HEAD revalidation before merge.

## License

A project license will be committed only after the repository owner makes an explicit license choice. Until then, contribution acceptance does not imply a particular open-source license grant.
