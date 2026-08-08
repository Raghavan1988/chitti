# Stdlib HTTP API + SSE for the Chitti mobile harness.
"""HTTP surface for the iPhone client.

Endpoints (all require Authorization: Bearer <CHITTI_API_KEY>):

  GET  /health
  POST /v1/sessions
  GET  /v1/sessions/{id}
  GET  /v1/sessions/{id}/events     (SSE)
  POST /v1/sessions/{id}/messages   {"text": "..."}
  POST /v1/sessions/{id}/approvals/{aid}  {"approved": true|false}
  GET  /v1/memory
  PUT  /v1/memory                   {"text": "..."}  full replace

No third-party web framework: ThreadingHTTPServer + JSON + text/event-stream.
"""

from __future__ import annotations

import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import auth
from .config import config
from .store import store
from .tools_mobile import MEMORY_FILE


def _json_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _send_json(handler, status: int, body: dict | list):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
    handler.end_headers()
    handler.wfile.write(data)


def _send_text(handler, status: int, text: str, content_type: str = "text/plain"):
    data = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(data)


class ChittiHandler(BaseHTTPRequestHandler):
    """Route table for the mobile harness API."""

    server_version = "ChittiMobile/0.1"

    def log_message(self, fmt, *args):
        # Quieter than default; still useful for debugging.
        sys_stderr = __import__("sys").stderr
        print(f"[chitti] {self.address_string()} {fmt % args}", file=sys_stderr)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/health":
            return _send_json(self, 200, {"ok": True, "service": "chitti-mobile"})
        if not auth.authorized(self):
            return _send_json(self, 401, {"error": "unauthorized"})
        if path == "/v1/memory":
            return self._get_memory()
        if path.startswith("/v1/sessions/") and path.endswith("/events"):
            sid = path[len("/v1/sessions/") : -len("/events")].strip("/")
            return self._sse(sid)
        if path.startswith("/v1/sessions/"):
            sid = path[len("/v1/sessions/") :].strip("/")
            if "/" not in sid:
                return self._get_session(sid)
        return _send_json(self, 404, {"error": "not found", "path": path})

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/health":
            return _send_json(self, 200, {"ok": True})
        if not auth.authorized(self):
            return _send_json(self, 401, {"error": "unauthorized"})
        try:
            body = _json_body(self)
        except json.JSONDecodeError:
            return _send_json(self, 400, {"error": "invalid json"})

        if path == "/v1/sessions":
            label = (body.get("label") or "mobile")[:40]
            live = store.create(label=label)
            return _send_json(
                self,
                201,
                {
                    "id": live.id,
                    "session_path": live.harness.session_path,
                },
            )

        # /v1/sessions/{id}/messages
        if path.startswith("/v1/sessions/") and path.endswith("/messages"):
            sid = path[len("/v1/sessions/") : -len("/messages")].strip("/")
            return self._post_message(sid, body)

        # /v1/sessions/{id}/approvals/{aid}
        if "/approvals/" in path and path.startswith("/v1/sessions/"):
            rest = path[len("/v1/sessions/") :]
            parts = rest.split("/")
            # {id}/approvals/{aid}
            if len(parts) == 3 and parts[1] == "approvals":
                return self._post_approval(parts[0], parts[2], body)

        return _send_json(self, 404, {"error": "not found", "path": path})

    def do_PUT(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if not auth.authorized(self):
            return _send_json(self, 401, {"error": "unauthorized"})
        if path == "/v1/memory":
            try:
                body = _json_body(self)
            except json.JSONDecodeError:
                return _send_json(self, 400, {"error": "invalid json"})
            text = body.get("text", "")
            mem = Path(config.workdir) / MEMORY_FILE
            mem.parent.mkdir(parents=True, exist_ok=True)
            with open(mem, "w", encoding="utf-8") as f:
                f.write(text if text.endswith("\n") or text == "" else text + "\n")
            return _send_json(self, 200, {"ok": True, "bytes": len(text)})
        return _send_json(self, 404, {"error": "not found"})

    # --- handlers ---

    def _get_memory(self):
        mem = Path(config.workdir) / MEMORY_FILE
        text = mem.read_text(encoding="utf-8") if mem.is_file() else ""
        return _send_json(self, 200, {"text": text, "file": MEMORY_FILE})

    def _get_session(self, sid: str):
        live = store.get(sid)
        if not live:
            return _send_json(self, 404, {"error": "session not found"})
        return _send_json(
            self,
            200,
            {
                "id": live.id,
                "running": live.running,
                "session_path": live.harness.session_path,
                "messages": live.harness.messages,
                "pending_approvals": live.harness.gate.pending_snapshot(),
                "last_error": live.last_error,
            },
        )

    def _post_message(self, sid: str, body: dict):
        live = store.get(sid)
        if not live:
            return _send_json(self, 404, {"error": "session not found"})
        text = (body.get("text") or "").strip()
        if not text:
            return _send_json(self, 400, {"error": "text is required"})
        with live.lock:
            if live.running:
                return _send_json(self, 409, {"error": "session already running a turn"})
            live.running = True
            live.last_error = None

        def worker():
            try:
                live.harness.run(text)
            except Exception as e:
                live.last_error = f"{type(e).__name__}: {e}"
                live.push("error", {"message": live.last_error, "trace": traceback.format_exc()})
            finally:
                with live.lock:
                    live.running = False
                live.push("turn_complete", {"ok": live.last_error is None})

        threading.Thread(target=worker, daemon=True).start()
        return _send_json(self, 202, {"ok": True, "session_id": sid, "accepted": text[:200]})

    def _post_approval(self, sid: str, aid: str, body: dict):
        live = store.get(sid)
        if not live:
            return _send_json(self, 404, {"error": "session not found"})
        approved = bool(body.get("approved"))
        ok = live.harness.gate.resolve(aid, approved)
        if not ok:
            return _send_json(self, 404, {"error": "approval not found or already resolved"})
        live.push("approval_resolved", {"id": aid, "approved": approved})
        return _send_json(self, 200, {"ok": True, "id": aid, "approved": approved})

    def _sse(self, sid: str):
        live = store.get(sid)
        if not live:
            return _send_json(self, 404, {"error": "session not found"})

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Hello event so clients know the stream is live.
        self._sse_write({"kind": "hello", "payload": {"session_id": sid}})

        try:
            while True:
                try:
                    item = live.events.get(timeout=15.0)
                except Exception:
                    # Keep-alive comment
                    try:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    except BrokenPipeError:
                        break
                    continue
                if item is None:
                    break
                if not self._sse_write(item):
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _sse_write(self, item: dict) -> bool:
        try:
            data = json.dumps(item, ensure_ascii=False)
            chunk = f"event: {item.get('kind', 'message')}\ndata: {data}\n\n".encode("utf-8")
            self.wfile.write(chunk)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False


def create_server(host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    """Build a ThreadingHTTPServer bound to host:port."""
    config.ensure_workdir()
    # Put repo root on path is caller's job; workspace ready here.
    addr = (host or config.host, port if port is not None else config.port)
    httpd = ThreadingHTTPServer(addr, ChittiHandler)
    return httpd


def serve_forever(host: str | None = None, port: int | None = None):
    """Run the server until KeyboardInterrupt."""
    httpd = create_server(host, port)
    host_, port_ = httpd.server_address[:2]
    print(f"Chitti mobile harness listening on http://{host_}:{port_}")
    print(f"  workdir: {config.workdir}")
    print(f"  policy:  {config.policy_mode}")
    print(f"  auth:    Bearer {config.api_key[:4]}…")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        httpd.server_close()
