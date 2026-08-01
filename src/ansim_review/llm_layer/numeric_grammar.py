"""Deterministic scanner for canonical Track A numeric tokens."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NumericToken:
    """One exact numeric token and its original code-point span."""

    text: str
    start: int
    end: int


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
    return not _is_ascii_identifier_character(text[end])


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
