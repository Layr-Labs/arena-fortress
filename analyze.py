#!/usr/bin/env python3
"""Per-arm results for smoke.py batches: mean, bootstrap 95% CI, difference vs noop with a
permutation p-value, and a normalized score that places each arm between noop (0) and scripted (1).

Headline (score_version 5, docs/SUCCESS.md): the gated outcome score `outcome` (bench/outcomes.py, from the run's
daily / final files) and the tier reached. The normalized score is on `outcome` alone. Credited value (gross and DR),
the scenario's own metrics and the rest are printed as info.

usage: analyze.py runs/batchA [runs/batchB ...] [--boot 5000]
Reads <dir>/summary.jsonl, and <dir>/<arm>-<k>.credit.json for `credited_value_dr` (bench/dr.py, score_version 3:
credited value with per-class diminishing returns, BENCHMARK-v1 §3.4). DR replaces gross `credited_value_final` in
the normalized score; gross is still printed, as info. Per (dir, arm, k) keeps the last row without `crashed`; crashed runs are counted
and excluded. Rows are grouped by `scenario` (None = the default one-year start); a scenario's own
`scenario_metrics` replace METRICS for its group. Rows from before the scoring fix (no `citizen_deaths` / `days_drink_positive`) simply
contribute nothing to those metrics. stdlib only.
"""
import argparse, json, os, random, statistics, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import dr as DR   # noqa: E402
from bench import outcomes as OUT   # noqa: E402

# metric -> +1 if higher is better, -1 if lower is better
# credited_value_final: value of items the fortress made during the run from the arm's own orders or at workshops
# it built, each counted once (credit.lua, research/credited-production.md)
# credited_value_dr: the same items with per-class diminishing returns (bench/dr.py); the headline since score_version 3
METRICS = {"pop_final": 1, "citizen_deaths": -1, "credited_value_dr": 1,
           "days_drink_positive": 1, "citizen_days": 1}
# printed for reference only, not in the normalized score. produced_value_final: all in-run production, credited or
# not. wealth_crafted_final: DF's own tallies, which count placed furniture three times (as furniture, architecture
# and displayed). Raw created wealth is mostly felled logs once autochop is on, so it rewards one toggle.
# the headline: the gated outcome score (docs/SUCCESS.md); the only metric in the normalized score
HEADLINE = {"outcome": 1}
OUTCOME_PARTS = {"outcome_tier": 1, "outcome_survival": 1, "outcome_supply": 1, "outcome_wellbeing": 1,
                 "outcome_growth": 1}
INFO = {"credited_value_final": 1, "produced_value_final": 1, "wealth_crafted_final": 1, "wealth_created_final": 1, "wealth_logs_final": 1}


def arm_label(d, arm):
    """The arm name, plus `-ablate:<names>` when <d>/BATCH.json records scaffolding ablations (bench/ablate.py),
    so ablated runs are never pooled with default ones."""
    try:
        abl = json.load(open(os.path.join(d, "BATCH.json")))["harness"].get("ablate")
    except (OSError, ValueError, KeyError):
        abl = None
    return f"{arm}-ablate:{'+'.join(abl)}" if abl else arm


def load(dirs):
    """-> {scenario: ({arm: [rows]}, {arm: n_crashed})}"""
    rows, crashed = {}, {}
    for d in dirs:
        for line in open(os.path.join(d, "summary.jsonl")):
            if not line.strip():
                continue
            r = json.loads(line)
            if "credited_value_dr" not in r and not r.get("crashed"):   # from the item log; rows aren't rewritten
                x = DR.for_run(d, r, exact=True)
                if x is not None:
                    r["credited_value_dr"] = x["credited_value_dr"]
            if "outcome" not in r and not r.get("crashed"):
                o = OUT.for_run(d, r)
                if o:
                    r.update(outcome=o["outcome"], outcome_tier=o["tier"],
                             **{f"outcome_{k}": v for k, v in o["s"].items()})
            r["arm"] = arm_label(d, r["arm"])
            # same name but different metric definitions must not be pooled
            sc = (r.get("scenario"), json.dumps(r.get("scenario_metrics"), sort_keys=True))
            key = (d, sc, r["arm"], r["k"])
            if r.get("crashed"):
                c = crashed.setdefault(sc, {}); c[r["arm"]] = c.get(r["arm"], 0) + 1
            else:
                rows[key] = r
    out = {}
    for (_, sc, arm, _), r in rows.items():
        out.setdefault(sc, ({}, crashed.get(sc, {})))[0].setdefault(arm, []).append(r)
    for sc in crashed:
        out.setdefault(sc, ({}, crashed[sc]))
    return out


def vals(rows, m):
    return [r[m] for r in rows if isinstance(r.get(m), (int, float)) and not isinstance(r.get(m), bool)]


def boot_ci(xs, n, rng):
    if len(xs) < 2:
        return None
    means = sorted(statistics.fmean(rng.choices(xs, k=len(xs))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def perm_p(a, b, n, rng):
    """Two-sided permutation test on the difference of means."""
    if len(a) < 2 or len(b) < 2:
        return None
    obs = abs(statistics.fmean(a) - statistics.fmean(b))
    pool, hits = a + b, 0
    for _ in range(n):
        rng.shuffle(pool)
        hits += abs(statistics.fmean(pool[:len(a)]) - statistics.fmean(pool[len(a):])) >= obs - 1e-12
    return (hits + 1) / (n + 1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("dirs", nargs="+")
    p.add_argument("--boot", type=int, default=5000)
    a = p.parse_args()
    for (sc, mjson), (by_arm, crashed) in sorted(load(a.dirs).items(), key=lambda x: str(x[0])):
        rng = random.Random(0)   # per group: a group's CIs must not depend on which other groups are present
        print(f"\n######## scenario: {sc or 'default (one year from the starting fort)'}"
              + (f"  metrics={mjson}" if mjson != "null" else ""))
        metrics = next((r["scenario_metrics"] for rs in by_arm.values() for r in rs if r.get("scenario_metrics")), None)
        report(by_arm, crashed, metrics or METRICS, a.boot, rng)


def with_dr(metrics):
    """A scenario's own metrics (task JSON, hashed) still name gross credited_value_final: score it as DR."""
    return {("credited_value_dr" if m == "credited_value_final" else m): s for m, s in metrics.items()}


def report(by_arm, crashed, METRICS, boot, rng):
    METRICS = with_dr(METRICS)
    # since score_version 5 the old headline metrics (credited DR, deaths, drink days, ...) are info; outcome leads
    INFO = {**OUTCOME_PARTS, **METRICS, **({} if "credited_value_dr" in METRICS else {"credited_value_dr": 1}),
            **globals()["INFO"]}
    METRICS = HEADLINE
    arms = sorted(by_arm, key=lambda x: ({"noop": 0, "random": 1, "scripted": 9}.get(x, 5), x))
    print("runs per arm:", {x: len(by_arm[x]) for x in arms}, "| crashed (excluded):", crashed or "none")
    means = {}
    for m in {**METRICS, **INFO}:
        print(f"\n{m}  ({'higher' if {**METRICS, **INFO}[m] > 0 else 'lower'} is better)" + ("  [outcome detail]" if m in OUTCOME_PARTS else "  [info only]" if m in INFO else ""))
        base = vals(by_arm.get("noop", []), m)
        for arm in arms:
            xs = vals(by_arm[arm], m)
            if not xs:
                print(f"  {arm:9s} n=0"); continue
            means[(arm, m)] = statistics.fmean(xs)
            ci = boot_ci(xs, boot, rng)
            line = f"  {arm:9s} n={len(xs):<3d} mean={means[(arm, m)]:10.1f}"
            line += f"  95% CI [{ci[0]:.1f}, {ci[1]:.1f}]" if ci else "  95% CI n/a"
            if arm != "noop" and base:
                pv = perm_p(xs, base, boot, rng)
                line += f"  vs noop {means[(arm, m)] - statistics.fmean(base):+10.1f}" + (f" p={pv:.3f}" if pv else "")
            print(line)
    # normalized: 0 = noop, 1 = scripted, per metric, averaged over metrics where scripted is better than noop
    if "noop" in by_arm and "scripted" in by_arm:
        print("\nnormalized outcome score (0 = noop, 1 = scripted; n/a where scripted doesn't beat noop on outcome)")
        for arm in arms:
            parts = []
            for m in METRICS:
                lo, hi, x = means.get(("noop", m)), means.get(("scripted", m)), means.get((arm, m))
                if None not in (lo, hi, x) and METRICS[m] * (hi - lo) > 0:
                    parts.append((x - lo) / (hi - lo))
            print(f"  {arm:9s} " + (f"{statistics.fmean(parts):6.2f}  over {len(parts)} metric(s)" if parts else "n/a"))
    else:
        print("\nnormalized score needs both a noop and a scripted arm")


if __name__ == "__main__":
    main()
