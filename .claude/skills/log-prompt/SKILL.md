---
name: log-prompt
description: Append a prompt to this project's prompts.md AI-usage log, tagged with its source. Use when the user says "log this prompt", "add this to prompts.md", or wants to record an AI interaction that happened outside this Claude Code session (e.g. a ChatGPT/Gemini prompt used for Part 3 feature brainstorming) -- prompts sent inside this session are already auto-logged by a hook, so this skill is for everything the hook can't see.
---

# Log Prompt

Append an entry to `prompts.md` at the project root. This is the manual
complement to the automatic `UserPromptSubmit` hook (`tools/log_prompt_hook.py`),
which already logs every prompt sent inside this Claude Code session. Use
this skill for prompts issued somewhere the hook has no visibility into:
another AI tool, a teammate's session, or something worth logging
retroactively.

## Input

The user will give you either:
- Raw prompt text to log, or
- A prompt plus which tool/model it was sent to (e.g. "log this ChatGPT
  prompt: ...").

If they don't say which tool, ask -- the disclosure requirement is "clearly
describe how you used them," and "which AI" is part of that.

## What to do

1. Read `prompts.md` (don't skip -- Edit requires a prior Read).
2. Append an entry using this format, matching the hook-generated entries'
   style but with an explicit source tag:

   ```
   ## <UTC timestamp, e.g. 2026-07-08T21:15:00Z> (source: <tool name>)

   <prompt text, verbatim, in a fenced code block>
   ```

3. If the user also tells you what the AI's response/suggestion was used
   for, add a one-line note after the code block (e.g. "Used to shape the
   Part 3 predictive-scheduling design; rejected its suggestion to add a
   caching layer as out of scope").
4. Don't summarize or shorten the prompt text itself -- this file is the
   verbatim backing record. Summaries belong in `PROJECT.md`'s "AI usage
   log" table instead (update that too if this entry is significant enough
   to be worth citing in `report.pdf`).
