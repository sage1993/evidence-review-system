"""Contracts for the presentation-only boundary between review surfaces."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from evidence_review.presentation.tokens import presentation_tokens
from evidence_review.review_packet.html_renderer import render_review_html
from evidence_review.workbench.html_renderer import render_workbench_html


@dataclass(frozen=True)
class _CssDeclaration:
    value: str
    important: bool
    specificity: tuple[int, int, int]
    source_order: int


@dataclass(frozen=True)
class _RenderedNode:
    tag: str
    attributes: tuple[tuple[str, str | None], ...]
    parent: int | None


class _RenderedDomParser(HTMLParser):
    _VOID_TAGS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "source",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__()
        self.nodes: list[_RenderedNode] = []
        self._open_nodes: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node_index = len(self.nodes)
        parent = self._open_nodes[-1] if self._open_nodes else None
        self.nodes.append(_RenderedNode(tag, tuple(attrs), parent))
        if tag not in self._VOID_TAGS:
            self._open_nodes.append(node_index)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent = self._open_nodes[-1] if self._open_nodes else None
        self.nodes.append(_RenderedNode(tag, tuple(attrs), parent))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._open_nodes) - 1, -1, -1):
            if self.nodes[self._open_nodes[index]].tag == tag:
                del self._open_nodes[index:]
                return


def _rendered_nodes(rendered_html: str) -> list[_RenderedNode]:
    parser = _RenderedDomParser()
    parser.feed(rendered_html)
    parser.close()
    return parser.nodes


def _inline_css(rendered_html: str) -> str:
    match = re.search(r"<style\b[^>]*>(?P<css>.*?)</style>", rendered_html, flags=re.DOTALL)
    assert match is not None
    return match.group("css")


def _css_blocks(css: str) -> list[tuple[str, str]]:
    """Return top-level CSS blocks while preserving their source order."""
    blocks: list[tuple[str, str]] = []
    start = 0
    position = 0
    quote: str | None = None

    while position < len(css):
        character = css[position]
        if quote is not None:
            if character == "\\" and position + 1 < len(css):
                position += 2
                continue
            if character == quote:
                quote = None
            position += 1
            continue
        if character in {"'", '"'}:
            quote = character
            position += 1
            continue
        if character != "{":
            position += 1
            continue

        header = css[start:position].strip()
        depth = 1
        body_start = position + 1
        position += 1
        block_quote: str | None = None
        while position < len(css) and depth:
            block_character = css[position]
            if block_quote is not None:
                if block_character == "\\" and position + 1 < len(css):
                    position += 2
                    continue
                if block_character == block_quote:
                    block_quote = None
            elif block_character in {"'", '"'}:
                block_quote = block_character
            elif block_character == "{":
                depth += 1
            elif block_character == "}":
                depth -= 1
            position += 1

        assert depth == 0
        blocks.append((header, css[body_start : position - 1]))
        start = position

    return blocks


def _split_css_list(value: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    parentheses = 0
    brackets = 0
    quote: str | None = None

    for index, character in enumerate(value):
        if quote is not None:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "(":
            parentheses += 1
        elif character == ")":
            parentheses -= 1
        elif character == "[":
            brackets += 1
        elif character == "]":
            brackets -= 1
        elif character == delimiter and parentheses == 0 and brackets == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def _media_applies(query: str, *, medium: str, screen_width: int | None) -> bool:
    normalized = query.lower()
    if re.search(r"\bprint\b", normalized) and medium != "print":
        return False
    if re.search(r"\bscreen\b", normalized) and medium != "screen":
        return False

    for kind, width in re.findall(r"\(\s*(max|min)-width\s*:\s*(\d+)px\s*\)", normalized):
        if screen_width is None:
            return False
        if kind == "max" and screen_width > int(width):
            return False
        if kind == "min" and screen_width < int(width):
            return False
    return True


def _iter_applicable_rules(
    css: str,
    *,
    medium: str,
    screen_width: int | None,
) -> list[tuple[str, str]]:
    rules: list[tuple[str, str]] = []
    without_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    for header, body in _css_blocks(without_comments):
        if header.lower().startswith("@media"):
            query = header[len("@media") :].strip()
            if _media_applies(query, medium=medium, screen_width=screen_width):
                rules.extend(
                    _iter_applicable_rules(body, medium=medium, screen_width=screen_width)
                )
        elif not header.startswith("@"):
            rules.append((header, body))
    return rules


def _node_attribute(node: _RenderedNode, name: str) -> str | None:
    return next((value for attribute, value in node.attributes if attribute == name), None)


def _node_matches_simple_selector(node: _RenderedNode, selector: str) -> bool:
    simple_selector = selector.strip()
    if not simple_selector or re.search(r"[\[\]:+~]", simple_selector):
        return False

    tag_match = re.match(r"(?:[A-Za-z_][\w-]*|\*)", simple_selector)
    if tag_match is not None:
        tag = tag_match.group(0)
        if tag != "*" and node.tag != tag:
            return False
        simple_selector = simple_selector[tag_match.end() :]

    identifiers = re.findall(r"#[A-Za-z_][\w-]*", simple_selector)
    classes = re.findall(r"\.[A-Za-z_][\w-]*", simple_selector)
    remainder = re.sub(r"(?:#[A-Za-z_][\w-]*|\.[A-Za-z_][\w-]*)", "", simple_selector)
    if remainder:
        return False
    if any(_node_attribute(node, "id") != identifier[1:] for identifier in identifiers):
        return False

    node_classes = set((_node_attribute(node, "class") or "").split())
    return all(css_class[1:] in node_classes for css_class in classes)


def _selector_chain(selector: str) -> tuple[list[str], list[str]] | None:
    if re.search(r"[+~]", selector):
        return None
    tokens = re.sub(r"\s*>\s*", " > ", selector.strip()).split()
    if not tokens or tokens[0] == ">" or tokens[-1] == ">":
        return None

    selectors = [tokens[0]]
    combinators: list[str] = []
    pending_combinator = " "
    for token in tokens[1:]:
        if token == ">":
            if pending_combinator == ">":
                return None
            pending_combinator = ">"
            continue
        combinators.append(pending_combinator)
        selectors.append(token)
        pending_combinator = " "
    return selectors, combinators


def _selector_matches_node(selector: str, node_index: int, nodes: list[_RenderedNode]) -> bool:
    chain = _selector_chain(selector)
    if chain is None:
        return False
    selectors, combinators = chain
    if not _node_matches_simple_selector(nodes[node_index], selectors[-1]):
        return False

    current_index = node_index
    for expected_selector, combinator in reversed(
        list(zip(selectors[:-1], combinators, strict=True))
    ):
        parent_index = nodes[current_index].parent
        if combinator == ">":
            if parent_index is None or not _node_matches_simple_selector(
                nodes[parent_index], expected_selector
            ):
                return False
            current_index = parent_index
            continue
        while parent_index is not None and not _node_matches_simple_selector(
            nodes[parent_index], expected_selector
        ):
            parent_index = nodes[parent_index].parent
        if parent_index is None:
            return False
        current_index = parent_index
    return True


def _selector_matches_rendered_target(
    selector: str,
    *,
    target_selector: str,
    nodes: list[_RenderedNode],
) -> bool:
    return any(
        _node_matches_simple_selector(node, target_selector)
        and _selector_matches_node(selector, index, nodes)
        for index, node in enumerate(nodes)
    )


def _balanced_delimited_content(
    value: str,
    opening_position: int,
    *,
    opening_character: str,
    closing_character: str,
) -> tuple[str, int]:
    depth = 1
    position = opening_position + 1
    quote: str | None = None
    while position < len(value) and depth:
        character = value[position]
        if quote is not None:
            if character == "\\" and position + 1 < len(value):
                position += 2
                continue
            if character == quote:
                quote = None
        elif character in {"'", '"'}:
            quote = character
        elif character == opening_character:
            depth += 1
        elif character == closing_character:
            depth -= 1
        position += 1
    assert depth == 0
    return value[opening_position + 1 : position - 1], position


def _balanced_function_content(value: str, opening_parenthesis: int) -> tuple[str, int]:
    return _balanced_delimited_content(
        value,
        opening_parenthesis,
        opening_character="(",
        closing_character=")",
    )


def _specificity(selector: str) -> tuple[int, int, int]:
    id_count = 0
    class_count = 0
    type_count = 0
    position = 0

    while position < len(selector):
        character = selector[position]
        identifier_match = re.match(r"[A-Za-z_][\w-]*", selector[position + 1 :])
        if character == "#" and identifier_match is not None:
            id_count += 1
            position += identifier_match.end() + 1
        elif character == "." and identifier_match is not None:
            class_count += 1
            position += identifier_match.end() + 1
        elif character == "[":
            _attribute, position = _balanced_delimited_content(
                selector,
                position,
                opening_character="[",
                closing_character="]",
            )
            class_count += 1
        elif character == ":":
            pseudo_element = position + 1 < len(selector) and selector[position + 1] == ":"
            name_start = position + 2 if pseudo_element else position + 1
            name_match = re.match(r"[A-Za-z-]+", selector[name_start:])
            if name_match is None:
                position += 1
                continue
            name = name_match.group(0).lower()
            position = name_start + name_match.end()
            if position < len(selector) and selector[position] == "(":
                arguments, position = _balanced_function_content(selector, position)
                if name in {"is", "not", "has"}:
                    argument_specificities = [
                        _specificity(argument.strip())
                        for argument in _split_css_list(arguments, ",")
                        if argument.strip()
                    ]
                    if argument_specificities:
                        maximum = max(argument_specificities)
                        id_count += maximum[0]
                        class_count += maximum[1]
                        type_count += maximum[2]
                elif name != "where":
                    if pseudo_element:
                        type_count += 1
                    else:
                        class_count += 1
            elif pseudo_element or name in {
                "after",
                "before",
                "first-letter",
                "first-line",
                "marker",
                "placeholder",
                "selection",
            }:
                type_count += 1
            else:
                class_count += 1
        elif identifier_match is not None:
            type_count += 1
            position += identifier_match.end() + 1
        else:
            position += 1
    return id_count, class_count, type_count


def _winning_inline_css_declaration(
    rendered_html: str,
    *,
    target_selector: str,
    property_name: str,
    medium: str,
    screen_width: int | None = None,
) -> _CssDeclaration | None:
    """Resolve a property for selectors that match the rendered target element."""
    winner: _CssDeclaration | None = None
    source_order = 0
    nodes = _rendered_nodes(rendered_html)

    for selectors, body in _iter_applicable_rules(
        _inline_css(rendered_html), medium=medium, screen_width=screen_width
    ):
        matching_selectors = [
            selector.strip()
            for selector in _split_css_list(selectors, ",")
            if _selector_matches_rendered_target(
                selector,
                target_selector=target_selector,
                nodes=nodes,
            )
        ]
        for declaration in _split_css_list(body, ";"):
            name, separator, raw_value = declaration.partition(":")
            if separator == "":
                continue
            source_order += 1
            if not matching_selectors or name.strip() != property_name:
                continue
            specificity = max(_specificity(selector) for selector in matching_selectors)
            value = raw_value.strip()
            important = bool(re.search(r"\s*!important\s*$", value, flags=re.IGNORECASE))
            if important:
                value = re.sub(r"\s*!important\s*$", "", value, flags=re.IGNORECASE)
            candidate = _CssDeclaration(value, important, specificity, source_order)
            if winner is None or (
                candidate.important,
                candidate.specificity,
                candidate.source_order,
            ) > (
                winner.important,
                winner.specificity,
                winner.source_order,
            ):
                winner = candidate
    return winner


def _with_inline_css_suffix(rendered_html: str, suffix: str) -> str:
    match = re.search(r"<style\b[^>]*>(?P<css>.*?)</style>", rendered_html, flags=re.DOTALL)
    assert match is not None
    return rendered_html[: match.end("css")] + suffix + rendered_html[match.end("css") :]


def _formal_model() -> dict[str, object]:
    return {
        "run_id": "RUN-PRESENTATION-001",
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "human_decision": None,
        "question": "Is the rendered review authority-distinct?",
        "answer_summary": "Ready for human review.",
        "claims": [],
        "calculations": [],
        "rules": [],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
        "issue_results": [],
        "decision": {
            "allowed_values": [
                "SATISFIED",
                "NOT_SATISFIED",
                "CONDITIONAL",
                "ADDITIONAL_REVIEW_REQUIRED",
            ],
            "human_decision": None,
            "packet_sha256": "a" * 64,
        },
        "metadata": {},
        "summary": {
            "citation_count": 0,
            "missing_input_count": 0,
            "exception_count": 0,
            "conflict_count": 0,
        },
    }


def _workbench_model() -> dict[str, object]:
    return {
        "surface": "workbench",
        "matter_id": "MATTER-PRESENTATION-001",
        "title": "Presentation boundary",
        "revision": 1,
        "issues": [],
        "evidence": [],
        "navigation": None,
        "draft_observations": [],
        "formal_run_history": [],
        "formalize": {
            "expected_revision": 1,
            "enabled": False,
            "blockers": [],
            "confirmation_label": "Formalize this Matter revision.",
        },
    }


def test_shared_visual_tokens_do_not_collapse_surface_authority() -> None:
    tokens = presentation_tokens()

    assert tokens == presentation_tokens()
    assert tokens["control_height_px"] >= 36
    assert set(tokens).isdisjoint({"matter", "packet", "route", "state"})

    formal = render_review_html(_formal_model(), page_image_root=Path("."))
    workbench = render_workbench_html(_workbench_model())

    assert f'--ers-control-height: {tokens["control_height_px"]}px;' in formal
    assert f'--ers-control-height: {tokens["control_height_px"]}px;' in workbench
    assert "button,\ninput {\n  font: inherit;\n}" in workbench
    assert 'data-surface="formal-review"' in formal
    assert 'data-surface="workbench"' in workbench
    assert "human-decision" in formal
    assert "human-decision" not in workbench


def test_formal_review_print_typography_overrides_shared_screen_font_size() -> None:
    formal = render_review_html(_formal_model(), page_image_root=Path("."))

    shared_projection = formal.index("/* shared presentation tokens */")
    print_override = formal.index("@media print {", shared_projection)

    assert print_override > shared_projection
    assert "body {\n    font-size: 11pt;" in formal[print_override:]


def test_formal_review_narrow_status_header_wraps_controls_without_vertical_text() -> None:
    formal = render_review_html(_formal_model(), page_image_root=Path("."))
    flex_wrap = _winning_inline_css_declaration(
        formal,
        target_selector=".header-actions",
        property_name="flex-wrap",
        medium="screen",
        screen_width=390,
    )
    min_width = _winning_inline_css_declaration(
        formal,
        target_selector=".header-actions",
        property_name="min-width",
        medium="screen",
        screen_width=390,
    )

    assert flex_wrap is not None
    assert flex_wrap.value == "wrap"
    assert min_width is not None
    assert min_width.value == "0"


def test_formal_review_narrow_result_summary_resets_fact_grid_span() -> None:
    formal = render_review_html(_formal_model(), page_image_root=Path("."))
    grid_column = _winning_inline_css_declaration(
        formal,
        target_selector=".result-facts",
        property_name="grid-column",
        medium="screen",
        screen_width=390,
    )

    assert grid_column is not None
    assert grid_column.value == "auto"


def test_formal_review_print_hides_the_rendered_viewer_toolbar() -> None:
    formal = render_review_html(_formal_model(), page_image_root=Path("."))
    display = _winning_inline_css_declaration(
        formal,
        target_selector=".viewer-toolbar",
        property_name="display",
        medium="print",
    )

    assert display is not None
    assert display.value == "none"
    assert display.important is True


def test_presentation_cascade_helper_rejects_later_same_specificity_conflicts() -> None:
    formal = _with_inline_css_suffix(
        render_review_html(_formal_model(), page_image_root=Path(".")),
        """
        .header-actions { flex-wrap: nowrap; }
        .result-facts { grid-column: span 2; }
        .viewer-toolbar { display: flex !important; }
        """,
    )

    flex_wrap = _winning_inline_css_declaration(
        formal,
        target_selector=".header-actions",
        property_name="flex-wrap",
        medium="screen",
        screen_width=390,
    )
    grid_column = _winning_inline_css_declaration(
        formal,
        target_selector=".result-facts",
        property_name="grid-column",
        medium="screen",
        screen_width=390,
    )
    display = _winning_inline_css_declaration(
        formal,
        target_selector=".viewer-toolbar",
        property_name="display",
        medium="print",
    )

    assert flex_wrap is not None
    assert flex_wrap.value == "nowrap"
    assert grid_column is not None
    assert grid_column.value == "span 2"
    assert display is not None
    assert display.value == "flex"
    assert display.important is True


def test_presentation_cascade_helper_counts_id_class_and_element_specificity() -> None:
    assert _specificity("article#record.notice") == (1, 1, 1)
    assert _specificity("article::before") == (0, 0, 2)
    assert _specificity(":where(#ignored.notice) article") == (0, 0, 1)
    assert _specificity(":is(.notice, #record)") == (1, 0, 0)
    assert _specificity(":not(.notice, article#record)") == (1, 0, 1)
    assert _specificity("section:has(.notice, #record)") == (1, 0, 1)


def test_presentation_cascade_helper_honors_matching_scoped_selectors() -> None:
    formal = _with_inline_css_suffix(
        render_review_html(_formal_model(), page_image_root=Path(".")),
        """
        .app-shell .header-actions { flex-wrap: nowrap; }
        .app-shell .result-facts { grid-column: span 2; }
        .app-shell .viewer-toolbar { display: flex !important; }
        """,
    )

    flex_wrap = _winning_inline_css_declaration(
        formal,
        target_selector=".header-actions",
        property_name="flex-wrap",
        medium="screen",
        screen_width=390,
    )
    grid_column = _winning_inline_css_declaration(
        formal,
        target_selector=".result-facts",
        property_name="grid-column",
        medium="screen",
        screen_width=390,
    )
    display = _winning_inline_css_declaration(
        formal,
        target_selector=".viewer-toolbar",
        property_name="display",
        medium="print",
    )

    assert flex_wrap is not None
    assert flex_wrap.value == "nowrap"
    assert flex_wrap.specificity == (0, 2, 0)
    assert grid_column is not None
    assert grid_column.value == "span 2"
    assert grid_column.specificity == (0, 2, 0)
    assert display is not None
    assert display.value == "flex"
    assert display.important is True
    assert display.specificity == (0, 2, 0)
