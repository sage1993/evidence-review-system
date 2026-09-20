# Changelog

All notable changes to Evidence Review System are documented here.

The project follows semantic versioning for public releases where practical.

## [0.2.1] - 2026-09-20

This patch release candidate contains the corrective, governance, and
repository-hardening work merged after v0.2.0. Public release status is
determined by the published GitHub Release and exact validated tag, not by
this source version or changelog entry alone.

### Fixed

- Corrected raw-question authority, confidence initialization/formalization, Track B semantic validation, Windows runtime filesystem handling, and unified Review Workspace behavior from the post-audit remediation under #233.
- Reworked OpenDataLoader table identity so the raw parser table ID remains provenance while the persisted canonical table ID is deterministically bound to source revision, page, raw parser ID, and structural path. Cross-page raw-ID reuse now ingests correctly, while true canonical identity collisions still fail closed under #237.
- Corrected parser warning classification so INFO/progress output is excluded, actual warning/error severities are retained, Korean Java logger severity aliases are recognized, and raw logs remain unchanged under #237.

### Changed

- Hardened public repository governance and exact-SHA repository/package/issue/PR evidence checks under #227.
- Removed tracked local review/agent work products and synchronized current-authority documentation with the merged ReviewMatter and post-audit implementation under #229 and #235.

### Security

- Re-verified the release dependency floors on 2026-09-20. The configured floors remain `pypdf>=6.18.1,<7`, `pypdfium2>=5.12.1,<6`, and `Pillow>=12.3,<13`; no dependency floor change is required for this patch candidate.

## [0.2.0] - 2026-09-12

This source version contains the stabilized 0.2.0 scope. Public release status
is determined by the published GitHub Release and exact validated tag, not by
this source version or changelog entry alone.

The release preserves the authority chain: Evidence Navigation, mutable
ReviewMatter, Formalization, Formal Review, then a separate append-only Human
Decision.

### Changed

- Packaging metadata now uses the PEP 639 SPDX expression `Apache-2.0` with `license-files = ["LICENSE"]`; the build backend floor is `setuptools>=77.0.3`, the first setuptools release line with standardized PEP 639 project metadata support.
- Official Python support is `>=3.13,<3.14`, with Python 3.13 as the sole development and release-validation interpreter.
- Canonical implementation ownership moved to the `evidence_review` namespace; `ansim_review` remains only as a minimal compatibility surface.
- Runtime command routing is consolidated behind one canonical dispatcher.
- Public repository contribution, security, issue, and pull-request guidance has been added.
- ANSIM-specific governed rule artifacts moved from the repository root into `tests/fixtures/ansim/rules/`; runtime workspaces continue to own their governed `rules/` trees.
- Codex bundles now publish only the current `ers-pdf` and `ers-review` workflow skills.
- Natural-language `$ERS_REVIEW` questions now pass through an external, bounded AI Question Planner handoff before deterministic retrieval. The validated QuestionPlan is immutable run input; the planner cannot decide the answer or create evidence authority.
- Retrieval now preserves deterministic `issue → search_request → evidence` lineage without changing channel weights or fusion ranking.

### Fixed

- Human-decision loading now excludes records whose review timestamp is beyond the permitted future-skew window, preventing a future-dated archival import from pinning the active review state.
- Web-runtime self-test now requires every runtime-critical file to be represented in the integrity manifest instead of accepting existence without manifest coverage.
- Natural-language whole-sentence retrieval false no-evidence behavior under #112 by validating bounded semantic search requests before the existing deterministic retrieval/review pipeline.
- Multi-document Review Workspace provenance and page navigation under #105.
- Persisted append-only human-decision display/state under #107.
- Protected page-image lazy delivery while preserving standalone archive HTML under #108.
- Web runtime manifest schema, path-containment, size, and hash validation under #109.
- CLI dispatch equivalence and compatibility routing under #110.
- Review Workspace responsive-layout regression against the #89 canonical three-column design.

### Security

- Raised the pypdf support floor to `>=6.18.1,<7` after reviewing three 2026-09-11 upstream advisories fixed in pypdf 6.18.1. PDF geometry and parser regression tests are required against the installed patched line.
- Raised the pypdfium2 support floor to `>=5.12.1,<6` to exclude the yanked 5.12.0 setup-bug release; the installed qualification version is 5.13.0.
- Re-verified the Pillow security floor at `>=12.3,<13`; Pillow 12.3.0 includes the 2026 PDF-stream decompression fix and other unsafe-input security fixes.

- Added Apache License 2.0 and public vulnerability-reporting guidance.
- Preserved loopback-only protected review and serve-time page-image verification.
- Planner output is treated as untrusted input: unknown conclusion/decision/confidence fields, malformed issue graphs, invalid references, and unbounded plans fail closed before retrieval.

### Removed

- Historical issue-specific acceptance artifacts and one-off validation scripts that no longer belong in the active source tree.
- Legacy five-stage PDF-to-Grist skill set and stale skill-validation output.
- Grist Desktop QA documentation and obsolete Grist export/repair scripts from the active product tree.
- Python 3.11 support and dual-version release-validation requirements.

### Deprecated

- `ansim-review` and `python -m ansim_review` are compatibility names only and are not the implementation namespace.

## [0.1.0] - 2026-08-12

Initial sanitized source-only release. The release removed original PDFs, parser outputs, extracted images, visual artifacts, database files, and CSV exports from rewritten Git history/release archives and established the first packaged Evidence Review System release line.
