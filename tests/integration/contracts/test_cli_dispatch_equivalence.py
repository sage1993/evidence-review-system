from __future__ import annotations

import importlib
import inspect
import subprocess
import sys

import evidence_review.cli


def test_canonical_business_dispatcher_is_the_single_runtime_owner() -> None:
    dispatch = importlib.import_module("evidence_review.command_dispatch")
    handlers = importlib.import_module("evidence_review.cli_handlers")

    assert callable(dispatch.main)
    assert "def main(" not in inspect.getsource(handlers)
    assert "from evidence_review.entrypoint" not in inspect.getsource(evidence_review.cli)


def test_legacy_and_canonical_module_entrypoints_have_same_help_contract() -> None:
    canonical = subprocess.run(
        [sys.executable, "-m", "evidence_review", "--help"],
        text=True,
        capture_output=True,
        check=True,
    )
    legacy = subprocess.run(
        [sys.executable, "-m", "ansim_review", "--help"],
        text=True,
        capture_output=True,
        check=True,
    )

    assert canonical.stdout == legacy.stdout
    assert canonical.stderr == legacy.stderr
