#!/usr/bin/env python3
"""UserPromptSubmit hook: append every prompt verbatim to prompts.md."""

import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAX_LEN = 4000


def main() -> None:
    payload = json.load(sys.stdin)
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return

    if len(prompt) > MAX_LEN:
        prompt = prompt[:MAX_LEN] + f"\n... [truncated, {len(prompt)} chars total]"

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"\n## {ts}\n\n```\n{prompt}\n```\n"

    with open(ROOT / "prompts.md", "a") as f:
        f.write(entry)


if __name__ == "__main__":
    main()
