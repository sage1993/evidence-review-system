#!/usr/bin/env python3
"""Inventory, back up, and migrate an external Ansim Housing workspace."""
from __future__ import annotations

import argparse
from pathlib import Path

from ansim_review.migration.ansim_workspace import inventory_and_backup
from ansim_review.migration.evidence import migrate_evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--date", required=True)
    arguments = parser.parse_args()
    inventory_and_backup(arguments.workspace, arguments.output, date_label=arguments.date)
    migrate_evidence(arguments.workspace, arguments.output)
    print("ANSIM_MIGRATION_COMPLETE")


if __name__ == "__main__":
    main()
