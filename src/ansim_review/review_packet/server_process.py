"""Detached protected loopback server process entrypoint."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ansim_review.review_packet.local_server import create_review_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args(argv)
    server = create_review_server(Path(args.workspace), run_tokens={args.run_id: args.token})
    state_path = Path(args.workspace) / "runs" / args.run_id / "review-server.json"
    try:
        port = server.server_address[1]
        state = {"pid": os.getpid(), "port": port, "run_id": args.run_id}
        with state_path.open("x", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
        print(port, flush=True)
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        state_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
