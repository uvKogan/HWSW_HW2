#!/usr/bin/env python3
"""PostToolUse hook (matcher Edit|Write): if STATUS.json was just touched
directly (bypassing tools/sync_status.py), regenerate PROJECT.md from it
so the two can never drift, even from a hand-edit."""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}
    file_path = tool_input.get("file_path") or tool_response.get("filePath") or ""

    if not file_path.endswith("STATUS.json"):
        return

    subprocess.run([sys.executable, str(ROOT / "tools" / "sync_status.py"), "render"], check=False)


if __name__ == "__main__":
    main()
