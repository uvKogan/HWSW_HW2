"""
Timestamp-paced, bounded-concurrency dispatcher for bench/mixed_burst.py.

Every existing bench/*.py script fires its whole task list at once via
`ThreadPoolExecutor(max_workers=len(tasks))` -- fine for a few dozen tasks,
but firing "hundreds" of FaaS calls that way means hundreds of simultaneous
subprocess spawns at once (a fork-storm, not a serverless platform). This
module instead:

  1. paces *submission* of each event to its scheduled "t" (from
     bench/burst_workload.py's timeline), using real wall-clock time, and
  2. caps *execution* concurrency with a fixed-size thread pool,

so a burst applies real, bounded pressure instead of either firing everything
at once or serializing everything. Submission never blocks on completion
(ThreadPoolExecutor.submit queues internally), so if a phase saturates the
pool, dispatch stays on schedule while completions trail behind -- exactly
the "queueing under load" behaviour a real platform would show.

Run standalone against a synthetic stub to verify pacing and the concurrency
cap before pointing this at real ops:

    python -m bench.bounded_dispatch --selftest --pool-size 8
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field


@dataclass
class _Progress:
    total: int
    phase_totals: dict
    lock: threading.Lock = field(default_factory=threading.Lock)
    done: int = 0
    phase_done: dict = field(default_factory=dict)
    phase_first_start: dict = field(default_factory=dict)
    in_flight: int = 0
    max_in_flight: int = 0
    start_ts: float = 0.0

    def record_start(self, phase: str, now: float) -> None:
        with self.lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            self.phase_first_start.setdefault(phase, now)

    def record_done(self, phase: str, now: float, label: str) -> None:
        with self.lock:
            self.in_flight -= 1
            self.done += 1
            self.phase_done[phase] = self.phase_done.get(phase, 0) + 1
            self._print_locked(phase, now, label)

    def _print_locked(self, phase: str, now: float, label: str) -> None:
        elapsed = now - self.start_ts
        pct = 100.0 * self.done / self.total if self.total else 100.0

        eta = None
        first = self.phase_first_start.get(phase)
        if first is not None and now > first:
            rate = self.phase_done[phase] / (now - first)
            remaining_here = self.phase_totals.get(phase, 0) - self.phase_done[phase]
            if rate > 0:
                eta = max(0.0, remaining_here / rate)
        eta = eta or 0.0
        # Phases not yet started: approximate their remaining cost as "0" here
        # (added by the caller, which knows each phase's scheduled window) --
        # kept simple in this module, refined per-op by mixed_burst.py's
        # phase-window knowledge if a tighter estimate is needed.

        prefix = f"{label} " if label else ""
        line = (f"\r{prefix}{pct:5.1f}% ({self.done}/{self.total}, phase: {phase}) "
                f"-- elapsed {elapsed:5.1f}s, ETA ~{eta:4.1f}s (this phase)")
        print(line, end="", file=sys.stderr, flush=True)
        if self.done == self.total:
            print(f"\r{prefix}100.0% done in {elapsed:.1f}s" + " " * 20, file=sys.stderr)


def run_timeline(events: list[dict], call_fn, pool_size: int, speed: float = 1.0,
                  label: str = "") -> list[dict]:
    """Dispatch `events` (each a dict with "t", "phase", "op", "params") against
    `call_fn(op, params) -> result`, pacing submission to each event's "t"
    (scaled by 1/speed) and capping concurrent execution at `pool_size`.

    Returns one record per event: {"phase", "op", "params", "dispatch_ts",
    "start_ts", "end_ts", "result", "error"} with all timestamps relative to
    the run's start (time.monotonic()-based).
    """
    events = sorted(events, key=lambda e: e["t"])
    phase_totals: dict = {}
    for e in events:
        phase_totals[e["phase"]] = phase_totals.get(e["phase"], 0) + 1

    progress = _Progress(total=len(events), phase_totals=phase_totals)
    progress.start_ts = time.monotonic()
    records: list[dict] = []
    records_lock = threading.Lock()

    def _worker(event: dict, dispatch_ts: float) -> None:
        start_ts = time.monotonic()
        progress.record_start(event["phase"], start_ts)
        result, error = None, None
        try:
            result = call_fn(event["op"], event["params"])
        except Exception as exc:  # noqa: BLE001 -- record and keep going
            error = repr(exc)
        end_ts = time.monotonic()
        with records_lock:
            records.append({
                "phase": event["phase"], "op": event["op"], "params": event["params"],
                "dispatch_ts": dispatch_ts - progress.start_ts,
                "start_ts": start_ts - progress.start_ts,
                "end_ts": end_ts - progress.start_ts,
                "result": result, "error": error,
            })
        progress.record_done(event["phase"], end_ts, label)

    with ThreadPoolExecutor(max_workers=pool_size) as ex:
        for event in events:
            target = progress.start_ts + event["t"] / speed
            now = time.monotonic()
            if target > now:
                time.sleep(target - now)
            dispatch_ts = time.monotonic()
            ex.submit(_worker, event, dispatch_ts)
        # Exiting the `with` block waits for all submitted work to finish.

    records.sort(key=lambda r: r["dispatch_ts"])
    return records, progress.max_in_flight


def _selftest(pool_size: int) -> None:
    events = []
    for i in range(40):
        events.append({"t": i * 0.05, "phase": "steady", "op": "noop", "params": {}})
    for i in range(20):
        events.append({"t": 1.5, "phase": "spike", "op": "noop", "params": {}})

    def stub(op, params):
        time.sleep(0.05)
        return {"ok": True}

    t0 = time.monotonic()
    records, max_in_flight = run_timeline(events, stub, pool_size=pool_size, label="[selftest]")
    wall = time.monotonic() - t0

    spike_records = [r for r in records if r["phase"] == "spike"]
    spike_start = min(r["dispatch_ts"] for r in spike_records)
    spike_end = max(r["end_ts"] for r in spike_records)
    spike_drain = spike_end - spike_start
    expected_min = 0.05 * ((20 + pool_size - 1) // pool_size) * 0.6  # generous lower bound
    expected_max = 0.05 * ((20 + pool_size - 1) // pool_size) * 3.0  # generous upper bound

    print(f"\ntotal events: {len(events)}, wall clock: {wall:.2f}s")
    print(f"max observed concurrency: {max_in_flight} (cap was {pool_size})")
    print(f"spike drain time: {spike_drain:.3f}s "
          f"(expected roughly {expected_min:.3f}s - {expected_max:.3f}s)")

    ok = True
    if max_in_flight > pool_size:
        print(f"FAIL: observed concurrency {max_in_flight} exceeded pool cap {pool_size}")
        ok = False
    if not (expected_min <= spike_drain <= expected_max):
        print("FAIL: spike drain time outside expected range -- pacing or capping is off")
        ok = False
    steady_records = [r for r in records if r["phase"] == "steady"]
    drift = max(abs(r["dispatch_ts"] - e["t"])
                for r, e in zip(sorted(steady_records, key=lambda r: r["dispatch_ts"]),
                                 [e for e in events if e["phase"] == "steady"]))
    print(f"max dispatch-time drift on steady events: {drift:.3f}s")
    if drift > 0.05:
        print("FAIL: steady events drifted too far from their requested schedule")
        ok = False

    sys.exit(0 if ok else 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--pool-size", type=int, default=8)
    args = ap.parse_args()
    if args.selftest:
        _selftest(args.pool_size)
    else:
        ap.error("only --selftest is supported when run standalone")


if __name__ == "__main__":
    main()
