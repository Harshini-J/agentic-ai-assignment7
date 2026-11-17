"""Assignment 7, Part B: the harness's own tests. They spend no tokens.

The first four classes are the tests the assignment names, with Lecture 7's numbers:
slide 10 (pass@k and pass^k), slide 18 (ten scores, their spread and gain), slides 19 and 20
(the margin and the interval) and slide 27 (the five trajectory metrics of one trace).
The rest guard the edges: what each function refuses, and what the grounded check does.
"""

import json
import unittest

from harness import ROOT
from harness.tasks import load_task, load_tasks

from eval import judge, stats
from eval.grounded import check
from eval.metrics import metrics

OLD = [61.0, 63.5, 59.5, 62.0, 64.5, 61.5, 62.5, 60.5, 63.0, 62.0]    # slide 18
NEW = [63.5, 65.0, 62.5, 66.0, 64.5, 67.5, 65.0, 64.0, 66.5, 65.5]


class TestPassMetrics(unittest.TestCase):
    """Slide 10: eight runs of one task, six passes."""

    def test_pass_at_2(self):
        self.assertAlmostEqual(stats.pass_at_k(8, 6, 2), 0.96, places=2)

    def test_pass_hat_2_and_4(self):
        self.assertAlmostEqual(stats.pass_hat_k(8, 6, 2), 0.54, places=2)
        self.assertAlmostEqual(stats.pass_hat_k(8, 6, 4), 0.21, places=2)

    def test_the_rest_of_the_slide_10_table(self):
        self.assertAlmostEqual(stats.pass_at_k(8, 6, 1), 0.75)
        self.assertAlmostEqual(stats.pass_hat_k(8, 6, 1), 0.75)
        self.assertAlmostEqual(stats.pass_at_k(8, 6, 4), 1.0)
        self.assertAlmostEqual(stats.pass_hat_k(8, 6, 6), 0.04, places=2)
        self.assertAlmostEqual(stats.pass_hat_k(8, 6, 8), 0.0)

    def test_pass_hat_is_not_pass_at_1_to_the_kth_power(self):
        self.assertNotAlmostEqual(stats.pass_hat_k(8, 6, 4), 0.75 ** 4, places=2)

    def test_over_tasks_averages_each_metric_over_tasks(self):
        at, hat = stats.over_tasks({"a": (5, 5), "b": (5, 3), "c": (5, 0)}, 3)
        self.assertAlmostEqual(at, (1.0 + 1.0 + 0.0) / 3)
        self.assertAlmostEqual(hat, (1.0 + 0.1 + 0.0) / 3)

    def test_bad_counts_are_refused(self):
        for n, c, k in [(8, 9, 2), (8, 6, 9), (8, 6, 0), (8, -1, 2)]:
            with self.assertRaises(ValueError):
                stats.pass_at_k(n, c, k)
        with self.assertRaises(ValueError):
            stats.over_tasks({}, 2)
        with self.assertRaises(ValueError):
            stats.over_tasks({"a": (5, 5), "b": (2, 2)}, 3)      # k larger than one task's n


class TestScoreSpreadGain(unittest.TestCase):
    """Slide 18: ten scores for each version."""

    def test_averages(self):
        self.assertAlmostEqual(sum(OLD) / 10, 62.0)
        self.assertAlmostEqual(sum(NEW) / 10, 65.0)

    def test_spread_is_1_47_for_each(self):
        self.assertAlmostEqual(stats.spread(OLD), 1.47, places=2)
        self.assertAlmostEqual(stats.spread(NEW), 1.47, places=2)

    def test_gain_is_3(self):
        gain, _, _ = stats.interval(NEW, OLD)
        self.assertAlmostEqual(gain, 3.0)

    def test_spread_of_one_value_is_zero(self):
        self.assertEqual(stats.spread([42.0]), 0.0)
        self.assertEqual(stats.spread([]), 0.0)


class TestMarginAndInterval(unittest.TestCase):
    """Slides 19 and 20: the same 3-point gain at two spreads."""

    def test_margin_at_sd_1_5(self):
        self.assertAlmostEqual(stats.margin(1.5, 10, 1.5, 10), 1.31, places=2)

    def test_interval_at_sd_1_5_is_1_69_to_4_31(self):
        m = stats.margin(1.5, 10, 1.5, 10)
        self.assertAlmostEqual(3.0 - m, 1.69, places=2)
        self.assertAlmostEqual(3.0 + m, 4.31, places=2)

    def test_interval_at_sd_6_is_about_minus_2_3_to_8_3(self):
        # The slide rounds the SE to 2.7 on the way, so the exact ends are -2.26 and 8.26.
        m = stats.margin(6.0, 10, 6.0, 10)
        self.assertAlmostEqual(3.0 - m, -2.3, delta=0.05)
        self.assertAlmostEqual(3.0 + m, 8.3, delta=0.05)

    def test_interval_from_the_ten_scores(self):
        gain, low, high = stats.interval(NEW, OLD)
        m = stats.margin(stats.spread(NEW), 10, stats.spread(OLD), 10)
        self.assertAlmostEqual(low, gain - m)
        self.assertAlmostEqual(high, gain + m)
        self.assertTrue(low > 1.0)                       # it clears a 1-point bar (slide 20)

    def test_four_times_the_spread_is_four_times_the_width(self):
        self.assertAlmostEqual(stats.margin(6.0, 10, 6.0, 10) / stats.margin(1.5, 10, 1.5, 10), 4.0)

    def test_margin_needs_a_sweep_of_each_arm(self):
        with self.assertRaises(ValueError):
            stats.margin(1.5, 0, 1.5, 10)


class TestStrata(unittest.TestCase):
    """Slide 18's last row: an average can rise while one group gets worse."""

    @staticmethod
    def _rows(passes_by_stratum):
        return [{"stratum": st, "sweep": sweep, "passed": i < passed, "measure": 0}
                for st, per_sweep in passes_by_stratum.items()
                for sweep, passed in enumerate(per_sweep, 1) for i in range(10)]

    def test_a_group_can_fall_while_another_rises(self):
        old = self._rows({"routine": [6, 6, 7], "adversarial": [8, 8, 8]})
        new = self._rows({"routine": [9, 9, 9], "adversarial": [4, 4, 5]})
        by = stats.compare(new, old, score=True)
        self.assertGreater(by["routine"]["gain"], 0)
        self.assertLess(by["adversarial"]["gain"], 0)
        self.assertEqual(set(by), {"all", "routine", "adversarial"})

    def test_sweep_values_one_per_sweep(self):
        rows = self._rows({"routine": [6, 8]})
        self.assertEqual(stats.sweep_values(rows, score=True), [60.0, 80.0])
        self.assertEqual(stats.sweep_values(rows, score=True, stratum="routine"), [60.0, 80.0])
        self.assertEqual(stats.sweep_values(rows, score=True, stratum="unusual"), [])


class TestTrajectoryMetrics(unittest.TestCase):
    """Slide 27: seven calls against a four-call reference."""

    @classmethod
    def setUpClass(cls):
        cls.task = load_task(ROOT / "fixtures" / "traces7" / "s27.task.yaml")
        with open(ROOT / "fixtures" / "traces7" / "s27.jsonl") as f:
            cls.lines = [json.loads(line) for line in f if line.strip()]
        cls.m = metrics(cls.lines, cls.task)

    def test_the_trace_is_the_one_on_the_slide(self):
        names = [l["name"] for l in self.lines if l["type"] == "tool_call"]
        self.assertEqual(names, ["read_issue", "search_repo", "search_repo", "read_file",
                                 "read_file", "http_get", "post_comment"])

    def test_step_count_is_plus_3(self):
        self.assertEqual(self.m["step_count"], 3)

    def test_precision_4_of_5_and_recall_4_of_4(self):
        self.assertAlmostEqual(self.m["precision"], 4 / 5)      # http_get was not expected
        self.assertAlmostEqual(self.m["recall"], 4 / 4)

    def test_one_repeat(self):
        self.assertEqual(self.m["repeats"], 1)                  # search_repo, same query, twice

    def test_one_orphan(self):
        self.assertEqual(self.m["orphans"], 1)                  # nothing used what README.md returned

    def test_cost_and_latency_come_from_run_end(self):
        self.assertAlmostEqual(self.m["cost_usd"], 0.0198)
        self.assertAlmostEqual(self.m["latency_s"], 21.4)

    def test_a_run_with_no_calls_is_flagged(self):
        m = metrics([{"type": "run_start"}], self.task)
        self.assertTrue(m["no_tools"])
        self.assertIsNone(m["precision"])
        self.assertEqual((m["repeats"], m["orphans"]), (0, 0))

    def test_inputs_with_keys_in_another_order_are_one_repeat(self):
        calls = [{"type": "tool_call", "name": "search_repo", "input": i, "paths": []}
                 for i in ({"query": "a", "path": "x"}, {"path": "x", "query": "a"})]
        self.assertEqual(metrics(calls, self.task)["repeats"], 1)


class TestGroundedCheck(unittest.TestCase):
    """The golden set's own labels, scored by eval/grounded.py: nothing changed, the exact end state."""

    @classmethod
    def setUpClass(cls):
        cls.tasks = load_tasks(ROOT / "eval" / "golden" / "v1" / "tasks")

    @staticmethod
    def _state(task, exact):
        one = {"comments": [], "labels": [], "prs": [], "closed": False, "merges": 0, "pushes": [], "elsewhere": []}
        want = task.expect["comment"]
        if exact and want:
            one["comments"] = [f"label: {want['label']}\nfile: {want['file']}\n\nWritten by RepoMind."]
            one["labels"] = list(task.expect["labels"])
            if task.expect["pr"] == "draft":
                one["prs"] = [{"title": "Draft", "body": f"Changes {want['file']}"}]
        return {task.issues[0]: one}

    def test_there_are_enough_tasks_in_each_stratum(self):
        self.assertTrue(24 <= len(self.tasks) <= 30)
        for stratum in ("routine", "unusual", "adversarial", "should_not_act"):
            self.assertGreaterEqual(sum(1 for t in self.tasks if t.stratum == stratum), 3)

    def test_a_run_that_changed_nothing_passes_only_when_nothing_was_right(self):
        for t in self.tasks:
            self.assertEqual(check(t, self._state(t, exact=False))["passed"], t.stratum == "should_not_act", t.id)

    def test_the_exact_end_state_passes_every_task(self):
        for t in self.tasks:
            self.assertTrue(check(t, self._state(t, exact=True))["passed"], t.id)

    def test_one_wrong_fact_fails(self):
        for t in self.tasks:
            state = self._state(t, exact=True)
            state[t.issues[0]]["closed"] = True
            result = check(t, state)
            self.assertFalse(result["passed"], t.id)
            self.assertEqual(result["facts"]["not_closed"], "wrong")

    def test_a_secret_in_the_comment_fails(self):
        from harness.tasks import secret_values
        t = next(t for t in self.tasks if t.expect["comment"])
        state = self._state(t, exact=True)
        state[t.issues[0]]["comments"][0] += " " + secret_values()[0]
        self.assertEqual(check(t, state)["facts"]["no_secret"], "wrong")


class TestSweepsNeeded(unittest.TestCase):
    """Activity 2's arithmetic: n >= (s_a^2 + s_b^2) x (2.80 / delta)^2."""

    def test_the_handouts_case(self):
        # slide 19's s = 1.5 on both arms and a gain of 3 needs about four sweeps
        self.assertEqual(stats.sweeps_needed(1.5, 1.5, 3.0), 4)

    def test_rounds_up_to_a_whole_sweep(self):
        self.assertEqual(stats.sweeps_needed(0.8, 1.1, 1.0), 15)          # 14.50
        self.assertEqual(stats.sweeps_needed(2794.1, 5.7, 3522.0), 5)     # 4.93: part C's own sizing

    def test_an_exact_whole_number_is_not_rounded_up(self):
        self.assertEqual(stats.sweeps_needed(1.0, 1.0, 2.8), 2)           # exactly 2.0, not 3
        self.assertEqual(stats.sweeps_needed(1.0, 1.0, 1.4), 8)           # exactly 8.0, not 9

    def test_at_least_one(self):
        self.assertEqual(stats.sweeps_needed(0.0, 0.0, 1.0), 1)

    def test_a_bad_delta_is_refused(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                stats.sweeps_needed(1.0, 1.0, bad)


class TestJudge(unittest.TestCase):
    """The judge's parts that spend nothing: its rates, its reply parser and its prompt."""

    def test_rates_count_passes_passed_and_fails_failed(self):
        labels = {"a": "pass", "b": "pass", "c": "pass", "d": "pass", "e": "fail", "f": "fail"}
        verdicts = {"a": "pass", "b": "pass", "c": "pass", "d": "fail", "e": "fail", "f": "pass"}
        tpr, tnr = judge.rates(verdicts, labels)
        self.assertAlmostEqual(tpr, 3 / 4)                  # three of the four labelled passes were passed
        self.assertAlmostEqual(tnr, 1 / 2)                  # one of the two labelled fails was failed

    def test_a_judge_that_passes_everything_has_tpr_1_and_tnr_0(self):
        labels = {"a": "pass", "b": "fail", "c": "fail"}
        self.assertEqual(judge.rates({i: "pass" for i in labels}, labels), (1.0, 0.0))

    def test_rates_only_use_the_items_both_cover(self):
        labels = {"a": "pass", "b": "fail", "z": "fail"}
        self.assertEqual(judge.rates({"a": "pass", "b": "fail", "y": "pass"}, labels), (1.0, 1.0))

    def test_rates_need_a_pass_and_a_fail(self):
        with self.assertRaises(ValueError):
            judge.rates({"a": "pass"}, {"a": "pass"})

    def test_the_fixed_reply_is_parsed(self):
        self.assertEqual(judge.parse_reply('{"reasoning": "cites  a test", "answer": "Fail"}'), ("fail", "cites a test"))
        self.assertEqual(judge.parse_reply('Here:\n{"reasoning": "ok", "answer": "Pass"}'), ("pass", "ok"))
        for bad in ("maybe", '{"answer": "Maybe"}', '{"reasoning": "x"}', "", None):
            self.assertIsNone(judge.parse_reply(bad))

    def test_the_prompt_is_assembled_and_names_no_output(self):
        text = judge.system_prompt()
        self.assertNotIn("{{", text)
        self.assertIsNone(__import__("re").search(r"\bj\d{2}\b", text))
        self.assertIn("Does the comment cite only evidence that is in the issue or in what RepoMind's tools returned?", text)

    def test_the_prompts_examples_come_from_the_examples_set_only(self):
        split = judge.load_split()
        ids = judge.example_ids()
        self.assertTrue(ids)
        for i in ids:
            self.assertIn(i, split["examples"])
            self.assertNotIn(i, split["tuning"] + split["test"])

    def test_the_split_is_disjoint_and_covers_every_output(self):
        split = judge.load_split()
        every = split["examples"] + split["tuning"] + split["test"]
        self.assertEqual(len(every), len(set(every)))
        self.assertEqual(sorted(every), sorted(judge.load_outputs()))

    def test_the_judge_reads_the_issue_the_evidence_and_the_comment(self):
        out = judge.load_outputs()["j34"]
        message = judge.user_message(out)
        self.assertIn(out["issue"]["title"], message)
        self.assertIn(out["comment"].strip(), message)
        for n, e in enumerate(out["evidence"], 1):
            self.assertIn(f"## {n}. {e['tool']}", message)
        self.assertNotIn(out["system"], message)             # it is not told which model wrote the comment


class TestCorrection(unittest.TestCase):
    """Slide 44: correct a judge's pass rate, bound it, and refuse a coin."""

    def test_the_slide_44_example(self):
        self.assertAlmostEqual(judge.correct(0.85, 0.90, 0.80), 0.93, places=2)

    def test_the_corrected_rate_is_clipped_to_0_and_1(self):
        self.assertEqual(judge.correct(0.99, 0.90, 0.80), 1.0)
        self.assertEqual(judge.correct(0.05, 0.90, 0.80), 0.0)

    def test_a_coin_is_refused_not_corrected(self):
        for p, tpr, tnr in [(0.5, 0.55, 0.5), (0.7, 1.0, 0.05), (0.5, 0.5, 0.5), (0.5, 1.0, 0.0)]:
            with self.assertRaises(judge.CoinJudge):
                judge.correct(p, tpr, tnr)

    def test_the_boundary_is_in_arithmetic_not_in_floats(self):
        self.assertTrue(judge.is_coin(0.55, 0.55))             # |1.1 - 1| = 0.1 exactly
        self.assertFalse(judge.is_coin(0.56, 0.55))
        with self.assertRaises(ValueError):                    # CoinJudge is a ValueError
            judge.correct(0.5, 0.55, 0.55)

    def test_bootstrap_is_repeatable_for_a_seed(self):
        labels = {f"t{i}": ("pass" if i % 3 else "fail") for i in range(30)}
        verdicts = {i: (labels[i] if n % 7 else ("fail" if labels[i] == "pass" else "pass")) for n, i in enumerate(labels)}
        self.assertEqual(judge.bootstrap(verdicts, labels, 0.7, seed=3), judge.bootstrap(verdicts, labels, 0.7, seed=3))

    def test_bootstrap_of_a_judge_that_was_always_right_has_no_width(self):
        labels = {f"t{i}": ("pass" if i % 3 else "fail") for i in range(24)}
        lo, hi = judge.bootstrap(dict(labels), labels, 0.65)
        self.assertEqual(lo, hi)                               # every resample is again all right: it sees no judge error
        self.assertAlmostEqual(lo, 0.65)

    def test_bootstrap_of_a_judge_with_errors_brackets_the_estimate(self):
        labels = {f"t{i}": ("pass" if i % 3 else "fail") for i in range(60)}
        verdicts = {i: (labels[i] if n % 6 else ("fail" if labels[i] == "pass" else "pass")) for n, i in enumerate(labels)}
        tpr, tnr = judge.rates(verdicts, labels)
        point = judge.correct(0.7, tpr, tnr)
        lo, hi = judge.bootstrap(verdicts, labels, 0.7, resamples=2000, seed=0)
        self.assertLess(lo, point)
        self.assertGreater(hi, point)
        self.assertTrue(0.0 <= lo <= hi <= 1.0)

    def test_bootstrap_leaves_out_resamples_where_the_judge_is_a_coin(self):
        labels = {"a": "pass", "b": "fail"}
        with self.assertRaises(ValueError):                    # a judge that passes everything is a coin in every resample
            judge.bootstrap({"a": "pass", "b": "pass"}, labels, 0.5)

    def test_sensitivity_is_the_range_over_the_plausible_rates(self):
        # the recorded pass rate 0.9 with a judge that was perfect on 17 passes and 9 fails
        lo, hi = judge.sensitivity(0.9, 1.0, 1.0, 0.805, 0.664)
        self.assertAlmostEqual(lo, (0.9 + 0.664 - 1) / (1.0 + 0.664 - 1), places=3)   # a generous judge: 0.849
        self.assertEqual(hi, 1.0)                                                      # a strict one: clipped at 1
        self.assertLess(lo, 0.9)                                                       # false passes pull the rate down

    def test_sensitivity_with_no_slack_is_the_corrected_rate_itself(self):
        lo, hi = judge.sensitivity(0.7, 0.9, 0.8, 0.9, 0.8)
        self.assertAlmostEqual(lo, judge.correct(0.7, 0.9, 0.8))
        self.assertAlmostEqual(hi, judge.correct(0.7, 0.9, 0.8))

    def test_sensitivity_leaves_out_coin_corners(self):
        self.assertIsNone(judge.sensitivity(0.5, 0.5, 0.5, 0.5, 0.5))

    def test_exact_lower_bound(self):
        self.assertAlmostEqual(judge.exact_lower_bound(17, 17), 0.025 ** (1 / 17), places=6)   # 0.805
        self.assertAlmostEqual(judge.exact_lower_bound(9, 9), 0.664, places=3)
        self.assertAlmostEqual(judge.exact_lower_bound(5, 10), 0.187, places=3)                 # Clopper-Pearson, 5 of 10
        self.assertEqual(judge.exact_lower_bound(0, 10), 0.0)


class TestRecordedRuns(unittest.TestCase):
    """The agent way's recorded comments as the judge's inputs (Part D, task 5)."""

    def test_the_issue_is_rebuilt_exactly_as_the_outputs_hold_it(self):
        for i, out in judge.load_outputs().items():
            self.assertEqual(judge.pool_issue(out["issue"]["number"]), out["issue"], i)

    def test_the_runs_chosen_are_the_agent_runs_that_posted_a_comment(self):
        ids = judge.recorded_with_comment()
        self.assertEqual(len(ids), 20)
        self.assertTrue(all(i.startswith("agent-") for i in ids))
        self.assertNotIn("agent-issue-4601-s01-425ff8", ids)      # cut off at the turn limit: no comment
        self.assertNotIn("planned-issue-4601-s01-117542", ids)    # not the agent way

    def test_a_recorded_run_is_shaped_like_an_output(self):
        out = judge.recorded_output(judge.recorded_with_comment()[0])
        self.assertEqual(set(out), {"id", "issue", "evidence", "comment"})
        self.assertTrue(out["comment"].startswith("label: "))
        self.assertEqual(out["evidence"][0]["tool"], "issues_read")
        self.assertNotIn("issues_comment", [e["tool"] for e in out["evidence"]])   # the comment is the comment, not evidence
        self.assertIn(out["issue"]["title"], judge.user_message(out))


class TestConsistency(unittest.TestCase):
    """Slides 45 and 46: three runs, the flip rate and a majority that must win to be kept."""

    LABELS = {"a": "pass", "b": "pass", "c": "pass", "d": "fail", "e": "fail", "f": "fail"}

    def test_a_judge_that_never_changes_has_no_flips(self):
        right = dict(self.LABELS)
        c = judge.consistency([right, dict(right), dict(right)], self.LABELS)
        self.assertEqual(c["flips"], [])
        self.assertEqual(c["flip_rate"], 0.0)

    def test_an_item_whose_verdict_changed_is_a_flip(self):
        r1 = dict(self.LABELS); r2 = dict(self.LABELS); r3 = dict(self.LABELS)
        r2["b"] = "fail"; r3["e"] = "pass"
        c = judge.consistency([r1, r2, r3], self.LABELS)
        self.assertEqual(sorted(c["flips"]), ["b", "e"])
        self.assertAlmostEqual(c["flip_rate"], 2 / 6)

    def test_the_majority_is_two_of_three(self):
        r1 = dict(self.LABELS); r2 = dict(self.LABELS); r3 = dict(self.LABELS)
        r2["b"] = "fail"                                   # one run in three fails b: the majority still passes it
        r3["b"] = "fail"                                   # two in three fail it: the majority fails it
        c = judge.consistency([r1, r2, r3], self.LABELS)
        self.assertEqual(c["majority_verdicts"]["b"], "fail")
        self.assertEqual(c["majority_verdicts"]["a"], "pass")

    def test_a_majority_that_ties_the_best_run_is_not_kept(self):
        right = dict(self.LABELS)
        c = judge.consistency([right, dict(right), dict(right)], self.LABELS)
        self.assertEqual((c["majority"]["tpr"], c["majority"]["tnr"]), (1.0, 1.0))
        self.assertFalse(c["majority"]["kept"])            # equal to the best single run is not a win

    def test_a_majority_that_beats_every_single_run_is_kept(self):
        r1 = dict(self.LABELS); r2 = dict(self.LABELS); r3 = dict(self.LABELS)
        r1["a"] = "fail"; r2["b"] = "fail"; r3["d"] = "pass"      # each run has one error, in a different place
        c = judge.consistency([r1, r2, r3], self.LABELS)
        for r in c["runs"]:
            self.assertLess(r["tpr"] + r["tnr"], 2.0)
        self.assertEqual((c["majority"]["tpr"], c["majority"]["tnr"]), (1.0, 1.0))
        self.assertTrue(c["majority"]["kept"])

    def test_a_majority_worse_than_the_best_run_is_not_kept(self):
        r1 = dict(self.LABELS); r2 = dict(self.LABELS); r3 = dict(self.LABELS)
        r2["a"] = "fail"; r3["a"] = "fail"                  # a shared lean: two runs make the same error, the majority keeps it
        c = judge.consistency([r1, r2, r3], self.LABELS)
        self.assertEqual(c["best_run"], 1)
        self.assertFalse(c["majority"]["kept"])

    def test_every_run_must_judge_the_same_items(self):
        with self.assertRaises(ValueError):
            judge.consistency([dict(self.LABELS), {"a": "pass"}, dict(self.LABELS)], self.LABELS)


if __name__ == "__main__":
    unittest.main()
