# Changelog

All notable changes to Evidence Review System are documented here.

The project follows semantic versioning for public releases where practical.

## [0.2.0] - 2026-08-15

### Changed

- Official Python support is `>=3.13,<3.14`; Python 3.11 support has ended.
- The canonical implementation namespace is `evidence_review`.
- `ansim-review` remains only as a deprecated compatibility entrypoint.

### Fixed

- Multi-document Review Workspace provenance and page-navigation correctness are fixed.
- Persisted human-decision display/state is fixed with append-only packet binding.
- Protected page-image delivery is lazy and bounded while archive HTML remains standalone.
- Web runtime manifest/path validation is fail-closed.
- CLI dispatch is consolidated under one canonical dispatcher.

### Security

- Added Apache License 2.0 and public vulnerability-reporting guidance.
- Preserved loopback-only protected review and serve-time page-image verification.

### Removed

- Historical issue-specific acceptance artifacts, Grist-only scripts, and numbered legacy skills were removed from the active source tree.

### Deprecated

- `ansim-review` and `python -m ansim_review` are compatibility names only and are not the implementation namespace.
## [0.1.0] - 2026-08-12

Initial sanitized source-only release. The release removed original PDFs, parser outputs, extracted images, visual artifacts, database files, and CSV exports from rewritten Git history/release archives and established the first packaged Evidence Review System release line.
