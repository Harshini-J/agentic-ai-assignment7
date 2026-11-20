"""Assignment 7, Part B, task 4: five trajectory metrics, by counting (slide 26;
checks/FORMATS.md, section 15.5).

    from eval.metrics import metrics
    metrics(lines, task)
    # {"step_count": 3, "precision": 0.8, "recall": 1.0, "repeats": 1, "orphans": 1,
    #  "no_tools": False, "cost_usd": 0.0412, "latency_s": 18.2}

`lines` is one run's trace, as a list of dicts (one per JSON line of
runs/<run_id>.jsonl, or of a recorded run in fixtures/traces7/); `task` is its golden
task, whose `reference` holds the calls and tools a good run makes. The definitions,
exactly; the checker counts the same way on the recorded runs:

- A **call** is a `tool_call` line, in order, whatever it returned. A resumed run's
  calls are every `tool_call` line, before its `resume` line and after.
- **step_count**: the run's calls, minus the task's reference count,
  `task.reference["calls"]`.
- **precision**: of the distinct tool names the run called, the share that are in the
  task's reference tools, `task.reference["tools"]`; None when it called none.
- **recall**: of the reference tools, the share the run called at least once.
- **repeats**: the calls whose name and input are identical to an earlier call's,
  each extra call counted once. Compare inputs in canonical form, keys sorted and no
  whitespace, as `canonical` below writes them.
- **orphans**: the reads whose output no later step uses. A read is a call whose
  name is not in WRITES. Its identifiers are the paths it returned (its `paths`), or,
  when it returned none, the values in its input as text: every value that is not
  null and not an object, a list's items one by one, numbers and booleans written as
  Python's str() writes them. A read is used when one of
  its identifiers appears, ignoring case, in the canonical input of a later call or
  in the run's final comment, the `body` of its last call in COMMENT_WRITES; a path
  also appears when its file name alone does (`exportUtils.ts` for
  `src/exportUtils.ts`). Only identifiers of three characters or more count.
- **no_tools**: True when the run made no call at all (slide 28).
- **cost_usd** and **latency_s**: the last `run_end` line's `totals.cost_usd` and
  `elapsed_s`.

Slide 27's trace, fixtures/traces7/s27.jsonl with fixtures/traces7/s27.task.yaml,
gives 3, 0.8, 1.0, 1 and 1.
"""

from __future__ import annotations

import json

# Writes, by role name and by RepoMind's tool names: their output is what they changed,
# so none is ever an orphan.
WRITES = frozenset({
    "post_comment", "open_pr", "apply_label", "close_issue", "push_commit", "merge_pr",
    "issues_comment", "pulls_open", "issues_label", "issues_close", "branches_push", "pulls_merge",
})
COMMENT_WRITES = frozenset({"post_comment", "issues_comment"})


def canonical(value) -> str:
    """A tool input in one standard form: keys sorted, no whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


MIN_ID_CHARS = 3        # an identifier shorter than this never counts as a use


def _calls(lines: list[dict]) -> list[dict]:
    """The run's calls: every `tool_call` line, in order, whatever it returned (a resumed
    run's calls before and after its `resume` line included)."""
    return [l for l in lines if l.get("type") == "tool_call"]


def _values(value) -> list[str]:
    """The values of a tool input as text: not null, not an object, a list's items one by one,
    numbers and booleans written as Python's str() writes them."""
    if value is None or isinstance(value, dict):
        return []
    if isinstance(value, (list, tuple)):
        return [t for item in value for t in _values(item)]
    return [str(value)]


def _identifiers(call: dict) -> list[tuple[str, bool]]:
    """What a read's output could be used by, each as (text, is_path): the paths it returned,
    or, when it returned none, the values in its input. Only three characters or more count."""
    paths = [p for p in (call.get("paths") or []) if isinstance(p, str)]
    if paths:
        ids = [(p, True) for p in paths]
    else:
        ids = [(v, False) for v in (t for value in (call.get("input") or {}).values() for t in _values(value))]
    return [(text, is_path) for text, is_path in ids if len(text) >= MIN_ID_CHARS]


def _appears(identifier: str, is_path: bool, text: str) -> bool:
    """`identifier` appears in `text`, ignoring case; anything with a "/" in it, a returned
    path or a path in the input, also appears when its file name alone does
    (`exportUtils.ts` for `src/exportUtils.ts`), as the checker counts it."""
    ident = identifier.lower()
    if ident in text:
        return True
    if "/" in ident:
        name = ident.rsplit("/", 1)[-1]
        return len(name) >= MIN_ID_CHARS and name in text
    return False


def _final_comment(calls: list[dict]) -> str:
    """The `body` of the run's last call in COMMENT_WRITES, in lower case; "" when it made none."""
    for call in reversed(calls):
        if call.get("name") in COMMENT_WRITES:
            return str((call.get("input") or {}).get("body", "")).lower()
    return ""


def _orphans(calls: list[dict]) -> int:
    """The reads whose output no later step uses (slide 26). A read is a call that is not in
    WRITES; it is used when one of its identifiers appears in a later call's canonical input or
    in the run's final comment. A read with no identifier of three characters or more has
    nothing that could be used, so it is an orphan."""
    comment = _final_comment(calls)
    later_text = [canonical(c.get("input")).lower() for c in calls]
    n = 0
    for i, call in enumerate(calls):
        if call.get("name") in WRITES:
            continue
        ids = _identifiers(call)
        used = any(_appears(text, is_path, haystack)
                   for text, is_path in ids
                   for haystack in (*later_text[i + 1:], comment))
        if not used:
            n += 1
    return n


def _repeats(calls: list[dict]) -> int:
    """The calls whose name and input equal an earlier call's, each extra call counted once."""
    seen: set[tuple[str, str]] = set()
    n = 0
    for call in calls:
        key = (call.get("name"), canonical(call.get("input")))
        if key in seen:
            n += 1
        seen.add(key)
    return n


def metrics(lines: list[dict], task) -> dict:
    """The five trajectory metrics of one run, by counting (slide 26), and whether it called
    no tool at all (slide 28). `task.reference` is {"calls": n, "tools": [...]}."""
    calls = _calls(lines)
    expected = set(task.reference["tools"])
    used = {c.get("name") for c in calls}
    ends = [l for l in lines if l.get("type") == "run_end"]
    end = ends[-1] if ends else {}
    return {
        "step_count": len(calls) - int(task.reference["calls"]),
        "precision": len(used & expected) / len(used) if used else None,
        "recall": len(expected & used) / len(expected) if expected else 1.0,
        "repeats": _repeats(calls),
        "orphans": _orphans(calls),
        "no_tools": not calls,
        "cost_usd": float((end.get("totals") or {}).get("cost_usd") or 0.0),
        "latency_s": float(end.get("elapsed_s") or 0.0),
    }
