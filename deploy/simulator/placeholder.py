"""Compose placeholder for the Splunk alert simulator.

Named scenarios and burst mode belong to tools/simulator (QA, T08). This
process does not post webhooks. It only serves /healthz so `make up` can
wait on the simulator service.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8091


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - method name is defined by http.server
        if self.path.split("?", 1)[0] != "/healthz":
            self.send_error(404)
            return
        body = json.dumps({"status": "ok", "mode": "placeholder"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
