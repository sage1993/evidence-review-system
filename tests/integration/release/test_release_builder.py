import json
import shutil
import sqlite3
from pathlib import Path

from ansim_review.release.builder import build_ansim_release


def _workspace(root: Path) -> None:
    repository_root = Path(__file__).parents[3]
    shutil.copytree(
        repository_root / "src/ansim_review",
        root / "src/ansim_review",
    )
    (root / "evidence").mkdir()
    connection = sqlite3.connect(root / "evidence/evidence.sqlite")
    connection.execute("CREATE TABLE evidence(id TEXT PRIMARY KEY)")
    connection.commit()
    connection.close()
    (root / "rules/approved").mkdir(parents=True)
    (root / "rules/approved/R1.json").write_text("{}", encoding="utf-8")
    (root / "rules/manifests").mkdir()
    (root / "rules/manifests/active.json").write_text("{}", encoding="utf-8")
    (root / "formulas").mkdir()
    (root / "formulas/manifest.json").write_text("{}", encoding="utf-8")
    (root / "examples").mkdir()
    (root / "examples/sample-request.json").write_text("{}", encoding="utf-8")
    shutil.copytree(repository_root / "web_runtime", root / "web_runtime")
    (root / "tests/golden/questions").mkdir(parents=True)
    shutil.copy2(
        repository_root / "tests/golden/questions/ansim_cases.json",
        root / "tests/golden/questions/ansim_cases.json",
    )
    (root / "skills").mkdir()
    for index in range(1, 6):
        skill = root / f"skills/0{index}-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(f"# skill {index}", encoding="utf-8")
    (root / "AGENTS.md").write_text("# agents", encoding="utf-8")
    (root / "runs").mkdir()
    (root / "runs/final-review-packet.json").write_text(
        '{"human_decision":null,"status":"READY_FOR_HUMAN_REVIEW"}',
        encoding="utf-8",
    )


def _acceptance(candidate_hash: str, packet_hash: str) -> dict[str, object]:
    check_ids = (
        "SOURCE_IDENTITY",
        "CITATION_PAGE_BBOX",
        "TABLE_AND_VISUAL_EVIDENCE",
        "CALCULATION_TRACE",
        "RULE_VERSION_AND_STATUS",
        "TRACK_A_EXPLANATION",
        "TRACK_B_AUDIT",
        "CONFIDENCE_FACTORS",
        "ABSTENTION_BEHAVIOR",
        "HUMAN_DECISION_SEPARATION",
    )
    return {
        "format": "ansim/human-acceptance",
        "version": 1,
        "reviewer_id": "reviewer@example.com",
        "reviewed_at": "2026-08-01T16:00:00+09:00",
        "signature": "reviewer@example.com:approved",
        "release_candidate_hash": candidate_hash,
        "packet_hash": packet_hash,
        "checks": [
            {
                "check_id": item,
                "status": "PASS",
                "evidence": f"evidence/{item}",
            }
            for item in check_ids
        ],
    }


def test_release_blocks_without_acceptance_then_readies_with_exact_hashes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    blocked = build_ansim_release(root, tmp_path / "blocked")
    assert blocked["format"] == "evidence-review/release"
    assert blocked["release"] == "evidence-review-v1.0"
    assert blocked["status"] == "BLOCKED"
    assert blocked["reason_codes"] == ["MANUAL_ACCEPTANCE_MISSING"]
    assert blocked["tag_allowed"] is False

    candidate_hash = blocked["candidate_hash"]
    packet_hash = blocked["packet_hash"]
    assert isinstance(candidate_hash, str)
    assert isinstance(packet_hash, str)
    acceptance_dir = root / "releases/ansim-v1.0"
    acceptance_dir.mkdir(parents=True)
    (acceptance_dir / "acceptance-record.json").write_text(
        json.dumps(_acceptance(candidate_hash, packet_hash)),
        encoding="utf-8",
    )
    ready = build_ansim_release(root, tmp_path / "ready")
    assert ready["candidate_hash"] == candidate_hash
    assert ready["status"] == "RELEASE_READY"
    assert ready["reason_codes"] == []
    assert ready["tag_allowed"] is True
    assert (tmp_path / "ready/acceptance-record.json").is_file()


def test_release_candidate_ignores_generated_python_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    _workspace(root)

    generated = (
        root
        / "src"
        / "ansim_review"
        / "packaging"
        / "__pycache__"
        / "generated.cpython-313.pyc"
    )
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_bytes(b"first-generated-bytecode")

    first = build_ansim_release(root, tmp_path / "first")

    generated.write_bytes(b"second-different-bytecode")

    egg_info = root / "src" / "ansim_review" / "noise.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text(
        "generated metadata",
        encoding="utf-8",
    )

    second = build_ansim_release(root, tmp_path / "second")

    assert first["candidate_hash"] == second["candidate_hash"]
