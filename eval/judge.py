"""Assignment 7, Part D: the judge, its rates and its correction (checks/FORMATS.md,
section 15.10).

    python -m eval.judge tune          # refine the prompt: the tuning set, and the examples not in the prompt
    python -m eval.judge freeze        # pin the judge: its prompt, model and settings (eval/judge/frozen.json)
    python -m eval.judge test 1        # run 1 on the test set: eval/judge/verdicts/test_1.jsonl
    python -m eval.judge versions      # the test items' list and long versions: versions.jsonl, and how many verdicts moved
    python -m eval.judge moved         # print that result again from versions.jsonl: no model calls
    python -m eval.judge recorded      # judge the agent way's recorded comments, correct the pass rate, bound it
    python -m eval.judge correction    # print that correction again from the verdict files: no model calls
    python -m eval.judge flips         # after test runs 1 to 3: the flip rate, the majority of three, for_a_person.txt

Your judge reads one output, its issue and what RepoMind's tools returned, and
answers with slide 36's fixed reply: JSON with a one-line "reasoning", then an
"answer", "Pass" or "Fail". Every call goes through a metered judge session, so its
tokens and cost are recorded and priced, and count against lab_token_ceiling:

    from harness.meter import judge_session
    with judge_session("test-1") as session:
        response = session.client.create(system=prompt, messages=[{"role": "user", "content": text}])
        session.trace.model_call(0, response, purpose="judge")

Write session.id on every verdict line. To test the plumbing for nothing, pass
--backend harness.scripted:PassEverything, a judge that passes everything: a coin.

The checker calls `correct`, `rates` and `bootstrap` on cases of its own, and
`correct` on a coin, so keep their names, arguments and returns.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import random
import re
import sys
import time
from pathlib import Path

import yaml

from harness import ROOT
from harness.meter import judge_session
from harness.settings import load_settings

OUTPUTS = ROOT / "fixtures" / "judge" / "outputs"
VERDICTS = ROOT / "eval" / "judge" / "verdicts"
PROMPT = ROOT / "prompts" / "judge.md"
CRITERION = ROOT / "eval" / "judge" / "criterion.md"
SPLIT = ROOT / "eval" / "labels" / "split.yaml"
LABELS = ROOT / "eval" / "labels" / "labels.csv"
FROZEN = ROOT / "eval" / "judge" / "frozen.json"
TUNING_LOG = ROOT / "eval" / "judge" / "tuning_log.jsonl"
SCRIPTED = "harness.scripted:PassEverything"


class CoinJudge(ValueError):
    """TPR + TNR is within 0.1 of 1: the judge is no better than a coin. Fix it, do not
    correct it (slide 44)."""


def is_coin(tpr: float, tnr: float) -> bool:
    """TPR + TNR within 0.1 of 1: the judge is no better than a coin. Rounded first, so that float noise
    cannot decide the boundary (0.55 + 0.55 - 1 is 0.10000000000000009 in floats and 0.1 in arithmetic)."""
    return abs(round(tpr + tnr - 1, 9)) <= 0.1


def correct(p: float, tpr: float, tnr: float) -> float:
    """The share you would pass, labelling by hand, from the judge's pass rate p on
    outputs nobody labelled: (p + TNR - 1) / (TPR + TNR - 1) (slide 44), clipped to
    0 to 1. Raises CoinJudge when TPR + TNR is within 0.1 of 1."""
    if is_coin(tpr, tnr):
        raise CoinJudge(f"TPR + TNR is {tpr + tnr:.3f}, within 0.1 of 1: the judge is no better than a coin, "
                        "so its pass rate cannot be corrected. Fix the judge; do not correct it (slide 44)")
    return min(1.0, max(0.0, (p + tnr - 1) / (tpr + tnr - 1)))


def rates(verdicts: dict[str, str], labels: dict[str, str]) -> tuple[float, float]:
    """(TPR, TNR) of the judge's verdicts against your labels, each "pass" or "fail",
    on the items both cover (slide 43): TPR is the share of the labelled passes the
    judge passed, TNR the share of the labelled fails it failed."""
    shared = [i for i in verdicts if i in labels]
    passes = [i for i in shared if str(labels[i]).lower() == "pass"]
    fails = [i for i in shared if str(labels[i]).lower() == "fail"]
    if not passes or not fails:
        raise ValueError(f"rates needs at least one labelled pass and one labelled fail among the items both "
                         f"cover; it has {len(passes)} passes and {len(fails)} fails")
    tpr = sum(1 for i in passes if str(verdicts[i]).lower() == "pass") / len(passes)
    tnr = sum(1 for i in fails if str(verdicts[i]).lower() == "fail") / len(fails)
    return tpr, tnr


def bootstrap(verdicts: dict[str, str], labels: dict[str, str], p: float,
              resamples: int = 2000, seed: int = 0) -> tuple[float, float]:
    """The middle 95% of the corrected rate over resamples of the test items, drawn
    with replacement, as many as there are, each time recomputing TPR and TNR
    (slide 44). A resample on which the judge is a coin is left out.

    A resample with no labelled pass or no labelled fail has no TPR or no TNR, so it is left out too. The
    interval is the 2.5th and 97.5th of the sorted corrected rates, taken at index int(q * (n - 1))."""
    items = [i for i in labels if i in verdicts]
    rng = random.Random(seed)
    got: list[float] = []
    for _ in range(resamples):
        draw = [rng.choice(items) for _ in items]
        n_pass = sum(1 for i in draw if str(labels[i]).lower() == "pass")
        n_fail = len(draw) - n_pass
        if not n_pass or not n_fail:
            continue
        tpr = sum(1 for i in draw if str(labels[i]).lower() == "pass" and str(verdicts[i]).lower() == "pass") / n_pass
        tnr = sum(1 for i in draw if str(labels[i]).lower() == "fail" and str(verdicts[i]).lower() == "fail") / n_fail
        if is_coin(tpr, tnr):
            continue
        got.append(correct(p, tpr, tnr))
    if not got:
        raise ValueError("no resample of the test items gave a judge that is not a coin: there is no interval to report")
    got.sort()
    return got[int(0.025 * (len(got) - 1))], got[int(0.975 * (len(got) - 1))]


def exact_lower_bound(correct_items: int, n: int, alpha: float = 0.05) -> float:
    """The exact (Clopper-Pearson) lower bound of a share seen as `correct_items` of `n`: how low the true rate
    can be and still give a result this good with probability alpha / 2. For a perfect score it is (alpha/2)^(1/n)."""
    if correct_items <= 0:
        return 0.0
    def tail(q: float) -> float:        # P(X >= correct_items) when the true rate is q
        return sum(math.comb(n, i) * q ** i * (1 - q) ** (n - i) for i in range(correct_items, n + 1))
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if tail(mid) < alpha / 2 else (lo, mid)
    return (lo + hi) / 2


def sensitivity(p: float, tpr: float, tnr: float, tpr_lo: float, tnr_lo: float) -> tuple[float, float] | None:
    """How far the corrected rate could move if the judge's true rates were anywhere between their exact lower
    bounds and what the test set showed: the lowest and highest corrected rate over the four corners of that
    box, leaving out corners where the judge would be a coin. A low true TNR means more false passes, so it pulls
    the corrected rate down; a low true TPR pushes it up. None when every corner is a coin."""
    values = [correct(p, t, n) for t in {tpr_lo, tpr} for n in {tnr_lo, tnr} if not is_coin(t, n)]
    return (min(values), max(values)) if values else None


def load_outputs(root: Path = ROOT) -> dict[str, dict]:
    """The 60 outputs to label, by ID (section 15.9)."""
    return {p.stem: json.loads(p.read_text()) for p in sorted((root / "fixtures" / "judge" / "outputs").glob("*.json"))}


# -- the recorded runs of the agent way (Part D, task 5): outputs nobody labelled ---------------------

TRACES = ROOT / "fixtures" / "traces7"
POOL = ROOT / "fixtures" / "issues" / "pool"
COMMENT_WRITES = ("issues_comment", "post_comment")


def read_trace_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def pool_issue(number: int) -> dict:
    """An issue as the outputs hold it: {"number", "title", "body"}, from fixtures/issues/pool/<n>.md: the title
    unescaped, the body without the front matter and without the sentinel comment."""
    text = (POOL / f"{number}.md").read_text()
    _, front, body = text.split("---\n", 2)
    title = re.search(r"^title:\s*(.*)$", front, flags=re.M).group(1).replace('\\"', '"').strip()
    body = re.sub(r"\s*<!--\s*sentinel:.*?-->\s*", "\n", body, flags=re.S).strip()      # the blank lines around it become one newline
    return {"number": number, "title": title, "body": body}


def recorded_with_comment(traces: Path = TRACES) -> list[str]:
    """The IDs of the recorded runs of the agent way that posted a comment (a comment write that did not fail)."""
    ids = []
    for path in sorted(traces.glob("*.jsonl")):
        if path.name.startswith("s27") or ".calls" in path.name:
            continue
        lines = read_trace_lines(path)
        if lines and lines[0].get("way") == "agent" and any(
                x.get("type") == "tool_call" and x.get("name") in COMMENT_WRITES and not x.get("is_error") for x in lines):
            ids.append(lines[0].get("run_id") or path.stem)
    return ids


def recorded_output(run_id: str, traces: Path = TRACES) -> dict:
    """One recorded run as a judge input, shaped like fixtures/judge/outputs/*.json: its issue, the tool calls it made
    before it commented (each with its whole result), and the last comment it posted, as its end state holds it."""
    lines = read_trace_lines(traces / f"{run_id}.jsonl")
    state = json.loads((traces / f"{run_id}.state.json").read_text())
    evidence = [{"tool": x["name"], "input": x["input"], "result": str(x.get("result", ""))}
                for x in lines if x.get("type") == "tool_call" and x["name"] not in COMMENT_WRITES and not x.get("is_error")]
    comments = state["state"][str(state["issue"])]["comments"]
    return {"id": run_id, "issue": pool_issue(int(state["issue"])), "evidence": evidence, "comment": comments[-1]}


# -- the labels and the split -----------------------------------------------------------------

def load_labels(path: Path = LABELS) -> dict[str, str]:
    with open(path, newline="") as f:
        return {r["id"].strip(): r["label"].strip().lower() for r in csv.DictReader(f)}


def load_split(path: Path = SPLIT) -> dict[str, list[str]]:
    data = yaml.safe_load(path.read_text())
    return {k: list(data[k]) for k in ("examples", "tuning", "test")}


# -- the prompt: slide 36's four parts -------------------------------------------------------

_ID = re.compile(r"\bj\d{2}\b")


def criterion_text(path: Path = CRITERION) -> str:
    """criterion.md as the judge sees it: without its title, and without the lists of output IDs
    that record which outputs a rule was applied to (the judge must not learn which outputs exist), and
    without the bullet that tells the labeller to add a line and relabel, which a judge cannot do."""
    text = path.read_text()
    text = "\n".join(text.split("\n")[1:]).strip()                       # drop the "# Criterion: ..." title
    text = re.sub(r"[ \t]*\*[^*\n]*\bj\d{2}\b[^*\n]*\*", "", text)         # *Applied to j06, j10 ...*
    text = re.sub(r"^- \*\*Add a line rather than force a defect\.\*\*.*\n?", "", text, flags=re.M)  # for the labeller
    if re.search(r"\brelabel", text, re.I):
        raise ValueError("criterion.md's labeller bullet (the one about relabelling) is still in what the judge reads: "
                         "keep it on one line, starting `- **Add a line rather than force a defect.**`")
    if _ID.search(text):
        raise ValueError(f"criterion.md still names an output ID in what the judge reads: {_ID.search(text).group(0)}")
    return text


def system_prompt() -> str:
    """prompts/judge.md with its comment removed and {{CRITERION}} replaced by the criterion."""
    text = re.sub(r"<!--.*?-->", "", PROMPT.read_text(), flags=re.S)
    if "{{CRITERION}}" not in text:
        raise ValueError("prompts/judge.md has no {{CRITERION}} placeholder")
    text = text.replace("{{CRITERION}}", criterion_text()).strip()
    if _ID.search(text):
        raise ValueError(f"prompts/judge.md names an output ID in what the judge reads: {_ID.search(text).group(0)}")
    return text


def example_ids() -> list[str]:
    """The outputs the prompt's examples come from, named in the prompt's first comment. Each must be
    in the examples set, and in no other set (slide 42)."""
    comment = re.search(r"<!--(.*?)-->", PROMPT.read_text(), flags=re.S)
    ids = sorted(set(_ID.findall(comment.group(1)))) if comment else []
    split = load_split()
    bad = [i for i in ids if i not in split["examples"]]
    if not ids or bad:
        raise ValueError(f"the prompt's examples must come from the examples set; not in it: {bad or 'none named'}")
    return ids


def user_message(output: dict) -> str:
    """What the judge reads about one output: its issue, what the tools returned, and the comment."""
    issue = output["issue"]
    parts = [f"# THE ISSUE\n\n#{issue['number']}: {issue['title']}\n\n{issue['body'].strip()}", "# THE EVIDENCE"]
    for n, e in enumerate(output["evidence"], 1):
        parts.append(f"## {n}. {e['tool']}\n\nINPUT: {json.dumps(e['input'], ensure_ascii=False)}\n\nRESULT:\n{e['result']}")
    parts.append(f"# THE COMMENT\n\n{output['comment'].strip()}")
    parts.append("Judge the comment. Reply with the JSON object only.")
    return "\n\n".join(parts)


def parse_reply(text: str) -> tuple[str, str] | None:
    """(answer, reasoning) from the fixed reply, or None when it is not one: answer is "pass" or "fail"."""
    m = re.search(r"\{.*\}", text or "", flags=re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    answer = str(obj.get("answer", "")).strip().lower()
    if answer not in ("pass", "fail"):
        return None
    return answer, " ".join(str(obj.get("reasoning", "")).split())


# -- one judgement, one session ----------------------------------------------------------------

def judge_one(session, output: dict, system: str, numbers) -> dict:
    """Judge one output: up to three calls. A reply that is not the fixed reply is asked for again; if
    none is, the verdict is fail, because an unclear case is a fail (criterion.md)."""
    messages = [{"role": "user", "content": user_message(output)}]
    reply, response = None, None
    for _ in range(3):
        response = session.client.create(system=system, messages=messages)
        session.trace.model_call(next(numbers), response, purpose="judge")
        reply = parse_reply(response.text)
        if reply:
            break
        messages += [{"role": "assistant", "content": response.text or "(empty)"},
                     {"role": "user", "content": 'That was not the fixed reply. Reply with only the JSON object: '
                                                '{"reasoning": "...", "answer": "Pass" or "Fail"}.'}]
    answer, reasoning = reply or ("fail", "no valid JSON reply after three tries; counted as Fail (unclear)")
    return {"id": output["id"], "answer": answer, "reasoning": reasoning, "session": session.id,
            "model": response.model}                  # the version that served the call, as the API reports it


def run(ids: list[str], name: str, backend: str | None = None, outputs: dict[str, dict] | None = None) -> list[dict]:
    """The judge over these outputs, in one metered session (its tokens and cost are recorded and priced)."""
    outputs, system = outputs or load_outputs(), system_prompt()
    numbers, verdicts = itertools.count(), []
    with judge_session(name, backend) as session:
        for i in ids:
            verdicts.append(judge_one(session, outputs[i], system, numbers))
    return verdicts


def write_verdicts(path: Path, verdicts: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in verdicts))


# -- freezing: a judge is its model, its prompt and its settings together (slides 36 and 41) ----

def pin() -> dict:
    s = load_settings(ROOT / "settings.yaml")
    prompt = system_prompt()
    return {"prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "provider": s.provider, "model": s.model, "base_url": s.base_url,
            "max_tokens": s.max_tokens, "effort": s.effort}


def frozen_check() -> dict:
    if not FROZEN.exists():
        raise SystemExit("the judge is not frozen: refine the prompt with `tune`, then run `freeze` once; "
                         "the test set is only for a judge that is frozen")
    then, now = json.loads(FROZEN.read_text()), pin()
    changed = [k for k in now if then["pin"].get(k) != now[k]]
    if changed:
        raise SystemExit(f"the judge changed since it was frozen ({', '.join(changed)}): it is a different judge, "
                         "to validate again. Run `tune` and `freeze` again, and treat every number as new")
    return then


def table(rows, labels) -> None:
    for v in rows:
        mark = "ok  " if v["answer"] == labels[v["id"]] else "MISS"
        print(f"{mark} {v['id']}  label {labels[v['id']]:4}  judge {v['answer']:4}  {v['reasoning']}")


def report(verdicts: list[dict], labels: dict[str, str], where: str) -> None:
    got = {v["id"]: v["answer"] for v in verdicts}
    tpr, tnr = rates(got, labels)
    tp = sum(1 for i in got if labels[i] == "pass" and got[i] == "pass")
    fp = sum(1 for i in got if labels[i] == "fail" and got[i] == "pass")
    P = sum(1 for i in got if labels[i] == "pass")
    N = len(got) - P
    print(f"{where}: {len(got)} items | TPR {tpr:.3f} ({tp}/{P} labelled passes passed) | "
          f"TNR {tnr:.3f} ({N - fp}/{N} labelled fails failed) | TPR + TNR = {tpr + tnr:.3f}")


def show_correction(verdicts: list[dict], tests: Path, labels: dict[str, str], split: dict, out: Path, wrote: bool = True) -> int:
    """Print the recorded runs' pass rate, corrected with the test set's TPR and TNR (run 1), with its bootstrap
    interval and how far it could move; write eval/judge/correction.json. Spends no tokens."""
    passed = sum(1 for v in verdicts if v["answer"] == "pass")
    p = passed / len(verdicts)
    test_v = {v["id"]: v["answer"] for v in map(json.loads, tests.read_text().splitlines()) if v}
    test_l = {i: labels[i] for i in split["test"]}
    tpr, tnr = rates(test_v, test_l)
    n_pass = sum(1 for i in test_l if test_l[i] == "pass"); n_fail = len(test_l) - n_pass
    print(f"recorded runs of the agent way that posted a comment: {len(verdicts)} judged, {passed} passed: p = {p:.3f}")
    print(f"the judge's rates on the test set (run 1): TPR {tpr:.3f}, TNR {tnr:.3f}, TPR + TNR = {tpr + tnr:.3f}")
    summary = {"p": p, "tpr": tpr, "tnr": tnr, "recorded": len(verdicts), "coin": is_coin(tpr, tnr)}
    target = ROOT / "eval" / "judge" / "correction.json"
    try:
        raw = (p + tnr - 1) / (tpr + tnr - 1) if not is_coin(tpr, tnr) else None
        corrected = correct(p, tpr, tnr)
    except CoinJudge as exc:
        print(f"REFUSED: {exc}")
        summary.update(corrected=None, interval=None)
        target.write_text(json.dumps(summary, indent=2) + "\n")
        return 1
    lo, hi = bootstrap(test_v, test_l, p)
    print(f"corrected pass rate: {corrected:.3f}" + (f"   (the formula gave {raw:.3f}, clipped to 0..1)" if raw != corrected else "")
          + f"   95% bootstrap interval {lo:.3f} to {hi:.3f}   (2,000 resamples of the {len(test_l)} test items)")
    if lo == hi and tpr == 1.0 and tnr == 1.0:
        print("note: the interval has no width: a judge that was right on every test item is right on every item of "
              "every resample, so the bootstrap sees no judge error to carry. It is not a bound on the judge.")
    elif lo == hi and raw != corrected:
        print(f"note: the interval is one point because the corrected rate is clipped to {corrected:.0f} in every resample: "
              "the pass rate is at least as high (or low) as the judge's errors can explain.")
    tpr_lo = exact_lower_bound(round(tpr * n_pass), n_pass); tnr_lo = exact_lower_bound(round(tnr * n_fail), n_fail)
    box = sensitivity(p, tpr, tnr, tpr_lo, tnr_lo)
    print(f"what the test set cannot rule out: with {n_pass} passes and {n_fail} fails, an exact 95% interval puts the true TPR at "
          f"{tpr_lo:.3f} or more and the true TNR at {tnr_lo:.3f} or more; for true rates anywhere in that range the corrected rate would lie between "
          + (f"{box[0]:.3f} and {box[1]:.3f}" if box else "nothing defined (the judge would be a coin)"))
    summary.update(corrected=corrected, interval=[lo, hi], tpr_lower=tpr_lo, tnr_lower=tnr_lo,
                   sensitivity=list(box) if box else None)
    target.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {out.relative_to(ROOT)} and eval/judge/correction.json" if wrote else "wrote eval/judge/correction.json")
    return 0


# -- consistency: three runs, the flip rate and a majority (slides 45 and 46) -------------------------

PERSON = ROOT / "eval" / "judge" / "for_a_person.txt"


def consistency(runs: list[dict[str, str]], labels: dict[str, str]) -> dict:
    """What three runs of the same judge on the same items show: the items whose verdict changed (the flips, each
    one for a person), the flip rate, each run's TPR and TNR, the majority's, and whether the majority is kept.

    A majority is an ensemble of one model, and three copies of one model share its lean (slide 46), so it is kept
    only if it wins: on the same labels its TPR + TNR must be strictly higher than the best single run's. A tie is
    not a win; it costs three runs for nothing."""
    missing = [n for n, r in enumerate(runs, 1) if set(r) != set(labels)]
    if missing:
        raise ValueError(f"every run must judge exactly the test items; run(s) {missing} do not")
    ids = list(labels)
    flips = [i for i in ids if len({str(r[i]).lower() for r in runs}) > 1]
    majority = {i: "pass" if sum(1 for r in runs if str(r[i]).lower() == "pass") * 2 > len(runs) else "fail" for i in ids}
    singles = [rates({i: r[i] for i in ids}, {i: labels[i] for i in ids}) for r in runs]
    m_tpr, m_tnr = rates(majority, {i: labels[i] for i in ids})
    best = max(range(len(runs)), key=lambda k: singles[k][0] + singles[k][1])
    kept = (m_tpr + m_tnr) > (singles[best][0] + singles[best][1]) + 1e-12
    return {"items": len(ids), "flips": flips, "flip_rate": len(flips) / len(ids) if ids else 0.0,
            "runs": [{"tpr": t, "tnr": n} for t, n in singles], "majority": {"tpr": m_tpr, "tnr": m_tnr, "kept": kept},
            "best_run": best + 1, "majority_verdicts": majority}


def show_consistency(labels: dict[str, str], split: dict) -> int:
    runs = []
    for n in (1, 2, 3):
        path = VERDICTS / f"test_{n}.jsonl"
        if not path.exists():
            raise SystemExit(f"{path.relative_to(ROOT)} does not exist: run `python -m eval.judge test {n}` first")
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        runs.append({v["id"]: v["answer"] for v in rows})
    test_l = {i: labels[i] for i in split["test"]}
    c = consistency(runs, test_l)
    for n, r in enumerate(c["runs"], 1):
        print(f"test run {n}: TPR {r['tpr']:.3f}, TNR {r['tnr']:.3f}, TPR + TNR = {r['tpr'] + r['tnr']:.3f}")
    print(f"flip rate: {len(c['flips'])} of {c['items']} test items changed verdict between the three runs = {c['flip_rate']:.3f}"
          + (f": {', '.join(c['flips'])}" if c["flips"] else ""))
    m = c["majority"]; b = c["runs"][c["best_run"] - 1]
    print(f"majority of three: TPR {m['tpr']:.3f}, TNR {m['tnr']:.3f}, TPR + TNR = {m['tpr'] + m['tnr']:.3f} "
          f"| best single run (run {c['best_run']}): {b['tpr'] + b['tnr']:.3f}")
    tie = abs((m["tpr"] + m["tnr"]) - (b["tpr"] + b["tnr"])) < 1e-12
    print("the majority is " + ("KEPT: it beats the best single run on the same labels" if m["kept"] else
          "NOT kept: it does not beat the best single run on the same labels" + (" (it ties it, and a tie is not a win)" if tie else "")
          + ", and it costs three runs"))
    PERSON.write_text("".join(f"{i}\n" for i in c["flips"]))
    (ROOT / "eval" / "judge" / "consistency.json").write_text(json.dumps({k: v for k, v in c.items() if k != "majority_verdicts"}, indent=2) + "\n")
    print(f"wrote {PERSON.relative_to(ROOT)} ({len(c['flips'])} IDs, each for a person) and eval/judge/consistency.json")
    return 0


# -- formatting and length: does the verdict move when only the presentation does? (slide 38) ----------

VERSION_KINDS = ("list", "long")


def moved_items(versions: list[dict], run1: dict[str, str]) -> dict[str, list[str]]:
    """{item: the versions whose verdict differs from run 1's verdict on the original}: an item moved when either
    its list version or its long version got a different verdict (checks/FORMATS.md, section 15.10)."""
    moved: dict[str, list[str]] = {}
    for v in versions:
        if str(v["answer"]).lower() != str(run1[v["id"]]).lower():
            moved.setdefault(v["id"], []).append(v["version"])
    return moved


def version_outputs(ids: list[str]) -> dict[str, dict]:
    """The judge's inputs for the list and the long version of each item: the same issue and evidence, with the
    comment replaced by the version (the substance is the same, the presentation is not). Keyed `jNN:list`."""
    base = load_outputs()
    return {f"{i}:{kind}": {**base[i], "comment": base[i]["versions"][kind]} for i in ids for kind in VERSION_KINDS}


def show_versions(rows: list[dict], tests: Path, labels: dict[str, str], split: dict) -> int:
    """Report the share of test items whose verdict moved, version by version, and write
    eval/judge/versions_summary.json. Spends no tokens."""
    run1 = {v["id"]: v["answer"] for v in map(json.loads, tests.read_text().splitlines()) if v}
    test = split["test"]
    wanted = sorted((i, k) for i in test for k in VERSION_KINDS)
    if sorted((v["id"], v["version"]) for v in rows) != wanted:
        raise SystemExit("versions.jsonl must judge each test item's list and long versions once")
    moved = moved_items(rows, run1)
    test_l = {i: labels[i] for i in test}
    summary = {"items": len(test), "moved_share": len(moved) / len(test), "moved": moved, "by_version": {}}
    print(f"{len(rows)} judgements: the list and the long version of each of the {len(test)} test items")
    for kind in VERSION_KINDS:
        part = {v["id"]: v["answer"] for v in rows if v["version"] == kind}
        tpr, tnr = rates(part, test_l)
        n_moved = sum(1 for i in part if part[i] != run1[i])
        summary["by_version"][kind] = {"moved": n_moved, "tpr": tpr, "tnr": tnr}
        print(f"  {kind:4} version: {n_moved} of {len(test)} verdicts differ from run 1 | against the labels: TPR {tpr:.3f}, TNR {tnr:.3f}")
    print(f"moved: {len(moved)} of {len(test)} test items = {len(moved) / len(test):.3f}"
          + (f": {', '.join(sorted(moved))}" if moved else ": no verdict moved with the formatting or the length"))
    for i in sorted(moved):
        for v in rows:
            if v["id"] == i and v["version"] in moved[i]:
                print(f"  {i} ({v['version']}): label {labels[i]}, run 1 {run1[i]}, this version {v['answer']}: {v['reasoning']}")
    if moved:
        print("the verdict should not move with the form (slide 38): fix one output format, or add a line telling the "
              "judge what to ignore; either change makes a new judge, to tune, freeze and validate again")
    (ROOT / "eval" / "judge" / "versions_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("wrote eval/judge/versions_summary.json")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    t = sub.add_parser("tune", help="run the judge on the tuning set and the examples not in the prompt")
    t.add_argument("--all", action="store_true", help="print every verdict, not only the misses")
    t.add_argument("--backend", default=None)
    sub.add_parser("freeze", help="pin the prompt, model and settings; the test set needs it")
    te = sub.add_parser("test", help="run the frozen judge on the test set")
    te.add_argument("n", type=int, choices=(1, 2, 3))
    te.add_argument("--backend", default=None)
    te.add_argument("--force", action="store_true", help="overwrite a verdict file that exists")
    ve = sub.add_parser("versions", help="judge the list and long versions of every test item and report how many verdicts moved")
    ve.add_argument("--backend", default=None)
    ve.add_argument("--force", action="store_true", help="overwrite a verdict file that exists")
    sub.add_parser("moved", help="print the formatting and length result again from versions.jsonl; spends no tokens")
    rc = sub.add_parser("recorded", help="judge the agent way's recorded comments, correct the pass rate, bound it")
    rc.add_argument("--backend", default=None)
    rc.add_argument("--force", action="store_true", help="overwrite a verdict file that exists")
    sub.add_parser("flips", help="the flip rate over test runs 1 to 3, the majority of three, and for_a_person.txt; spends no tokens")
    sub.add_parser("correction", help="print the correction again from recorded.jsonl and test_1.jsonl; spends no tokens")
    a = ap.parse_args(argv)
    labels, split = load_labels(), load_split()

    if a.command == "tune":
        prompt_examples = example_ids()
        ids = split["tuning"] + [i for i in split["examples"] if i not in prompt_examples]
        verdicts = run(ids, "tune", a.backend)
        table(verdicts if a.all else [v for v in verdicts if v["answer"] != labels[v["id"]]], labels)
        report(verdicts, labels, f"tuning set + {len(ids) - len(split['tuning'])} examples not in the prompt")
        if a.backend != SCRIPTED:
            with open(TUNING_LOG, "a") as f:
                got = {v["id"]: v["answer"] for v in verdicts}
                tpr, tnr = rates(got, labels)
                f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "prompt_sha256": pin()["prompt_sha256"],
                                    "session": verdicts[0]["session"], "items": len(ids), "tpr": tpr, "tnr": tnr,
                                    "misses": [v["id"] for v in verdicts if v["answer"] != labels[v["id"]]]}) + "\n")
        return 0

    if a.command == "freeze":
        record = {"frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pin": pin(), "examples": example_ids(),
                  "settings_digest": load_settings(ROOT / "settings.yaml").digest()}
        FROZEN.write_text(json.dumps(record, indent=2) + "\n")
        print(f"frozen: prompt {record['pin']['prompt_sha256'][:12]}, model {record['pin']['model']}, "
              f"max_tokens {record['pin']['max_tokens']}, effort {record['pin']['effort']} -> {FROZEN.relative_to(ROOT)}")
        return 0

    if a.command == "test":
        scripted = a.backend == SCRIPTED
        if not scripted:
            frozen_check()
        out = VERDICTS / (f"scripted_test_{a.n}.jsonl" if scripted else f"test_{a.n}.jsonl")
        if out.exists() and not a.force:
            raise SystemExit(f"{out.relative_to(ROOT)} exists: a test run is not repeated to pick a better one "
                             "(pass --force only if the run failed)")
        verdicts = run(split["test"], f"test-{a.n}", a.backend)
        write_verdicts(out, verdicts)
        report(verdicts, labels, f"test run {a.n}")
        print(f"wrote {out.relative_to(ROOT)}")
        return 0

    if a.command == "recorded":
        scripted = a.backend == SCRIPTED
        if not scripted:
            frozen_check()
        tests = VERDICTS / ("scripted_test_1.jsonl" if scripted else "test_1.jsonl")
        if not tests.exists():
            raise SystemExit(f"{tests.relative_to(ROOT)} does not exist: run `test 1` first, its TPR and TNR are what "
                             "corrects the pass rate")
        out = VERDICTS / ("scripted_recorded.jsonl" if scripted else "recorded.jsonl")
        if out.exists() and not a.force:
            raise SystemExit(f"{out.relative_to(ROOT)} exists (pass --force only if the run failed)")
        ids = recorded_with_comment()
        verdicts = run(ids, "recorded", a.backend, {i: recorded_output(i) for i in ids})
        write_verdicts(out, verdicts)
        return show_correction(verdicts, tests, labels, split, out)

    if a.command == "versions":
        scripted = a.backend == SCRIPTED
        if not scripted:
            frozen_check()
        tests = VERDICTS / ("scripted_test_1.jsonl" if scripted else "test_1.jsonl")
        if not tests.exists():
            raise SystemExit(f"{tests.relative_to(ROOT)} does not exist: run `test 1` first, the versions are compared with it")
        out = VERDICTS / ("scripted_versions.jsonl" if scripted else "versions.jsonl")
        if out.exists() and not a.force:
            raise SystemExit(f"{out.relative_to(ROOT)} exists (pass --force only if the run failed)")
        outputs = version_outputs(split["test"])
        verdicts = run(list(outputs), "versions", a.backend, outputs)
        for key, v in zip(outputs, verdicts):
            v["version"] = key.split(":")[1]
        write_verdicts(out, verdicts)
        return show_versions(verdicts, tests, labels, split)

    if a.command == "moved":
        out, tests = VERDICTS / "versions.jsonl", VERDICTS / "test_1.jsonl"
        for f in (out, tests):
            if not f.exists():
                raise SystemExit(f"{f.relative_to(ROOT)} does not exist: run `test 1` and `versions` first")
        rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
        return show_versions(rows, tests, labels, split)

    if a.command == "flips":
        return show_consistency(labels, split)

    if a.command == "correction":
        out, tests = VERDICTS / "recorded.jsonl", VERDICTS / "test_1.jsonl"
        for f in (out, tests):
            if not f.exists():
                raise SystemExit(f"{f.relative_to(ROOT)} does not exist: run `test 1` and `recorded` first")
        verdicts = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
        return show_correction(verdicts, tests, labels, split, out, wrote=False)

    raise SystemExit(f"`{a.command}` is a later task of Part D")


if __name__ == "__main__":
    raise SystemExit(main())
