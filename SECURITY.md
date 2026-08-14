# Security Policy

Evidence Review System processes local documents, parser artifacts, evidence databases, review packets, and human-decision records. Security issues affecting source integrity, path containment, offline guarantees, packet binding, or release validation are treated as high priority.

## Supported versions

The active development line targets `v0.2.x` on Python `>=3.13,<3.14`. The historical `v0.1.0` release is not the preferred target for new security fixes once `v0.2.0` is released.

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
- **Source/evidence integrity:** source hashes and immutable parser/evidence artifacts are authoritative.
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
