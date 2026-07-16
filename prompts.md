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

## Backfill note (2026-07-16)

The `UserPromptSubmit` hook was broken for this entire session: its command
in `.claude/settings.json` was hardcoded to a teammate's absolute Linux path
(`/home/yuvalk/HWSW/HWSW_HW2/tools/log_prompt_hook.py`), which doesn't exist
on this machine, so it silently failed every time (`2>/dev/null || true`
swallows the error). Fixed to a relative path. The entries below are
reconstructed from conversation context, not the hook's raw capture, so
timestamps are approximate (ordering is accurate, exact times are not).

## 2026-07-16T00:00:00Z (source: Claude Code session, backfilled -- hook was broken)

```
/plan Let's plan how to solve HW2 guide.pdf and update all the mds
accordingly, Our General idea is to create an "Olympic Games" management
system i.e. given players, competition and venues, let's build a system
for assignment, live tournament management and maybe even livestreaming
```
Kicked off HW2 planning; led to reading the existing dual-architecture
scaffold and choosing the Olympics scenario.

## 2026-07-16T00:05:00Z (source: Claude Code session, backfilled -- hook was broken)

```
Plan-mode clarifying answers: (1) Part 3's new op ships in the same main
workload/script.sh run, not a separate demo fixture. (2) Part 5
(security/maintainability) is skipped -- optional per course amendment.
(3) Scenario name: "Olympic Games Management System".
```
Locked in scope for Parts 3-5 and the scenario title.

## 2026-07-16T00:10:00Z (source: Claude Code session, backfilled -- hook was broken)

```
Things that our system can manage (You can add more or don't use these):
1. Hotel bookings
2. Shuttle service
3. Venue allocation for tournament phases (Maybe use the real LA 2026 venues)
4. Resteraunt reservations for atheletes
5. Laundry service
6. high throughput ticketing system (with locking maybe) - good for
   benchmark and traditional vs newer
7. Live streaming
8. Live push events (who won, what happened, medals)
9. scoring for each country
10. Volunteer allocation

Remember that we need at least 7 and adding a new one later (hopefully
some interesting example)
```
Replaced the initial 7-op placeholder rename with a richer, more diverse
operation menu; became the basis for the final 9-op catalog + go_live
Part 3 feature.

## 2026-07-16T00:15:00Z (source: Claude Code session, backfilled -- hook was broken)

```
[Plan approval rejected] I'm sending this plan to Ultraplan to be refined
remotely. Let me know it's been handed off and that a web link will appear
here in a moment...
```
Plan was sent to a parallel cloud (Ultraplan) session for independent
refinement while local iteration continued.

## 2026-07-16T00:20:00Z (source: Claude Code session, backfilled -- hook was broken)

```
Couple of notes
1. we need a countries/athletes/volunteers database no?
2. too much focus on volunteers - we can add restaurants/shuttles/both
3. how push events will work? you need also to subscribe to events am I right?
4. We need to simulate Users in some manner how do you plan to approach this
```
Directly shaped four plan sections: `common/reference_data.py`, the
rebalanced op list (dropped a volunteer op, added shuttle + restaurant),
the `subscribe_to_updates`/`push_live_event` pub-sub pair, and the
`common/concurrent_clients.py` concurrency demo.

## 2026-07-16T00:25:00Z (source: Claude Code session, backfilled -- hook was broken)

```
Also maybe the ticketing should take into account the seating this will
be more interesting since you need to lock only specific seats and not
just a counter
```
Changed `book_ticket` from a capacity counter to seat-level booking
(`seat_id -> user_id`), sharpening the concurrency race demo to a provable
double-sold-seat scenario instead of a miscounted tally.

## 2026-07-16T00:30:00Z (source: Claude Code session, backfilled -- hook was broken)

```
I want to turn this plan into an "execution tracker" that you can work and
update live this way We can see what is happening, also try to say when a
commit should happen and let's commit small advancements to git, the most
important thing is to plan small steps to follow during execution.
```
Restructured the plan file into phases A-G with explicit commit
boundaries, later mirrored into `PROJECT.md`.

## 2026-07-16T00:35:00Z (source: Claude Code session, backfilled -- hook was broken)

```
First, I think the skills don't work, are they loaded for you, second, can
you please first update the documents with the Execution tracker and then
launch the phases?
```
Led to discovering and fixing the broken hook (hardcoded absolute path)
and front-loading the STATUS.json/PROJECT.md updates before Phase A.

## 2026-07-16T00:40:00Z (source: Claude Code session, backfilled -- hook was broken)

```
Also rerun the skills like updating the prompts?
```
This entry -- backfilling the prompt log by hand via the `log-prompt`
skill since the automatic hook missed the whole session.
