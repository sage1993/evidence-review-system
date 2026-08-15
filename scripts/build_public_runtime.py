#!/usr/bin/env python3
"""Build the public software-only Evidence Review runtime ZIP."""
from __future__ import annotations

import argparse
from pathlib import Path

from evidence_review.packaging.web_bundle import build_public_runtime_zip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    print(build_public_runtime_zip(arguments.workspace, arguments.output))


if __name__ == "__main__":
    main()