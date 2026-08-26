"""Deterministic scanner for canonical Track A numeric tokens."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NumericToken:
    """One exact numeric token and its original code-point span."""

    text: str
    start: int
    end: int


class UnsupportedNumericSyntax(ValueError):
    """Raised when claim text contains numeric meaning outside the grammar."""


@dataclass(frozen=True, slots=True)
class _OffendingSpan:
    start: int
    end: int


_EXPONENT = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?[0-9]+(?:\.[0-9]+)?[eE][+-]?[0-9]+"
    r"(?![A-Za-z0-9_])"
)
_LEADING_DOT = re.compile(
    r"(?<![A-Za-z0-9_.])[-+]?\.[0-9]+(?![A-Za-z0-9_.])"
)
_UNDERSCORE = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?[0-9]+(?:_[0-9]+)+(?:\.[0-9]+)?%?"
    r"(?![A-Za-z0-9_])"
)
_COMMA_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?[0-9][0-9,]*(?:\.[0-9]+)?%?"
    r"(?![A-Za-z0-9_])"
)
_VALID_GROUPED = re.compile(
    r"[-+]?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?%?"
)
_ATTACHED_MEASUREMENT_UNIT = re.compile(
    r"(?:mm|cm|km|m²|m)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


def _is_ascii_digit(character: str) -> bool:
    return character.isascii() and character.isdigit()


def _is_ascii_identifier_character(character: str) -> bool:
    return character.isascii() and (character.isalnum() or character in "_.")


def _has_valid_left_boundary(text: str, start: int) -> bool:
    if start == 0:
        return True
    previous = text[start - 1]
    return not _is_ascii_identifier_character(previous) and previous not in "+-"


def _has_valid_right_boundary(text: str, end: int) -> bool:
    if end >= len(text):
        return True
    if not _is_ascii_identifier_character(text[end]):
        return True
    return _ATTACHED_MEASUREMENT_UNIT.match(text, end) is not None


def _scan_number_end(text: str, start: int) -> int | None:
    cursor = start
    if text[cursor] in "+-":
        cursor += 1
        if cursor >= len(text) or not _is_ascii_digit(text[cursor]):
            return None

    integer_start = cursor
    while cursor < len(text) and _is_ascii_digit(text[cursor]):
        cursor += 1
    first_group_length = cursor - integer_start
    if first_group_length == 0:
        return None

    if cursor < len(text) and text[cursor] == ",":
        if first_group_length > 3:
            return None
        while cursor < len(text) and text[cursor] == ",":
            cursor += 1
            group_start = cursor
            while cursor < len(text) and _is_ascii_digit(text[cursor]):
                cursor += 1
            if cursor - group_start != 3:
                return None

    if cursor < len(text) and text[cursor] == ".":
        fraction_start = cursor + 1
        cursor = fraction_start
        while cursor < len(text) and _is_ascii_digit(text[cursor]):
            cursor += 1
        if cursor == fraction_start:
            return None

    if cursor < len(text) and text[cursor] == "%":
        cursor += 1
    return cursor


def scan_numeric_tokens(text: str) -> tuple[NumericToken, ...]:
    """Return supported numeric tokens without conversion or normalization."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    tokens: list[NumericToken] = []
    cursor = 0
    while cursor < len(text):
        character = text[cursor]
        is_start = _is_ascii_digit(character) or (
            character in "+-"
            and cursor + 1 < len(text)
            and _is_ascii_digit(text[cursor + 1])
        )
        if not is_start or not _has_valid_left_boundary(text, cursor):
            cursor += 1
            continue
        end = _scan_number_end(text, cursor)
        if end is None or not _has_valid_right_boundary(text, end):
            cursor += 1
            continue
        tokens.append(NumericToken(text=text[cursor:end], start=cursor, end=end))
        cursor = end
    return tuple(tokens)


def extract_numeric_tokens(text: str) -> tuple[str, ...]:
    """Return exact supported token text in source order."""
    return tuple(token.text for token in scan_numeric_tokens(text))


def _consumed_mask(text: str, tokens: tuple[NumericToken, ...]) -> list[bool]:
    consumed = [False] * len(text)
    previous_end = 0
    for token in tokens:
        if (
            token.start < previous_end
            or token.start < 0
            or token.end > len(text)
            or token.start >= token.end
            or text[token.start : token.end] != token.text
        ):
            raise ValueError("numeric token spans are invalid")
        for index in range(token.start, token.end):
            consumed[index] = True
        unit_match = _ATTACHED_MEASUREMENT_UNIT.match(text, token.end)
        if unit_match is not None:
            for index in range(unit_match.start(), unit_match.end()):
                consumed[index] = True
        previous_end = token.end
    return consumed


def _has_unconsumed(consumed: list[bool], start: int, end: int) -> bool:
    return any(not consumed[index] for index in range(start, end))


def _ascii_identifier_span(text: str, index: int) -> tuple[int, int]:
    allowed = set("_-.+")
    start = index
    while start > 0:
        character = text[start - 1]
        if not character.isascii() or not (character.isalnum() or character in allowed):
            break
        start -= 1
    end = index + 1
    while end < len(text):
        character = text[end]
        if not character.isascii() or not (character.isalnum() or character in allowed):
            break
        end += 1
    return start, end


def _is_identifier_digit(text: str, index: int) -> bool:
    start, end = _ascii_identifier_span(text, index)
    return any(character.isalpha() for character in text[start:end])


def _regex_spans(
    pattern: re.Pattern[str],
    text: str,
    consumed: list[bool],
) -> list[_OffendingSpan]:
    return [
        _OffendingSpan(match.start(), match.end())
        for match in pattern.finditer(text)
        if _has_unconsumed(consumed, match.start(), match.end())
    ]


def _unicode_numeric_span(text: str, start: int, consumed: list[bool]) -> int:
    cursor = start
    while cursor < len(text) and not consumed[cursor] and not text[cursor].isascii():
        try:
            unicodedata.numeric(text[cursor])
        except (TypeError, ValueError):
            break
        cursor += 1
    return cursor


def reject_unsupported_numeric_syntax(
    text: str,
    tokens: tuple[NumericToken, ...],
) -> None:
    """Reject the first unconsumed numeric-looking expression deterministically."""
    consumed = _consumed_mask(text, tokens)
    candidates: list[_OffendingSpan] = []
    for pattern in (_EXPONENT, _LEADING_DOT, _UNDERSCORE):
        candidates.extend(_regex_spans(pattern, text, consumed))

    for match in _COMMA_CANDIDATE.finditer(text):
        value = match.group(0)
        if "," not in value or _VALID_GROUPED.fullmatch(value) is not None:
            continue
        if _has_unconsumed(consumed, match.start(), match.end()):
            candidates.append(_OffendingSpan(match.start(), match.end()))

    index = 0
    while index < len(text):
        if consumed[index]:
            index += 1
            continue
        character = text[index]
        if not character.isascii():
            try:
                unicodedata.numeric(character)
            except (TypeError, ValueError):
                index += 1
                continue
            end = _unicode_numeric_span(text, index, consumed)
            candidates.append(_OffendingSpan(index, max(index + 1, end)))
            index = max(index + 1, end)
            continue
        if _is_ascii_digit(character) and not _is_identifier_digit(text, index):
            end = index + 1
            while end < len(text) and _is_ascii_digit(text[end]) and not consumed[end]:
                end += 1
            candidates.append(_OffendingSpan(index, end))
            index = end
            continue
        index += 1

    if not candidates:
        return
    offending = min(
        candidates,
        key=lambda span: (span.start, -(span.end - span.start), span.end),
    )
    fragment = text[offending.start : offending.end]
    raise UnsupportedNumericSyntax(
        "UNSUPPORTED_NUMERIC_SYNTAX "
        f"at {offending.start}:{offending.end}: {fragment}"
    )
