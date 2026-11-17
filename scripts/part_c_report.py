"""Part C, task 6: every number the report asks for, from results/A.jsonl and results/B.jsonl,
by the rules the checker applies (checks/FORMATS.md, sections 15.4 and 15.8).

    python scripts/part_c_report.py                  # print the report's tables and the verdict
    python scripts/part_c_report.py --write-json     # also fill `claim` and `arms` in reports/LAB_07.json

It reads the bar, the group rule, k and the prediction from eval/thresholds/claim.yaml, as committed.
Run it only after sweeps 1 to 5 of both arms are finished and results_07 has been rerun.
"""
import argparse
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from eval import stats

STRATA = ("routine", "unusual", "adversarial", "should_not_act")
LABEL = {"routine": "routine", "unusual": "unusual", "adversarial": "adversarial", "should_not_act": "should-not-act"}


def load(arm: str) -> list[dict]:
    with open(os.path.join(ROOT, "results", f"{arm}.jsonl")) as f:
        return [json.loads(line) for line in f if line.strip()]


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def counts_by_task(rows):
    """{task: (n runs, c passes)}: where pass@k and pass^k begin (slide 10)."""
    out = {}
    for r in rows:
        n, c = out.get(r["task"], (0, 0))
        out[r["task"]] = (n + 1, c + bool(r["passed"]))
    return out


def pass_metrics(rows, k):
    counts = counts_by_task(rows)
    if not counts or any(n < k for n, _ in counts.values()):
        return None, None
    return stats.over_tasks(counts, k)


def arm_numbers(rows, k):
    measure, score = stats.sweep_values(rows, "measure"), stats.sweep_values(rows, "measure", score=True)
    at, hat = pass_metrics(rows, k)
    present = sum(r["facts"]["present"] for r in rows)
    total = sum(r["facts"]["total"] for r in rows)
    return {"runs": len(rows),
            "measure": {"mean": mean(measure), "sd": stats.spread(measure)},
            "score": {"mean": mean(score), "sd": stats.spread(score)},
            "pass_at_k": at, "pass_hat_k": hat,
            "facts_share": present / total if total else None,
            "cost_per_run_usd": mean(r["cost_usd"] for r in rows),
            "no_tools": sum(1 for r in rows if (r.get("metrics") or {}).get("no_tools"))}


def stratum_numbers(rows, k):
    out = {}
    for s in STRATA:
        part = [r for r in rows if r["stratum"] == s]
        if not part:
            continue
        at, hat = pass_metrics(part, k)
        out[s] = {"runs": len(part), "measure": mean(stats.sweep_values(part, "measure")),
                  "score": mean(stats.sweep_values(part, "measure", score=True)),
                  "pass_at_k": at, "pass_hat_k": hat}
    return out


def signed(gain_text, a_vals, b_vals):
    """(gain, low, high) as `gain` says it is signed: 'A - B' or 'B - A'."""
    if gain_text.replace(" ", "") == "B-A":
        return stats.interval(b_vals, a_vals)
    return stats.interval(a_vals, b_vals)


def fmt(x, nd=1, pct=False):
    if x is None:
        return "n/a"
    return f"{x * 100:.{nd}f}%" if pct else f"{x:,.{nd}f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write-json", action="store_true")
    args = ap.parse_args()

    spec = yaml.safe_load(open(os.path.join(ROOT, "eval", "thresholds", "claim.yaml")))
    k, bar, floor, gain_text = int(spec["k"]), spec["bar"], spec["group_floor"], str(spec["gain"])
    rows = {"A": load("A"), "B": load("B")}
    sweeps = {a: sorted({r["sweep"] for r in rows[a]}) for a in rows}
    if any(len(v) < 2 for v in sweeps.values()):
        sys.exit(f"need at least two sweeps of each arm; have {sweeps}")
    if sweeps["A"] != sweeps["B"]:
        print(f"WARNING: the arms' sweeps differ: {sweeps}\n")

    arms = {a: arm_numbers(rows[a], k) for a in rows}
    by_arm = {a: stratum_numbers(rows[a], k) for a in rows}
    a_vals, b_vals = stats.sweep_values(rows["A"], "measure"), stats.sweep_values(rows["B"], "measure")
    diff, lo, hi = signed(gain_text, a_vals, b_vals)
    by = {}
    for s in STRATA:
        av = stats.sweep_values(rows["A"], "measure", stratum=s)
        bv = stats.sweep_values(rows["B"], "measure", stratum=s)
        if len(av) >= 2 and len(bv) >= 2:
            by[s] = signed(gain_text, av, bv)
    breaks = [s for s, v in by.items() if v[0] < floor]
    verdict = "holds" if lo > bar and not breaks else "fails" if hi < bar else "cannot_settle"

    print(f"claim: {spec['claim']} ({spec['measure']}), gain {gain_text}; k = {k}; bar {bar:,}; group floor {floor}\n")
    print("| Arm | Runs | Measure: mean (SD) | Score: mean (SD) | pass@k | pass^k | Facts right | Cost per run |")
    print("|---|---|---|---|---|---|---|---|")
    for a in "AB":
        x = arms[a]
        print(f"| {a} | {x['runs']} | {fmt(x['measure']['mean'], 0)} ({fmt(x['measure']['sd'], 0)}) | "
              f"{fmt(x['score']['mean'])} ({fmt(x['score']['sd'])}) | {fmt(x['pass_at_k'], 2)} | {fmt(x['pass_hat_k'], 2)} | "
              f"{fmt(x['facts_share'], 1, True)} | ${x['cost_per_run_usd']:.4f} |")
    print(f"\n(pass@k and pass^k at k = {k}; runs that called no tool: A {arms['A']['no_tools']}, B {arms['B']['no_tools']})\n")

    print("| Arm | Stratum | Runs | Measure mean | Score | pass@k | pass^k |")
    print("|---|---|---|---|---|---|---|")
    for a in "AB":
        for s, v in by_arm[a].items():
            print(f"| {a} | {LABEL[s]} | {v['runs']} | {fmt(v['measure'], 0)} | {fmt(v['score'])} | "
                  f"{fmt(v['pass_at_k'], 2)} | {fmt(v['pass_hat_k'], 2)} |")

    print("\n| Stratum | Gain | 95% interval |")
    print("|---|---|---|")
    print(f"| All tasks | {diff:,.0f} | {lo:,.0f} to {hi:,.0f} |")
    for s, (d, l, h) in by.items():
        print(f"| {LABEL[s]} | {d:,.0f} | {l:,.0f} to {h:,.0f} |")

    print(f"\nverdict: {verdict.upper()}: interval low end {lo:,.0f} vs bar {bar:,}; "
          f"high end {hi:,.0f}; strata below {floor}: {breaks or 'none'}")

    # the arithmetic behind "n needed", now with all the sweeps
    s_a, s_b = stats.spread(a_vals), stats.spread(b_vals)
    n_now = stats.sweeps_needed(s_a, s_b, spec["delta"])
    pooled = mean(sum(r["cost_usd"] for r in rows[a] if r["sweep"] == s) for a in "AB" for s in sweeps[a])
    print(f"\nspread from all {len(a_vals)} sweeps: s_A = {s_a:,.1f}, s_B = {s_b:,.2f}; at delta = {spec['delta']:,} "
          f"that needs n = {n_now} sweeps per arm (committed: {spec['sweeps']}); "
          f"{n_now} x 2 x ${pooled:.4f} = ${n_now * 2 * pooled:.2f}"
          + ("   <-- more than the 5 you ran: report this n and its price" if n_now > spec["sweeps"] else ""))

    # the prediction, part by part
    pred = spec["prediction"]
    favoured = "A" if diff > 0 else "B"
    top = max(by, key=lambda s: by[s][0]) if by else None
    print(f"\nprediction: arm {pred['arm']}, by {pred['by']:,}, largest in {pred['stratum']}")
    print(f"observed:   arm {favoured}, by {abs(diff):,.0f} ({abs(diff) / pred['by']:.2f} x the prediction), largest in {LABEL.get(top, top)}")
    print("  arm:     " + ("as predicted" if favoured == pred["arm"] else "MISSED"))
    print("  by:      " + ("within 25% of the prediction" if abs(abs(diff) - pred["by"]) <= 0.25 * pred["by"] else "MISSED by more than 25%"))
    print("  stratum: " + ("as predicted" if top == pred["stratum"] else f"MISSED (the largest gap was in {LABEL.get(top, top)})"))
    longest = sorted(rows["A"], key=lambda r: -r["tokens"])[:3]
    print("  arm A's longest runs: " + "; ".join(f"{r['run_id']} ({r['stratum']}, {r['tokens']:,} tokens)" for r in longest))

    if args.write_json:
        path = os.path.join(ROOT, "reports", "LAB_07.json")
        doc = json.load(open(path))
        doc["claim"] = {"claim": spec["claim"], "measure": spec["measure"], "gain": gain_text, "k": k,
                        "sweeps": spec["sweeps"], "s_a": spec["s_a"], "s_b": spec["s_b"], "delta": spec["delta"],
                        "n_needed": spec["n_needed"], "price_usd": spec["price_usd"],
                        "difference": diff, "interval": [lo, hi],
                        "by_stratum": {s: {"difference": v[0], "interval": [v[1], v[2]]} for s, v in by.items()},
                        "verdict": verdict}
        doc["arms"] = {}
        for a, key in (("A", "arm_a"), ("B", "arm_b")):
            doc["arms"][a] = {"way": spec[key]["way"], "switches": spec[key].get("switches") or {},
                              **arms[a], "by_stratum": by_arm[a]}
        json.dump(doc, open(path, "w"), indent=2)
        print(f"\nwrote `claim` and `arms` to reports/LAB_07.json")


if __name__ == "__main__":
    main()