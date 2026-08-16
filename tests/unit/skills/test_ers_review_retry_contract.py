from __future__ import annotations

from pathlib import Path

_SKILL = Path(__file__).parents[3] / ".agents" / "skills" / "ers-review" / "SKILL.md"


def _skill_text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def test_track_outputs_are_written_to_attempt_paths_before_runtime_validation() -> None:
    text = _skill_text()

    assert "track-a-attempt-<N>.json" in text
    assert "track-b-attempt-<N>.json" in text
    assert "canonical `track-a-output.json`" in text
    assert "canonical `track-b-output.json`" in text


def test_validated_success_stops_external_retries_for_that_stage() -> None:
    text = _skill_text()

    assert "WAITING_TRACK_B" in text
    assert "Track A 외부 호출을 다시 수행하지 않는다" in text
    assert "Track B 외부 호출을 다시 수행하지 않는다" in text
    assert "FILEEXISTSERROR" in text
