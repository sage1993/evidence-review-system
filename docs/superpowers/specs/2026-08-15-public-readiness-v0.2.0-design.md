# Evidence Review System Public Readiness v0.2.0 Design

**Status:** Approved design baseline

**Target branch:** `release/public-readiness-v0.2.0`

**Baseline:** `main` at `73d0a37c2a4619ea5297766c814549931ab0e6f7`

**Target release:** `v0.2.0`

**Issues covered:** #105, #106, #107, #108, #109, #110

## 1. Goal

Convert the current private, owner-oriented repository into a repository that can be made public and used for external collaboration without carrying unnecessary historical artifacts into the active source tree.

The completion standard is not only “all tests pass.” An external contributor must be able to:

1. understand what Evidence Review System is from the repository root;
2. clone and install it using the documented supported environment;
3. identify the canonical Python namespace and CLI;
4. run the documented validation gates;
5. understand how to report bugs, propose changes, and submit pull requests;
6. distinguish current product/runtime material from historical acceptance evidence;
7. build and verify the current release artifacts;
8. use the Review Workspace without misleading provenance, persisted-decision ambiguity, or unnecessary protected-browser payload cost.

## 2. Delivery model

All six open issues are delivered through one Draft PR from:

```text
release/public-readiness-v0.2.0
```

to:

```text
main
```

The PR is intentionally integrated because repository cleanup, namespace migration, CLI consolidation, documentation, packaging, and release metadata have cross-cutting references. However, the PR must be composed of independently reviewable commits so a regression can be isolated or reverted without discarding the whole release-preparation effort.

The PR stays Draft until the full exact-HEAD release gate is complete.

## 3. Scope and ordering

The implementation order is fixed to reduce rewrite and merge-conflict risk.

### Phase A — Active-tree cleanup (#106)

Remove or relocate material that does not belong in the active public source tree.

Cleanup policy:

```text
Needed by current runtime/product?
  yes -> keep
  no  -> needed by automated tests/examples?
           yes -> move to a clearly named fixture/example location
           no  -> delete from active tree; Git history and Issue/PR history remain the archive
```

High-confidence cleanup candidates include:

- historical `docs/acceptance/issue-*` records that no longer participate in a current validation contract;
- issue-specific acceptance builders and manual scripts such as `scripts/build_issues_98_101_acceptance_workspace.py` and `scripts/verify_issue_6_manual.ps1`;
- Grist-only documentation, scripts, and numbered legacy skills if Grist is no longer a supported product path;
- ANSIM-named release/migration wrappers after equivalent generic functionality is established;
- legacy documentation whose corresponding compatibility feature is removed in the same PR.

`rules/`, schemas, parser reproducibility contracts, current golden/fixture resources, and release-integrity material are not deleted merely because they are old. Anything participating in current runtime path/hash validation remains until its replacement is implemented and verified.

### Phase B — Canonical namespace and CLI (#106 + #110)

Move the implementation toward one canonical namespace:

```text
src/evidence_review/
```

instead of the current split where `evidence_review` is the public facade while implementation/package-data still lives substantially under `ansim_review`.

The canonical user/developer entrypoints become:

```text
evidence-review ...
python -m evidence_review ...
```

There must be exactly one post-preflight business-command dispatcher.

`ansim-review` / `python -m ansim_review` may remain only as a minimal compatibility shim for the v0.2.0 transition if removing them would cause unnecessary breakage. They must not own an alternate dispatcher or duplicate business logic.

Namespace migration and CLI consolidation are performed together to avoid first refactoring a dispatch tree under `ansim_review` and then immediately relocating the same code.

### Phase C — Public collaboration contract

Add the repository-facing material expected for public collaboration:

- `CONTRIBUTING.md`
- `SECURITY.md`
- `CHANGELOG.md`
- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/ISSUE_TEMPLATE/feature_request.yml`
- `.github/pull_request_template.md`
- `LICENSE`

The repository owner must make the final license choice before the repository is made public. Recommended default for this project is **Apache-2.0** because it is permissive and includes an explicit patent grant, but the PR must not silently choose a legal license without owner confirmation.

README is rewritten as the public entrypoint. It should explain:

1. what the project does;
2. supported environment and installation;
3. quick start;
4. architecture and trust boundaries;
5. developer setup and validation;
6. contributing/security links;
7. license and release information.

Historical issue-number acceptance narratives are removed from the root README. Current design/operational documentation can remain under `docs/`, but historical evidence should not dominate the public navigation surface.

Repository metadata should also be updated before visibility changes: concise description, relevant topics, and public-facing homepage only if one exists and is intentionally supported.

### Phase D — Web runtime hardening (#109)

Treat `runtime-manifest.json` as untrusted input during `bootstrap.py --self-test`.

Validation order:

```text
exact manifest schema
-> safe relative POSIX path syntax
-> root containment
-> no symlink/reparse traversal
-> regular-file check
-> declared size
-> SHA-256
-> SQLite integrity/FK checks
```

The bootstrap remains stdlib-only and installation-free. Valid runtime ZIP reproducibility must remain unchanged.

### Phase E — Review Workspace correctness (#105 + #107)

#### Evidence viewer provenance (#105)

The viewer becomes document/revision aware.

It must distinguish:

```text
cited-page position within the active source
```

from:

```text
original source page number
```

Multiple documents may never be presented as one continuous PDF sequence. Source selection must be real and keyboard accessible. Inactive/fake controls are removed. Government-only provenance text is replaced with source-neutral wording suitable for arbitrary user-provided documents.

#### Persisted human decision state (#107)

Protected mode must display the latest valid decision bound to the current immutable packet hash.

A completed review exposes validated:

- decision;
- reviewer ID;
- reviewed-at timestamp;
- notes.

The existing append-only model remains. Recording another decision requires an explicit action; reopening a completed review must not look like a blank first-time decision form.

Decision filename precision is increased enough to avoid accidental same-second collisions while preserving create-only semantics.

### Phase F — Protected browser performance (#108)

This phase follows the document-aware viewer work because lazy loading depends on stable source/page state.

Two presentation modes are retained:

```text
review.html
  archival, standalone, self-contained, embedded verified page images

review-protected.html
  protected localhost presentation, token-protected verified page routes, bounded lazy loading
```

The protected presentation must not contain base64 payloads for every cited page. The active page is loaded immediately and only a bounded adjacent set may be prefetched.

Every served image remains verified against authoritative page metadata/source hash/image SHA before bytes are returned.

No remote image/CDN/network dependency is introduced.

### Phase G — Validation and contributor ergonomics

The project should expose one documented validation sequence for contributors. A new wrapper command is not required if the existing commands are sufficient; YAGNI applies.

Required exact-HEAD validation for the integrated PR:

```text
pytest -v
ruff check src tests web_runtime
mypy <canonical source tree>
python -m compileall -q src scripts web_runtime tests
documentation integrity
wheel build
installed-wheel smoke
web runtime self-test
formal-review E2E
real-browser Review Workspace acceptance
```

Where the supported Python policy still includes both 3.11 and 3.13 at implementation time, wheel/smoke/E2E coverage must match that policy. If the repository separately changes its Python support policy, that change must be explicit and reflected consistently in `pyproject.toml`, documentation, tests, and release notes rather than being an incidental consequence of this PR.

GitHub Actions availability is not itself the release truth. If Actions are unavailable or blocked, the repository’s documented reproducible manual validation policy remains an accepted evidence path, with exact HEAD/interpreter/OS/command/result recorded.

### Phase H — v0.2.0 release preparation

This work is release-minor, not patch-level, because it changes repository structure, namespace/CLI internals, public collaboration contracts, Review Workspace behavior, runtime validation, and performance behavior.

Set package version to:

```text
0.2.0
```

Target tag/release:

```text
v0.2.0
```

Release assets should include at minimum:

```text
evidence_review_system-0.2.0-py3-none-any.whl
evidence-review-system-v0.2.0-runtime.zip
SHA256SUMS.txt
```

If the existing release-governance workflow produces a `release-manifest.json`, preserve and attach it as the authoritative machine-readable release manifest.

Do not place the following in release assets:

- source PDFs;
- parser outputs;
- extracted page images/screenshots;
- SQLite workspaces/databases produced from user documents;
- CSV exports;
- human decision records;
- historical acceptance directories;
- development-only fixtures.

The existing `v0.1.0` release remains historical. `v0.2.0` is built from the final merged exact HEAD after all release gates pass.

## 4. Target active-tree shape

The exact tree may vary where current runtime contracts require it, but the public-facing structure should converge on:

```text
evidence-review-system/
├─ .github/
├─ docs/
├─ examples/                 # only durable, current examples
├─ rules/                    # governed runtime rules only
├─ schemas/
├─ scripts/                  # current operational/developer scripts only
├─ skills/
│  ├─ ers-pdf/
│  └─ ers-review/
├─ src/
│  └─ evidence_review/
├─ tests/
├─ web_runtime/
├─ CHANGELOG.md
├─ CONTRIBUTING.md
├─ LICENSE
├─ README.md
├─ SECURITY.md
└─ pyproject.toml
```

Do not create directories merely to match this diagram. A directory exists only if it has a current responsibility.

## 5. Commit strategy inside the integrated PR

Preferred logical commits:

```text
1. chore: remove historical acceptance and Grist-only artifacts
2. refactor: migrate implementation to evidence_review namespace
3. refactor: consolidate canonical CLI dispatch
4. docs: add public contribution and security documentation
5. security: harden web runtime manifest validation
6. fix: make evidence viewer document-aware
7. fix: surface persisted human decision state
8. perf: lazy-load protected review page images
9. chore: normalize tests docs and package metadata
10. release: prepare v0.2.0 metadata and artifacts
```

The actual count can change if a task has a stronger independent review boundary, but unrelated changes must not be collapsed into one opaque commit.

## 6. PR contract

Draft PR title:

```text
release: prepare Evidence Review System for public collaboration and v0.2.0
```

The PR body must include:

```text
Closes #105
Closes #106
Closes #107
Closes #108
Closes #109
Closes #110
```

The PR remains Draft while implementation is in progress. Individual issues remain open until merge.

The PR checklist covers:

- repository cleanup;
- namespace consolidation;
- CLI consolidation;
- public collaboration files;
- runtime security;
- viewer provenance;
- persisted human decisions;
- protected browser performance;
- documentation integrity;
- packaging and release artifacts;
- full automated/manual validation;
- final public-readiness review.

## 7. Public visibility gate

Merging this PR does not automatically make the repository public.

Before changing repository visibility, verify at the merged exact HEAD:

1. no secrets, credentials, private URLs, proprietary PDFs, customer/user data, generated evidence DBs, or sensitive acceptance artifacts exist in the current tree;
2. Git history has already been sanitized to the intended standard and no newly introduced sensitive content exists;
3. the chosen open-source license is present and intentional;
4. README/CONTRIBUTING/SECURITY describe the actual supported behavior;
5. a clean clone can install and run the documented validation path;
6. v0.2.0 release artifacts are built from the same accepted code line and hashes are published;
7. the release notes state compatibility/deprecation behavior for `ansim_review` names if any remain.

Repository visibility change is a separate owner action after these gates pass.

## 8. Non-goals

This integrated PR does not:

- add unrelated product features;
- redesign the evidence/review state machine;
- change parser algorithms except where import/namespace relocation requires mechanical updates;
- weaken fail-closed source/rule/page/release verification;
- introduce a frontend framework;
- introduce remote runtime services;
- preserve historical files in `main` solely because they might be useful someday;
- delete governed runtime assets solely to reduce repository file count.

## 9. Success criteria

The project is ready for public collaboration when all of the following are true:

- #105 through #110 are satisfied by the integrated PR;
- active source tree contains only current runtime/product/developer material or clearly scoped fixtures/examples;
- `evidence_review` is the canonical implementation namespace;
- one canonical CLI dispatcher exists;
- public contribution/security/license/release documentation is present and accurate;
- manifest/path self-test fails closed;
- Review Workspace provenance and persisted decision state are truthful;
- protected review no longer eagerly embeds all page images;
- all declared validation gates pass at exact HEAD;
- wheel/runtime release artifacts are reproducible and hash-published;
- `v0.2.0` release is created from the accepted merged code;
- repository can then be switched from private to public as an explicit final owner action.