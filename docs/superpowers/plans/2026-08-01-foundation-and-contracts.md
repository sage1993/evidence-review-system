# Foundation and Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the package, canonical contracts, deterministic serialization, immutable run directories, CLI shell, and no-network policy.

**Architecture:** Frozen dataclasses and explicit decoders define the interfaces shared by all subsystems. Every command activates a socket guard and writes canonical JSON into a new hash-derived run directory.

**Tech Stack:** Python 3.11+, dataclasses, typing, json, hashlib, pathlib, argparse, pytest, ruff, mypy.

## Global Constraints

- Standard-library-only runtime.
- Canonical JSON: UTF-8, sorted keys, compact separators, no NaN/Infinity.
- Machine review packets accept only `human_decision: null`.
- Existing run artifacts are never overwritten.

---

### Task 1: Package and CLI Scaffold

**Files:** Create `pyproject.toml`, `src/ansim_review/__init__.py`, `src/ansim_review/__main__.py`, `src/ansim_review/cli.py`; test `tests/integration/test_cli_help.py`.

**Interfaces:** `python -m ansim_review --help`; `ansim_review.__version__`.

- [ ] **Step 1: Write the failing test**

```python
from subprocess import run
import sys

def test_module_help() -> None:
    result = run([sys.executable, "-m", "ansim_review", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "evidence-first regulatory review" in result.stdout.lower()
```

- [ ] **Step 2: Run:** `pytest tests/integration/test_cli_help.py -v` — expect module-not-found failure.
- [ ] **Step 3: Implement `__main__.py` calling `cli.main()` and define Python `>=3.11` plus dev extras in `pyproject.toml`.**
- [ ] **Step 4: Run:** `python -m pip install -e .[dev] && pytest -v && ruff check src tests && mypy src`.
- [ ] **Step 5: Commit:** `git commit -m "chore: scaffold deterministic review runtime"`.

### Task 2: Canonical JSON and Hashes

**Files:** Create `src/ansim_review/canonical_json.py`; test `tests/unit/test_canonical_json.py`.

**Interfaces:** `dumps(value) -> str`, `dump_bytes(value) -> bytes`, `sha256_json(value) -> str`.

- [ ] **Step 1: Write the failing test**

```python
from ansim_review.canonical_json import dump_bytes, sha256_json

def test_order_independent_json() -> None:
    assert dump_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})
```

- [ ] **Step 2: Run:** `pytest tests/unit/test_canonical_json.py -v` — expect import failure.
- [ ] **Step 3: Implement with `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)` and SHA-256.**
- [ ] **Step 4: Run the unit test and type checks.**
- [ ] **Step 5: Commit:** `git commit -m "feat: add canonical json hashing"`.

### Task 3: Core Contracts and Decoders

**Files:** Create `src/ansim_review/contracts/common.py`, `src/ansim_review/contracts/evidence.py`, `src/ansim_review/contracts/engines.py`, `src/ansim_review/contracts/review.py`, `src/ansim_review/contracts/codecs.py`; test `tests/unit/test_contract_codecs.py`.

**Interfaces:** `BBox`, `Citation`, `EvidenceRecord`, `CalculationResult`, `RuleResult`, `Claim`, `TrackADraft`, `TrackBAudit`, `ConfidenceResult`, `ReviewPacket`.

- [ ] **Step 1: Write a test rejecting a machine-set decision**

```python
import pytest
from ansim_review.contracts.codecs import decode_review_packet

def test_machine_packet_rejects_decision() -> None:
    with pytest.raises(ValueError, match="human_decision must be null"):
        decode_review_packet({"run_id": "R", "status": "READY_FOR_HUMAN_REVIEW", "human_decision": "SATISFIED"})
```

- [ ] **Step 2: Run:** `pytest tests/unit/test_contract_codecs.py -v` — expect missing decoder.
- [ ] **Step 3: Implement frozen dataclasses, `Literal` statuses, and explicit type-checked decoders; do not use unchecked `**payload` construction.
- [ ] **Step 4: Run:** `pytest tests/unit/test_contract_codecs.py -v && mypy src/ansim_review/contracts`.
- [ ] **Step 5: Commit:** `git commit -m "feat: define review system contracts"`.

### Task 4: Immutable Run Context

**Files:** Create `src/ansim_review/contracts/run_context.py`; test `tests/unit/test_run_id.py`.

**Interfaces:** `compute_run_id(question, inputs, evidence_hash, rule_hash, formula_hash) -> str`; `create_run_directory(root, run_id) -> Path`.

- [ ] **Step 1: Test equivalent input order yields the same ID and existing directories raise `FileExistsError`.**
- [ ] **Step 2: Run the test and observe failure.**
- [ ] **Step 3: Generate `RUN-` plus 20 uppercase hex characters from canonical input hash; use `mkdir(exist_ok=False)`.**
- [ ] **Step 4: Run:** `pytest tests/unit/test_run_id.py -v`.
- [ ] **Step 5: Commit:** `git commit -m "feat: add immutable deterministic run context"`.

### Task 5: No-Network Guard

**Files:** Create `src/ansim_review/network_guard.py`; modify CLI; test `tests/unit/test_network_guard.py`.

**Interfaces:** `install_network_guard() -> None`.

- [ ] **Step 1: Write a test asserting `socket.create_connection` raises `RuntimeError("network access is disabled")`.**
- [ ] **Step 2: Run and observe failure.**
- [ ] **Step 3: Replace outbound socket connect functions at CLI startup; add a static scan for `requests`, `httpx`, `openai`, and `urllib.request` imports.**
- [ ] **Step 4: Run:** `pytest tests/unit/test_network_guard.py -v` and the static scan.
- [ ] **Step 5: Commit:** `git commit -m "feat: enforce api-free runtime"`.
