"""Static validation of commands documented in Markdown."""
from __future__ import annotations

import contextlib
import io
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from ansim_review.cli_parser import build_parser
from ansim_review.documentation_integrity.contract import (
    DocumentationFinding,
    DocumentClassification,
)
from ansim_review.documentation_integrity.markdown import CommandBlock

TOOL_OPTIONS: Mapping[str, Mapping[str, int]] = {
    "pytest": {
        "-v": 0,
        "-q": 0,
        "-k": 1,
        "-m": 1,
        "--maxfail": 1,
        "--tb": 1,
    },
    "ruff check": {
        "--fix": 0,
        "--diff": 0,
        "--output-format": 1,
        "--select": 1,
        "--ignore": 1,
        "--exclude": 1,
        "--target-version": 1,
        "--no-cache": 0,
    },
    "mypy": {
        "--strict": 0,
        "--config-file": 1,
        "--python-version": 1,
        "--show-error-codes": 0,
        "--no-incremental": 0,
        "--cache-dir": 1,
        "--exclude": 1,
    },
    "compileall": {
        "-q": 0,
        "-f": 0,
        "-j": 1,
        "-x": 1,
        "-b": 0,
        "-d": 1,
        "-s": 1,
        "-p": 1,
        "--invalidation-mode": 1,
    },
}

_RECOGNIZED_PLACEHOLDERS = frozenset(
    {
        "<path>",
        "<output>",
        "<SHA256>",
        "${WORKSPACE}",
        "$WORKSPACE",
        "$env:WORKSPACE",
        "%WORKSPACE%",
    }
)
_PLACEHOLDER_RE = re.compile(
    r"^(?:<[^>]+>|\$\{[^}]+\}|\$env:[A-Za-z_][A-Za-z0-9_]*|\$[A-Za-z_][A-Za-z0-9_]*|%[^%]+%)$"
)
_PROMPT_RE = re.compile(r"^(?:PS\s+[^>]*>|>>|\$|>)\s*")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[/\\]")
_RECOGNIZED_EXECUTABLES = frozenset(
    {
        "evidence-review",
        "python",
        "python3",
        "py",
        "pytest",
        "ruff",
        "mypy",
        "bash",
        "sh",
        "pwsh",
        "powershell",
    }
)


class CommandDocument(Protocol):
    @property
    def path(self) -> str: ...

    @property
    def classification(self) -> DocumentClassification: ...


@dataclass(frozen=True, slots=True)
class CommandLine:
    tokens: tuple[str, ...]
    line: int
    raw: str


def _strip_prompt(line: str) -> str:
    return _PROMPT_RE.sub("", line, count=1).strip()


def _continuation_suffix(language: str) -> str:
    return "`" if language in {"powershell", "pwsh"} else "\\"


def _logical_lines(block: CommandBlock) -> tuple[tuple[str, int], ...]:
    logical: list[tuple[str, int]] = []
    accumulated: list[str] = []
    start_line = block.start_line
    suffix = _continuation_suffix(block.language)
    for offset, physical in enumerate(block.text.splitlines()):
        line_number = block.start_line + offset
        stripped = _strip_prompt(physical)
        if not accumulated and (not stripped or stripped.startswith("#")):
            continue
        if not accumulated:
            start_line = line_number
        continued = stripped.endswith(suffix)
        if continued:
            stripped = stripped[: -len(suffix)].rstrip()
        if stripped:
            accumulated.append(stripped)
        if continued:
            continue
        if accumulated:
            logical.append((" ".join(accumulated), start_line))
            accumulated = []
    if accumulated:
        logical.append((" ".join(accumulated), start_line))
    return tuple(logical)


def _token_segments(raw: str) -> tuple[tuple[tuple[str, ...], str], ...]:
    lexer = shlex.shlex(raw, posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    tokens = list(lexer)
    segments: list[tuple[tuple[str, ...], str]] = []
    current: list[str] = []
    for token in tokens:
        if token in {";", "&&", "||", "&"}:
            if current:
                segments.append((tuple(current), " ".join(current)))
                current = []
            continue
        current.append(token)
    if current:
        segments.append((tuple(current), raw if len(segments) == 0 else " ".join(current)))
    return tuple(segments)


def _is_recognized(tokens: Sequence[str]) -> bool:
    return bool(tokens) and tokens[0].casefold() in _RECOGNIZED_EXECUTABLES


def normalize_command_block(block: CommandBlock) -> tuple[CommandLine, ...]:
    """Normalize a fenced command block into independent command lines."""
    result: list[CommandLine] = []
    for raw, line_number in _logical_lines(block):
        segments = _token_segments(raw)
        for tokens, segment_raw in segments:
            if block.language == "text" and not _is_recognized(tokens):
                continue
            if not _is_recognized(tokens):
                continue
            normalized_raw = segment_raw
            if len(segments) == 1:
                normalized_raw = raw
            result.append(CommandLine(tokens=tokens, line=line_number, raw=normalized_raw))
    return tuple(result)


def _cli_arguments(tokens: Sequence[str]) -> tuple[str, ...] | None:
    if not tokens:
        return None
    executable = tokens[0].casefold()
    if executable == "evidence-review":
        return tuple(tokens[1:])
    if executable in {"python", "python3", "py"} and len(tokens) >= 3:
        if tokens[1] == "-m" and tokens[2] in {"ansim_review", "evidence_review"}:
            return tuple(tokens[3:])
    return None


def validate_cli_tokens(tokens: Sequence[str]) -> str | None:
    """Validate project CLI tokens with argparse without dispatching handlers."""
    arguments = _cli_arguments(tokens)
    if arguments is None:
        return "not a project CLI command"
    replaced = tuple(
        "__DOCUMENTATION_PLACEHOLDER__" if token in _RECOGNIZED_PLACEHOLDERS else token
        for token in arguments
    )
    parser = build_parser()
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            parser.parse_args(replaced)
    except SystemExit as error:
        if error.code == 0:
            return None
        return "command does not match the evidence-review parser"
    return None


def _tool_family(tokens: Sequence[str]) -> tuple[str, tuple[str, ...]] | None:
    if not tokens:
        return None
    executable = tokens[0].casefold()
    offset = 1
    family: str | None = None
    if executable in {"python", "python3", "py"} and len(tokens) >= 3 and tokens[1] == "-m":
        module = tokens[2].casefold()
        offset = 3
        if module in {"pytest", "mypy", "compileall"}:
            family = module
        elif module == "ruff" and len(tokens) > offset and tokens[offset] == "check":
            family = "ruff check"
            offset += 1
    elif executable in {"pytest", "mypy"}:
        family = executable
    elif executable == "ruff" and len(tokens) > 1 and tokens[1] == "check":
        family = "ruff check"
        offset = 2
    if family is None:
        return None
    return family, tuple(tokens[offset:])


def _validate_tool_options(family: str, arguments: Sequence[str]) -> str | None:
    registry = TOOL_OPTIONS[family]
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token == "--":
            return None
        if not token.startswith("-") or token == "-":
            index += 1
            continue
        option = token
        inline_value = False
        if token.startswith("--") and "=" in token:
            option, _ = token.split("=", 1)
            inline_value = True
        arity = registry.get(option)
        if arity is None:
            return f"unsupported {family} option: {option}"
        if arity == 1 and not inline_value:
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("-"):
                return f"missing value for {family} option: {option}"
            index += 1
        index += 1
    return None


def _script_target(tokens: Sequence[str]) -> str | None:
    if not tokens:
        return None
    executable = tokens[0].casefold()
    if executable in {"python", "python3", "py"} and len(tokens) >= 2:
        candidate = tokens[1]
        if candidate != "-m" and candidate.casefold().endswith(".py"):
            return candidate
    if executable in {"bash", "sh"} and len(tokens) >= 2:
        candidate = tokens[1]
        if candidate.casefold().endswith(".sh"):
            return candidate
    if executable == "pwsh" and len(tokens) >= 2:
        candidate = tokens[1]
        if candidate.casefold().endswith(".ps1"):
            return candidate
    if executable == "powershell" and len(tokens) >= 3 and tokens[1].casefold() == "-file":
        candidate = tokens[2]
        if candidate.casefold().endswith(".ps1"):
            return candidate
    return None


def _finding(
    document: CommandDocument,
    command: CommandLine,
    *,
    severity: str,
    code: str,
    target: str,
    message: str,
) -> DocumentationFinding:
    return DocumentationFinding(
        severity=severity,  # type: ignore[arg-type]
        code=code,
        document_path=document.path,
        line=command.line,
        column=1,
        target=target,
        message=message,
    )


def _ambiguous_placeholders(tokens: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        token
        for token in tokens
        if _PLACEHOLDER_RE.fullmatch(token)
        and token not in _RECOGNIZED_PLACEHOLDERS
    )


def _safe_script_path(target: str) -> PurePosixPath | None:
    if "\\" in target or target.startswith("/") or _WINDOWS_ABSOLUTE_RE.match(target):
        return None
    path = PurePosixPath(target)
    stack: list[str] = []
    for component in path.parts:
        if component in {"", "."}:
            continue
        if component == "..":
            if not stack:
                return None
            stack.pop()
        else:
            stack.append(component)
    return PurePosixPath(*stack) if stack else None


def validate_command_lines(
    lines: Sequence[CommandLine],
    repository_root: Path,
    document: CommandDocument,
) -> tuple[DocumentationFinding, ...]:
    """Validate normalized command lines without executing any command."""
    if document.classification == "HISTORICAL":
        return ()
    findings: list[DocumentationFinding] = []
    root = repository_root.resolve()
    for command in lines:
        for placeholder in _ambiguous_placeholders(command.tokens):
            findings.append(
                _finding(
                    document,
                    command,
                    severity="WARNING",
                    code="COMMAND_PLACEHOLDER_AMBIGUOUS",
                    target=placeholder,
                    message="Documented placeholder is not in the approved placeholder set.",
                )
            )
        cli_arguments = _cli_arguments(command.tokens)
        if cli_arguments is not None:
            error = validate_cli_tokens(command.tokens)
            if error is not None:
                findings.append(
                    _finding(
                        document,
                        command,
                        severity="ERROR",
                        code="COMMAND_CLI_INVALID",
                        target=command.raw,
                        message="Documented evidence-review command is invalid.",
                    )
                )
            continue
        tool = _tool_family(command.tokens)
        if tool is not None:
            error = _validate_tool_options(*tool)
            if error is not None:
                findings.append(
                    _finding(
                        document,
                        command,
                        severity="ERROR",
                        code="COMMAND_TOOL_OPTION_INVALID",
                        target=command.raw,
                        message="Documented tool command uses an unsupported or incomplete option.",
                    )
                )
            continue
        script = _script_target(command.tokens)
        if script is None:
            continue
        safe = _safe_script_path(script)
        if safe is None:
            findings.append(
                _finding(
                    document,
                    command,
                    severity="ERROR",
                    code="COMMAND_SCRIPT_PATH_INVALID",
                    target=script,
                    message="Documented script path must be repository-relative and safe.",
                )
            )
            continue
        resolved = (root / safe).resolve(strict=False)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            findings.append(
                _finding(
                    document,
                    command,
                    severity="ERROR",
                    code="COMMAND_SCRIPT_MISSING",
                    target=script,
                    message="Documented repository script does not exist.",
                )
            )
    return tuple(findings)
