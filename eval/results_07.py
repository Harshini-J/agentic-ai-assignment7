"""Assignment 7, Part B, task 1: one line per run, in results/<arm>.jsonl
(checks/FORMATS.md, section 15.4).

    python -m eval.results_07 --arm A --way planned --claim plan
    python -m eval.results_07 --arm B --way planned --switch TOOL_EXAMPLES=off --claim examples

Reads the arm's finished runs on your subset's golden tasks in runs/, checks each with your
grounded check, computes Part C's measure and the five metrics, and writes one line
per run. The helpers below find the runs and read them; the rest is yours.

A line (section 15.4):

    {"arm": "A", "way": "planned", "switches": {...}, "run_id": "...", "task": "g07",
     "stratum": "routine", "sweep": 1, "passed": true, "facts": {"present": 6, "total": 6},
     "measure": 0, "tokens": 31234, "cost_usd": 0.0412, "wall_clock_s": 18.2,
     "metrics": {"step_count": 2, "precision": 1.0, "recall": 1.0, "repeats": 0,
                 "orphans": 1, "no_tools": false, "cost_usd": 0.0412, "latency_s": 18.2}}

Part C's measure, per run, by claim (section 15.4): tokens, the run_end line's
totals.total_tokens; plan, the run's repeats; examples, its wasted calls: the lines of
its call record (runs/<run_id>.calls.jsonl) whose outcome is "rejected", "error" or
"protocol", plus the search calls whose result has "count": 0; checkpoint, its duplicate
writes: the comments beyond one, plus the open pull requests beyond one, on its issue
in its end state; split, 100 when the run passed and 0 when it did not.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from harness import LAB, ROOT
from harness import switches as switch_board
from harness.formats import UNFINISHED
from harness.tasks import end_state, load_tasks, read_subset
from harness.tracker import Tracker
from harness.trace import read_trace

from eval import metrics as trajectory
from eval.grounded import check


def finished_runs(way: str, switches: dict | None = None, root: Path = ROOT,
                  scripted: bool = False) -> list[list[dict]]:
    """Every finished Assignment 7 run of `way` with these switches (unset ones at their
    defaults), on a real model, as its trace's lines: one list per run. A run is finished
    when its last line is run_end and it did not end quota or rate_limited. With
    scripted=True, the runs on a scripted model instead, to test your code for free."""
    want = {**switch_board.DEFAULTS, **(switches or {})}
    out = []
    for path in sorted((root / "runs").glob("*.jsonl")):
        if path.name.startswith("_") or path.name.count(".") > 1:
            continue
        lines = read_trace(path)
        start = lines[0] if lines else {}
        if start.get("type") != "run_start" or start.get("lab") != LAB or start.get("way") != way:
            continue
        if {**switch_board.DEFAULTS, **(start.get("switches") or {})} != want:
            continue
        free = str(start.get("backend", "")).startswith("harness.scripted:") or start.get("backend") == "never-stops"
        if free != scripted:
            continue
        ends = [r.get("terminal_reason") for r in lines if r.get("type") == "end"]
        if lines[-1].get("type") != "run_end" or set(ends) & set(UNFINISHED):
            continue
        out.append(lines)
    return out


def call_record(run_id: str, root: Path = ROOT) -> list[dict]:
    """A run's call record, runs/<run_id>.calls.jsonl, one dict per line."""
    path = root / "runs" / f"{run_id}.calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


# -- one run's line ---------------------------------------------------------------------------

_EMPTY_SEARCH = re.compile(r'"count"\s*:\s*0\b')
_WASTED_OUTCOMES = ("rejected", "error", "protocol")


def parse_switches(pairs: list[str]) -> dict:
    """`--switch TOOL_EXAMPLES=off` -> {"tool_examples": "off"}: the names and values as the
    run_start line records them (harness/switches.py), so finished_runs can match them."""
    out: dict = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        key = name.strip().lower()
        if not sep or key not in switch_board.DEFAULTS:
            raise SystemExit(f"--switch {pair!r}: write NAME=VALUE, NAME one of "
                             f"{', '.join(k.upper() for k in switch_board.DEFAULTS)}")
        value = value.strip().lower()
        if isinstance(switch_board.DEFAULTS[key], bool):
            if value not in ("1", "0", "on", "off", "true", "false", "yes", "no"):
                raise SystemExit(f"--switch {pair!r}: {name} is 1 or 0")
            out[key] = value in ("1", "on", "true", "yes")
        else:
            out[key] = value
    return out


def wasted_calls(run_id: str, root: Path = ROOT) -> int:
    """Claim `examples`: the lines of the run's call record whose outcome is rejected, error
    or protocol, plus those of the search role whose result says count 0. A line is counted
    once, however many of the two it meets."""
    n = 0
    for call in call_record(run_id, root):
        if call.get("outcome") in _WASTED_OUTCOMES:
            n += 1
        elif call.get("role") == "search" and _EMPTY_SEARCH.search(str(call.get("result", ""))):
            n += 1
    return n


def duplicate_writes(task, state: dict) -> int:
    """Claim `checkpoint`: the comments beyond one, plus the open pull requests beyond one,
    on the task's issue in the run's end state."""
    one = state.get(task.issues[0], state.get(str(task.issues[0]))) or {}
    return max(0, len(one.get("comments") or []) - 1) + max(0, len(one.get("prs") or []) - 1)


def measure_of(claim: str, *, lines: list[dict], run_metrics: dict, passed: bool, run_id: str,
               task, state: dict, root: Path = ROOT):
    totals = lines[-1].get("totals") or {}
    if claim == "tokens":
        return totals.get("total_tokens", 0)
    if claim == "plan":
        return run_metrics["repeats"]
    if claim == "examples":
        return wasted_calls(run_id, root)
    if claim == "checkpoint":
        return duplicate_writes(task, state)
    if claim == "split":
        return 100 if passed else 0
    raise ValueError(f"unknown claim {claim!r}")


def result_line(arm: str, way: str, claim: str, lines: list[dict], task, tracker: Tracker,
                root: Path = ROOT) -> dict:
    """One finished run as a line of results/<arm>.jsonl (section 15.4)."""
    start, last = lines[0], lines[-1]
    run_id = start["run_id"]
    state = end_state(tracker, run_id, task)
    graded = check(task, state)
    run_metrics = trajectory.metrics(lines, task)
    totals = last.get("totals") or {}
    return {
        "arm": arm, "way": way, "switches": start.get("switches") or {},
        "run_id": run_id, "task": task.id, "stratum": task.stratum, "sweep": start.get("sweep"),
        "passed": bool(graded["passed"]),
        "facts": {"present": sum(1 for v in graded["facts"].values() if v == "present"),
                  "total": len(graded["facts"])},
        "measure": measure_of(claim, lines=lines, run_metrics=run_metrics, passed=bool(graded["passed"]),
                              run_id=run_id, task=task, state=state, root=root),
        "tokens": totals.get("total_tokens", 0), "cost_usd": totals.get("cost_usd", 0.0),
        "wall_clock_s": last.get("elapsed_s", 0.0),
        "metrics": run_metrics,
    }


# -- one arm's file ---------------------------------------------------------------------------

def build(arm: str, way: str, switches: dict, claim: str, tasks_dir: str, subset: str | None, *,
          scripted: bool = False, root: Path = ROOT, tracker: Tracker | None = None) -> tuple[list[dict], list[str]]:
    """The arm's result lines, and the notes to print. Only runs on the subset's tasks count.
    Every finished run is kept, as the checker counts every finished run of the arm; when two
    share a task and a sweep (a sweep run twice), the note says so."""
    tasks = {t.id: t for t in load_tasks(tasks_dir if Path(tasks_dir).is_absolute() else root / tasks_dir)}
    wanted = read_subset(subset) if subset else sorted(tasks)
    unknown = [i for i in wanted if i not in tasks]
    if unknown:
        raise SystemExit(f"{subset} names tasks {tasks_dir} does not have: {', '.join(unknown)}")
    tracker = tracker or Tracker(flaky=False, readback_fail=False)
    notes: list[str] = []
    seen: dict[tuple, str] = {}
    picked: list[list[dict]] = []
    for lines in finished_runs(way, switches, root, scripted):
        start = lines[0]
        if start.get("task") not in wanted:
            continue
        key = (start["task"], start.get("sweep"))
        if key in seen:
            notes.append(f"{key[0]} sweep {key[1]} has two finished runs ({seen[key]} and "
                         f"{start['run_id']}); both are kept, as the checker counts every finished run")
        seen[key] = start["run_id"]
        picked.append(lines)
    rows = [result_line(arm, way, claim, lines, tasks[lines[0]["task"]], tracker, root)
            for lines in sorted(picked, key=lambda l: (l[0]["task"], l[0].get("sweep") or 0, l[0]["run_id"]))]
    sweeps = sorted({r["sweep"] for r in rows})
    for sweep in sweeps:
        missing = [i for i in wanted if (i, sweep) not in seen]
        if missing:
            notes.append(f"sweep {sweep} lacks {len(missing)} of the subset's {len(wanted)} tasks: {', '.join(missing)}")
    if not rows:
        notes.append("no finished runs of this arm on the subset's tasks: nothing written")
    return rows, notes


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", required=True, choices=["A", "B"])
    p.add_argument("--way", required=True)
    p.add_argument("--switch", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument("--claim", required=True, choices=["tokens", "plan", "examples", "checkpoint", "split"])
    p.add_argument("--tasks", default="eval/golden/v1/tasks")
    p.add_argument("--subset", default="eval/subsets/claim.txt", help="only these task IDs (Part C)")
    p.add_argument("--scripted", action="store_true",
                   help="the runs on a scripted model, to test this script for free: writes "
                        "results/scripted_<arm>.jsonl, which the checker never reads")
    a = p.parse_args(argv)

    rows, notes = build(a.arm, a.way, parse_switches(a.switch), a.claim, a.tasks, a.subset, scripted=a.scripted)
    for note in notes:
        print("note:", note, file=sys.stderr)
    if not rows:
        return 1          # an existing results file is left alone: a mistyped --way or --switch must not empty it
    out = ROOT / "results" / (f"scripted_{a.arm}.jsonl" if a.scripted else f"{a.arm}.jsonl")
    out.parent.mkdir(exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    tasks = {r["task"] for r in rows}
    sweeps = sorted({r["sweep"] for r in rows})
    passes = sum(r["passed"] for r in rows)
    print(f"arm {a.arm}: {len(rows)} runs, {len(tasks)} tasks, sweeps {sweeps}, "
          f"{passes} passed, {sum(r['cost_usd'] for r in rows):.4f} USD -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
