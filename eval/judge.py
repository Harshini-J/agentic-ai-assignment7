"""Assignment 7, Part D: the judge, its rates and its correction (checks/FORMATS.md,
section 15.10).

    python -m eval.judge tune          # refine the prompt: the tuning set, and the examples not in the prompt
    python -m eval.judge freeze        # pin the judge: its prompt, model and settings (eval/judge/frozen.json)
    python -m eval.judge test 1        # run 1 on the test set: eval/judge/verdicts/test_1.jsonl
    python -m eval.judge versions      # the test items' list and long versions: versions.jsonl
    python -m eval.judge recorded      # the agent way's recorded comments: recorded.jsonl

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


def correct(p: float, tpr: float, tnr: float) -> float:
    """The share you would pass, labelling by hand, from the judge's pass rate p on
    outputs nobody labelled: (p + TNR - 1) / (TPR + TNR - 1) (slide 44), clipped to
    0 to 1. Raises CoinJudge when TPR + TNR is within 0.1 of 1."""
    raise NotImplementedError("Part D, task 5")


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
    (slide 44). A resample on which the judge is a coin is left out."""
    raise NotImplementedError("Part D, task 5")


def load_outputs(root: Path = ROOT) -> dict[str, dict]:
    """The 60 outputs to label, by ID (section 15.9)."""
    return {p.stem: json.loads(p.read_text()) for p in sorted((root / "fixtures" / "judge" / "outputs").glob("*.json"))}


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


def run(ids: list[str], name: str, backend: str | None = None) -> list[dict]:
    """The judge over these outputs, in one metered session (its tokens and cost are recorded and priced)."""
    outputs, system = load_outputs(), system_prompt()
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
    sub.add_parser("versions", help="(a later task) the test items' list and long versions")
    sub.add_parser("recorded", help="(a later task) the agent way's recorded comments")
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

    raise SystemExit(f"`{a.command}` is a later task of Part D")


if __name__ == "__main__":
    raise SystemExit(main())
