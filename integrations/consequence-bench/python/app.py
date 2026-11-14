"""Loopback-only live checker experiment. Recorded tool names are never executed."""

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY_BYTES = 4096
ROOT = Path(__file__).resolve().parent
LOCK = threading.Lock()


def strict(raw):
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                raise ValueError("duplicate key")
            d[k] = v
        return d

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
    )


def validate(d):
    if not isinstance(d, dict) or set(d) != {"second_tool", "unknown", "missing_hash"}:
        raise ValueError("invalid fields")
    if not isinstance(d["second_tool"], str) or not re.fullmatch(
        r"[a-zA-Z0-9_-]{0,40}", d["second_tool"]
    ):
        raise ValueError("invalid tool")
    if type(d["unknown"]) is not bool or type(d["missing_hash"]) is not bool:
        raise ValueError("invalid flag")
    return d


def run_check(d, emit):
    run_id = uuid.uuid4().hex

    def event(kind, **data):
        emit({"run_id": run_id, "event": kind, "at_ns": time.time_ns(), **data})

    event("accepted", input=d)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "vendor")

    # Only fixed executable and CLI subcommands. User values enter JSON, never shell.
    def cli(*args):
        p = subprocess.run(
            [sys.executable, "-m", "tracegate.cli", *map(str, args)],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if p.returncode not in (0, 2):
            raise RuntimeError("checker failed")
        return p

    with tempfile.TemporaryDirectory(prefix="trace-live-") as temporary_directory:
        t = Path(temporary_directory)

        def save(n, x):
            p = t / n
            p.write_text(json.dumps(x))
            return p

        rubric = save("rubric.json", {"forbidden_tools": [f"deny_{i}" for i in range(20)]})
        baseline_trace = {
            "name": "demo",
            "messages": [{"tool_calls": [{"id": "first", "function": {"name": "read"}}]}],
        }
        good = save("baseline-trace.json", baseline_trace)
        pin = t / "pin.json"
        event("baseline_started")
        p = cli("freeze", good, "--rubric", rubric, "--out", pin, "--tolerance", "0.05")
        if p.returncode:
            raise RuntimeError("freeze failed")
        event("baseline_completed", sha256=hashlib.sha256(pin.read_bytes()).hexdigest())
        if d["missing_hash"]:
            obj = json.loads(pin.read_text())
            del obj["rubric_sha256"]
            save("pin.json", obj)
        candidate = json.loads(json.dumps(baseline_trace))
        if d["second_tool"]:
            candidate["messages"][0]["tool_calls"].append(
                {"id": "second", "function": {"name": d["second_tool"]}}
            )
        if d["unknown"]:
            candidate["name"] = "not-pinned"
        current = save("current.json", candidate)
        event(
            "check_started",
            trace=candidate,
            sha256=hashlib.sha256(current.read_bytes()).hexdigest(),
        )
        p = cli("check", current, "--rubric", rubric, "--baseline", pin, "--json")
        result = json.loads(p.stdout)
        score = json.loads(cli("score", current, "--rubric", rubric, "--json").stdout)[0]
        event("completed", exit_code=p.returncode, result=result, score=score)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def allowed(self):
        expected = f"127.0.0.1:{self.server.server_port}"
        return self.headers.get("Host") == expected and self.headers.get("Origin") in (
            None,
            "http://" + expected,
        )

    def do_GET(self):
        if not self.allowed():
            self.send_error(403)
            return
        paths = {
            "/": "index.html",
            "/app.js": "app.js",
            "/style.css": "style.css",
            "/receipt.js": "receipt.js",
        }
        if self.path not in paths:
            self.send_error(404)
            return
        p = ROOT / "static" / paths[self.path]
        self.send_response(200)
        self.send_header(
            "Content-Type",
            {"html": "text/html", "js": "text/javascript", "css": "text/css"}[p.suffix[1:]],
        )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'",
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(p.read_bytes())

    def do_POST(self):
        if self.path != "/api/check":
            self.send_error(404)
            return
        if not self.allowed() or self.headers.get("Content-Type") != "application/json":
            self.send_error(403)
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= MAX_BODY_BYTES:
                raise ValueError()
            d = validate(strict(self.rfile.read(n)))
        except (ValueError, TypeError, RecursionError):
            self.send_error(400)
            return
        if not LOCK.acquire(False):
            self.send_error(429)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def emit(x):
            self.wfile.write((json.dumps(x) + "\n").encode())
            self.wfile.flush()

        try:
            run_check(d, emit)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                emit(
                    {
                        "event": "error",
                        "message": "Checker did not complete. No success is claimed.",
                    }
                )
        finally:
            LOCK.release()


def server(port=8765):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    s = server()
    print("Open http://127.0.0.1:8765 (Ctrl+C to stop)", flush=True)
    s.serve_forever()
