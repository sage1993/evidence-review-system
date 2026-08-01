"""SQLite evidence store lifecycle helpers."""
from __future__ import annotations

import sqlite3
from importlib.resources import files
from pathlib import Path
from types import TracebackType
from typing import Any


class EvidenceStore:
    """Own one SQLite connection with foreign keys and canonical schema."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> "EvidenceStore":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        schema = files("ansim_review.evidence").joinpath("schema.sql").read_text(encoding="utf-8")
        connection.executescript(schema)
        self.connection = connection
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def require_connection(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("evidence store is not open")
        return self.connection

    def scalar(self, sql: str, parameters: tuple[Any, ...] = ()) -> Any | None:
        row = self.require_connection().execute(sql, parameters).fetchone()
        return None if row is None else row[0]
