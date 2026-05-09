"""Minimal OpenAI-compatible mock server for integration testing.

Runs in a background thread. Records every request so tests can inspect
exactly what the wrapper sent (compressed or original).
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass  # silence default access log

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        # Record the request on the server instance
        self.server.requests.append({"path": self.path, "body": body})  # type: ignore[attr-defined]

        messages = body.get("messages", [])
        reply_text = f"[mock] Received {len(messages)} message(s)."

        if self.path.rstrip("/").endswith("chat/completions"):
            response = {
                "id": "mock-id",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": reply_text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
            }
        else:
            response = {"error": "unknown path"}

        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class MockOpenAIServer:
    def __init__(self, port: int = 0) -> None:
        self._server = HTTPServer(("127.0.0.1", port), _Handler)
        self._server.requests: list[dict] = []  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    @property
    def requests(self) -> list[dict]:
        return self._server.requests  # type: ignore[attr-defined]

    def start(self) -> "MockOpenAIServer":
        self._thread.start()
        time.sleep(0.05)  # let the socket bind
        return self

    def stop(self) -> None:
        self._server.shutdown()

    def last_messages(self) -> list[dict]:
        if not self.requests:
            return []
        return self.requests[-1]["body"].get("messages", [])

    def clear(self) -> None:
        self.requests.clear()
