"""Part D: fill the `judge` block of reports/LAB_07.json from the verdict files, computing every value fresh with
the functions eval/judge.py already uses, so no number is copied by hand and none can be stale.

    python scripts/fill_judge_block.py            # print the block
    python scripts/fill_judge_block.py --write    # write it into reports/LAB_07.json (every other key is kept)

It reads eval/labels/{labels.csv,split.yaml}, eval/judge/verdicts/{test_1,test_2,test_3,recorded,versions}.jsonl and
fixtures/judge/outputs/ (for each output's system). It spends no tokens.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from eval import judge

V = judge.VERDICTS


def rows(name: str) -> list[dict]:
    path = V / f"{name}.jsonl"
    if not path.exists():
        sys.exit(f"{path.relative_to(ROOT)} does not exist yet: it comes from `python -m eval.judge "
                 f"{ {'test_1': 'test 1', 'test_2': 'test 2', 'test_3': 'test 3', 'recorded': 'recorded', 'versions': 'versions'}[name] }`")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


labels, split = judge.load_labels(), judge.load_split()
test_l = {i: labels[i] for i in split["test"]}
runs = [{v["id"]: v["answer"] for v in rows(f"test_{n}")} for n in (1, 2, 3)]
recorded = rows("recorded")
versions = rows("versions")

tpr, tnr = judge.rates(runs[0], test_l)
p = sum(1 for v in recorded if v["answer"] == "pass") / len(recorded)
coin = judge.is_coin(tpr, tnr)
corrected = None if coin else judge.correct(p, tpr, tnr)
interval = None if coin else list(judge.bootstrap(runs[0], test_l, p))
c = judge.consistency(runs, test_l)
moved = judge.moved_items(versions, runs[0])
outputs = judge.load_outputs()
systems = {i: o.get("system") for i, o in outputs.items()}
per_system = judge.by_system(runs[0], test_l, systems)

block = {
    "split": {k: len(split[k]) for k in ("examples", "tuning", "test")},
    "model": rows("test_1")[0]["model"],                       # the version that served the calls, as the API reported it
    "tpr": tpr, "tnr": tnr, "p": p, "corrected": corrected, "interval": interval, "coin": coin,
    "flip_rate": c["flip_rate"],
    "majority": {"tpr": c["majority"]["tpr"], "tnr": c["majority"]["tnr"], "kept": c["majority"]["kept"]},
    "moved_share": len(moved) / len(split["test"]),
    "by_system": {sy: {"tpr": r["tpr"], "tnr": r["tnr"]} for sy, r in per_system.items()},
}
print(json.dumps(block, indent=2))
if "--write" in sys.argv:
    path = os.path.join(ROOT, "reports", "LAB_07.json")
    doc = json.load(open(path))
    doc["judge"] = block
    json.dump(doc, open(path, "w"), indent=2)
    print(f"\nwrote the judge block into reports/LAB_07.json ({len(doc)} keys kept)")
