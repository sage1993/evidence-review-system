"""Bounded, deterministic Markdown structure extraction."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

_COMMAND_LANGUAGES = frozenset(
    {"powershell", "pwsh", "bash", "sh", "shell", "console", "text"}
)
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_ATX_RE = re.compile(r"^( {0,3})(#{1,6})[ \t]+(.+?)[ \t]*$")
_SETEXT_RE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
_REFERENCE_DEFINITION_RE = re.compile(
    r"^ {0,3}\[((?:\\.|[^\]])+)\]:[ \t]*(?:<([^>]+)>|(\S+))"
)
_RAW_URL_RE = re.compile(
    r"(?:https?|ftp)://[^\s<>()\[\]{}]+|(?<![:/])//[A-Za-z0-9][^\s<>()\[\]{}]*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class MarkdownHeading:
    text: str
    anchor: str
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class MarkdownLink:
    label: str
    target: str
    is_image: bool
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class CommandBlock:
    language: str
    text: str
    start_line: int


@dataclass(frozen=True, slots=True)
class MarkdownRawUrl:
    target: str
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class ParsedMarkdown:
    headings: tuple[MarkdownHeading, ...]
    links: tuple[MarkdownLink, ...]
    command_blocks: tuple[CommandBlock, ...]
    raw_urls: tuple[MarkdownRawUrl, ...]
    first_non_empty_line: str | None


def normalize_heading_anchor(text: str) -> str:
    """Normalize one heading using the repository's frozen anchor policy."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    kept = "".join(
        character
        for character in normalized
        if character.isalnum()
        or character in {"_", "-"}
        or character.isspace()
    )
    collapsed = re.sub(r"\s+", "-", kept)
    collapsed = re.sub(r"-+", "-", collapsed).strip("-")
    return collapsed or "section"


def assign_heading_anchors(headings: Sequence[str]) -> tuple[str, ...]:
    """Assign stable duplicate suffixes to normalized heading anchors."""
    counts: dict[str, int] = {}
    result: list[str] = []
    for heading in headings:
        base = normalize_heading_anchor(heading)
        count = counts.get(base, 0)
        result.append(base if count == 0 else f"{base}-{count}")
        counts[base] = count + 1
    return tuple(result)


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _mask_inline_code(line: str) -> str:
    masked = list(line)
    index = 0
    while index < len(line):
        if line[index] != "`" or _is_escaped(line, index):
            index += 1
            continue
        end_of_run = index
        while end_of_run < len(line) and line[end_of_run] == "`":
            end_of_run += 1
        delimiter = line[index:end_of_run]
        closing = line.find(delimiter, end_of_run)
        if closing < 0:
            index = end_of_run
            continue
        for position in range(index, closing + len(delimiter)):
            masked[position] = " "
        index = closing + len(delimiter)
    return "".join(masked)


def _unescape_markdown(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def _reference_key(label: str) -> str:
    return " ".join(_unescape_markdown(label).split()).casefold()


def _extract_target(contents: str) -> str:
    value = contents.strip()
    if value.startswith("<"):
        closing = value.find(">", 1)
        if closing >= 0:
            return value[1:closing]
    target: list[str] = []
    escaped = False
    depth = 0
    for character in value:
        if escaped:
            target.append(character)
            escaped = False
            continue
        if character == "\\":
            escaped = True
            target.append(character)
            continue
        if character == "(":
            depth += 1
        elif character == ")" and depth > 0:
            depth -= 1
        if character.isspace() and depth == 0:
            break
        target.append(character)
    return "".join(target)


def _find_closing_bracket(text: str, start: int) -> int | None:
    index = start
    while index < len(text):
        if text[index] == "]" and not _is_escaped(text, index):
            return index
        index += 1
    return None


def _find_closing_parenthesis(text: str, start: int) -> int | None:
    depth = 1
    index = start
    while index < len(text):
        character = text[index]
        if _is_escaped(text, index):
            index += 1
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _extract_line_links(
    line: str,
    masked_line: str,
    line_number: int,
    definitions: dict[str, str],
) -> tuple[list[MarkdownLink], list[tuple[int, int]]]:
    links: list[MarkdownLink] = []
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(masked_line):
        image = masked_line.startswith("![", index)
        if image:
            bracket = index + 1
        elif masked_line[index] == "[":
            bracket = index
        else:
            index += 1
            continue
        if _is_escaped(masked_line, bracket):
            index = bracket + 1
            continue
        label_end = _find_closing_bracket(masked_line, bracket + 1)
        if label_end is None:
            index = bracket + 1
            continue
        label = _unescape_markdown(line[bracket + 1 : label_end])
        cursor = label_end + 1
        target: str | None = None
        end = cursor
        if cursor < len(masked_line) and masked_line[cursor] == "(":
            closing = _find_closing_parenthesis(masked_line, cursor + 1)
            if closing is not None:
                target = _extract_target(line[cursor + 1 : closing])
                end = closing + 1
        elif cursor < len(masked_line) and masked_line[cursor] == "[":
            reference_end = _find_closing_bracket(masked_line, cursor + 1)
            if reference_end is not None:
                reference = line[cursor + 1 : reference_end]
                key = _reference_key(reference or label)
                target = definitions.get(key)
                end = reference_end + 1
        else:
            target = definitions.get(_reference_key(label))
            end = cursor
        if target is None:
            index = max(cursor, bracket + 1)
            continue
        links.append(
            MarkdownLink(
                label=label,
                target=target,
                is_image=image,
                line=line_number,
                column=index + 1,
            )
        )
        spans.append((index, end))
        index = max(end, index + 1)
    return links, spans


def _mask_spans(text: str, spans: Sequence[tuple[int, int]]) -> str:
    result = list(text)
    for start, end in spans:
        for index in range(start, min(end, len(result))):
            result[index] = " "
    return "".join(result)


def _trim_raw_url(value: str) -> str:
    return value.rstrip(".,;:!?")


def _fence_ranges_and_commands(
    lines: list[str],
) -> tuple[set[int], tuple[CommandBlock, ...]]:
    blocked: set[int] = set()
    blocks: list[CommandBlock] = []
    index = 0
    while index < len(lines):
        opening = _FENCE_RE.match(lines[index])
        if opening is None:
            index += 1
            continue
        fence = opening.group(1)
        fence_character = fence[0]
        info = opening.group(2).strip()
        language = info.split(maxsplit=1)[0].casefold() if info else ""
        closing_index = index + 1
        closing_re = re.compile(
            rf"^ {{0,3}}{re.escape(fence_character)}{{{len(fence)},}}[ \t]*$"
        )
        while (
            closing_index < len(lines)
            and closing_re.match(lines[closing_index]) is None
        ):
            closing_index += 1
        content_end = closing_index if closing_index < len(lines) else len(lines)
        blocked.update(range(index, min(closing_index + 1, len(lines))))
        if language in _COMMAND_LANGUAGES:
            blocks.append(
                CommandBlock(
                    language=language,
                    text="\n".join(lines[index + 1 : content_end]),
                    start_line=index + 2,
                )
            )
        index = closing_index + 1 if closing_index < len(lines) else len(lines)
    return blocked, tuple(blocks)


def parse_markdown(text: str) -> ParsedMarkdown:
    """Extract bounded Markdown structures without executing or rendering it."""
    lines = text.splitlines()
    first_non_empty = next((line.strip() for line in lines if line.strip()), None)
    blocked, command_blocks = _fence_ranges_and_commands(lines)

    definitions: dict[str, str] = {}
    definition_lines: set[int] = set()
    for index, line in enumerate(lines):
        if index in blocked:
            continue
        match = _REFERENCE_DEFINITION_RE.match(_mask_inline_code(line))
        if match is None:
            continue
        target = match.group(2) or match.group(3)
        definitions.setdefault(_reference_key(match.group(1)), target)
        definition_lines.add(index)

    raw_headings: list[tuple[str, int, int]] = []
    index = 0
    while index < len(lines):
        if index in blocked:
            index += 1
            continue
        line = lines[index]
        atx = _ATX_RE.match(line)
        if atx is not None:
            heading_text = re.sub(r"[ \t]+#+[ \t]*$", "", atx.group(3)).strip()
            raw_headings.append((heading_text, index + 1, atx.start(3) + 1))
            index += 1
            continue
        if (
            line.strip()
            and index + 1 < len(lines)
            and index + 1 not in blocked
            and _SETEXT_RE.match(lines[index + 1]) is not None
        ):
            heading_text = line.strip()
            raw_headings.append(
                (
                    heading_text,
                    index + 1,
                    len(line) - len(line.lstrip()) + 1,
                )
            )
            index += 2
            continue
        index += 1

    anchors = assign_heading_anchors([heading[0] for heading in raw_headings])
    headings = tuple(
        MarkdownHeading(text=value[0], anchor=anchor, line=value[1], column=value[2])
        for value, anchor in zip(raw_headings, anchors, strict=True)
    )

    links: list[MarkdownLink] = []
    raw_urls: list[MarkdownRawUrl] = []
    for index, line in enumerate(lines):
        if index in blocked or index in definition_lines:
            continue
        masked = _mask_inline_code(line)
        line_links, spans = _extract_line_links(
            line,
            masked,
            index + 1,
            definitions,
        )
        links.extend(line_links)
        raw_scan = _mask_spans(masked, spans)
        for match in _RAW_URL_RE.finditer(raw_scan):
            target = _trim_raw_url(match.group(0))
            if target:
                raw_urls.append(
                    MarkdownRawUrl(
                        target=target,
                        line=index + 1,
                        column=match.start() + 1,
                    )
                )

    return ParsedMarkdown(
        headings=headings,
        links=tuple(links),
        command_blocks=command_blocks,
        raw_urls=tuple(raw_urls),
        first_non_empty_line=first_non_empty,
    )
