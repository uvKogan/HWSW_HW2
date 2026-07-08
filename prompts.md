# Prompt Log

Raw record of prompts used while building HW2, for the assignment's AI-usage
disclosure requirement ("you may use AI tools for architectural discussion,
but you must clearly describe how you used them").

Two sources feed this file:
- **Automatic**: every prompt sent in a Claude Code session rooted in this
  repo is appended below by a `UserPromptSubmit` hook (see
  `.claude/settings.json` / `tools/log_prompt_hook.py`). No action needed.
- **Manual**: use the `log-prompt` skill (`/log-prompt <text>`) to record a
  prompt used in a *different* tool (e.g. ChatGPT/Gemini for Part 3 feature
  brainstorming), since the hook only sees this session.

See `PROJECT.md`'s "AI usage log" table for the curated summary that should
actually go in `report.pdf` -- this file is the verbatim backing record, not
something to paste wholesale into the 6-page report.
