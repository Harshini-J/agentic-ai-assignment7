"""Assignment 7, Part B: the statistics of a result (checks/FORMATS.md, section 15.5).

Every function here is yours to write. The checker calls each one on cases of its
own, so keep the names, the arguments and what each returns. Slide numbers are
Lecture 7's.

    from eval.stats import pass_at_k, pass_hat_k, spread, margin, interval, sweeps_needed
    pass_at_k(8, 6, 2)                     # about 0.96 (slide 10)
    interval([63.5, 65.0, ...], [61.0, 63.5, ...])   # (gain, low, high), slide 19's four steps
    margin(1.5, 10, 1.5, 10)               # about 1.31: slide 19, from the spreads alone
"""

from __future__ import annotations

from math import ceil, comb, sqrt

Z95 = 1.96        # 95% of a bell curve lies within 1.96 SE of its middle (slide 17)
POWER_Z = 2.80    # 1.96 + 0.84: 95% confidence and 80% power (Activity 2)


def _check_counts(n: int, c: int, k: int) -> None:
    """n runs, c passes, k picked: whole numbers, 0 <= c <= n, 1 <= k <= n."""
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (n, c, k)):
        raise TypeError(f"n, c and k are whole numbers, not {n!r}, {c!r}, {k!r}")
    if not 0 <= c <= n:
        raise ValueError(f"c passes out of n runs needs 0 <= c <= n, not c={c}, n={n}")
    if not 1 <= k <= n:
        raise ValueError(f"k runs picked from n needs 1 <= k <= n, not k={k}, n={n}")


def pass_at_k(n: int, c: int, k: int) -> float:
    """The chance that at least one of k runs picked from n passed, when c of the n
    passed: 1 - C(n - c, k) / C(n, k) (slide 10). k is at most n."""
    _check_counts(n, c, k)
    return 1 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """The chance that all k runs picked from n passed, when c of the n passed:
    C(c, k) / C(n, k) (slide 10). Never pass@1 to the kth power."""
    _check_counts(n, c, k)
    return comb(c, k) / comb(n, k)


def over_tasks(counts: dict[str, tuple[int, int]], k: int) -> tuple[float, float]:
    """pass@k and pass^k averaged over tasks, from each task's (n, c). Every task is
    counted, whatever its own n, and k must fit in each task's n: a task run fewer than k
    times has no pass@k, and it is refused, not skipped."""
    if not counts:
        raise ValueError("over_tasks needs at least one task")
    at = [pass_at_k(n, c, k) for n, c in counts.values()]
    hat = [pass_hat_k(n, c, k) for n, c in counts.values()]
    return sum(at) / len(at), sum(hat) / len(hat)


def spread(values: list[float]) -> float:
    """The SD of the values: sqrt(sum((v - average)^2) / (n - 1)) (slide 17); 0.0 for
    a single value (or none): one sweep has no spread to measure."""
    values = list(values)
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    return sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def margin(s_first: float, n_first: int, s_second: float, n_second: int) -> float:
    """Slide 19's margin from two arms' spreads and sweep counts: 1.96 x the SE of the
    difference, where each arm's SE is s / sqrt(n) and the difference's is
    sqrt(SE_first^2 + SE_second^2). margin(1.5, 10, 1.5, 10) is about 1.31."""
    if n_first < 1 or n_second < 1:
        raise ValueError(f"each arm needs at least one sweep, not {n_first} and {n_second}")
    se_first, se_second = s_first / sqrt(n_first), s_second / sqrt(n_second)
    return Z95 * sqrt(se_first ** 2 + se_second ** 2)


def interval(first: list[float], second: list[float]) -> tuple[float, float, float]:
    """Slide 19's four steps for two arms' sweep values: the gain, the average of
    `first` minus the average of `second`, and the low and high ends of its 95%
    interval. The SE of each average is s / sqrt(n); the SE of the difference is
    sqrt(SE_first^2 + SE_second^2); the interval is the gain +/- 1.96 x that SE.
    With one sweep an arm has no spread, so its margin is 0 and the interval says nothing:
    report it only from two sweeps of each arm."""
    first, second = list(first), list(second)
    if not first or not second:
        raise ValueError("interval needs the sweep values of both arms")
    gain = sum(first) / len(first) - sum(second) / len(second)
    m = margin(spread(first), len(first), spread(second), len(second))
    return gain, gain - m, gain + m


def sweeps_needed(s_a: float, s_b: float, delta: float) -> int:
    """Activity 2's arithmetic: the smallest whole n with
    n >= (s_a^2 + s_b^2) x (2.80 / delta)^2 (Part C, task 4)."""
    if delta <= 0:
        raise ValueError("delta, the smallest gain you would act on, must be above 0")
    return max(1, ceil((s_a ** 2 + s_b ** 2) * (POWER_Z / delta) ** 2 - 1e-9))


# -- from results lines (section 15.4) to sweep values, overall and by stratum ------------------

STRATA = ("routine", "unusual", "adversarial", "should_not_act")


def sweep_values(rows: list[dict], field: str = "measure", *, stratum: str | None = None,
                 score: bool = False) -> list[float]:
    """One value per sweep, in sweep order, from one arm's results lines. A sweep's value is the
    mean of `field` over its runs (slide 17), or, with score=True, its score: 100 x the share of
    its runs that passed. With `stratum`, only that stratum's runs count. A sweep with none of
    them is left out, so the arms must each be run on the same tasks (slide 16)."""
    by_sweep: dict = {}
    for r in rows:
        if stratum is None or r["stratum"] == stratum:
            by_sweep.setdefault(r["sweep"], []).append(r)
    out = []
    for sweep in sorted(by_sweep):
        runs = by_sweep[sweep]
        if score:
            out.append(100.0 * sum(1 for r in runs if r["passed"]) / len(runs))
        else:
            out.append(sum(r[field] for r in runs) / len(runs))
    return out


def compare(first_rows: list[dict], second_rows: list[dict], field: str = "measure", *,
            score: bool = False) -> dict:
    """The gain (first minus second) and its 95% interval over all tasks and on each stratum's
    tasks alone (slide 18's last row): {"all": {"gain", "low", "high", "n_first", "n_second",
    "s_first", "s_second"}, "<stratum>": {...}}. For "B - A", pass B's rows first."""
    out = {}
    for name in (None, *STRATA):
        a = sweep_values(first_rows, field, stratum=name, score=score)
        b = sweep_values(second_rows, field, stratum=name, score=score)
        if not a or not b:
            continue
        gain, low, high = interval(a, b)
        out["all" if name is None else name] = {"gain": gain, "low": low, "high": high,
                                                "n_first": len(a), "n_second": len(b),
                                                "s_first": spread(a), "s_second": spread(b)}
    return out
