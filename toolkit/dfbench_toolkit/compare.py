"""compare: is the difference between two runs real, or DF's run-to-run noise?"""
import math, statistics

from . import scoring

SEASON0_NOISE_SD = 3.8      # S points: SD of the difference between two runs of one harness (runs/s0-noise-2026-10-27)
PROMOTION_BIPS = 250        # challenge/benchmark.json minScoreImprovementBips
SMALL_N = 3                 # below this many games per task (either side), the bootstrap CI is floored

# Per-game noise floors, per task, in the task's metric (lab partial; O for MY1/OP1). Source:
# runs/s0-noise-2026-10-27/README.md "Per-task game SD": the plain baseline's three private-pool runs (the median
# run for MY1/OP1, the largest for labs). LT01/LT03 measured 0 (saturated for those harnesses); 0.05 is an assumed
# minimum, since other harnesses do vary there. Tasks not listed fall back to their kind's value.
NOISE_FLOOR_SD = {"LT01": 0.05, "LT02": 0.12, "LT03": 0.05, "LT08": 0.046, "MY1": 17.7, "OP1": 16.7}
NOISE_FLOOR_BY_KIND = {"lab": 0.12, "outcome": 17.7}


def _stats(xs):
    return (round(statistics.mean(xs), 2) if xs else None, round(statistics.stdev(xs), 2) if len(xs) > 1 else None)


def _value_key(task):
    return "partial" if task["kind"] == "lab" else "O"


def pairs(a, b):
    """{task: [(recA, recB)]} for games on the same fort and seed in both runs (same task, k and seed)."""
    def keyed(run):
        out = {}
        for g in run.games:
            r = run.records.get(g.id)
            if r and r.get("status") == "ok" and run._scorable(r):
                out[(g.task, g.k, g.seed)] = r
        return out
    ka, kb = keyed(a), keyed(b)
    out = {}
    for key in sorted(set(ka) & set(kb), key=str):
        out.setdefault(key[0], []).append((ka[key], kb[key]))
    return out


def floor_sd(task):
    return NOISE_FLOOR_SD.get(task["id"], NOISE_FLOOR_BY_KIND["lab" if task["kind"] == "lab" else "outcome"])


def floored_ci(common, abt, bbt, weights, anchors, diff):
    """A normal-approximation 95% CI of the S difference whose per-game spread is at least the measured season-0
    noise (NOISE_FLOOR_SD): S is linear in each task's mean metric (suite_value), so its SE is the weighted sum of
    the per-task SEs. Used when a bootstrap over 1-2 games per task has (almost) no spread to resample."""
    fams = {}
    for t in common:
        fams.setdefault(t.get("family", t["id"]), []).append(t)
    tot = sum(weights.get(f, 0.0) for f in fams)
    if not tot:
        return None
    var = 0.0
    for f, ts in fams.items():
        for t in ts:
            if t["kind"] == "lab":
                an = anchors.get(t["id"]) or {"noop": 0.0, "witness": 1.0}
                den = an["witness"] - an["noop"]
                dscore = 100.0 / den if den > 0 else 0.0
            else:
                dscore = 1.0
            g = weights.get(f, 0.0) / tot / len(ts) * dscore
            k = _value_key(t)
            for gs in (abt[t["id"]], bbt[t["id"]]):
                xs = [x[k] for x in gs]
                sd_obs = statistics.stdev(xs) if len(xs) > 1 else 0.0
                var += (g * max(sd_obs, floor_sd(t))) ** 2 / len(xs)
    half = 1.96 * math.sqrt(var)
    return diff - half, diff + half, half


def compare(a, b, resamples=4000, seed=7):
    tv, sv, bs, src = scoring.agg(a.dir)
    tasks = {t["id"]: t for t in a.tasks}
    for t in b.tasks:
        tasks.setdefault(t["id"], t)
    abt, bbt = a.by_task(), b.by_task()
    common = [t for t in tasks.values() if t["id"] in abt and t["id"] in bbt]
    if not common:
        raise SystemExit("the two runs share no scored task")
    abt = {t["id"]: abt[t["id"]] for t in common}
    bbt = {t["id"]: bbt[t["id"]] for t in common}
    if a.anchors != b.anchors or a.weights != b.weights:
        raise SystemExit("the runs were scored with different anchors or weights: pass --suite <suite.json> to score "
                         f"both against one suite (A: {a.suite_source}; B: {b.suite_source})")
    weights, anchors = a.weights, a.anchors
    per_task = []
    for t in common:
        k = _value_key(t)
        ma, sa = _stats([g[k] for g in abt[t["id"]]])
        mb, sb = _stats([g[k] for g in bbt[t["id"]]])
        per_task.append({"task": t["id"], "metric": k, "n_a": len(abt[t["id"]]), "mean_a": ma, "sd_a": sa,
                         "n_b": len(bbt[t["id"]]), "mean_b": mb, "sd_b": sb,
                         "score_a": round(tv(t, abt[t["id"]], anchors), 1),
                         "score_b": round(tv(t, bbt[t["id"]], anchors), 1)})
    pa, _ = sv(abt, common, weights, anchors)
    pb, _ = sv(bbt, common, weights, anchors)
    b_cfg = a.bootstrap_cfg
    la, ua = bs(abt, common, weights, anchors, int(b_cfg.get("resamples", 10000)), int(b_cfg.get("seed", 0)),
                float(b_cfg.get("alpha", 0.05)))
    lb, ub = bs(bbt, common, weights, anchors, int(b_cfg.get("resamples", 10000)), int(b_cfg.get("seed", 0)),
                float(b_cfg.get("alpha", 0.05)))
    prs = pairs(a, b)
    paired_ok = prs and all(len(prs.get(t["id"], [])) >= 2 for t in common)
    d_ind = [-x for x in scoring.diff_bootstrap(abt, bbt, common, weights, anchors, resamples, seed, sv=sv)][::-1]
    d_pair = None
    if paired_ok:
        d_pair = [-x for x in scoring.diff_bootstrap(abt, bbt, common, weights, anchors, resamples, seed,
                                                     paired={t["id"]: prs[t["id"]] for t in common}, sv=sv)][::-1]
    ci = lambda d: (d[int(.025 * len(d))], d[min(len(d) - 1, int(.975 * len(d)))]) if d else (None, None)
    diff = pb - pa
    lo, hi = ci(d_pair or d_ind)
    n_now = min(min(len(v) for v in abt.values()), min(len(v) for v in bbt.values()))
    small = n_now < SMALL_N
    floored = floored_ci(common, abt, bbt, weights, anchors, diff) if small else None
    if floored:
        lo, hi = min(lo, floored[0]) if lo is not None else floored[0], max(hi, floored[1]) if hi is not None else floored[1]
    if lo is not None and lo > 0:
        verdict = "likely real: B is better than A"
    elif hi is not None and hi < 0:
        verdict = "likely worse: B is below A"
    elif small:
        verdict = (f"too few games to tell: {n_now} game(s) per task on the thinnest task, and DF's per-game noise "
                   "is larger than this difference")
    else:
        verdict = "within noise: the runs can't tell A and B apart"
    more = None
    if lo is not None and not (lo > 0 or hi < 0):
        half = (hi - lo) / 2
        if abs(diff) >= 0.25:
            more = max(SMALL_N, math.ceil(n_now * (half / abs(diff)) ** 2))
    clears = (lb - la) * 10000 >= PROMOTION_BIPS * abs(la) if la else None
    la_, lb_ = a.labels(), b.labels()
    differ = [k for k in ("stack", "scope", "result_kind", "suite", "anchors_id", "watch") if la_.get(k) != lb_.get(k)]
    return {"a": a.label, "b": b.label, "source": src, "suite": a.suite_source, "tasks": per_task,
            "labels_a": la_, "labels_b": lb_, "labels_differ": differ,
            "point_a": round(pa, 2), "point_b": round(pb, 2), "lcb_a": round(la, 2), "lcb_b": round(lb, 2),
            "ucb_a": round(ua, 2), "ucb_b": round(ub, 2), "diff": round(diff, 2),
            "ci95_independent": tuple(round(x, 2) for x in ci(d_ind)) if d_ind else None,
            "ci95_paired": tuple(round(x, 2) for x in ci(d_pair)) if d_pair else None,
            "n_pairs": sum(len(v) for v in prs.values()) if prs else 0,
            "verdict": verdict, "games_per_task_to_resolve": more, "min_games_per_task": n_now,
            "ci95_floored": tuple(round(x, 2) for x in floored[:2]) if floored else None, "clears_promotion_threshold": clears,
            "common_tasks": [t["id"] for t in common],
            "only_a": sorted(set(a.by_task()) - set(bbt)), "only_b": sorted(set(b.by_task()) - set(abt))}


def markdown(r):
    L = [f"# compare: A = `{r['a']}`, B = `{r['b']}`", "",
         f"Scored by the {r['source']} with the anchors and weights of {r['suite']}, over the tasks both runs "
         f"have: {', '.join(r['common_tasks'])}."]
    if r["only_a"] or r["only_b"]:
        L.append(f"Ignored (only in one run): A {r['only_a'] or '–'}, B {r['only_b'] or '–'}.")
    from .report import labels_line
    L += ["", "A " + labels_line(r["labels_a"])[2:], "", "B " + labels_line(r["labels_b"])[2:]]
    if r["labels_differ"]:
        L += ["", f"> **Warning:** the runs differ in {', '.join(r['labels_differ'])}, so the comparison mixes kinds "
                  "of result (e.g. a fake-stack or smoke run against a real one). Compare like with like."]
    L += ["", f"**Games per task:** " + ", ".join(f"{t['task']} A {t['n_a']} / B {t['n_b']}" for t in r["tasks"])
          + (f" (fewer than {SMALL_N} on some task: the CI is floored with season-0 per-game noise)"
             if r["min_games_per_task"] < SMALL_N else "")]
    L += ["", "| task | metric | A n | A mean ± sd | B n | B mean ± sd | task score A → B |",
          "|---|---|---|---|---|---|---|"]
    for t in r["tasks"]:
        L.append(f"| {t['task']} | {t['metric']} | {t['n_a']} | {t['mean_a']} ± {t['sd_a']} | {t['n_b']} | "
                 f"{t['mean_b']} ± {t['sd_b']} | {t['score_a']} → {t['score_b']} |")
    L += ["", f"- S point: A {r['point_a']}, B {r['point_b']}: **difference {r['diff']:+.2f}**",
          f"- 95% lower bound (the published scalar): A {r['lcb_a']}, B {r['lcb_b']}"]
    if r["ci95_paired"]:
        L.append(f"- 95% CI of the difference, **paired** on {r['n_pairs']} same-fort-and-seed games: "
                 f"{r['ci95_paired'][0]:+.2f} to {r['ci95_paired'][1]:+.2f} "
                 f"(independent: {r['ci95_independent'][0]:+.2f} to {r['ci95_independent'][1]:+.2f})")
    elif r["ci95_independent"]:
        L.append(f"- 95% CI of the difference (independent resampling): {r['ci95_independent'][0]:+.2f} to "
                 f"{r['ci95_independent'][1]:+.2f}")
    if r.get("ci95_floored"):
        L.append(f"- 95% CI of the difference with the season-0 per-game noise floor: {r['ci95_floored'][0]:+.2f} "
                 f"to {r['ci95_floored'][1]:+.2f} (the bootstrap alone can't see noise with so few games)")
    L += ["", f"**Verdict: {r['verdict']}.**"]
    if r["games_per_task_to_resolve"]:
        L.append(f"About {r['games_per_task_to_resolve']} games per task in each run would be needed to resolve a "
                 f"difference this size (now {r['min_games_per_task']}).")
    L += ["", f"Context: in season 0, two runs of the *same* harness on the same private forts differed by "
              f"{SEASON0_NOISE_SD} S points (SD); DF itself isn't deterministic, and pairing on forts and seeds "
              f"barely reduces that. Official promotion needs the lower bound to beat the leader's by "
              f"{PROMOTION_BIPS} bips (2.5%) and then a confirmation batch of MY1 and OP1. "
              + (f"On these numbers B's lower bound {'would' if r['clears_promotion_threshold'] else 'would not'} "
                 f"clear 250 bips over A's." if r["clears_promotion_threshold"] is not None else "")]
    return "\n".join(L) + "\n"
