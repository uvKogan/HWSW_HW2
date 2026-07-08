"""
Traditional architecture entry point: one long-lived process holding
all state in memory.

Two run modes:

  python3 -m Traditional.server --serve [--port 8080]
      Runs a real (stdlib-only, no framework) HTTP server. POST a JSON
      body {"op": ..., "params": {...}} to /invoke. Demonstrates this
      is an actual traditional server application, not just a script.

  python3 -m Traditional.server --workload path/to/events.json
      Replays a workload directly in-process (no HTTP/network hop) and
      dumps the final state as JSON to stdout. This is the mode used
      for the Part 4 performance comparison against FaaS/gateway.py,
      so the two systems are compared on business-logic execution,
      not on an incidental network layer.
"""

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from Traditional.services import STATE, dispatch


class InvokeHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/invoke":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        result = dispatch(body["op"], body.get("params", {}))

        payload = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args) -> None:  # noqa: A002 - stdlib signature
        pass  # keep profiling output free of per-request noise


def run_server(port: int) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), InvokeHandler)
    print(f"Traditional server listening on http://127.0.0.1:{port}/invoke")
    httpd.serve_forever()


def run_workload(path: str) -> None:
    events = json.loads(open(path).read())
    for event in events:
        dispatch(event["op"], event["params"])
    json.dump(STATE, sys.stdout, indent=2, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--workload", type=str)
    args = parser.parse_args()

    if args.serve:
        run_server(args.port)
    elif args.workload:
        run_workload(args.workload)
    else:
        parser.error("pass --serve or --workload PATH")


if __name__ == "__main__":
    main()
