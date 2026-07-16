"""Small helper to start/stop a Traditional HTTP server subprocess for the
concurrency benchmarks, and to POST /invoke against it."""

import json
import socket
import subprocess
import sys
import time
import urllib.request


def wait_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.1)
    raise TimeoutError(f"server on port {port} did not come up")


def start_server(port: int, env: dict) -> subprocess.Popen:
    """Launch `python -m Traditional.server --serve --port <port>` with `env`
    (full environment; caller merges os.environ), wait until it accepts
    connections, and return the process handle."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "Traditional.server", "--serve", "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    wait_port(port)
    return proc


def stop_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def post_invoke(port: int, op: str, params: dict) -> dict:
    body = json.dumps({"op": op, "params": params}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/invoke", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())
