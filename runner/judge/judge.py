#!/usr/bin/env python3
"""dfbench season-0 promotion judge (challenge/RULES.md §8a). One call per improving submission, after scoring:

  python3 -I runner/judge/judge.py --repo-dir <checkout> --base <sha> --head <sha> \\
    --note <note.md> --dependencies <deps.json> --coauthors <a,b> --submitter <user> \\
    [--context-dir <dir>] [--base-producers <id,...>] [--score-json <score.json>] \\
    --out <dossier.json> [--md <summary.md>] [--provider openrouter|bedrock|fake] [--model <id>]

Writes the dossier (always, also on hold) and prints one JSON line {"verdict", "cost_usd", ...}. Exit 0 whenever a
dossier was written (read the verdict from it); 2 on bad usage. See runner/judge/README.md."""
import argparse, datetime, hashlib, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from judgelib import JUDGE_VERSION, committee, evidence as E, providers as P, report, schema as SC, signals  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def _tree_hash(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        with open(p, "rb") as f:
            h.update(os.path.relpath(p, HERE).encode() + b"\0" + hashlib.sha256(f.read()).digest())
    return h.hexdigest()


def versions():
    prompts = [os.path.join(committee.PROMPTS, n) for n in os.listdir(committee.PROMPTS) if n.endswith(".md")]
    code = [os.path.join(HERE, "judge.py")] + [os.path.join(HERE, "judgelib", n)
                                               for n in os.listdir(os.path.join(HERE, "judgelib")) if n.endswith(".py")]
    return {"judge_version": JUDGE_VERSION, "prompts_sha256": _tree_hash(prompts), "code_sha256": _tree_hash(code),
            "prompt_files": {os.path.basename(p): E.read_text(p)[1] for p in sorted(prompts)},
            "schemas_sha256": E.sha256_text(json.dumps([SC.REVIEWER_SCHEMAS, SC.DEFENDER_SCHEMA,
                                                        SC.ADJUDICATOR_SCHEMA], sort_keys=True)),
            "limits": E.LIMITS}


def gather(a):
    note, note_h = E.read_text(a.note, E.LIMITS["max_note_chars"], "note")
    deps, deps_h = E.load_dependencies(a.dependencies)
    declared = {d["submissionId"] for d in deps}
    producers = {x.strip().lower() for x in (a.base_producers or "").split(",") if x.strip()}
    sub = E.collect_submission(a.repo_dir, a.base, a.head)
    ctx = E.load_context(a.context_dir, declared, producers, a.submitter)
    ov = E.overlap(sub["scan_lines"], ctx)
    score, score_h = E.load_score(a.score_json)
    sig, total = signals.scan(sub["scan_lines"], note)
    sig = signals.deterministic_signals(ctx, ov, deps) + sig
    for i, s in enumerate(sig, 1):
        s["id"] = f"S{i}"
    ev = {"sub": sub, "note": note, "deps": deps, "contexts": ctx, "overlaps": ov, "score": score, "signals": sig,
          "signals_total": total, "submitter": (a.submitter or "")[:100],
          "coauthors": [c.strip() for c in (a.coauthors or "").split(",") if c.strip()][:40],
          "missing_declared": sorted(declared - {c["id"] for c in ctx}),
          "missing_producers": sorted(producers - {c["id"] for c in ctx})}
    hashes = {"note_sha256": note_h, "dependencies_sha256": deps_h, "score_json_sha256": score_h,
              "diff_sha256": sub["diff_sha256"],
              "context": [{"id": c["id"], "dir": c["dir"], "diff_sha256": c["diff_sha256"],
                           "truncated": c["truncated"], "why": c["why"], "own": c["own"]} for c in ctx],
              "context_status": E.load_context_status(a.context_dir)}
    return ev, hashes


def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-dir", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--note", required=True)
    ap.add_argument("--dependencies", required=True)
    ap.add_argument("--coauthors", default="")
    ap.add_argument("--submitter", required=True)
    ap.add_argument("--context-dir")
    ap.add_argument("--base-producers", default="", help="submission id(s) that produced the base (promoted main)")
    ap.add_argument("--score-json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md")
    ap.add_argument("--provider", default=os.environ.get("DFBENCH_JUDGE_PROVIDER", "openrouter"),
                    choices=["openrouter", "bedrock", "fake"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--reasoning-effort", default=os.environ.get("DFBENCH_JUDGE_REASONING", "medium"),
                    choices=["low", "medium", "high", "none"])
    ap.add_argument("--temperature", type=float, default=None,
                    help="sent only if given (OpenRouter's reasoning models don't take one; seed 0 is always sent)")
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--max-cost", type=float, default=float(os.environ.get("DFBENCH_JUDGE_MAX_COST", "3.0")),
                    help="USD cap for one judgment; reaching it is a hold")
    return ap.parse_args(argv)


def main(argv=None):
    return run(parse(argv))


def run(a, provider=None):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    d = {"schema": "dfbench-judge-dossier/1", "started": started, "versions": versions(),
         "inputs": {"repo_head": None, "base": a.base, "head": a.head, "submitter": a.submitter,
                    "coauthors": a.coauthors, "base_producers": a.base_producers},
         "config": {"provider": a.provider, "model": a.model}, "verdict": "hold", "reasons": [], "findings": [],
         "signals": [], "calls": [], "usage": {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                                                "cost_usd": 0.0, "cost_unknown": False}}
    log = lambda m: print(f"judge: {m}", file=sys.stderr)  # noqa: E731
    try:
        ev, hashes = gather(a)
        d["inputs"].update({"base": ev["sub"]["base"], "head": ev["sub"]["head"], **hashes,
                            "declared_dependencies": [x["submissionId"] for x in ev["deps"]],
                            "declared_but_not_in_context": ev["missing_declared"],
                            "base_producers_not_in_context": ev["missing_producers"]})
        d["evidence"] = {"files": [{k: v for k, v in f.items() if k != "added_lines"} for f in ev["sub"]["files"]],
                         "chunks": len(ev["sub"]["chunks"]), "chunk_chars": [len(c) for c in ev["sub"]["chunks"]],
                         "overlap": ev["overlaps"], "signals_total": ev["signals_total"],
                         "score_metrics": ev["score"]}
        d["signals"] = ev["signals"]
    except E.LimitHit as e:
        d["reasons"] = [f"size limit: {e}"]
        d["hold_conditions"] = d["reasons"]
        return finish(a, d)
    except E.InputError as e:
        d["reasons"] = [f"unusable input: {e}"]
        d["hold_conditions"] = d["reasons"]
        return finish(a, d)
    try:
        p = provider or P.make(a.provider, a.model, reasoning_effort=None if a.reasoning_effort == "none"
                               else a.reasoning_effort, max_tokens=a.max_tokens, temperature=a.temperature)
    except P.ProviderError as e:
        d["reasons"] = [f"judge infrastructure failure: {e}"]
        d["hold_conditions"] = d["reasons"]
        return finish(a, d)
    d["config"] = p.config()
    c = committee.Committee(ev, p, max_cost_usd=a.max_cost, log=log)
    res = c.run()
    d.update({"verdict": res["verdict"], "reasons": res["reasons"], "hold_conditions": res["hold_conditions"],
              "findings": res["findings"], "reviews": res["reviews"], "defense": res["defense"],
              "adjudication": res["adjudication"], "rulings": res["rulings"], "confirmed": res["confirmed"],
              "calls": c.calls})
    att = [x for r in c.calls for x in r["attempts"]]
    d["usage"] = {"calls": len(att),
                  "prompt_tokens": sum((x.get("usage") or {}).get("prompt_tokens") or 0 for x in att),
                  "completion_tokens": sum((x.get("usage") or {}).get("completion_tokens") or 0 for x in att),
                  "reasoning_tokens": sum((x.get("usage") or {}).get("reasoning_tokens") or 0 for x in att),
                  "cost_usd": round(c.cost, 6), "cost_unknown": c.cost_unknown,
                  "models_returned": sorted({x["model"] for x in att if x.get("model")})}
    return finish(a, d)


def finish(a, d):
    if d["verdict"] not in ("pass", "fail", "hold"):
        d["verdict"] = "hold"
    d["finished"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False, sort_keys=False, default=sorted)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as f:
            f.write(report.markdown(d))
    print(json.dumps({"verdict": d["verdict"], "cost_usd": d["usage"]["cost_usd"], "calls": d["usage"]["calls"],
                      "reasons": d["reasons"][:5]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
