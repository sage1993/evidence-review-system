from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from evidence_review.review_packet import server_process


def test_server_process_does_not_consume_linked_state_during_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "RUN-1234567890ABCDEF1234"
    run_directory = tmp_path / "runs" / run_id
    run_directory.mkdir(parents=True)
    state_path = run_directory / "review-server.json"
    external = tmp_path / "external-review-server.json"
    token = "test-token"
    external.write_text(
        server_process.json.dumps(
            {
                "pid": os.getpid(),
                "run_id": run_id,
                "token_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        server_process,
        "create_review_server",
        lambda *_args, **_kwargs: SimpleNamespace(
            server_address=("127.0.0.1", 8123),
            begin_shutdown=lambda: False,
            shutdown=lambda: None,
            server_close=lambda: None,
        ),
    )
    monkeypatch.setattr(server_process, "configure_case_visual_server", lambda _server: None)

    def replace_state_with_link(_server: object) -> None:
        state_path.unlink()
        try:
            state_path.symlink_to(external)
        except OSError as error:
            pytest.skip(f"file symlink creation unavailable: {error}")

    monkeypatch.setattr(server_process, "serve_with_idle_timeout", replace_state_with_link)

    result = server_process.main(
        [
            "--workspace",
            str(tmp_path),
            "--run-id",
            run_id,
            "--token",
            token,
        ]
    )

    assert result == 0
    assert state_path.is_symlink()
    assert external.is_file()
