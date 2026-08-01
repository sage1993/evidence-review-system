import math

import pytest

from ansim_review.canonical_json import dump_bytes, dumps, sha256_json


def test_order_independent_json() -> None:
    assert dump_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})


def test_unicode_is_not_ascii_escaped() -> None:
    assert dumps({"text": "안심"}) == '{"text":"안심"}'


def test_non_finite_numbers_are_rejected() -> None:
    with pytest.raises(ValueError):
        dump_bytes({"value": math.nan})
