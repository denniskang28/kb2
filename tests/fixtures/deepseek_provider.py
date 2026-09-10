from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote


MODELS = set(filter(None, os.getenv("KB2_FIXTURE_MODELS", "").split(",")))
REQUESTS: list[dict[str, object]] = []
FAIL_MODELS = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def _reply(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/models":
            authenticated = self.headers.get("Authorization", "").startswith("Bearer ")
            REQUESTS.append({"path": self.path, "authenticated": authenticated})
            if not authenticated:
                self._reply(401, {"error": {"code": "unauthorized"}})
            elif FAIL_MODELS:
                self._reply(503, {"error": {"message": "fixture provider unavailable"}})
            else:
                self._reply(200, {"object": "list", "data": [{"id": item} for item in sorted(MODELS)]})
        elif self.path == "/test/requests":
            self._reply(200, {"requests": REQUESTS})
        else:
            REQUESTS.append({"path": self.path, "authenticated": bool(self.headers.get("Authorization"))})
            self._reply(404, {"error": {"code": "not_found"}})

    def do_DELETE(self) -> None:
        prefix = "/test/models/"
        if self.path.startswith(prefix):
            MODELS.discard(unquote(self.path[len(prefix):]))
            self._reply(200, {"status": "removed"})
        else:
            self._reply(404, {"error": {"code": "not_found"}})

    def do_POST(self) -> None:
        global FAIL_MODELS
        prefix = "/test/models/"
        if self.path.startswith(prefix):
            MODELS.add(unquote(self.path[len(prefix):]))
            self._reply(200, {"status": "added"})
        elif self.path == "/test/failure/on":
            FAIL_MODELS = True
            self._reply(200, {"status": "enabled"})
        elif self.path == "/test/failure/off":
            FAIL_MODELS = False
            self._reply(200, {"status": "disabled"})
        else:
            REQUESTS.append({"path": self.path, "authenticated": bool(self.headers.get("Authorization"))})
            self._reply(404, {"error": {"code": "not_found"}})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
