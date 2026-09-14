"""SQLite evidence store lifecycle helpers."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path
from types import TracebackType
from typing import Any

from evidence_review.evidence.schema_version import detect_schema_version, require_current_schema

_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def sqlite_sidecar_paths(path: Path) -> tuple[Path, ...]:
    """Return SQLite sidecar paths that can extend one database artifact."""
    return tuple(
        path.with_name(path.name + suffix) for suffix in _SQLITE_SIDECAR_SUFFIXES
    )


def reject_sqlite_sidecars(path: Path) -> None:
    """Reject a database whose bytes are not self-contained in the main file."""
    for sidecar in sqlite_sidecar_paths(path):
        try:
            sidecar.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise RuntimeError("EVIDENCE_DATABASE_SIDECAR_PRESENT") from error
        raise RuntimeError("EVIDENCE_DATABASE_SIDECAR_PRESENT")


class EvidenceRow:
    """SQLite row compatibility object with tuple and named-field access."""

    __slots__ = ("_values", "_columns", "_positions")

    def __init__(self, cursor: sqlite3.Cursor, values: tuple[object, ...]) -> None:
        self._values = tuple(values)
        self._columns = tuple(str(item[0]) for item in cursor.description or ())
        self._positions = {name: index for index, name in enumerate(self._columns)}

    def __getitem__(self, key: int | slice | str) -> object:
        if isinstance(key, str):
            return self._values[self._positions[key]]
        return self._values[key]

    def __iter__(self) -> Iterator[object]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EvidenceRow):
            return self._values == other._values and self._columns == other._columns
        if isinstance(other, tuple):
            return self._values == other
        return NotImplemented

    def __repr__(self) -> str:
        return repr(self._values)

    def keys(self) -> tuple[str, ...]:
        return self._columns


def _evidence_row_factory(
    cursor: sqlite3.Cursor,
    values: tuple[object, ...],
) -> EvidenceRow:
    return EvidenceRow(cursor, values)


class EvidenceStore:
    """Own one version-checked SQLite evidence connection."""

    def __init__(
        self,
        path: Path,
        *,
        create: bool = False,
        read_only: bool = False,
        schema_resource: str = "schema.sql",
        require_current: bool = True,
    ) -> None:
        if create and read_only:
            raise ValueError("create and read_only cannot both be true")
        self.path = path
        self.create = create
        self.read_only = read_only
        self.schema_resource = schema_resource
        self.require_current = require_current
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
        connection.row_factory = _evidence_row_factory
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _create_new_database(self) -> sqlite3.Connection:
        if self.path.exists():
            raise FileExistsError(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._configured_connection(str(self.path))
        try:
            schema = (
                files("evidence_review.evidence")
                .joinpath(self.schema_resource)
                .read_text(encoding="utf-8")
            )
            connection.executescript(schema)
            if self.require_current:
                require_current_schema(connection)
        except BaseException:
            connection.close()
            self.path.unlink(missing_ok=True)
            raise
        return connection

    def _open_existing_database(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        if self.read_only:
            reject_sqlite_sidecars(self.path)
        mode = "ro" if self.read_only else "rw"
        uri = f"{self.path.resolve().as_uri()}?mode={mode}"
        connection = self._configured_connection(uri, uri=True)
        try:
            if self.read_only:
                connection.execute("PRAGMA query_only = ON")
            if self.require_current:
                require_current_schema(connection)
            else:
                detect_schema_version(connection)
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
