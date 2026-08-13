"""AST scanner for forbidden runtime network and process capabilities."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from ansim_review.offline_policy import OfflinePolicy, default_offline_policy


@dataclass(frozen=True, order=True, slots=True)
class OfflineFinding:
    """One stable source-level offline-policy finding."""

    path: str
    line: int
    kind: str
    symbol: str

    def document(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "kind": self.kind,
            "symbol": self.symbol,
        }


def _is_forbidden_import(module: str, policy: OfflinePolicy) -> bool:
    root = module.split(".", maxsplit=1)[0]
    return root in policy.forbidden_import_roots or module in policy.forbidden_import_names


def _is_allowed_subprocess(
    relative_path: str,
    symbol: str,
    policy: OfflinePolicy,
) -> bool:
    return (
        relative_path in policy.allowed_subprocess_paths
        and (symbol == "subprocess" or symbol.startswith("subprocess."))
    )


def _attribute_name(
    node: ast.expr,
    module_aliases: dict[str, str],
    symbol_aliases: dict[str, str],
) -> str | None:
    if isinstance(node, ast.Name):
        if node.id in symbol_aliases:
            return symbol_aliases[node.id]
        return module_aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _attribute_name(node.value, module_aliases, symbol_aliases)
        if parent is None:
            return None
        return f"{parent}.{node.attr}"
    return None


def _literal_string_argument(node: ast.Call) -> str | None:
    if not node.args:
        return None
    value = node.args[0]
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _scan_tree(
    tree: ast.AST,
    relative_path: str,
    policy: OfflinePolicy,
) -> set[OfflineFinding]:
    findings: set[OfflineFinding] = set()
    module_aliases: dict[str, str] = {}
    symbol_aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", maxsplit=1)[0]
                module_aliases[local] = alias.name
                if _is_forbidden_import(alias.name, policy) and not _is_allowed_subprocess(
                    relative_path,
                    alias.name,
                    policy,
                ):
                    findings.add(
                        OfflineFinding(
                            path=relative_path,
                            line=node.lineno,
                            kind="FORBIDDEN_IMPORT",
                            symbol=alias.name,
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            imported_module = node.module or ""
            for alias in node.names:
                full_name = (
                    f"{imported_module}.{alias.name}"
                    if imported_module
                    else alias.name
                )
                local = alias.asname or alias.name
                symbol_aliases[local] = full_name
                reported = (
                    full_name
                    if full_name in policy.forbidden_import_names
                    else imported_module
                )
                if (
                    reported
                    and _is_forbidden_import(full_name, policy)
                    and not _is_allowed_subprocess(relative_path, full_name, policy)
                ):
                    findings.add(
                        OfflineFinding(
                            path=relative_path,
                            line=node.lineno,
                            kind="FORBIDDEN_IMPORT",
                            symbol=reported,
                        )
                    )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        symbol = _attribute_name(node.func, module_aliases, symbol_aliases)
        if (
            symbol in policy.forbidden_process_calls
            and symbol is not None
            and not _is_allowed_subprocess(relative_path, symbol, policy)
        ):
            findings.add(
                OfflineFinding(
                    path=relative_path,
                    line=node.lineno,
                    kind="FORBIDDEN_PROCESS_CALL",
                    symbol=symbol,
                )
            )
        if symbol not in {"__import__", "importlib.import_module"}:
            continue
        dynamic_module = _literal_string_argument(node)
        if (
            dynamic_module is not None
            and _is_forbidden_import(dynamic_module, policy)
            and not _is_allowed_subprocess(relative_path, dynamic_module, policy)
        ):
            findings.add(
                OfflineFinding(
                    path=relative_path,
                    line=node.lineno,
                    kind="DYNAMIC_FORBIDDEN_IMPORT",
                    symbol=dynamic_module,
                )
            )
    return findings


def scan_source_tree(
    root: Path,
    policy: OfflinePolicy | None = None,
) -> tuple[OfflineFinding, ...]:
    """Scan Python files below *root* with deterministic root-relative findings."""
    resolved_root = root.resolve()
    selected_policy = policy or default_offline_policy()
    findings: set[OfflineFinding] = set()
    for path in sorted(resolved_root.rglob("*.py")):
        relative_path = path.relative_to(resolved_root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative_path)
        except SyntaxError as error:
            findings.add(
                OfflineFinding(
                    path=relative_path,
                    line=error.lineno or 0,
                    kind="SCAN_ERROR",
                    symbol="SyntaxError",
                )
            )
            continue
        except (OSError, UnicodeError) as error:
            findings.add(
                OfflineFinding(
                    path=relative_path,
                    line=0,
                    kind="SCAN_ERROR",
                    symbol=type(error).__name__,
                )
            )
            continue
        findings.update(_scan_tree(tree, relative_path, selected_policy))
    return tuple(sorted(findings))
