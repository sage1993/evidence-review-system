# Security Policy

Evidence Review System processes local documents, parser artifacts, evidence databases, review packets, and human-decision records. Security issues affecting source integrity, path containment, offline guarantees, packet binding, or release validation are treated as high priority.

## Supported versions

The current source metadata version is `0.2.1` and its supported Python range
is `>=3.13,<3.14`. Published support status follows actual [GitHub
Releases](https://github.com/sage1993/evidence-review-system/releases), not
source metadata alone.

## PDF parser dependency policy

Re-verified on 2026-09-20, the `0.2.1` source requires
`pypdf>=6.18.1,<7`. The August 2026 advisories GHSA-fc8x-2rww-xw9m,
GHSA-fwg2-594c-jp42, and GHSA-fp3f-mc75-235c affect versions `<6.15.0` and
are patched in `>=6.15.0`. Three additional upstream advisories published on
2026-09-11 affect versions `<6.18.1`: [GHSA-jw7q-gvrg-4vj3](https://github.com/py-pdf/pypdf/security/advisories/GHSA-jw7q-gvrg-4vj3)
covers long runtimes for partially malformed FlateDecode streams,
[GHSA-g9cg-prrw-2r8q](https://github.com/py-pdf/pypdf/security/advisories/GHSA-g9cg-prrw-2r8q)
covers memory use from oversized font widths, and
[GHSA-fp3h-c4fm-7vvf](https://github.com/py-pdf/pypdf/security/advisories/GHSA-fp3h-c4fm-7vvf)
covers memory use from oversized `/ToUnicode` streams. The upstream
[6.18.1 release](https://github.com/py-pdf/pypdf/releases/tag/6.18.1)
contains the corresponding security fixes, so the project floor is now
`>=6.18.1`. Recheck this floor against upstream advisories and release notes
before each future public release.

## PDF rendering dependency policy

Re-verified on 2026-09-20, the `0.2.1` source requires `pypdfium2>=5.12.1,<6`. PyPI
has [yanked 5.12.0](https://pypi.org/project/pypdfium2/5.12.0/) because its
setup broke system-search/fallback binding generation. The
[5.12.1 release](https://github.com/pypdfium2-team/pypdfium2/releases/tag/5.12.1)
corrects the setup issue, and 5.13.0 is the current compatible upstream
release. The floor was raised to exclude the yanked, defective version.
Recheck it against upstream release notes before each future public release.

## Pillow dependency policy

The `0.2.1` source requires `Pillow>=12.3,<13`. Pillow is part of the
visual-input runtime boundary. Re-verified on 2026-09-20, `12.3.0` remains the
current release and security floor. Its security fixes include protection
against unbounded PDF-stream decompression
([CVE-2026-59200](https://github.com/advisories/GHSA-jjj6-mw9f-p565)) and
additional unsafe-input/resource-exhaustion cases, including the
[Image.paste/Image.crop out-of-bounds write](https://github.com/python-pillow/Pillow/security/advisories/GHSA-6r8x-57c9-28j4).
Recheck this floor against upstream security releases before each future
public release.

## Reporting a vulnerability

Do **not** open a public GitHub issue for a vulnerability that could expose data, bypass integrity checks, escape path containment, enable unintended network access, or allow tampering with review/release authority.

Use GitHub private vulnerability reporting / a private security advisory when available. If that feature is not available, contact the repository maintainer privately through the GitHub account associated with this repository before public disclosure.

Include, when possible:

- affected commit/tag;
- affected component and command;
- minimal reproduction steps using non-sensitive fixtures;
- expected vs. observed behavior;
- security impact;
- whether the issue requires local file access, a crafted archive/manifest, browser access, or another precondition.

Never include real customer documents, credentials, private URLs, access tokens, or private keys in a report.

## Security boundaries

The project intentionally distinguishes several boundaries:

- **Application offline guard:** project/runtime code blocks non-loopback networking but this is not a complete OS sandbox.
- **OS isolation:** firewall, network namespace, VM, or equivalent deployment controls are separate assurances.
- **Source/evidence integrity:** source hashes and immutable parser/evidence artifacts are authoritative. Evidence databases are finalized before publication; active binding records both the logical snapshot identity and the exact SHA-256 of the closed database bytes, and post-bind review access is read-only and fail-closed.
- **Protected review server:** loopback-only, tokenized, origin/host checked, and bounded request handling.
- **Human decision:** append-only record bound to the current immutable packet hash; it does not mutate machine output.
- **Release validation:** archive membership, safe paths, size, hashes, and database integrity must fail closed.

A human attestation does not override a failed technical release validation.

## Out of scope for security claims

Unless separately demonstrated by deployment evidence, the project does not claim protection against:

- a hostile Python interpreter or compromised operating system;
- arbitrary administrator/root processes;
- malicious native extensions outside the audited runtime boundary;
- filesystem modification after validation;
- network connections opened before the application guard is installed;
- cryptographic reviewer identity verification.

## Disclosure and fixes

A security fix should include a regression test when technically feasible and should preserve fail-closed behavior. Release notes should describe security-relevant behavior without publishing unnecessary exploitation detail before users have a reasonable opportunity to update.
