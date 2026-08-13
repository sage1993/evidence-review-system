from pathlib import Path

import pytest

from ansim_review.offline_scanner import OfflineFinding, scan_source_tree


def write_source(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_safe_source_has_no_findings(tmp_path: Path) -> None:
    write_source(tmp_path, "safe.py", "from pathlib import Path\nvalue = Path('x')\n")

    assert scan_source_tree(tmp_path) == ()


@pytest.mark.parametrize(
    ("source", "kind", "symbol"),
    [
        ("import requests\n", "FORBIDDEN_IMPORT", "requests"),
        ("from urllib import request\n", "FORBIDDEN_IMPORT", "urllib.request"),
        ("import subprocess as sp\n", "FORBIDDEN_IMPORT", "subprocess"),
        ("import os\nos.system('x')\n", "FORBIDDEN_PROCESS_CALL", "os.system"),
        ("from os import popen as run\nrun('x')\n", "FORBIDDEN_PROCESS_CALL", "os.popen"),
        (
            "import asyncio\nasyncio.create_subprocess_exec('x')\n",
            "FORBIDDEN_PROCESS_CALL",
            "asyncio.create_subprocess_exec",
        ),
        ("__import__('httpx')\n", "DYNAMIC_FORBIDDEN_IMPORT", "httpx"),
        (
            "import importlib\nimportlib.import_module('aiohttp')\n",
            "DYNAMIC_FORBIDDEN_IMPORT",
            "aiohttp",
        ),
    ],
)
def test_scanner_detects_forbidden_capabilities(
    tmp_path: Path,
    source: str,
    kind: str,
    symbol: str,
) -> None:
    write_source(tmp_path, "runtime/example.py", source)

    findings = scan_source_tree(tmp_path)

    assert any(
        finding.kind == kind and finding.symbol == symbol for finding in findings
    )


def test_protected_server_launcher_is_the_only_subprocess_exception(tmp_path: Path) -> None:
    source = "import subprocess\nsubprocess.Popen(['python'])\n"
    write_source(
        tmp_path,
        "ansim_review/review_packet/browser_launcher.py",
        source,
    )
    write_source(tmp_path, "ansim_review/other_launcher.py", source)

    findings = scan_source_tree(tmp_path)

    assert findings == (
        OfflineFinding(
            path="ansim_review/other_launcher.py",
            line=1,
            kind="FORBIDDEN_IMPORT",
            symbol="subprocess",
        ),
        OfflineFinding(
            path="ansim_review/other_launcher.py",
            line=2,
            kind="FORBIDDEN_PROCESS_CALL",
            symbol="subprocess.Popen",
        ),
    )


def test_process_exception_does_not_allow_network_clients(tmp_path: Path) -> None:
    write_source(
        tmp_path,
        "ansim_review/review_packet/browser_launcher.py",
        "import requests\n",
    )

    assert scan_source_tree(tmp_path) == (
        OfflineFinding(
            path="ansim_review/review_packet/browser_launcher.py",
            line=1,
            kind="FORBIDDEN_IMPORT",
            symbol="requests",
        ),
    )


def test_scanner_reports_parse_failures(tmp_path: Path) -> None:
    write_source(tmp_path, "broken.py", "def broken(:\n")

    assert scan_source_tree(tmp_path) == (
        OfflineFinding(
            path="broken.py",
            line=1,
            kind="SCAN_ERROR",
            symbol="SyntaxError",
        ),
    )


def test_scanner_findings_are_sorted_and_root_relative(tmp_path: Path) -> None:
    write_source(tmp_path, "z.py", "import requests\n")
    write_source(tmp_path, "a.py", "import openai\n")

    findings = scan_source_tree(tmp_path)

    assert [finding.path for finding in findings] == ["a.py", "z.py"]
    assert [finding.line for finding in findings] == [1, 1]
    assert [finding.document() for finding in findings] == [
        {
            "path": "a.py",
            "line": 1,
            "kind": "FORBIDDEN_IMPORT",
            "symbol": "openai",
        },
        {
            "path": "z.py",
            "line": 1,
            "kind": "FORBIDDEN_IMPORT",
            "symbol": "requests",
        },
    ]
