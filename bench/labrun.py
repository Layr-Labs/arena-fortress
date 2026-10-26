#!/usr/bin/env python3
"""Run a lab task (BENCHMARK-v1 §2) with the reference arms: smoke.py, plus the task's hands-off window and witness.

  python3 bench/labrun.py --scenario scenarios/lt08-migrant-surge.json --only witness --runs 1 --out runs/job ...

All arguments go to smoke.py unchanged, except that `--only witness` runs the task's witness policy
(policies.WITNESSES[<task id>]) in smoke.py's scripted slot; its files and summary row are then relabelled `witness`
(summary `ref_policy` says which class ran). The hands-off window is in smoke.py's loop since v2 (every arm, LLM arms
included; docs/BENCHMARK-v2.md), so this wrapper no longer wraps the reference policies in a hands-off shim.
Docker: docker/batch.sh --entry bench/labrun.py --arms noop,witness ... -- --scenario ...
"""
import json, os, runpy, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import policies  # noqa: E402


def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def relabel(out, k_start, runs):
    """scripted-<k>.* -> witness-<k>.*, and the summary rows' arm."""
    for k in range(k_start, k_start + runs):
        for f in os.listdir(out):
            if f.startswith(f"scripted-{k}."):
                os.replace(os.path.join(out, f), os.path.join(out, "witness" + f[len("scripted"):]))
    p = os.path.join(out, "summary.jsonl")
    if os.path.exists(p):
        rows = [json.loads(l) for l in open(p) if l.strip()]
        for r in rows:
            if r.get("arm") == "scripted":
                r["arm"] = "witness"
        with open(p, "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)


def main(argv):
    scen = _arg(argv, "--scenario")
    sc = json.load(open(scen if os.path.isabs(scen) else os.path.join(ROOT, scen))) if scen else {}
    w = int(sc.get("hands_off_days") or 0)
    task = (sc.get("id") or "").split("-")[0]
    arm = _arg(argv, "--only")
    info = {"task": sc.get("id"), "hands_off_days": w, "arm": arm}
    if arm == "witness":
        wit = policies.WITNESSES.get(task)
        if wit is None:
            sys.exit(f"no witness for task {task!r} (policies.WITNESSES)")
        policies.Scripted = wit
        argv = list(argv)
        argv[argv.index("--only") + 1] = "scripted"
        info["ref_policy"] = wit.__name__
    out = _arg(argv, "--out", os.path.join(ROOT, "runs", "smoke5"))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "LABRUN.json"), "w") as f:
        json.dump(info, f)
    sys.argv = [os.path.join(ROOT, "smoke.py"), *argv]
    code = 0
    try:
        runpy.run_path(os.path.join(ROOT, "smoke.py"), run_name="__main__")
    except SystemExit as e:
        code = e.code
    if arm == "witness":
        relabel(out, int(_arg(argv, "--k-start", 0)), int(_arg(argv, "--runs", 5)))
        p = os.path.join(out, "summary.jsonl")
        rows = [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []
        for r in rows:
            r["ref_policy"] = info["ref_policy"]
        if rows:
            with open(p, "w") as f:
                f.writelines(json.dumps(r) + "\n" for r in rows)
    sys.exit(code)


if __name__ == "__main__":
    main(sys.argv[1:])
