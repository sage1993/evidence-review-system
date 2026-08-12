import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.golden_cases import run_golden_case
from ansim_review.packaging.web_bundle import build_web_runtime_zip


def _workspace(root: Path) -> None:
    repository_root = Path(__file__).parents[3]
    (root / "src").mkdir(parents=True)
    shutil.copytree(
        repository_root / "src/evidence_review",
        root / "src/evidence_review",
    )
    shutil.copytree(
        repository_root / "src/ansim_review",
        root / "src/ansim_review",
    )
    (root / "evidence").mkdir()
    (root / "evidence/ansim-evidence.sqlite").write_bytes(
        b"SQLite format 3\0fixture"
    )
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


def test_local_and_extracted_web_runtime_deterministic_fields_match_on_paths(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).parents[3]
    cases = json.loads(
        (repository_root / "tests/golden/questions/ansim_cases.json").read_text(
            encoding="utf-8"
        )
    )
    case = next(
        item for item in cases if item["case_id"] == "ratio-below-threshold"
    )
    local = dump_bytes(run_golden_case(case))
    workspace = tmp_path / "workspace"
    _workspace(workspace)
    archive = tmp_path / "runtime.zip"
    build_web_runtime_zip(workspace, archive)
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    for path_hint in ("C:\\Ansim\\workspace", "/opt/ansim/workspace"):
        completed = subprocess.run(
            [
                sys.executable,
                "runtime_runner.py",
                "--case-id",
                case["case_id"],
                "--path-hint",
                path_hint,
            ],
            cwd=extracted,
            capture_output=True,
            check=True,
        )
        assert completed.stdout == local
        assert path_hint.encode() not in completed.stdout
