"""Detached protected loopback server process entrypoint."""

from __future__ import annotations

import argparse
from pathlib import Path

from ansim_review.review_packet.local_server import create_review_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args(argv)
    server = create_review_server(Path(args.workspace), run_tokens={args.run_id: args.token})
    try:
        print(server.server_address[1], flush=True)
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
