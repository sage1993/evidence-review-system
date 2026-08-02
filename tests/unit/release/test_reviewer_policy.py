from __future__ import annotations

import pytest

from ansim_review.release.config import ReleaseConfig


def test_release_config_rejects_blank_expected_reviewer_id() -> None:
    with pytest.raises(ValueError, match="expected_reviewer_id"):
        ReleaseConfig(expected_reviewer_id="")
    with pytest.raises(ValueError, match="expected_reviewer_id"):
        ReleaseConfig(expected_reviewer_id=" reviewer@example.com ")


def test_release_config_preserves_exact_expected_reviewer_id() -> None:
    config = ReleaseConfig(expected_reviewer_id="reviewer@example.com")

    assert config.expected_reviewer_id == "reviewer@example.com"
