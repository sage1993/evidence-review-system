from __future__ import annotations

from pathlib import Path

SOURCE_ROOT = Path("src/ansim_review")
TOKENS = (
    '"ansim/',
    "'ansim/",
    '"ansim-v1.0"',
    "'ansim-v1.0'",
    '"ansim-evidence.sqlite"',
    "'ansim-evidence.sqlite'",
)


def test_new_runtime_source_has_no_sample_specific_artifact_defaults() -> None:
    findings: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(token in line for token in TOKENS):
                findings.append(f"{path.as_posix()}:{line_number}:{line.strip()}")

    assert findings == []
