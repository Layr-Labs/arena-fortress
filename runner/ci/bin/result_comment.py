#!/usr/bin/env python3
"""runner/ci/bin/result_comment.py: the plain-language result comment on a submission's pull request.

  result_comment.py --score .yukon/score.json --suite SUITE [--benchmark ID] [--user U] [--bips B] --out comment.md

Yukon's own comment headlines "Scored X — does not improve the current best" over 40+ raw metric rows, and reads
"Scored 0" for a stage-1-only result. This adds the interpretation the submitter needs before spending another of
their weekly attempts:
  1. where the run stands: its score, the bar for promotion (the leader's score + minScoreImprovementBips), the gap;
  2. how sure that is: the run's bounds and the run-to-run noise of one harness (~3.8 suite points, SCORING.md §4);
  3. where the points went: the run's OP1 / MY1 / labs against the leader's (pooled over all its scored games when
     the organiser's contender store has them, else its promoted run), and the biggest gap;
  4. what to do next: the attempts left this week, and the local comparison (SUBMITTING.md §3a).
Aggregates only: per-family values like those Yukon already publishes. Never per-game or per-fort data.
Everything it can't read (Yukon, the ops store) is left out of the comment, never guessed. Python 3 stdlib only.
Env: DFBENCH_YUKON_API, YUKON_API_KEY (the leader); DFBENCH_OPS_TOKEN or GITHUB_TOKEN, DFBENCH_OPS_REPO,
DFBENCH_SEASON (pooled leader values, this week's use); DFBENCH_TIERS (tier limits, as tier.py).
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "framework"))

RUN_NOISE = 3.8          # SD of the suite score between two runs of one harness (runs/s0-noise-2026-10-27)
FAMILIES = ("OP1", "MY1", "labs")


def _num(x):
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def bar_for(leader_score, bips):
    """Yukon's promotion bar: (score - incumbent) / |incumbent| x 10000 >= bips."""
    ls = _num(leader_score)
    return None if ls is None else ls + abs(ls) * float(bips or 0) / 10000


def chance_line(lb, point, ub, bar):
    """One sentence on whether a re-run of the same harness would likely clear the bar (scored on the lower bound)."""
    if bar is None or lb is None:
        return None
    gap = bar - lb
    if gap <= 0:
        return None
    if gap <= RUN_NOISE / 2:
        how = "a re-run of this same harness could clear it by luck alone, so a near miss isn't evidence your change helped"
    elif gap <= 1.5 * RUN_NOISE:
        how = "that's within the range one harness moves between runs; you'd need a real gain, not just another try"
    else:
        how = "that's more than run-to-run noise: resubmitting this harness unchanged won't get there"
    return f"You're **{gap:.2f}** below the bar: {how}."


def family_rows(metrics, leader_fams, leader_src):
    weights = {"OP1": "0.5", "MY1": "0.3", "labs": "0.2"}
    fmt = lambda v: "—" if v is None else f"{v:.1f}"
    rows, gaps = [], {}
    for f in FAMILIES:
        mine, theirs = _num(metrics.get(f"family_{f}")), _num((leader_fams or {}).get(f))
        if mine is None and theirs is None:
            continue
        d = None if mine is None or theirs is None else mine - theirs
        if d is not None:
            gaps[f] = d
        rows.append(f"| {f} ({weights[f]}) | {fmt(mine)} | {fmt(theirs)} | {'—' if d is None else f'{d:+.1f}'} |")
    if not rows:
        return []
    out = ["", f"| family (weight) | this run | leader ({leader_src}) | difference |", "|---|---|---|---|"] + rows
    if gaps:
        worst = min(gaps, key=gaps.get)
        if gaps[worst] < -1:
            out += ["", f"The biggest gap is **{worst}** ({gaps[worst]:+.1f})"
                    + (": OP1 counts for half of the score." if worst == "OP1" else ".")]
    return out


def render(score, leader_score=None, leader_fams=None, leader_src="its promoted run", bips=250, used=None,
           limit=None, leader_id=None):
    m = score.get("metrics") or {}
    stage, verdict = str(m.get("stage", "")), m.get("judge_verdict") or ""
    lb, point, ub = _num(m.get("lb95")), _num(m.get("point")), _num(m.get("ub95"))
    bar = bar_for(leader_score, bips)
    conf = str(m.get("confirmation") or "")
    L = ["**Your result, in plain words** (dfbench; aggregates only)", ""]
    if verdict in ("fail", "hold"):
        L += [f"The judge returned **{verdict}**, so this run can't be promoted whatever its score: see the judge's "
              "comment above for the findings. Fix those first; the numbers below are for your information."]
    if stage != "2":
        why = str(m.get("stage2") or "OP1 wasn't played").split("; not a failure")[0]
        why = why[len("skipped: "):] if why.startswith("skipped: ") else why
        L += [f"**Stage 1 only (the lab tasks and MY1), so this result can't be promoted.** Why: {why}"]
        if lb is not None:
            L += ["", f"Stage-1 score {lb:.2f} (bounds {lb:.2f}–{ub:.2f}). Stage 1 isn't on the same scale as the "
                  "full score, so don't compare it with the leader's."]
    else:
        if score.get("score") not in (None, 0) and conf == "passed" and verdict == "pass" and bar is not None and lb is not None and lb >= bar:
            L += [f"**{lb:.2f}: above the bar ({bar:.2f}) with a passed confirmation and judge.** Yukon promotes it "
                  "unless someone else was promoted first."]
        elif lb is not None:
            L += [f"**{lb:.2f}** (the lower bound of this run; point {point:.2f}, bounds {lb:.2f}–{ub:.2f})"
                  + ((f". The bar for promotion is **{bar:.2f}** (the leader's {float(leader_score):.2f} + "
                      f"{int(bips)} bips)." if bips else
                      f". To be promoted it has to beat the leader's **{float(leader_score):.2f}** and pass "
                      "confirmation.") if bar is not None else ".")]
            c = chance_line(lb, point, ub, bar)
            if c:
                L += ["", c]
            if conf.startswith("failed_paired"):
                L += ["", "It cleared the bar but **failed the paired check**: on the same games, played in the same "
                      f"window, it wasn't clearly better than the leader (difference {m.get('paired_diff_point')}, lower "
                      f"bound {m.get('paired_diff_lb')}). A single run can beat the leader's number by luck; the paired "
                      "check is what tells a real gain apart (SCORING.md §4.1)."]
        L += family_rows(m, leader_fams, leader_src)
    L += ["", f"One run of a harness is a noisy measurement: two runs of the same harness differ by about "
          f"{RUN_NOISE} points. Before you spend another attempt, compare your change with the leader"
          + (f" (`yukon reset {leader_id}`)" if leader_id else "")
          + " locally on the same day: `SUBMITTING.md` §3a (`dfbench-tk compare`)."]
    if used is not None and limit is not None:
        left = max(0, int(limit) - int(used))
        L += ["", f"Attempts this week: **{used} of {limit} used, {left} left** (weeks start Monday 00:00 UTC)."]
    return "\n".join(L) + "\n"


# ---- inputs (each optional: what can't be read is left out) ----

def leader_from_yukon(benchmark):
    try:
        import gate
        from tier import http_json, yukon_headers
        api = (os.environ.get("DFBENCH_YUKON_API") or "").rstrip("/")
        b = http_json(f"{api}/api/benchmarks/{benchmark}", yukon_headers())["benchmark"]
        m = b.get("currentBestMetrics") or {}
        fams = {f: m.get(f"family_{f}") for f in FAMILIES if m.get(f"family_{f}") is not None}
        return b.get("currentBestScore"), fams, gate.leader_id(benchmark)
    except Exception as e:          # never fail the run over a comment
        sys.stderr.write(f"result_comment: Yukon unreadable ({e})\n")
        return None, None, None


def pooled_leader(leader_id, suite):
    """The leader's per-family values pooled over all its scored games (organiser-only store; aggregates out)."""
    try:
        import band, ledger
        from dfbenchlib import score as S
        store, _ = ledger.load("contenders.json")
        e = (store.get("entries") or {}).get(leader_id or "")
        if not e or len(e.get("runs") or []) < 2:
            return None
        tasks, w, anc = band.suite_parts(suite)
        by = {}
        for r in e["runs"]:
            for t, gs in (r.get("games") or {}).items():
                by.setdefault(t, []).extend(gs)
        _, fam = S.suite_value(by, tasks, w, anc)
        return {f: round(v, 2) for f, v in fam.items()}
    except Exception as e:
        sys.stderr.write(f"result_comment: pooled leader unavailable ({e})\n")
        return None


def week_use(user, tier):
    try:
        import ledger, tier as T
        led, _ = ledger.load("ledger.json")
        wk = ledger.week_of(ledger.now().isoformat())
        used = sum(1 for e in led.get("entries", []) if e.get("user") == user and e.get("week") == wk
                   and e.get("status") in ledger.COUNTED)
        tiers = {**T.DEFAULT_TIERS, **json.loads(os.environ.get("DFBENCH_TIERS") or "{}")}
        return used, (tiers.get(tier) or {}).get("weekly")
    except Exception as e:
        sys.stderr.write(f"result_comment: ledger unavailable ({e})\n")
        return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--score", required=True); ap.add_argument("--suite", required=True)
    ap.add_argument("--benchmark", default=""); ap.add_argument("--user", default="")
    ap.add_argument("--bips", type=float, default=None); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    score = json.load(open(a.score)); suite = json.load(open(a.suite))
    bips = a.bips
    if bips is None:
        import gate
        bips = gate.manifest_bips()
    ls, fams, lid = leader_from_yukon(a.benchmark) if a.benchmark else (None, None, None)
    src = "its promoted run"
    pf = pooled_leader(lid, suite) if lid else None
    if pf:
        fams, src = pf, "pooled over its scored games"
    used, limit = week_use(a.user, (score.get("metrics") or {}).get("submitter_tier")) if a.user else (None, None)
    with open(a.out, "w") as f:
        f.write(render(score, ls, fams, src, bips, used, limit, lid))
    print(f"result_comment: wrote {a.out}")


if __name__ == "__main__":
    main()
