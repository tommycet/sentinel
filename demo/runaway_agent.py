"""Runaway agent simulation for Sentinel demo.

Simulates an agent that makes 5 normal (distinct) tool calls, then 15 identical
failing calls to the same tool with the same args — the signature of a runaway
loop. Repetition counting is keyed on (tool, args_hash); quarantine triggers
exactly once when repetition count reaches the threshold (8 by default).

Stdlib only. Testable via dependency injection: pass mock post/sleep functions.

Usage:
    python3 demo/runaway_agent.py [--url URL] [--threshold N] [--window-seconds N]
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Iterator, Tuple
from urllib.parse import urlsplit

# Policy defaults (mirror policies/runaway-tool-loop.yaml)
DEFAULT_THRESHOLD = 8
DEFAULT_WINDOW_SECONDS = 60

# Demo infrastructure defaults
DEFAULT_MOCK_PORT = 8099


def canonicalize_args(args: dict) -> str:
    """Return a stable SHA256 hex digest of args, order-independent.

    Two dicts with the same keys/values produce the same hash regardless of
    insertion order. Used to key repetition counts.
    """
    blob = json.dumps(args, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def call_sequence() -> Iterator[Tuple[str, dict]]:
    """Yield 5 distinct normal calls, then 15 identical failing calls.

    The first 5 use unique tools (tool_0..tool_4) with distinct args.
    The last 15 all use 'failing_tool' with {"query": "bad"} — the runaway loop.
    """
    for i in range(5):
        yield (f"tool_{i}", {"arg": i, "call": i})
    for _ in range(15):
        yield ("failing_tool", {"query": "bad"})


def run_demo(
    post_fn: Callable[[str, dict, dict], object],
    sleep_fn: Callable[[float], None],
    *,
    url: str = "http://localhost:8099/mcp",
    threshold: int = DEFAULT_THRESHOLD,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
):
    """Run the runaway agent simulation with injected post/sleep.

    Repetition counter is keyed on (tool, args_hash). When any key's count
    reaches `threshold`, quarantine fires exactly once for that key and the key
    is marked quarantined. Further repetitions of an already-quarantined key
    do not re-trigger.

    Args:
        post_fn: callable(url, data, headers) -> response object with .status, .read()
        sleep_fn: callable(seconds) — pause between calls.
        url, threshold, window_seconds: demo knobs.
    """
    counts: dict[Tuple[str, str], int] = {}
    quarantined: set[Tuple[str, str]] = set()

    for tool, args in call_sequence():
        args_hash = canonicalize_args(args)
        key = (tool, args_hash)
        counts[key] = counts.get(key, 0) + 1
        n = counts[key]

        data = {"tool": tool, "args": args, "repetition": n}
        post_fn(url, data, {"Content-Type": "application/json"})
        sleep_fn(0.05)

        if n >= threshold and key not in quarantined:
            quarantined.add(key)
            print(
                f"QUARANTINE: tool={tool} args_hash={args_hash[:12]} "
                f"repetition={n} threshold={threshold} window={window_seconds}s"
            )


# --- Mock MCP endpoint (for standalone demo run) ----------------------------


class _MockMCPHandler(BaseHTTPRequestHandler):
    """Tiny endpoint that logs incoming tool calls. No business logic."""

    def log_message(self, format, *args):  # noqa: A002 - signature from base
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}
        print(
            f"[mock-mcp] tool={payload.get('tool')} "
            f"repetition={payload.get('repetition')}"
        )
        resp = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


def _start_mock_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), _MockMCPHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def _real_post(url: str, data: dict, headers: dict) -> http.client.HTTPResponse:
    """Default post_fn: stdlib http.client POST."""
    parsed = urlsplit(url)
    if parsed.scheme == "https":
        conn_cls = http.client.HTTPSConnection
    else:
        conn_cls = http.client.HTTPConnection
    body = json.dumps(data).encode()
    conn = conn_cls(parsed.hostname or "localhost", parsed.port or 80)
    path = parsed.path or "/"
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    resp.read()  # drain so the connection can close cleanly
    conn.close()
    return resp


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Runaway agent simulation for Sentinel"
    )
    parser.add_argument(
        "--url",
        default=None,
        help="MCP-style endpoint to POST each call to. If omitted, start a local mock.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help="Quarantine repetition threshold (default: 8)",
    )
    parser.add_argument(
        "--window-seconds",
        type=int,
        default=DEFAULT_WINDOW_SECONDS,
        help="Sliding window in seconds (default: 60)",
    )
    parser.add_argument(
        "--mock-port",
        type=int,
        default=DEFAULT_MOCK_PORT,
        help="Port for the local mock MCP server when --url is not given.",
    )
    args = parser.parse_args()

    mock_server = None
    target_url = args.url
    if not target_url:
        mock_server = _start_mock_server(args.mock_port)
        target_url = f"http://localhost:{args.mock_port}/mcp"
        print(f"[demo] mock MCP server on http://localhost:{args.mock_port}/mcp")

    try:
        run_demo(
            _real_post,
            time.sleep,
            url=target_url,
            threshold=args.threshold,
            window_seconds=args.window_seconds,
        )
    finally:
        if mock_server is not None:
            mock_server.shutdown()


if __name__ == "__main__":
    main()
