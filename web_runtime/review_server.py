"""Localhost-only confirmation and final-review server."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ansim_review.contracts.identifiers import validate_identifier

def _route_path(path: str) -> tuple[str, str, str, str | None] | None:
    parts = [unquote(part) for part in urlsplit(path).path.split("/") if part]
    if len(parts) not in {3, 4} or parts[0] != "runs":
        return None
    if any(part in {".", ".."} or "\\" in part or ":" in part for part in parts):
        return None
    try:
        run_id = validate_identifier(parts[1], "run_id")
    except ValueError:
        return None
    return run_id, parts[2], parts[3] if len(parts) == 4 else None


def create_review_server(workspace_root: Path) -> ThreadingHTTPServer:
    """Create a loopback-only server bound to immutable run artifacts."""
    root = workspace_root.resolve()

    class ReviewHandler(BaseHTTPRequestHandler):
        server_version = "evidence-review-local/1"

        def do_GET(self) -> None:  # noqa: N802
            route = _route_path(self.path)
            if route is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            run_id, kind, candidate_id = route
            run_dir = root / "runs" / run_id
            if kind == "confirmation":
                if candidate_id is not None and not candidate_id:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                artifact = run_dir / "machine" / "drawing-confirmation.json"
                content_type = "application/json; charset=utf-8"
            elif kind == "review" and candidate_id is None:
                packet = run_dir / "final-review-packet.json"
                artifact = run_dir / "review.html"
                if not packet.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                content_type = "text/html; charset=utf-8"
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not artifact.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                payload = artifact.read_bytes()
            except OSError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return ThreadingHTTPServer(("127.0.0.1", 0), ReviewHandler)


__all__ = ["create_review_server"]
