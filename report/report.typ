// HW2 report -- max 6 pages. Compile with: typst compile report.typ report.pdf
#set page(margin: 1.5cm)
#set text(size: 10.5pt)

#align(center)[
  #text(size: 16pt, weight: "bold")[HW2: Traditional Software Design vs Function-as-a-Service]
]

= System Scenario
// TODO: name the chosen scenario (hospital / hotel / airport / university course
// management / other) and list the 7+ operations it implements, one line each.

= Part 1 -- Traditional Architecture
// TODO: describe Traditional/server.py's design: single long-lived process,
// in-memory state (Traditional/services/__init__.py), stdlib http.server.
// Note what a real request/response cycle looks like.

= Part 2 -- FaaS Architecture
// TODO: describe FaaS/gateway.py + FaaS/functions/*: subprocess-per-call,
// external sqlite-backed state (FaaS/storage.py), statelessness/isolation.
// Contrast directly against Part 1 using the shared common/operations.py
// functions as the fixed point of comparison.

= Part 3 -- Feature Extension Challenge
// TODO: pick/describe the new complex feature (own idea or AI-proposed --
// disclose which). Show partial implementation or design diff in both
// architectures. Discuss: how many parts of the system change, how risky
// each change is, which architecture is easier to extend.

= Part 4 -- Performance Evaluation
// TODO: perf stat / perf record results from profiling/run_perf_*.sh,
// comparing execution time, CPU cycles, context switches, memory, syscalls.
// Explain *why* the observed pattern makes sense (e.g. process-spawn +
// interpreter-startup cost per FaaS call vs. one long-lived Traditional
// process). Flamegraphs optional per course amendment -- include if time
// allows (profiling/make_flamegraph.sh).

#table(
  columns: 4,
  [*Metric*], [*Traditional*], [*FaaS*], [*Notes*],
  [Execution time], [], [], [],
  [CPU cycles], [], [], [],
  [Context switches], [], [], [],
  [Memory usage], [], [], [],
)

= Part 5 -- Security and Maintainability (optional per course amendment)
// TODO if time allows: attack surface, isolation between components, risk
// of bugs affecting the whole system, plus one more topic (maintainability /
// code complexity / ease of debugging), backed by concrete observations.

= AI Tool Usage Disclosure
// TODO: per the assignment rules, describe how AI tools were used
// (architectural discussion, scaffolding, etc.) and what was written/decided
// by the team.
