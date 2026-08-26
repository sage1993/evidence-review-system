"""Detached protected loopback server process entrypoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
from pathlib import Path
from threading import Thread

from evidence_review.review_packet.case_visual_asset_server import (
    configure_case_visual_server,
)
from evidence_review.review_packet.local_server import (
    create_review_server,
    serve_with_idle_timeout,
)
from evidence_review.review_packet.server_runtime import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    validate_idle_timeout,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--reviewer-id")
    parser.add_argument(
        "--idle-timeout-seconds",
        default=DEFAULT_IDLE_TIMEOUT_SECONDS,
        type=validate_idle_timeout,
    )
    args = parser.parse_args(argv)
    reviewer_ids = None if args.reviewer_id is None else {args.run_id: args.reviewer_id}
    server = create_review_server(
        Path(args.workspace),
        run_tokens={args.run_id: args.token},
        reviewer_ids=reviewer_ids,
        idle_timeout_seconds=args.idle_timeout_seconds,
    )
    configure_case_visual_server(server)
    state_path = Path(args.workspace) / "runs" / args.run_id / "review-server.json"
    try:
        port = server.server_address[1]
        state = {
            "pid": os.getpid(),
            "port": port,
            "run_id": args.run_id,
            "token_sha256": hashlib.sha256(args.token.encode("ascii")).hexdigest(),
            "reviewer_id": args.reviewer_id,
            "idle_timeout_seconds": args.idle_timeout_seconds,
        }
        with state_path.open("x", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
        print(port, flush=True)

        def request_shutdown(_signum: int, _frame: object) -> None:
            if server.begin_shutdown():
                Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, request_shutdown)
        signal.signal(signal.SIGINT, request_shutdown)
        serve_with_idle_timeout(server)
    finally:
        server.server_close()
        try:
            current = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = None
        if (
            isinstance(current, dict)
            and current.get("pid") == os.getpid()
            and current.get("run_id") == args.run_id
            and current.get("token_sha256")
            == hashlib.sha256(args.token.encode("ascii")).hexdigest()
        ):
            state_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
