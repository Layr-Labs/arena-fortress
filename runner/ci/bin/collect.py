#!/usr/bin/env python3
"""runner/ci/bin/collect.py: glue for the scoring workflow (runner/ci/score.yml; docs/SCORING-INFRA.md §5).
Stdlib only; never reads harness output; prints only game ids, statuses and counts.

  status   OUT_GAMES STAGE ATTEMPT JOB  > status.json    a play job's per-game statuses (ok | infra), plain JSON
  retry    PLAN_JSON STATUS_DIR          > matrix.json   the plan's games that have no `ok` in any attempt, as a
                                                         one-game-per-job matrix (empty: {"include": []})
  merge    BUNDLES_DIR OUT_DIR                           unpacked per-job bundles -> one run dir: for each game the
                                                         best attempt (ok over infra, then the latest attempt); a
                                                         game whose DF crashed on two attempts gets crash_twice
  finalize SCORE_JSON STAGE1_POINT OUT                   copy score.json, add flat metrics stage1_point and
                                                         workflow_run, check the Yukon shape ({score, metrics});
                                                         with DFBENCH_LEADER_S1 etc. set (score.yml), also `stage2`
                                                         (why OP1 was or wasn't played) and leader_stage1_point,
                                                         first in the table on a stage-1-only result
  pool-verdict POOLED FIRST LEADER_SCORE BIPS MAX_INFRA  the confirmation verdict on the pooled score (both batches):
                                                         adds metrics score_first_batch, lb95_first_batch and
                                                         confirmation passed|failed; prints infra_fail=, score=
"""
import glob, json, os, re, shutil, sys


def status(out_games, stage, attempt, job):
    games = {}
    for p in sorted(glob.glob(os.path.join(out_games, "*", "game.json"))):
        try:
            rec = json.load(open(p))
        except (OSError, ValueError):
            continue
        gid = (rec.get("spec") or {}).get("game_id") or os.path.basename(os.path.dirname(p))
        # crash_twice: DF crashed on both of the job's attempts; final (scored at the state reached), not re-run
        games[gid] = "crash_twice" if rec.get("status") != "ok" and rec.get("crash_twice") else (rec.get("status") or "infra")
    json.dump({"stage": int(stage), "attempt": int(attempt), "job": job, "games": games}, sys.stdout)


def _ok_games(status_dir):
    ok = set()
    for p in glob.glob(os.path.join(status_dir, "**", "status-*.json"), recursive=True):
        for g, s in json.load(open(p))["games"].items():
            if s in ("ok", "crash_twice"):
                ok.add(g)
    return ok


def retry(plan_json, status_dir):
    plan = json.load(open(plan_json)) if os.path.exists(plan_json) else json.loads(plan_json)
    ok = _ok_games(status_dir)
    inc = []
    for job in plan.get("include", []):
        for g in job["games"].split(","):
            if g and g not in ok:
                inc.append({"job": f"r-{g}", "games": g, "timeout_min": job["timeout_min"],
                            "play_timeout_min": job.get("play_timeout_min", job["timeout_min"])})
    sys.stderr.write(f"retry: {len(inc)} game(s) without an ok result: {','.join(x['games'] for x in inc) or '-'}\n")
    json.dump({"include": inc}, sys.stdout)


def merge(bundles_dir, out_dir):
    """bundles_dir/{cur,prev}/<artifact>/games/<game>/game.json; artifact names carry s<stage>-a<attempt>-r<run attempt>."""
    best, causes = {}, {}
    for p in glob.glob(os.path.join(bundles_dir, "**", "game.json"), recursive=True):
        gdir = os.path.dirname(p)
        if "attempt-" in os.path.basename(gdir):
            # an earlier attempt inside a job (dfbench --retries): never selected, but its infra cause counts
            try:
                rec = json.load(open(p))
            except (OSError, ValueError):
                continue
            if rec.get("status") != "ok":
                gid = (rec.get("spec") or {}).get("game_id") or os.path.basename(os.path.dirname(gdir))
                causes.setdefault(gid, []).append(rec.get("infra_cause"))
            continue
        if "attempt-" in gdir or not os.path.isdir(os.path.join(gdir, "game")) or os.path.isdir(os.path.join(gdir, "games")):
            continue
        rec = json.load(open(p))
        gid = (rec.get("spec") or {}).get("game_id") or os.path.basename(gdir)
        m = re.search(r"s(\d+)-a(\d+)-r(\d+)", gdir)
        cur = os.sep + "cur" + os.sep in gdir           # this run's bundles beat a merged earlier run's
        order = (rec.get("status") == "ok", cur, int(m.group(2)) if m else 0, int(m.group(3)) if m else 0)
        if rec.get("status") != "ok":
            causes.setdefault(gid, []).append(rec.get("infra_cause"))
        if gid not in best or order > best[gid][0]:
            best[gid] = (order, gdir)
    os.makedirs(out_dir, exist_ok=True)
    for gid, (_, gdir) in sorted(best.items()):
        dst = os.path.join(out_dir, os.path.basename(gdir))
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(gdir, dst)
        if not best[gid][0][0] and crash_twice(causes.get(gid, [])):
            p = os.path.join(dst, "game.json")
            rec = json.load(open(p))
            rec["crash_twice"] = True
            json.dump(rec, open(p, "w"), indent=1)
    n_ok = sum(1 for o, _ in best.values() if o[0])
    n_ct = sum(1 for g, (o, _) in best.items() if not o[0] and crash_twice(causes.get(g, [])))
    print(f"merge: {len(best)} games ({n_ok} ok, {n_ct} crashed twice, {len(best) - n_ok - n_ct} infra)")


def crash_twice(causes):
    """Two DF-side failures (DF crashed or hung, the server's artifacts missing) and no ok attempt: the game is
    scored at the state reached, not counted as infra (challenge/SCORING.md §6; runner/dfbenchlib/game.py)."""
    return sum(1 for c in causes if c == "game") >= 2


def finalize(score_json, stage1_point, out, env=os.environ):
    s = json.load(open(score_json))
    if not isinstance(s.get("score"), (int, float)) or not isinstance(s.get("metrics"), dict):
        sys.exit("finalize: score.json is not {score: number, metrics: {...}}")
    for k, v in s["metrics"].items():
        if isinstance(v, (dict, list)) and k != "harness_digest":
            sys.exit(f"finalize: metric {k} is nested; Yukon shows one row per flat key")
    s["metrics"]["stage1_point"] = float(stage1_point) if stage1_point not in ("", None) else None
    s["metrics"]["workflow_run"] = f"{env.get('GITHUB_RUN_ID', '')}/{env.get('GITHUB_RUN_ATTEMPT', '')}"
    if "DFBENCH_FULL_SUITE" in env:          # set by score.yml; Yukon's comment lists metrics in this order
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from gate import _num, stage2_note
        m = s["metrics"]
        note = stage2_note(m.get("stage"), env.get("DFBENCH_FULL_SUITE"), env.get("DFBENCH_TIER", ""),
                           env.get("DFBENCH_RUN_STAGE2"), env.get("DFBENCH_STAGE1_UB95"), env.get("DFBENCH_LEADER_S1"))
        add = {"stage2": note, "leader_stage1_point": _num(env.get("DFBENCH_LEADER_S1"))}
        s["metrics"] = {**add, **m} if m.get("stage") != 2 else {**m, **add}
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(s, open(out, "w"), indent=1)
    print(f"finalize: score {s['score']} stage {s['metrics'].get('stage')} -> {out}")


def pool_verdict(pooled, first, leader_score, bips, max_infra):
    """The final score is always the pooled lower bound: if it still clears Yukon's threshold the confirmation
    passed (Yukon promotes it after the judge); if not, Yukon records it as non-improving. Nothing else is emitted."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from gate import would_promote
    p, f = json.load(open(pooled)), json.load(open(first))
    m = p["metrics"]
    go, why = would_promote(p.get("score"), leader_score or None, float(bips or 0))
    m.update(score_first_batch=f.get("score"), lb95_first_batch=(f.get("metrics") or {}).get("lb95"),
             confirmation="passed" if go else "failed", confirmation_note=why)
    json.dump(p, open(pooled, "w"), indent=1)
    bad = m.get("infra_excluded", 0) > int(max_infra)
    print(f"infra_fail={'true' if bad else 'false'}")
    print(f"score={p['score']}")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["-h"]
    {"status": status, "retry": retry, "merge": merge, "finalize": finalize, "pool-verdict": pool_verdict}.get(cmd, lambda *_: sys.exit(__doc__))(*args)
