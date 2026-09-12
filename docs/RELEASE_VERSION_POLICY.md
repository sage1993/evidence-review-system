# Release Version Policy

## Authority

`pyproject.toml` is the authority for the source package version. A PEP 440
pre-release value in source metadata identifies a candidate only; it is not
proof that a public release has been published. Changelog dates and security
support statements likewise do not make an unpublished version final.

A public version exists only when a GitHub Release has been published and its
tag resolves to the exact validated commit. The source version, release tag,
and publication state must not be inferred from one another.

## Publication evidence

Before publication, the pull request evidence records the exact commit SHA,
verification states, and applicable artifact SHA-256 values. After
publication, verify the GitHub Release, tag SHA, and artifact hashes together
against that evidence and the exact validated commit.
