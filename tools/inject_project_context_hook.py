#!/usr/bin/env python3
"""SessionStart hook: inject PROJECT.md's content as additional context so
any session picking up this repo has current project state without asking."""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    content = (ROOT / "PROJECT.md").read_text()
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": content,
        }
    }))


if __name__ == "__main__":
    main()
