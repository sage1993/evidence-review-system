"""Strict route and payload contracts for the mutable Workbench surface."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from evidence_review.contracts.identifiers import validate_identifier


@dataclass(frozen=True, slots=True)
class RouteContract:
    """One Workbench endpoint's method and exact JSON payload boundary."""

    method: str
    required_fields: frozenset[str] = frozenset()
    allowed_fields: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class WorkbenchRoute:
    """A parsed Workbench path, before token authorization."""

    endpoint: str
    token: str
    query: Mapping[str, str]


class RoutePayloadError(ValueError):
    """A stable client-visible payload rejection."""

    def __init__(self, code: str = "INVALID_REQUEST") -> None:
        super().__init__(code)
        self.code = code


def _contract(method: str, *fields: str) -> RouteContract:
    values = frozenset(fields)
    return RouteContract(method=method, required_fields=values, allowed_fields=values)


ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "state": RouteContract(method="GET"),
    "issues": _contract(
        "POST",
        "expected_revision",
        "issue_id",
        "question",
        "work_state",
        "depends_on",
    ),
    "evidence/bind": _contract("POST", "expected_revision"),
    "evidence/search": RouteContract(method="GET"),
    "evidence/select": _contract("POST", "expected_revision", "query", "evidence_id", "limit"),
    "formalize": _contract("POST", "expected_revision"),
}


def workbench_path(matter_id: str, token: str, endpoint: str = "state") -> str:
    """Return an exact tokenized Workbench route from validated identities."""
    validate_identifier(matter_id, "matter_id")
    if endpoint not in ROUTE_CONTRACTS:
        raise ValueError("unknown workbench endpoint")
    return f"/workbench/{matter_id}/{token}/{endpoint}"


def parse_workbench_route(path: str, *, matter_id: str) -> WorkbenchRoute | None:
    """Parse only exact tokenized Workbench routes for one bound Matter."""
    parsed = urlsplit(path)
    if parsed.fragment:
        return None
    raw_parts = parsed.path.split("/")
    if len(raw_parts) < 5 or raw_parts[0] != "" or any(not part for part in raw_parts[1:]):
        return None
    parts = [unquote(part) for part in raw_parts[1:]]
    if any(part in {".", ".."} or "/" in part or "\\" in part or ":" in part for part in parts):
        return None
    if parts[:2] != ["workbench", matter_id] or not parts[2]:
        return None
    endpoint = "/".join(parts[3:])
    if endpoint not in ROUTE_CONTRACTS:
        return None
    if parsed.query and endpoint != "evidence/search":
        return None
    try:
        parsed_query = parse_qs(parsed.query, strict_parsing=True, keep_blank_values=True)
    except ValueError:
        return None
    if any(len(values) != 1 for values in parsed_query.values()):
        return None
    query = {key: values[0] for key, values in parsed_query.items()}
    if endpoint == "evidence/search":
        if set(query) - {"query", "limit"} or not query.get("query"):
            return None
    elif query:
        return None
    return WorkbenchRoute(endpoint=endpoint, token=parts[2], query=query)


def decode_payload(body: bytes, contract: RouteContract) -> dict[str, object]:
    """Decode one exact JSON object without accepting client reviewer identity."""

    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if not isinstance(key, str) or key in result:
                raise RoutePayloadError()
            result[key] = value
        return result

    try:
        decoded = json.loads(body.decode("utf-8"), object_pairs_hook=strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RoutePayloadError) as error:
        raise RoutePayloadError() from error
    if not isinstance(decoded, dict):
        raise RoutePayloadError()
    if "reviewer_id" in decoded:
        raise RoutePayloadError("REVIEWER_ID_READONLY")
    actual = frozenset(decoded)
    if actual != contract.required_fields or actual - contract.allowed_fields:
        raise RoutePayloadError()
    return decoded


def navigation_limit(query: Mapping[str, str]) -> int:
    """Decode the bounded optional navigation limit without changing service policy."""
    raw = query.get("limit", "20")
    try:
        value = int(raw)
    except ValueError as error:
        raise RoutePayloadError() from error
    if value < 1 or value > 100:
        raise RoutePayloadError()
    return value


__all__ = [
    "ROUTE_CONTRACTS",
    "RouteContract",
    "RoutePayloadError",
    "WorkbenchRoute",
    "decode_payload",
    "navigation_limit",
    "parse_workbench_route",
    "workbench_path",
]
