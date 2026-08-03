> Document status: CURRENT

# Issue #52 Parser Reproducibility Acceptance

## Current verdict

`MANUAL_PASS — READY FOR REVIEW`

Local manual acceptance was completed against implementation HEAD
`5e9c7f1910d5afeb79ce5ec21e0756b41e10a62c` plus the local verification fix
commit `662f9757fc1b674518ea071d31e5b9728fa74c9f` and the review-fix commit
`2cb34149d766340b59fd589a0d1243159b827819`. The final evidence code HEAD is
`2cb34149d766340b59fd589a0d1243159b827819`; the remote implementation branch
was verified at the same HEAD before this ledger update. GitHub Actions remains
excluded from acceptance.

## Environment

- Repository: `sage1993/evidence-review-system`
- Local branch: `verify/issue-52-final`
- Remote implementation branch before push: `agent/issue-52-opendataloader-reproducibility`
- Platform: Windows 10 Home, Version 2009
- Python 3.11: `3.11.9` workspace-local embeddable runtime
- Python 3.13: `3.13.14`
- OpenDataLoader CLI: `opendataloader-pdf 2.5.0`
- Raw source PDFs and parser outputs were not overwritten.

## Parser configuration and fixture identities

- Parser configuration SHA-256 from run authority: `53A07D14F2E664B179198C9F0F13A492E5457D920971DC1503A93F4104E476A3`

| Fixture | Source | Pages | Source SHA-256 | Run count |
|---|---|---:|---|---:|
| `law1` | `02_source_pdf/law-1.pdf` | 84 | `B2D9EDBD8813843B3C789A88C221055BABCBCB2C2E3A199D07B0B0380AEBA9403` | 2 |
| `law2` | `02_source_pdf/law-2.pdf` | 10 | `F509C89D7656AF4490B9D0AB65E5A2329B6F63684D9E49D7D8A914CBFB3B99ED` | 2 |
| `layout-page1` | `build/issue52-real-fixtures/layout-page1.pdf` | 1 | `CAF38CE59AB7B96A34A60B9574D6B64409FB90DA58B66B6AF11FB684EC9617F4` | 2 |

Each fixture was executed twice with the same OpenDataLoader options:

`-f json,markdown --image-output external --image-format png --markdown-with-html -q`

All six parser runs exited `0`. Each report, warning report, and review queue
was generated twice and was byte-identical on both generations.

## Reproducibility and warning evidence

| Fixture | Reproducibility status | Differences | Warnings | Report SHA-256 | Warning report SHA-256 | Queue SHA-256 |
|---|---|---:|---:|---|---|---|
| `law1` | `BYTE_IDENTICAL` | 0 | 0 | `2FA4A0A7A0FED6351FCCF5E82409DCBA9EA18094FA89AC0A1A949645472CD6ED` | `66BE2D49271D6E982CB043E07A089CF33BC055FB1E4B4C03DDE92AAFB94E52F4` | `5D2B7686729D73EAA2621B4EF37BA1F593D4E4BC2D2D8914EF970613F18FF88A` |
| `law2` | `BYTE_IDENTICAL` | 0 | 0 | `B4F5B74BE68BA6953FDCA82CC2F0EBE4B2F6D8A9FC62835C0043F74C160647F0` | `1531034271E8447A49BFABDBA6DB1C47FDA108654765069C29AEF23313BDB718` | `5D2B7686729D73EAA2621B4EF37BA1F593D4E4BC2D2D8914EF970613F18FF88A` |
| `layout-page1` | `BYTE_IDENTICAL` | 0 | 0 | `8649146A5B8E096360CB156278EF3BEA09A48224845B24A00166F92DDF692001` | `E9742AB0DF545AB065F4AD8F714930423734AB067D95CC675748B69A9C52E85F` | `5D2B7686729D73EAA2621B4EF37BA1F593D4E4BC2D2D8914EF970613F18FF88A` |

Warning collection status for all three fixtures was `COLLECTED` with
`warning_count=0` and `queue_count=0`. The generated repository warning fixture
matrix remains covered by the integration tests.

## Automated gates

| Gate | Result |
|---|---|
| Target parser reproducibility tests | `81 passed, 1 skipped` |
| Full pytest | `894 passed, 4 skipped` |
| Ruff | PASS |
| strict mypy | PASS, 150 source files |
| compileall | PASS |
| documentation integrity | PASS, 0 errors, 64 warnings |
| Documentation report repeatability | PASS, byte-identical; SHA-256 `A1202205886317F68B34A0E944B8E83C1A3E72B0F5D9627D866FA678EDED25DF` |
| Create-only and concurrent output protection | PASS in integration tests |
| Python 3.11 wheel | PASS; SHA-256 `00BC962BAC45CDD6B521D8C90EAAE783C56AC7006E959B56E59180B9EF59AA1A` |
| Python 3.11 `pip check` | PASS |
| Python 3.11 installed entrypoints | PASS: `evidence-review.exe`, `python -m evidence_review`, `python -m ansim_review` |
| Python 3.13 wheel | PASS; SHA-256 `F49994D33DCEB226270F9AE4DC4AA15B4617BE8636B83C8E3174AAD0E8F47DFC` |
| Python 3.13 `pip check` | PASS |

## Evidence lineage and revalidation

- Correct implementation base HEAD: `5e9c7f1910d5afeb79ce5ec21e0756b41e10a62c`.
- Final evidence code HEAD: `2cb34149d766340b59fd589a0d1243159b827819`.
- Final evidence HEAD was pushed to `origin/agent/issue-52-opendataloader-reproducibility` and matched by `git ls-remote`.
- The post-ledger revalidation was run at the exact ledger-update HEAD and is recorded in the PR update together with the clean worktree, `git diff --check`, full pytest, Ruff, mypy, compileall, and documentation report SHA.

## Human review and release controls

- Human review is still required.
- Draft PR may be created for review; do not mark Ready, merge, or close Issue #52/#27 before explicit human approval.
- Original PDFs, raw OpenDataLoader outputs, and source manifests remain immutable.
- No GitHub Actions acceptance dependency was used.
