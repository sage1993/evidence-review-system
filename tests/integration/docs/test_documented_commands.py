import os
import re
import subprocess
import sys
from pathlib import Path

_DOCS = (
    "REVIEWER_WORKFLOW.md",
    "CODEX_WORKFLOW.md",
    "CHATGPT_WEB_WORKFLOW.md",
)


def test_documented_smoke_commands_execute_and_do_not_claim_ai_decision() -> None:
    root = Path(__file__).parents[3]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root / "src")
    commands: list[str] = []
    for name in _DOCS:
        text = (root / "docs" / name).read_text(encoding="utf-8")
        assert "AI final decision" not in text
        commands.extend(re.findall(r"```bash smoke\n(.*?)\n```", text, re.S))
    assert len(commands) >= 3
    for block in commands:
        for command in [
            line
            for line in block.splitlines()
            if line.strip() and not line.startswith("#")
        ]:
            executable = f'"{sys.executable}" '
            command = command.replace("python ", executable, 1)
            subprocess.run(
                command,
                cwd=root,
                env=environment,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
            )
