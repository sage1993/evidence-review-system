"""Compact presentation preserves authority while deferring secondary content."""
from html.parser import HTMLParser

from evidence_review.review_packet.render_decision import render_decision_form
from evidence_review.review_packet.render_summary import render_summary
from evidence_review.review_packet.render_workspace import render_workspace
from tests.unit.review_packet.test_formal_review_summary_ux import _model


class Elements(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_question_is_not_duplicated_for_assistive_technology():
    model = _model()
    html = render_summary(model)
    assert html.count(str(model['question'])) == 1
    assert 'summary-attention' in html
    assert 'parking-count' in html


def test_secondary_results_are_in_closed_disclosure_not_deleted():
    html = render_workspace(_model(), status_question='question',
                            evidence_workspace='evidence', detail_issue_results='unique-gap',
                            human_decision='decision', audit='audit')
    elements = Elements(html).elements
    disclosures = [attrs for tag, attrs in elements if tag == 'details'
                   and attrs.get('id') == 'review-details']
    assert len(disclosures) == 1
    assert 'open' not in disclosures[0]
    assert 'unique-gap' in html


def test_decision_editor_starts_closed_with_explicit_open_and_cancel():
    html = render_decision_form(_model())
    elements = Elements(html).elements
    editor = next(attrs for _, attrs in elements if 'data-decision-editor' in attrs)
    assert 'hidden' in editor
    assert any(tag == 'button' and 'data-add-decision' in attrs for tag, attrs in elements)
    assert any(tag == 'button' and 'data-cancel-decision' in attrs for tag, attrs in elements)
    assert 'notes help' not in html
    assert 'name="packet_hash"' not in html


def test_explicit_packet_answer_is_not_hidden_with_repeated_status():
    model = _model()
    model['answer_summary'] = 'Packet-backed answer'
    html = render_summary(model)
    assert 'class="result-conclusion-block">' in html
    assert 'Packet-backed answer' in html
