# 비개발자용 README 사용 안내서 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GitHub README에서 비개발자가 PDF 입력 준비부터 사람 검토까지 실제 사용 흐름을 따라갈 수 있게 한다.

**Architecture:** 기존 README의 기술적 근거와 상세 문서 링크는 유지하되, 상단을 사용자 여정 중심으로 재배치한다. 실제 CLI parser에 등록된 명령만 예시로 사용하고, 고급 운영·개발 내용을 후반부로 분리한다.

**Tech Stack:** Markdown, PowerShell examples, `evidence-review` CLI, documentation integrity validator.

## Global Constraints

- 원본 PDF와 raw parser artifact를 덮어쓰지 않는다.
- `READY_FOR_HUMAN_REVIEW`를 승인 결과로 표현하지 않는다.
- 프로젝트 런타임은 오프라인으로 동작하며 외부 API 사용을 안내하지 않는다.
- 명령어와 파일명은 `src/ansim_review/cli_parser.py` 및 저장소 지침과 일치해야 한다.

---

### Task 1: Rewrite the README for first-time users

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: current CLI commands, source-batch workflow, review-run workflow, repository documentation links.
- Produces: Korean beginner-oriented usage guide with copyable PowerShell commands and clear result expectations.

- [ ] **Step 1: Add a beginner-oriented overview**

Explain the input → processing → output flow, the human-review boundary, prerequisites, installation, and the difference between reference PDFs and drawing PDFs.

- [ ] **Step 2: Add a copyable first-run walkthrough**

Show workspace preparation, source manifest creation, `source-batch prepare`, `source-batch ingest`, `query`, `math-run`, and `review-run` in the actual order.

- [ ] **Step 3: Add troubleshooting and terminology guidance**

Explain the common state values, expected output files, parser artifact requirement, drawing confirmation boundary, and where to find detailed technical documentation.

- [ ] **Step 4: Preserve and relocate advanced reference material**

Keep accurate legacy, release, safety, and developer verification details, but make them secondary to the beginner workflow.

### Task 2: Verify command and documentation accuracy

**Files:**
- Modify: `README.md` only if verification finds an incorrect command, path, or link.

**Interfaces:**
- Consumes: `src/ansim_review/cli_parser.py`, `AGENTS.md`, `documentation-integrity.json`.
- Produces: README whose commands and links match the current repository authority.

- [ ] **Step 1: Compare every command example with the CLI parser**

Check command names, required options, and output paths against the registered parser definitions.

- [ ] **Step 2: Run documentation validation to a fresh output path**

Run `evidence-review documentation validate --repository-root . --config documentation-integrity.json --output build/documentation-integrity-readme-report.json` and inspect the status and counts.

### Task 3: Run repository verification and report evidence

**Files:**
- No source changes expected.

**Interfaces:**
- Consumes: updated README and repository test configuration.
- Produces: exact validation results for documentation, tests, Ruff, mypy, and compileall.

- [ ] **Step 1: Run `pytest -v`**
- [ ] **Step 2: Run `ruff check src tests`**
- [ ] **Step 3: Run `mypy src`**
- [ ] **Step 4: Run `python -m compileall -q src scripts web_runtime tests`**
- [ ] **Step 5: Record changed files, commit state, and any unrelated pre-existing workspace changes**
