"""Layer 4 — the HTTP framework driver + idle timer.

A tiny stdlib HTTP server is the entry point for hook events. It does no
business logic: it parses the request body and hands the dict to the controller.
A background timer periodically runs the idle use case so the soundtrack decays
when the agent goes quiet.
"""

from __future__ import annotations

import json
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import Config
from .container import Container

# Max accepted POST body. A hook event is a few hundred bytes; this cap guards the
# local daemon against a memory-exhausting payload while leaving generous headroom.
_MAX_BODY_BYTES = 64 * 1024


def _make_handler(container: Container):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # silence default access logs
            pass

        def do_GET(self) -> None:
            if self.path == "/health":
                self._json(200, {"status": "ok"})
            elif self.path == "/state":
                # Read-only snapshot for visualisers / the menu bar app.
                self._json(200, container.state_snapshot())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path == "/event":
                self._handle(lambda p: container.controller.handle(p))
            elif self.path == "/theme":
                self._handle(self._switch_theme)
            elif self.path == "/voice":
                self._handle(self._switch_voice)
            elif self.path == "/pad":
                self._handle(self._switch_pad)
            elif self.path == "/shutdown":
                # Graceful self-stop for clients that hold no pidfile (the menu
                # app / `hearcode stop` fallback). Reply first, then raise SIGTERM
                # so the main loop runs the same clean shutdown as Ctrl-C.
                self._json(200, {"stopping": True})
                os.kill(os.getpid(), signal.SIGTERM)
            else:
                self._json(404, {"error": "not found"})

        def _switch_theme(self, payload: dict) -> dict:
            ok, msg = container.set_theme(str(payload.get("theme", "")))
            # Always 200 with an `ok` flag so a fire-and-forget caller need not
            # read the body; a bad theme just comes back with ok=false.
            return {"ok": ok, "message": msg, **container.state_snapshot()}

        def _switch_voice(self, payload: dict) -> dict:
            ok, msg = container.set_voice(payload.get("voice") or None)
            return {"ok": ok, "message": msg, **container.state_snapshot()}

        def _switch_pad(self, payload: dict) -> dict:
            ok, msg = container.set_pad_style(str(payload.get("style", "")))
            return {"ok": ok, "message": msg, **container.state_snapshot()}

        def _handle(self, action) -> None:  # noqa: ANN001
            try:
                length = int(self.headers.get("Content-Length", 0))
                # Reject oversized bodies before reading them — a hook payload is a
                # few hundred bytes; anything near this cap is a bug or an attempt to
                # exhaust memory. 413 keeps the local daemon robust to bad input.
                if length > _MAX_BODY_BYTES:
                    self._json(413, {"error": "payload too large"})
                    return
                body = self.rfile.read(length) if length else b"{}"
                payload = json.loads(body or b"{}")
                self._json(200, action(payload))
            except Exception as exc:
                self._json(400, {"error": str(exc)})

        def _json(self, code: int, data: dict) -> None:
            encoded = json.dumps(data).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return Handler


def _start_idle_loop(container: Container, config: Config, stop: threading.Event) -> None:
    def loop() -> None:
        while not stop.wait(config.idle_poll_seconds):
            try:
                container.mark_idle.execute()
            except Exception:
                pass

    threading.Thread(target=loop, name="hearcode-idle", daemon=True).start()


def serve(config: Config, log=print) -> None:
    container = Container(config, log=log)
    stop = threading.Event()
    _start_idle_loop(container, config, stop)

    httpd = ThreadingHTTPServer((config.host, config.port), _make_handler(container))
    log(f"HearCode daemon listening on http://{config.host}:{config.port}")
    log("waiting for agent events…  (Ctrl-C to stop)")

    # `hearcode stop` sends SIGTERM; turn it into the same clean shutdown as Ctrl-C
    # so the audio device is released (the `finally` runs container.shutdown()).
    def _on_term(*_) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _on_term)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("\nstopping…")
    finally:
        stop.set()
        httpd.shutdown()
        container.shutdown()
