# Offline Boundary Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the documented offline assurance level match the application's actual static and runtime controls.

**Architecture:** Define one versioned offline policy consumed by both the runtime guard and release validator. Block non-loopback TCP and UDP at Python socket entry points, detect prohibited network and process-spawning code in packaged runtime files, validate manifest path containment, and distinguish application-level controls from operator-supplied OS isolation.

**Tech Stack:** Python 3.11 standard library, `ast`, `socket`, `ipaddress`, pathlib, unittest.mock, pytest.

## Global Constraints

- Runtime dependencies remain empty.
- Local SQLite and file access must continue to work.
- The localhost browser review server must continue to work over IPv4 and IPv6 loopback.
- Application controls must not be described as an OS security sandbox.
- Runtime guard and release validator must consume the same policy object and policy version.
- Packaged runtime code may not spawn external network tools.
- Build-only scripts are outside the runtime scan only when the release manifest explicitly excludes them.

---

## File Map

### Create

- `src/ansim_review/offline_policy.py`: assurance enum, shared block lists, address classification, and static policy helpers.
- `tests/unit/test_offline_policy.py`: policy and address tests.
- `docs/OFFLINE_ASSURANCE.md`: application guard and OS-isolated deployment profiles.

### Modify

- `src/ansim_review/network_guard.py`: shared policy and TCP/UDP enforcement.
- `src/ansim_review/release/validator.py`: shared AST scanner, exact release file set, assurance output, and path containment.
- `tests/unit/test_network_guard.py`: runtime connection tests.
- `tests/integration/release/test_no_network_runtime.py`: release scan and local-functionality tests.
- `tests/integration/release/test_release_validator.py`: manifest containment and assurance reporting.
- `README.md`: accurate offline claim and link to operations guide.
- `docs/CODEX_WORKFLOW.md`: runtime assurance wording.

## Public Interfaces

```python
OfflineAssuranceLevel = Literal[
    "APPLICATION_OFFLINE_GUARD",
    "OS_ISOLATED",
]

POLICY_VERSION = 1

@dataclass(frozen=True, slots=True)
class OfflinePolicy:
    version: int
    forbidden_import_roots: frozenset[str]
    forbidden_import_names: frozenset[str]
    forbidden_process_calls: frozenset[str]


def default_offline_policy() -> OfflinePolicy:
    ...


def is_allowed_local_address(address: object) -> bool:
    ...


def scan_runtime_source(root: Path, policy: OfflinePolicy) -> tuple[PolicyFinding, ...]:
    ...
```

Required blocked import roots:

```text
requests
httpx
aiohttp
openai
anthropic
```

Required blocked names:

```text
urllib.request
subprocess
asyncio.create_subprocess_exec
asyncio.create_subprocess_shell
os.system
os.popen
```

---

### Task 1: Define one versioned offline policy

**Files:**
- Create: `src/ansim_review/offline_policy.py`
- Create: `tests/unit/test_offline_policy.py`

**Interfaces:**
- Produces: `default_offline_policy()`
- Produces: `is_allowed_local_address(address)`
- Produces: stable `PolicyFinding(path, line, code, symbol)`

- [ ] **Step 1: Write failing policy tests**

```python
def test_policy_has_stable_version_and_required_blocks() -> None:
    policy = default_offline_policy()
    assert policy.version == 1
    assert {"requests", "httpx", "aiohttp", "openai", "anthropic"} <= policy.forbidden_import_roots
    assert "urllib.request" in policy.forbidden_import_names
    assert "subprocess" in policy.forbidden_import_roots
```

- [ ] **Step 2: Write address-classification tests**

Accept:

```text
("127.0.0.1", 17841)
("::1", 17841, 0, 0)
Unix-domain string/path addresses where supported
```

Reject:

```text
("8.8.8.8", 53)
("192.168.0.10", 80)
("0.0.0.0", 80)
("::", 80, 0, 0)
("2001:4860:4860::8888", 53, 0, 0)
hostname strings such as example.com
```

- [ ] **Step 3: Run focused tests**

Run: `pytest tests/unit/test_offline_policy.py -v`

Expected: FAIL because the module does not exist.

- [ ] **Step 4: Implement immutable policy data**

Use `ipaddress.ip_address(host).is_loopback`. Do not resolve hostnames through DNS. A non-IP hostname is rejected unless it is exactly `localhost`; normalize `localhost` to allowed local intent without performing lookup.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/test_offline_policy.py -v
git add src/ansim_review/offline_policy.py tests/unit/test_offline_policy.py
git commit -m "feat: define shared offline execution policy"
```

### Task 2: Enforce non-loopback TCP and UDP blocking

**Files:**
- Modify: `src/ansim_review/network_guard.py`
- Modify: `tests/unit/test_network_guard.py`

**Interfaces:**
- `install_network_guard(policy: OfflinePolicy | None = None) -> None`
- Guard remains idempotent.

- [ ] **Step 1: Add failing runtime tests**

Test patched entry points directly without contacting the network:

```text
socket.create_connection(non-loopback) -> RuntimeError
socket.socket.connect(non-loopback)     -> RuntimeError
socket.socket.connect_ex(non-loopback)  -> RuntimeError
socket.socket.sendto(non-loopback)      -> RuntimeError
loopback TCP                             -> delegates to original function
loopback UDP                             -> delegates to original function
```

Capture original functions before guard installation so tests can verify delegation through mocks.

- [ ] **Step 2: Confirm current loopback is blocked and UDP is unguarded**

Run: `pytest tests/unit/test_network_guard.py -v`

- [ ] **Step 3: Store original socket callables once**

Module constants:

```python
_ORIGINAL_CREATE_CONNECTION = socket.create_connection
_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_SENDTO = socket.socket.sendto
```

Guard wrappers call the original only when `is_allowed_local_address(address)` is true.

- [ ] **Step 4: Preserve server behavior**

Do not patch `bind`, `listen`, `accept`, `send`, or `sendall`. The review server binds explicitly to `127.0.0.1`; this remains permitted.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/test_network_guard.py tests/unit/test_offline_policy.py -v
git add src/ansim_review/network_guard.py tests/unit/test_network_guard.py
git commit -m "fix: block non-loopback TCP and UDP access"
```

### Task 3: Build a shared AST policy scanner

**Files:**
- Modify: `src/ansim_review/offline_policy.py`
- Modify: `tests/unit/test_offline_policy.py`

**Interfaces:**
- Produces: `scan_runtime_source(root, policy) -> tuple[PolicyFinding, ...]`

- [ ] **Step 1: Add failing scanner fixtures**

Create temporary Python files covering:

```python
import requests
from urllib import request
import subprocess
import asyncio
asyncio.create_subprocess_exec("curl", "https://example.com")
import os
os.system("curl https://example.com")
__import__("httpx")
importlib.import_module("aiohttp")
```

Also cover allowed imports such as `sqlite3`, `pathlib`, and `socket` itself.

- [ ] **Step 2: Assert deterministic findings**

Expected shape:

```text
relative/path.py:4:FORBIDDEN_IMPORT:requests
relative/path.py:9:FORBIDDEN_PROCESS_CALL:os.system
```

Sort by `(path, line, code, symbol)`.

- [ ] **Step 3: Run tests and confirm failure**

- [ ] **Step 4: Implement AST symbol resolution for required forms**

Support direct imports, `from` imports, literal `__import__`, literal `importlib.import_module`, and direct attribute calls. Do not attempt general data-flow analysis.

A source parse failure produces `SCAN_ERROR`, never a pass.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/test_offline_policy.py -v
git add src/ansim_review/offline_policy.py tests/unit/test_offline_policy.py
git commit -m "feat: scan packaged runtime for offline policy violations"
```

### Task 4: Make release validation consume the shared policy

**Files:**
- Modify: `src/ansim_review/release/validator.py`
- Modify: `tests/integration/release/test_no_network_runtime.py`
- Modify: `tests/integration/release/test_release_validator.py`

**Interfaces:**
- Remove the private `_FORBIDDEN_IMPORTS` and `_forbidden_imports()` implementation.
- Release report includes:

```json
{
  "offline_assurance": {
    "level": "APPLICATION_OFFLINE_GUARD",
    "policy_version": 1,
    "os_isolation_verified": false
  }
}
```

- [ ] **Step 1: Add failing equality test**

Assert the runtime guard and release scanner report the same `POLICY_VERSION` imported from `offline_policy.py`.

- [ ] **Step 2: Add prohibited subprocess test**

Place `import subprocess` under the packaged runtime root and assert release validation fails with `FORBIDDEN_RUNTIME_CAPABILITY`.

- [ ] **Step 3: Add allowed local operations test**

Under `blocked_network()` or the installed guard, verify:

```text
SQLite create/read/write succeeds
local file hashing succeeds
localhost review server request succeeds
```

- [ ] **Step 4: Replace release scanner implementation**

Call:

```python
findings = scan_runtime_source(packaged_source_root, default_offline_policy())
```

A nonempty finding tuple adds `FORBIDDEN_RUNTIME_CAPABILITY`.

- [ ] **Step 5: Use the production guard in release reproducibility checks**

Delete the divergent `BlockedSocket` policy where possible. Install or contextually patch through shared guard wrappers so test and runtime semantics match.

- [ ] **Step 6: Run tests and commit**

```bash
pytest tests/integration/release/test_no_network_runtime.py tests/integration/release/test_release_validator.py -v
git add src/ansim_review/release/validator.py tests/integration/release
git commit -m "refactor: unify release and runtime offline policy"
```

### Task 5: Validate release manifest path containment

**Files:**
- Modify: `src/ansim_review/release/validator.py`
- Modify: `tests/integration/release/test_release_validator.py`

**Interfaces:**
- Produces internal helper: `_resolve_manifest_member(manifest_dir: Path, relative: str) -> Path`

- [ ] **Step 1: Add failing traversal tests**

Reject manifest entries:

```text
../outside.txt
/absolute/path
C:\outside.txt
nested/../../outside.txt
```

Confirm the validator rejects before reading or hashing the outside target.

- [ ] **Step 2: Implement containment check**

```python
root = manifest_dir.resolve()
target = (root / relative).resolve()
if not target.is_relative_to(root):
    raise ValueError("MANIFEST_PATH_ESCAPE")
```

Also reject backslashes and drive prefixes for canonical manifest paths.

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/integration/release/test_release_validator.py -v
git add src/ansim_review/release/validator.py tests/integration/release/test_release_validator.py
git commit -m "fix: contain release manifest paths"
```

### Task 6: Document assurance profiles accurately

**Files:**
- Create: `docs/OFFLINE_ASSURANCE.md`
- Modify: `README.md`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `tests/unit/test_documentation_contracts.py`

- [ ] **Step 1: Add documentation contract tests**

Assert user-facing docs contain both exact names:

```text
APPLICATION_OFFLINE_GUARD
OS_ISOLATED
```

Assert they do not claim the Python guard is a sandbox or complete network isolation.

- [ ] **Step 2: Write Profile A instructions**

Document what is covered:

```text
static packaged-source scan
non-loopback Python TCP blocking
non-loopback Python UDP blocking
prohibited runtime process-spawning policy
local SQLite/files/localhost allowed
```

Document exclusions: native extensions, hostile interpreter replacement, already-open descriptors, and processes launched outside the guarded runtime.

- [ ] **Step 3: Write Profile B operator examples**

Include:

```text
Windows outbound firewall rule for the executable
Docker/Podman --network none
Linux network namespace or equivalent host policy
```

State that the application cannot self-assert `OS_ISOLATED`; the operator must supply and record it.

- [ ] **Step 4: Run tests and commit**

```bash
pytest tests/unit/test_documentation_contracts.py -v
git add docs/OFFLINE_ASSURANCE.md README.md docs/CODEX_WORKFLOW.md tests/unit/test_documentation_contracts.py
git commit -m "docs: define offline assurance profiles"
```

### Task 7: Full verification and issue closure

- [ ] **Step 1: Run focused suites**

```bash
pytest tests/unit/test_offline_policy.py tests/unit/test_network_guard.py -v
pytest tests/integration/release -v
```

- [ ] **Step 2: Run full quality gate**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

- [ ] **Step 3: Confirm policy-list uniqueness**

Search for private duplicate forbidden-module sets:

```bash
git grep -n "FORBIDDEN.*IMPORT\|requests.*httpx\|anthropic.*openai" src
```

The only policy definition must be `src/ansim_review/offline_policy.py`; tests may contain expected literals.

- [ ] **Step 4: Commit verification corrections**

```bash
git add -A
git commit -m "test: verify offline execution boundary"
```

- [ ] **Step 5: PR body**

Use `Closes #26` only after all gates pass.