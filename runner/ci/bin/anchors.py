#!/usr/bin/env python3
"""runner/ci/bin/anchors.py: the organiser-only anchors workflow's plan and aggregate (runner/ci/anchors.yml).

Re-measures the season's reference arms on the private pool on the verifier's host class (GitHub-hosted native
x86_64), off the Rosetta box the pool was built and first measured on (infra/RUNBOOK.md §1.9):
  labs (LT01, LT02, LT03, LT08)   noop and witness, n each (bench/labrun.py; the lab anchors p̄_noop, p̄_witness)
  MY1, OP1                        noop n, automation and scripted n/2 each (smoke.py; the published reference lines)
No model calls: these arms are scripted. One matrix job per (task, arm, k).

  anchors.py plan [--n 8] [--only LT01,MY1]       -> {"include": [{job, task, arm, k, file, cap, moods, entry}, ...]}
  anchors.py aggregate RUN_DIRS... [--suite S]    -> aggregates JSON on stdout (per task and arm: n, p̄ or mean O,
                                                     pass count); with --suite, the delta to the suite's anchors
  anchors.py kit --out KIT.tgz                    -> (organiser, research checkout) the witness kit to seal into the
                                                     ops store's pool release; the challenge repo never has it

The aggregate prints no fort id, seed, per-game value or observation: only n, means and pass counts per task and
arm, the same shape as the committed anchors. Per-game run dirs stay sealed in the ops store.
"""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# task id -> (staged task file in the pool bundle's tasks/, smoke.py --decision-cap, strange moods, kind)
# Caps and mood settings as in the first measurement (runs/s0-pool-2026-10-26/scripts/measure.sh).
TASKS = {
    "LT01": ("lt01-drought.json", 78, False, "lab"),
    "LT02": ("lt02-rescue-neglected.json", 138, False, "lab"),
    "LT03": ("lt03-mood-artifact.json", 76, True, "lab"),
    "LT08": ("lt08-migrant-surge.json", 78, False, "lab"),
    "MY1": ("my1-handover-lean.json", 320, False, "outcome"),
    "OP1": ("op1-start-year.json", 500, False, "outcome"),
}
LAB_ARMS = ("noop", "witness")
REF_ARMS = ("noop", "automation", "scripted")


def plan(n=8, only=None):
    inc = []
    for task, (f, cap, moods, kind) in TASKS.items():
        if only and task not in only:
            continue
        if kind == "lab":
            arms = [(a, n) for a in LAB_ARMS]
            entry = "bench/labrun.py"
        else:
            arms = [("noop", n), ("automation", max(1, n // 2)), ("scripted", max(1, n // 2))]
            entry = "smoke.py"
        for arm, runs in arms:
            for k in range(runs):
                inc.append({"job": f"{task}-{arm}-{k}", "task": task, "arm": arm, "k": k, "file": f, "cap": cap,
                            "moods": moods, "entry": entry})
    return {"include": inc}


def _mean(xs):
    return round(sum(xs) / len(xs), 4) if xs else None


def aggregate(dirs, suite=None):
    """dirs: run dirs named <task>-<arm>-<k>/ (each holding batch.sh output). -> {task: {arm: {...}}, "delta": ...}"""
    sys.path.insert(0, ROOT)
    from bench import outcomes, predicates   # noqa: E402  (trusted scorers, same as the official run)
    by_task = {}
    for d in dirs:
        task = os.path.basename(os.path.normpath(d)).split("-")[0]
        by_task.setdefault(task, []).append(d)
    out = {"tasks": {}}
    for task, ds in sorted(by_task.items()):
        if task not in TASKS:
            continue
        kind = TASKS[task][3]
        res = {}
        if kind == "lab":
            for arm, rows in predicates.score(task, ds).items():
                res[arm] = {"n": len(rows), "p_mean": _mean([r["partial"] for r in rows]),
                            "pass": sum(1 for r in rows if r["pass"])}
        else:
            per = {}
            for (_batch, _scen, arm), rows in outcomes.discover(ds).items():
                for r, rd in rows:
                    o = outcomes.for_run(rd, r)
                    if o is not None:
                        per.setdefault(arm, []).append(o)
            for arm, os_ in per.items():
                res[arm] = {"n": len(os_), "O_mean": _mean([o["outcome"] for o in os_]),
                            "O_min": round(min(o["outcome"] for o in os_), 1),
                            "O_max": round(max(o["outcome"] for o in os_), 1)}
            refs = [o for a in ("automation", "scripted") for o in per.get(a, [])]
            if refs:
                res["references"] = {"n": len(refs), "O_mean": _mean([o["outcome"] for o in refs]),
                                     "O_min": round(min(o["outcome"] for o in refs), 1)}
        out["tasks"][task] = res
    if suite:
        s = json.load(open(suite))
        delta = {}
        for t in s.get("tasks", []):
            a, got = t.get("anchor"), out["tasks"].get(t.get("id"), {})
            if not a or not got:
                continue
            delta[t["id"]] = {arm: {"suite": a[arm], "native": got[arm]["p_mean"],
                                    "delta": round(got[arm]["p_mean"] - a[arm], 4)}
                              for arm in ("noop", "witness") if arm in a and arm in got and got[arm]["p_mean"] is not None}
        out["delta_vs_suite"] = delta
    return out


KIT_FILES = ("policies.py",)   # the witnesses live in policies.py, withheld from the challenge export in-season


def kit(out, root=ROOT):
    """Tarball of the research checkout's witness-bearing files, for sealing into the ops store (never the repo).
    Refuses a checkout whose policies.py is the export's stub (no witnesses)."""
    import tarfile
    src = open(os.path.join(root, "policies.py")).read()
    if "WITNESSES = {" not in src or "Withheld from the public release" in src:
        raise SystemExit("policies.py has no witnesses (an export tree?); build the kit from the research repo")
    with tarfile.open(out, "w:gz") as t:
        for f in KIT_FILES:
            t.add(os.path.join(root, f), arcname=f)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("plan"); p.add_argument("--n", type=int, default=8); p.add_argument("--only", default="")
    g = sp.add_parser("aggregate"); g.add_argument("dirs", nargs="+"); g.add_argument("--suite")
    k = sp.add_parser("kit"); k.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "kit":
        print(kit(a.out))
    elif a.cmd == "plan":
        only = {x.strip() for x in a.only.split(",") if x.strip()} or None
        bad = (only or set()) - set(TASKS)
        if bad:
            ap.error(f"unknown task(s): {', '.join(sorted(bad))}")
        print(json.dumps(plan(a.n, only)))
    else:
        print(json.dumps(aggregate([d for d in a.dirs if os.path.isdir(d)], a.suite), indent=1))


if __name__ == "__main__":
    main()
