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
    assert "`submit-track-b` 성공 응답을 받은 즉시" in text
    assert "직전 `submit-track-b`가 검증 실패를 반환한 경우에만" in text
    assert "브라우저 handoff 실패는 Track B 재생성 사유가 아니다" in text


def test_review_skill_resolves_bound_workspace_without_filesystem_guessing() -> None:
    text = _skill_text()

    assert "evidence-review workspace active" in text
    assert "ACTIVE_WORKSPACE_NOT_BOUND" in text
    assert "ACTIVE_WORKSPACE_STALE" in text
    assert "`evidence.sqlite`를 재귀 검색하지 않는다" in text
