# Changelog

All notable changes to Evidence Review System are documented here.

The project follows semantic versioning for public releases where practical.

## [0.2.0] - 2026-08-15

### Changed

- Official Python support is `>=3.13,<3.14`, with Python 3.13 as the sole development and release-validation interpreter.
- Canonical implementation ownership moved to the `evidence_review` namespace; `ansim_review` remains only as a minimal compatibility surface.
- Runtime command routing is consolidated behind one canonical dispatcher.
- Public repository contribution, security, issue, and pull-request guidance has been added.
- ANSIM-specific governed rule artifacts moved from the repository root into `tests/fixtures/ansim/rules/`; runtime workspaces continue to own their governed `rules/` trees.
- Codex bundles now publish only the current `ers-pdf` and `ers-review` workflow skills.

### Fixed

- Multi-document Review Workspace provenance and page navigation under #105.
- Persisted append-only human-decision display/state under #107.
- Protected page-image lazy delivery while preserving standalone archive HTML under #108.
- Web runtime manifest schema, path-containment, size, and hash validation under #109.
- CLI dispatch equivalence and compatibility routing under #110.
- Review Workspace responsive-layout regression against the #89 canonical three-column design.

### Security

- Added Apache License 2.0 and public vulnerability-reporting guidance.
- Preserved loopback-only protected review and serve-time page-image verification.

### Removed

- Historical issue-specific acceptance artifacts and one-off validation scripts that no longer belong in the active source tree.
- Legacy five-stage PDF-to-Grist skill set and stale skill-validation output.
- Grist Desktop QA documentation and obsolete Grist export/repair scripts from the active product tree.
- Python 3.11 support and dual-version release-validation requirements.### Deprecated

- `ansim-review` and `python -m ansim_review` are compatibility names only and are not the implementation namespace.
## [0.1.0] - 2026-08-12

Initial sanitized source-only release. The release removed original PDFs, parser outputs, extracted images, visual artifacts, database files, and CSV exports from rewritten Git history/release archives and established the first packaged Evidence Review System release line.
