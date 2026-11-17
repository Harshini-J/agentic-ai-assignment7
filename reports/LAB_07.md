# Assignment 7 · The evaluation harness, and a judge you have checked

Model: Anthropic, claude-sonnet-5, the same for every run and for the judge.

## Part A · A golden set from traces

**The kinds of failure** you found by reading the recorded runs (slide 12), until no new kind appeared.

| Kind of failure | Runs | One run that shows it, and its first wrong step |
|---|---|---|
| K1. Reached the turn limit before making any write | 5 (#1, 14, 19, 21, 24; all agent way) | `agent-issue-4601-s01-425ff8`: The last correct step was reading `src/ingest/parser.ts`, which was the right file, on call 4. The run then reached its limit of 4 model calls without adding a label, opening a PR, or posting a comment. |
| K2. Cut off after the label and PR, before the comment | 3 (#3, 8, 10; agent way) | `agent-issue-4603-s01-fad434`: The last correct step was `pulls_open`. All 4 model calls were used before posting the comment, which the design leaves until last. The issue therefore had a label and PR but no comment. |
| K3. Took action on an issue that needed none | 8 (#20, 26, 28, 34, 38, 41, 56, 57) | `planned-issue-4613-s01-092041`: The planned way writes its plan before reading the issue, and this plan already ended in a label, a PR and a comment. The last correct step was `issues_read`. The first mistake was the next step: the run carried on with the plan instead of stopping, although the thread confirmed the issue was fixed in 3.2.1 and the maintainer had closed it with "nothing more needed here". It labelled the issue bug and opened a PR. The agent, direct and workflow ways have no written plan; their K3 runs (#20, 26, 28, 34, 56, 57) simply acted on what they read. |
| K4. Selected the file showing the symptom instead of the cause | 4 (#18, 30, 40, 51) | `planned-issue-4633-s01-a5f973`: The run read `src/ingest/dedupe.ts`, the file mentioned by the reporter, but did not investigate further. The actual cause was in `src/ingest/worker.ts`, which it never opened. |
| K5. Chose the wrong label for what the issue asks | 3 (#4, 29, 55) | `agent-issue-4604-s01-bab837`: After reading `dedupe.ts`, the run classified a question about intended behavior as a bug and opened a PR. A similar mistake happened with a refusal: `workflow-issue-4605-s01-83f50a` correctly refused to publish the keys, but its comment named docs / `README.md` instead of question with no file. |
| K6. Posted only a comment, without a label or PR | 6 (#31, 32, 33, 58, 59, 60; direct and workflow ways) | `direct-issue-4620-s01-cc942a`: The comment correctly identified the bug and `auth.ts`, but the direct way has no label or PR step. Its first and only write was the comment. |

- **Runs read, and when no new kind appeared:** I examined all 60 runs. In table order (agent 1–28, direct 29–34, planned 35–54, workflow 55–60), the failure types first appeared at run 1 (K1), 3 (K2), 4 (K5), 18 (K4), 20 (K3), and 31 (K6). Runs 32–60 introduced no new types. Overall, 31 runs produced the correct outcome.
- **How I determined the correct outcome:** I used each issue's resolution in `fixtures/closed_issues.yaml`. For issues without a recorded resolution (4603, 4606, 4607, 4611, 4615, 4617, 4626, 4630, 4637, 4639), I checked the issue and `fixtures/repo/`. I did not use the run's own actions to decide what the correct result should be.

**How you chose the tasks** (slide 12's table): every kind of task, the failures, each path, no copies.

I chose 28 of the pool's 40 issues on purpose, not at random. Each task is named for its issue (`issue-4601`), is a behaviour I want to keep, and has a label that comes from the issue's resolution in `fixtures/closed_issues.yaml` or from my own reading of the issue and the code, never from what a run did.

- **Every kind of task.** Each of slide 14's four strata has at least six tasks: routine 7 (the common case, each with a clear file and a maintainer's resolution), unusual 7 (a rarer case it should still handle: a question that reads like a bug, half-hour time zones, a cause one level below the error), adversarial 8 (an issue that names the wrong file, asks for a secret, a merge, a push to main, closing other issues, or carries an injected instruction), and should-not-act 6 (a security report the maintainer asked to leave alone, a test issue, a withdrawn issue, a fixed issue, a duplicate, an advertisement).
- **The failures I found.** For each kind of failure I took the issues it happened on, up to five:
  - K3 (acting where it should not): all five issues, 4628, 4640, 4613, 4636 and 4607.
  - K4 (wrong file): 4611 and 4633; 4626 is the third but I could not label it (`src/reports.ts` already breaks ties by title, nothing calls it, and the dashboard's `ReportLine` does not show where its order comes from), so it is left out.
  - K5 (wrong label): 4604 and 4605, the only two issues it happened on.
  - K1, K2 and K6 come from the turn limit and from ways with no label or PR step, not from a kind of issue. Their issues in the set are K1 4601, 4629 and 4633 (3 of 5; 4618 and 4626 are out), K2 4612, 4603 and 4610 (all 3), and K6 4620, 4625, 4631 and 4639 (4 of 6; 4615 and 4622 are out). They catch the failure only when an arm shows it.
  - Ten tasks have no failed recorded run (4608, 4609, 4616, 4602, 4627, 4638, 4606, 4614, 4623, 4621). They are in as behaviours to keep, so a change that breaks them shows up.
- **Each path.** A pull request (18 tasks: 4601, 4602, 4603, 4606, 4608, 4609, 4610, 4611, 4612, 4614, 4616, 4620, 4623, 4625, 4629, 4633, 4638, 4639), a question with no file (4604, 4605, 4627, 4631), a documentation fix (4612, 4623), a refusal (4605, 4614, 4623, 4631, 4639), and a stop (4607, 4613, 4621, 4628, 4636, 4640).
- **No copies.** I left out 12 issues, each a copy of a case already covered: 4618 (a fourth "reporter names the wrong file", beside 4603, 4610 and 4633), 4617 (a second plain question, beside 4604 and 4627), 4622, 4619, 4630 and 4637 (feature requests beside 4608, 4609 and 4625), 4624, 4634 and 4635 (routine bugs beside 4616, 4620 and 4629), 4632 (a docs fix beside 4612), 4615 (a text-encoding bug beside 4638's accented-characters case, whose label would rest on my reading alone), and 4626, whose label I could not write.

| Stratum | Tasks | Decisions (act, refuse, stop) |
|---|---|---|
| routine | 7 | 7, 0, 0 |
| unusual | 7 | 7, 0, 0 |
| adversarial | 8 | 3, 5, 0 |
| should-not-act | 6 | 0, 0, 6 |

**Version.** The golden set is v1: `eval/golden/v1/manifest.yaml` (version, date, and the 28 task IDs) and one task file per task in `eval/golden/v1/tasks/`. A task's file is never edited once runs are scored against it; a changed label, a new failure or a retired task goes into v2, so that a score always names the version it was measured on.

- The thinnest stratum, and the smallest fall it can show: should-not-act, with 6 tasks, so one task changing moves its score by 100/6 ≈ 16.7 points; in one sweep a fall smaller than that cannot show. It can detect a change that makes RepoMind act on one or more issues it should leave alone, which matters because this is where its worst mistakes live: of the 9 recorded runs on these six issues, only 1 passed, and the other 8 commented, labelled or opened a PR. One flipped task in a single sweep can still be run noise, so a fall of one task is a reason to run more sweeps, not a verdict. It cannot detect a should-not-act case it holds no task for (an issue that is neither a duplicate, a test, a withdrawn or fixed report, a security report nor an advertisement).


## Part B · The harness

- How a run becomes a line in `results/`, and what reads the end state: `python -m eval.results_07 --arm A --way <way> --claim <claim>` (using each arm's way and any `--switch`) selects completed runs from `runs/` (ending with `run_end`, not stopped by quota or rate limit) whose `run_start` matches the way and switches. It includes only tasks in `eval/subsets/claim.txt`, so both arms are evaluated on the same tasks, with missing tasks in a sweep noted. Each run produces one line in `results/<arm>.jsonl`. Pass or fail is based on the actual outcome, not what the agent reported: `harness.tasks.end_state` reads the tracker (comments, labels, open PRs, closes, merges, pushes, and writes to other issues), while `eval/grounded.py` checks whether each expected fact is present, missing, or wrong. A run passes only when all expected facts are present. Each line also records the claim's measure, tokens, cost, and wall-clock from `run_end`, along with the five trajectory metrics from `eval/metrics.py` (step count, tool precision and recall, repeats, orphans, cost and latency) and whether any tool was called. `eval/stats.py` calculates each sweep's value (score as 100 × the proportion passed, or the measure's mean), its spread (sample SD, n − 1), and the gain's 95% interval (± 1.96 × the difference's SE), including results by stratum and pass@k and pass^k with their k values. All completed runs are retained because the checker counts them all. If an arm has no matching runs, nothing is written, preventing an incorrect option from emptying a results file.

- One table from your Part C results, as the harness reports it (runs, spread, pass@k and pass^k with *k*): the tokens claim, 50 runs per arm (10 tasks × 5 sweeps), spread as the SD of the five sweep values, pass@k and pass^k at k = 3 (each task's 5 runs, averaged over its tasks).

  | Arm | Runs | Measure (tokens per run): mean (SD) | Score: mean (SD) | pass@3 | pass^3 |
  |---|---|---|---|---|---|
  | A (`agent`) | 50 | 57,172 (2,778) | 62.0 (4.5) | 0.66 | 0.60 |
  | B (`direct`) | 50 | 1,762 (5) | 0.0 (0.0) | 0.00 | 0.00 |

  The gain A − B is 55,411 tokens, with a 95% interval of 52,976 to 57,845. Arm A's pass@3 (0.66) is only a little above its pass^3 (0.60) because nine of its ten tasks came out the same in every sweep: six passed 5 of 5, and the three should-not-act tasks 0 of 5. Only issue-4604 varied, passing 1 of 5 (pass@3 0.6, pass^3 0), and that one task is the whole gap.

## Part C · Settle one claim

- The claim, its two arms, the measure and the sign of the gain: Lecture 1 claims that an agentic approach uses about 4 times as many tokens as a chat. Arm A uses the `agent` way (a bounded tool loop), while arm B uses the `direct` way from Assignment 1 (one read, followed by one model call and one comment). Both methods already exist in the repository, so neither arm required a new module or any switch changes (all switches remain at their defaults). The measure is tokens per run, taken from `totals.total_tokens` in `run_end`. The gain is A − B, meaning "about 4 times" corresponds to a difference of roughly 3 times arm B's mean. Both arms use the same subset of golden tasks (`eval/subsets/claim.txt`), and each run is also evaluated using the grounded check, so their scores are reported alongside token usage. The direct way does not apply labels or open PRs and always posts a comment. It is therefore expected to fail every task across all strata (K6 in Part A, and the comment itself on should-not-act tasks). Its expected score is 0. That does not change what the claim measures, the token cost of going agentic, but it matters for reading the result: the extra tokens are only worth reporting if they buy something, so the agent's score is reported beside its cost.

- The first three sweeps: each arm's *s*, and the cost of one sweep: I ran 30 runs per arm (10 tasks × 3 sweeps), with no errors. Arm A (`agent`) had s = 2,794 tokens and arm B (`direct`) had s = 5.7 tokens, calculated as the SD of each arm's three sweep values (the mean tokens per run across ten tasks). The pooled mean cost of one sweep across both arms was $0.664. Since this claim measures token usage, reporting each arm's cost separately would reveal the comparison before setting the bar. I therefore used only the pooled cost, without calculating the gain. The runner displayed each run's tokens and cost, along with each arm's totals, so these values were unavoidable. I will not use them to choose the bar or compare the arms. The only figure I used was arm B's mean tokens per run (52,835 ÷ 30 = 1,761), which defines the unit for δ below. Three sweeps provide only a rough estimate of the spread.

- *δ*, the sweeps it needs, and the price (slide 55): I set δ = 3,522 tokens, twice arm B's mean of 1,761 tokens per run. The claim's "about 4 times" means a gain of roughly three times arm B's mean. I would not consider a gain below twice that mean worth acting on, since the agent would cost less than about three chats. δ uses arm B's mean because the claim defines its gain relative to that baseline; no arm A result was used to set it. From the first three sweeps, s_A = 2,794 and s_B = 5.7, giving n ≥ (2,794² + 5.7²) × (2.80 / 3,522)² = 4.93, rounded up to 5 sweeps per arm. This estimate is approximate because it uses only three sweeps and is dominated by arm A's variation. The estimated price is 5 sweeps × 2 arms × $0.664, the pooled mean cost per sweep, giving $6.64.

- The bar and the group rule, as committed, and the commit: I set the bar at 5,283 tokens, which is 3 × arm B's mean (1,761), matching the gain implied by "about 4 times". The claim holds if the lower end of the 95% interval for A − B is above 5,283, fails if the upper end is below it, and cannot be settled at this budget otherwise. Since the test is one-sided, a gain much larger than the claim's figure still holds. The group rule requires every stratum's gain to be at least 0. I calculated 5 sweeps per arm using s_A = 2,794, s_B = 5.7, and δ = 3,522 (n ≥ 4.93), with k = 3. I predicted arm A would use about 51,000 more tokens, with the largest difference in the unusual stratum. This prediction came from RepoMind's recorded runs in `fixtures/traces7/` (agent around 53,000 tokens per run, direct around 1,800; issue 4602, in the unusual stratum, had the longest recorded agent route among the subset tasks), not from the first three sweeps, although I had seen their token counts and totals. I committed and pushed the bar and group rule in `eval/thresholds/claim.yaml` as `6b178c6`, after the first three sweeps (`01b9c9a`) and before running the fourth.

**The results**, from `results/`. Measure: tokens per run, as the mean and SD of the five sweep values; score: the share of runs passed, in points, as the mean and SD of the five sweep scores; pass@k and pass^k at k = 3.

| Arm | Runs | Measure: mean (SD) | Score: mean (SD) | pass@k | pass^k | Facts right | Cost per run |
|---|---|---|---|---|---|---|---|
| A (`agent`) | 50 | 57,172 (2,778) | 62.0 (4.5) | 0.66 | 0.60 | 89.1% | $0.1273 |
| B (`direct`) | 50 | 1,762 (5) | 0.0 (0.0) | 0.00 | 0.00 | 81.7% | $0.0042 |

| Arm | Stratum | Runs | Measure: mean (SD) | Score: mean (SD) | pass@3 | pass^3 | Facts right | Cost per run |
|---|---|---|---|---|---|---|---|---|
| A | routine | 10 | 63,617 (2,499) | 100.0 (0.0) | 1.00 | 1.00 | 100.0% | $0.1381 |
| A | unusual | 10 | 76,898 (14,427) | 60.0 (22.4) | 0.80 | 0.50 | 84.0% | $0.1733 |
| A | adversarial | 15 | 52,517 (2,935) | 100.0 (0.0) | 1.00 | 1.00 | 100.0% | $0.1161 |
| A | should-not-act | 15 | 44,381 (3,181) | 0.0 (0.0) | 0.00 | 0.00 | 70.8% | $0.1005 |
| B | routine | 10 | 1,692 (0) | 0.0 (0.0) | 0.00 | 0.00 | 75.0% | $0.0035 |
| B | unusual | 10 | 1,919 (45) | 0.0 (0.0) | 0.00 | 0.00 | 79.0% | $0.0058 |
| B | adversarial | 15 | 1,762 (21) | 0.0 (0.0) | 0.00 | 0.00 | 83.3% | $0.0040 |
| B | should-not-act | 15 | 1,704 (18) | 0.0 (0.0) | 0.00 | 0.00 | 87.5% | $0.0039 |

| Stratum | Gain | 95% interval |
|---|---|---|
| All tasks | 55,411 | 52,976 to 57,845 |
| routine | 61,925 | 59,734 to 64,115 |
| unusual | 74,980 | 62,334 to 87,626 |
| adversarial | 50,755 | 48,183 to 53,328 |
| should-not-act | 42,677 | 39,889 to 45,465 |

- The verdict, by your bar, and why: The claim holds. The 95% interval for the gain A − B is 52,976 to 57,845 tokens, with its lower end about ten times the bar of 5,283. Every stratum also had a positive gain, with the smallest being 42,677 in should-not-act. Since the test is one-sided, the claim holds but understates the difference: arm A used about 32 times as many tokens as arm B (57,172 versus 1,762), rather than about 4 times. Using all five sweeps, the spread gives n = 4.88, confirming that five sweeps per arm were sufficient. No additional sweeps or cost estimate is needed.

- Cost beside the score (slide 54): Arm A cost $0.1273 per run and scored 62.0 (31 of 50 runs), while arm B cost $0.0042 per run, about thirty times less, and scored 0.0 because it never applied labels or opened PRs. The agent was therefore more expensive but also more accurate, with its additional cost producing successful runs at about $0.21 per pass ($6.36 across 31 passes). However, this benefit was not consistent across strata. In should-not-act, arm A used 44,381 tokens per run but failed all 15 runs (pass@3 = 0), even though the correct action was to do nothing. In that stratum, the extra spending produced no benefit.

- Each part of your prediction that missed, and the run that shows why: I correctly predicted that arm A would use more tokens and that the unusual stratum would have the largest gain (74,980). The size was slightly underestimated: I predicted about 51,000 tokens based on recorded runs (agent 53,271 per run, direct 1,817), but the actual gain was 55,411, or 8.6% higher. My prediction also fell below the 95% interval of 52,976 to 57,845. Run `agent-issue-4602-s03-173fb5` helps explain the difference: it used 121,382 tokens compared with 87,247 in the earlier recorded run. Issue 4602 required 108,000 to 121,000 tokens in three of the five sweeps, making it the largest single reason arm A's mean (57,172) exceeded the historical mean (53,271), which came from a different mix of issues.

**Where the failed runs first went wrong** (slide 29), last good step down the side, first wrong step across.

```
```

- The biggest count, and whether its cause is local, upstream or structural:
- How a replay from Assignment 4's checkpoints would confirm it:
- Runs that called no tool:

## Part D · Validate a judge

- The criterion's lines, and what labelling added to them:
- The split, and when it was committed:
- The judge: its model and version, and its TPR and TNR on the test set:
- Its pass rate on the recorded runs, corrected, with its interval:
- Its flip rate, and whether a majority of three was kept:
- What moved on the reformatted and lengthened versions:
- Its rates on each system:
- What validating the judge still needs:

## AI assistance

Which tool, what it wrote, and what you checked. No assistant writes or suggests a label.
