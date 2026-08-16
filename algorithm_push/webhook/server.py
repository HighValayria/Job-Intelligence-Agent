from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from algorithm_push.push import QQBotAdapter, load_qq_bot_config
from algorithm_push.registry import AlgorithmQuestionRepository
from algorithm_push.selector.config_loader import load_selection_config
from algorithm_push.webhook.handler import handle_qq_event


def run_qq_webhook_server(
    *,
    host: str,
    port: int,
    db_path: Path,
    config_path: Path,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path in {"/", "/health"}:
                self._send_json({"ok": True})
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if self.path != "/qq/events":
                self.send_error(404)
                return
            try:
                payload = self._read_json()
                with AlgorithmQuestionRepository(db_path) as repository:
                    repository.initialize()
                    result = handle_qq_event(
                        payload,
                        repository=repository,
                        adapter=QQBotAdapter(load_qq_bot_config(config_path)),
                        selection_config=load_selection_config(config_path),
                    )
                status = 200 if result.handled else 202
                self._send_json(
                    {
                        "handled": result.handled,
                        "sent": bool(result.push_result and result.push_result.ok),
                        "error": result.error,
                    },
                    status=status,
                )
            except Exception as exc:
                self._send_json({"handled": False, "error": str(exc)}, status=500)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} - {format % args}")

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw or "{}")
            if not isinstance(payload, dict):
                raise ValueError("QQ event payload must be a JSON object")
            return payload

        def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"QQ webhook server listening on http://{host}:{port}/qq/events")
    server.serve_forever()
