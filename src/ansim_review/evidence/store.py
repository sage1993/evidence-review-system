"""SQLite evidence store lifecycle helpers."""
from __future__ import annotations

import sqlite3
from importlib.resources import files
from pathlib import Path
from types import TracebackType
from typing import Any

from ansim_review.evidence.schema_version import require_current_schema


class EvidenceStore:
    """Own one version-checked SQLite evidence connection."""

    def __init__(self, path: Path, *, create: bool = False) -> None:
        self.path = path
        self.create = create
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> EvidenceStore:
        if self.create:
            connection = self._create_new_database()
        else:
            connection = self._open_existing_database()
        self.connection = connection
        return self

    def _configured_connection(self, target: str, *, uri: bool = False) -> sqlite3.Connection:
        connection = sqlite3.connect(target, uri=uri)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _create_new_database(self) -> sqlite3.Connection:
        if self.path.exists():
            raise FileExistsError(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._configured_connection(str(self.path))
        try:
            schema = (
                files("ansim_review.evidence")
                .joinpath("schema.sql")
                .read_text(encoding="utf-8")
            )
            connection.executescript(schema)
            require_current_schema(connection)
        except BaseException:
            connection.close()
            self.path.unlink(missing_ok=True)
            raise
        return connection

    def _open_existing_database(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        uri = f"{self.path.resolve().as_uri()}?mode=rw"
        connection = self._configured_connection(uri, uri=True)
        try:
            require_current_schema(connection)
        except BaseException:
            connection.close()
            raise
        return connection

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
