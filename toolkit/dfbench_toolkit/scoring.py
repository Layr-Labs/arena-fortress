"""Suite aggregation: a pinned copy of the challenge's (runner/dfbenchlib/score.py, s0-score/1), used when no
challenge clone is found. Inside a clone, `agg()` returns the challenge's own functions instead.

S = sum_f w_f * F_f / sum_f w_f over the families present (OP1 0.5, MY1 0.3, labs 0.2; labs = the mean of the lab
task scores). A task scores mean O (outcome tasks) or 100 * z of the mean partial (labs; z = (p - noop) /
(witness - noop), capped at 1.5, not floored). The published scalar is the one-sided 95% lower bound of S from a
stratified bootstrap over games (each task's games resampled within the task).
"""
import random

from . import challenge

Z_CAP = 1.5
DEFAULT_WEIGHTS = {"OP1": 0.5, "MY1": 0.3, "labs": 0.2}


def task_value(task, games, anchors):
    if task["kind"] == "lab":
        p = sum(g["partial"] for g in games) / len(games)
        a = anchors.get(task["id"]) or {"noop": 0.0, "witness": 1.0}
        den = a["witness"] - a["noop"]
        z = (p - a["noop"]) / den if den > 0 else 0.0
        lo, hi = task.get("zlim") or (None, Z_CAP)
        z = min(hi, z) if hi is not None else z
        z = max(lo, z) if lo is not None else z
        return 100 * z
    return sum(g["O"] for g in games) / len(games)


def suite_value(by_task, tasks, weights, anchors):
    fam = {}
    for t in tasks:
        gs = by_task.get(t["id"])
        if gs:
            fam.setdefault(t["family"], []).append(task_value(t, gs, anchors))
    present = {f: sum(v) / len(v) for f, v in fam.items()}
    w = {f: weights.get(f, 0.0) for f in present}
    tot = sum(w.values())
    return (sum(w[f] * present[f] for f in present) / tot if tot else None), present


def bootstrap(by_task, tasks, weights, anchors, B=10000, seed=0, alpha=0.05):
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        bt = {tid: [gs[rng.randrange(len(gs))] for _ in gs] for tid, gs in by_task.items()}
        v, _ = suite_value(bt, tasks, weights, anchors)
        vals.append(v)
    vals.sort()
    return vals[int(alpha * B)], vals[min(B - 1, int((1 - alpha) * B))]


def agg(start=None):
    """-> (task_value, suite_value, bootstrap, source): the challenge's own when a clone is found, else this copy."""
    score, _ = challenge.scorer(start)
    if score is not None and all(hasattr(score, n) for n in ("task_value", "suite_value", "bootstrap")):
        return score.task_value, score.suite_value, score.bootstrap, f"challenge scorer ({score.SCORE_VERSION})"
    return task_value, suite_value, bootstrap, "vendored copy (s0-score/1)"


def diff_bootstrap(a_by_task, b_by_task, tasks, weights, anchors, B=4000, seed=7, paired=None, sv=suite_value):
    """-> sorted list of S(A) - S(B) over bootstrap resamples.

    Independent: each run's games are resampled within each task. Paired (`paired` = {task: [(gameA, gameB)]}, the
    same fort and seed in both runs): the pairs are resampled together, so fort-to-fort differences cancel and only
    run-to-run noise remains."""
    rng = random.Random(seed)
    out = []
    for _ in range(B):
        if paired:
            ra, rb = {}, {}
            for tid, prs in paired.items():
                pick = [prs[rng.randrange(len(prs))] for _ in prs]
                ra[tid] = [p[0] for p in pick]
                rb[tid] = [p[1] for p in pick]
        else:
            ra = {t: [gs[rng.randrange(len(gs))] for _ in gs] for t, gs in a_by_task.items()}
            rb = {t: [gs[rng.randrange(len(gs))] for _ in gs] for t, gs in b_by_task.items()}
        va, _ = sv(ra, tasks, weights, anchors)
        vb, _ = sv(rb, tasks, weights, anchors)
        if va is not None and vb is not None:
            out.append(va - vb)
    out.sort()
    return out
