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

## 2026-07-21T17:33:33Z

```
I am reading the report @report/report.typ 
it says "All logic lives in one shared modul" - didn't we change it?
```

## 2026-07-21T18:10:11Z

```
explain @script.sh
```

## 2026-07-21T19:09:28Z

```
now let's talk the settings and the results.
I see we simulate only 200 users. what will happend if we simulate 2k or 20k? I assume that we will see better results for FaaS if we have 5k streams or 3k users trying to buy a ticket at the same time - am I wrong?
and another thing - don't we create a simulation over time with all functionalities? mixture of the different functions simulating the usage of real users/athletes/volunteers of the official app running the code we wrote?
```

## 2026-07-21T19:19:13Z

```
In my vision, I see a database of thousends of entries (with timestemps of execution?) performing multiple operations simulating the real olympic games - a venue is saved for a game, an athlete orders himself and his teammates food in one of the restourants while another team is ticketing the hotel which is currently full and then a streaming of a pupular game starts with a peak of streaming followed by ticket selling opened and a mass of users trying to buy tickets to the match and athletes are signed to the shuttle to go back to the room after a game and do their laundry - all this, using ALL functions, randomized, multiplied by hundreds, would be a suitable workload to show FaaS can win in the real world. what do you say?
```

## 2026-07-21T19:26:24Z

```
I just gave examples, we should use the existing ops.
what is the effort of simulating this kind of workload?
```

## 2026-07-21T19:36:43Z

```
don't change existing files. plan the work by steps. check yourself between each step. plan the burst to work appropriatly with the given hardware we have. test should not be too long, but to expose that under stressed workloads FaaS will work better.
```

## 2026-07-21T20:10:12Z

```
now run it locally here to see how it goes, then summarize what we see.
```

## 2026-07-21T20:15:48Z

```
where is the workload we are running?
```

## 2026-07-21T20:17:24Z

```
but we said we want hundreds/thousends of requests to challange the system, we want to see the benefit of FaaS over fully loaded monolith - can we enlarge the workload to give FaaS better results?
```

## 2026-07-21T20:26:43Z

```
write all the tasks summary into "full_throughput_test.md" - this file will be the context for recording this work in the final report by our other agent. make sure you miss nothing - from idea, code generation, testing, change in perspective, and the surprising results when soubled the number of transactions.
```

## 2026-07-21T20:30:40Z

```
give me a one-line commit message for the added uncommited files
```

## 2026-07-22T06:39:48Z

```
using /superpowers we want to evaluate the work done on this project.
the definition and expected result described in @"HW2 guide.pdf" and our report is in @report/report.typ 
1. make sure we answer each of the requested sub-tasks individually
2. make sure we fulfil the requirement of the project
3. evaluate report structure, syntax, logic flow, and appearence

don't change anything, you may create an md file for your summary.
```

## 2026-07-22T07:06:55Z

```
update @EVALUATION.md - are there open items?
```

## 2026-07-22T07:10:42Z

```
assuming the ids are closed - can we delete this file?
```
