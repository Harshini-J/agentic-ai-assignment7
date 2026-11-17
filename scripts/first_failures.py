"""Part C, task 7: where each failed run first went wrong (slide 29), for every run of both arms
whose grounded check failed, and the grid of the pairs (checks/FORMATS.md, section 15.8).

    python scripts/first_failures.py                 # the grid per arm, the biggest cell, the no-tool count
    python scripts/first_failures.py --list          # every failed run with its pair and the rule that gave it
    python scripts/first_failures.py --write-json    # fill `failures` and `grid` in reports/LAB_07.json
    python scripts/first_failures.py --recorded      # the same on the 60 recorded runs, to test the rules

Each failed run gets two marks, each a tool call the run made: its LAST GOOD step, and its FIRST
WRONG step, the earliest step that went wrong, not where it finally broke (slide 29). Two special
values: "start" for a last good step before any call, and "stop" for a first wrong step that never
happened because the run ended without it.

The rules, in the order they are tried (the task's `expect` is the right outcome):

  1. A run with no calls                          last good "start",       first wrong "stop"
  2. A stop task (right move: change nothing)     last good = its read,    first wrong = the call right
                                                   after the read (it should have ended there)
  3. Otherwise walk the calls in order. The first one that is wrong is the first wrong step:
       - an action the design never allows (close, merge, push)
       - issues_label with a label other than the expected one
       - pulls_open when none is expected, or one that does not name the expected file
       - issues_comment whose label or file is not the expected one, or a second comment
     If it is wrong because of the FILE and the run never read the expected file, the first wrong
     step is instead the first code_read_file of another file (it took the wrong turn there);
     if it read no file at all, it is the write itself.
  4. No call is wrong, yet the check failed: a step is missing. The last good step is the run's last
     call and the first wrong step is "stop" (the label, the pull request or the comment never came).
"""
import argparse
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness.formats import normalize_path, parse_triage_comment
from harness.tasks import load_state, load_tasks
from eval.grounded import check

READS = {"issues_read", "code_search", "code_read_file"}
KNOWN = READS | {"issues_label", "pulls_open", "issues_comment"}


def _names_file(call: dict, path: str) -> bool:
    inp = call.get("input") or {}
    text = f"{inp.get('title', '')}\n{inp.get('body', '')}".lower()
    return path.lower() in text or path.rsplit("/", 1)[-1].lower() in text


def first_failure(task, calls: list[dict]) -> tuple[str, str, str]:
    """(last_good, first_wrong, the rule that gave them) for one failed run."""
    names = [c["name"] for c in calls]
    if not calls:
        return "start", "stop", "1: the run made no call"
    want, exp = task.expect["comment"], task.expect

    if want is None:                                              # rule 2: a stop task
        if names[0] != "issues_read":
            return "start", names[0], "2: a stop task, and the first call was not the read"
        if len(calls) > 1:
            return names[0], names[1], "2: a stop task: it should have ended after the read"
        return names[0], "stop", "2: a stop task"

    file_, label_ = want["file"], want["label"]
    read_files, comments = [], 0
    for i, c in enumerate(calls):                                 # rule 3
        name, inp = c["name"], c.get("input") or {}
        prev = names[i - 1] if i else "start"
        bad, file_wrong = False, False
        if name not in KNOWN:
            bad = True
        elif name == "code_read_file":
            read_files.append(normalize_path(inp.get("path", "")))
        elif name == "issues_label":
            bad = str(inp.get("label", "")).strip().lower() != label_
        elif name == "pulls_open":
            bad = exp["pr"] == "none" or not _names_file(c, file_)
            file_wrong = exp["pr"] != "none"
        elif name == "issues_comment":
            comments += 1
            got_label, got_file = parse_triage_comment(str(inp.get("body", "")))
            got_label = (got_label or "").strip().lower()
            got_file = normalize_path(got_file) if got_file else None
            file_wrong = got_file != file_
            bad = comments > 1 or got_label != label_ or file_wrong
            if comments > 1:
                file_wrong = False
        if not bad:
            continue
        if file_wrong and file_ not in read_files:
            for j, r in enumerate(calls[:i]):
                if r["name"] == "code_read_file" and normalize_path((r.get("input") or {}).get("path", "")) != file_:
                    before = names[j - 1] if j else "start"
                    return before, "code_read_file", "3: it read another file and never read the expected one"
        return prev, name, f"3: {name} is wrong"
    return names[-1], "stop", "4: nothing it did was wrong, a step is missing"      # rule 4


def calls_of(path: str) -> list[dict]:
    with open(path) as f:
        return [d for d in (json.loads(l) for l in f if l.strip()) if d.get("type") == "tool_call"]


def gather(recorded: bool):
    """[(arm, run_id, task, calls, no_tools)] for every FAILED run."""
    tasks = {t.id: t for t in load_tasks(os.path.join(ROOT, "eval", "golden", "v1", "tasks"))}
    out = []
    if recorded:
        by_issue = {t.issues[0]: t for t in tasks.values()}
        import glob
        for sf in sorted(glob.glob(os.path.join(ROOT, "fixtures", "traces7", "*.state.json"))):
            meta = json.load(open(sf))
            task = by_issue.get(meta["issue"])
            if task is None:
                continue
            rid = os.path.basename(sf)[:-len(".state.json")]
            if not check(task, load_state(sf))["passed"]:
                calls = calls_of(sf.replace(".state.json", ".jsonl"))
                out.append((meta["way"], rid, task, calls, not calls))
        return out
    for arm in ("A", "B"):
        with open(os.path.join(ROOT, "results", f"{arm}.jsonl")) as f:
            for line in f:
                r = json.loads(line)
                if r["passed"]:
                    continue
                calls = calls_of(os.path.join(ROOT, "runs", f"{r['run_id']}.jsonl"))
                out.append((arm, r["run_id"], tasks[r["task"]], calls, bool((r.get("metrics") or {}).get("no_tools"))))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--write-json", action="store_true")
    ap.add_argument("--recorded", action="store_true", help="test the rules on fixtures/traces7")
    args = ap.parse_args()

    failed = gather(args.recorded)
    failures, grid, notool = [], {}, Counter()
    for arm, rid, task, calls, no_tools in failed:
        last_good, first_wrong, why = first_failure(task, calls)
        names = {c["name"] for c in calls}                      # the checker's rule (checks/check_07.py)
        if (last_good != "start" and last_good not in names) or (first_wrong != "stop" and first_wrong not in names):
            sys.exit(f"{rid}: last_good {last_good!r} and first_wrong {first_wrong!r} must be calls the run made, or start and stop")
        failures.append({"run_id": rid, "arm": arm, "last_good": last_good, "first_wrong": first_wrong})
        grid.setdefault(arm, {}).setdefault(last_good, {}).setdefault(first_wrong, 0)
        grid[arm][last_good][first_wrong] += 1
        notool[arm] += no_tools
        if args.list:
            print(f"{arm}  {rid:38} {task.stratum:15} {last_good:15} -> {first_wrong:15} [{why}]")

    for arm in sorted(grid):
        rows = grid[arm]
        cols = sorted({c for r in rows.values() for c in r})
        n = sum(sum(r.values()) for r in rows.values())
        print(f"\narm {arm}: {n} failed runs (last good step down the side, first wrong step across the top)")
        print("| last good \\ first wrong | " + " | ".join(cols) + " |")
        print("|---|" + "---|" * len(cols))
        for last in sorted(rows):
            print(f"| {last} | " + " | ".join(str(rows[last].get(c, "—")) for c in cols) + " |")
    cells = [(n, arm, last, first) for arm, rows in grid.items() for last, r in rows.items() for first, n in r.items()]
    if cells:
        n, arm, last, first = max(cells)
        print(f"\nbiggest cell: {n} runs of arm {arm}, last good {last}, first wrong {first}")
        for arm2 in sorted(grid):
            top = max(((n2, l, f) for l, r in grid[arm2].items() for f, n2 in r.items()))
            print(f"  arm {arm2}'s biggest: {top[0]} runs, {top[1]} -> {top[2]}")
    print("\nruns that called no tool at all: " + ", ".join(f"arm {a}: {notool[a]}" for a in sorted(grid)) if grid else "")

    if args.write_json:
        path = os.path.join(ROOT, "reports", "LAB_07.json")
        doc = json.load(open(path))
        doc["failures"], doc["grid"] = failures, grid
        json.dump(doc, open(path, "w"), indent=2)
        print(f"\nwrote `failures` ({len(failures)}) and `grid` to reports/LAB_07.json")


if __name__ == "__main__":
    main()