#!/usr/bin/env python3
"""Retired ambiguous workspace-validator entrypoint."""
from __future__ import annotations

import sys

_MESSAGE = """scripts/validate_workspace.py is retired and is not a current release gate.
Current release validation: scripts/validate_release.py <workspace>
Current release build: scripts/build_release.py <workspace> <output>
Legacy ANSIM/Grist validation only: scripts/validate_legacy_ansim_workspace.py
"""


def main() -> None:
    print(_MESSAGE, file=sys.stderr, end="")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
