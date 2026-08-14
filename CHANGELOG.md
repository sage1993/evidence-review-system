# Changelog

All notable changes to Evidence Review System are documented here.

The project follows semantic versioning for public releases where practical.

## [Unreleased]

### Changed

- Official Python support is being narrowed to `>=3.13,<3.14`.
- The canonical implementation namespace is being consolidated under `evidence_review`.
- Public repository documentation and contribution/security policies are being prepared.

### Fixed

- Multi-document Review Workspace provenance and page-navigation correctness are scheduled under #105.
- Persisted human-decision display/state is scheduled under #107.
- Protected page-image delivery performance is scheduled under #108.
- Web runtime manifest/path validation is hardened under #109.
- CLI dispatch consolidation is scheduled under #110.

### Removed

- Historical issue-specific acceptance artifacts and one-off validation scripts that no longer belong in the active source tree are being removed under #106.

## [0.1.0] - 2026-08-12

Initial sanitized source-only release. The release removed original PDFs, parser outputs, extracted images, visual artifacts, database files, and CSV exports from rewritten Git history/release archives and established the first packaged Evidence Review System release line.
