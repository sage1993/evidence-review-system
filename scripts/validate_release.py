#!/usr/bin/env python3
"""Validate an offline Ansim release workspace."""
from __future__ import annotations

import argparse
from pathlib import Path

from evidence_review.release.validator import validate_release_workspace


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("release-validation.json"),
    )
    parser.add_argument("--run-id", required=True)
    arguments = parser.parse_args()
    report = validate_release_workspace(
        arguments.workspace,
        arguments.output,
        run_id=arguments.run_id,
    )
    print(report["status"])
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
