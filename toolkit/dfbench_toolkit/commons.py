"""export --commons: package a run batch as a research-commons dataset (github.com/research-common/research-commons).

Writes a CSV of per-game results (one row per game: the scored values, cost, wall time, comparability key, harness
digest; no harness output and no DF saves) plus a JSON sidecar describing the batch, then prints the
`commons publish dataset` command to run from inside your hub clone. Publishing is left to you: it signs with your
key and pushes to a hub you choose.
"""
import csv, hashlib, json, os

from . import __version__

FIELDS = ["game_id", "task", "k", "seed", "status", "O", "tier", "partial", "passed", "days", "wall_s",
          "wall_capped", "finished_by", "actions_used", "actions_rejected", "cost_usd", "model_calls",
          "harness_digest", "key"]


def export(run, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for g in run.games:
        r = run.records.get(g.id) or {}
        led = r.get("ledger") or {}
        rows.append({"game_id": g.id, "task": g.task, "k": g.k, "seed": g.seed, "status": r.get("status"),
                     "O": r.get("O"), "tier": r.get("tier"), "partial": r.get("partial"), "passed": r.get("passed"),
                     "days": r.get("days"), "wall_s": r.get("wall_s"), "wall_capped": r.get("wall_capped"),
                     "finished_by": r.get("finished_by"), "actions_used": r.get("actions_used"),
                     "actions_rejected": r.get("actions_rejected"), "cost_usd": led.get("cost_usd"),
                     "model_calls": led.get("calls"), "harness_digest": r.get("harness_digest"), "key": r.get("key")})
    csv_path = os.path.join(out_dir, "games.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    digest = hashlib.sha256(open(csv_path, "rb").read()).hexdigest()
    digests = sorted({r["harness_digest"] for r in rows if r["harness_digest"]})
    meta = {"schema": "dfbench-toolkit/commons-batch/1", "toolkit": __version__, "games": len(rows),
            "tasks": sorted({r["task"] for r in rows}), "harness_digests": digests, "csv_sha256": digest,
            "scored_by": run.scored_by,
            "remeasurable": "re-run the same harness on the same public forts: results agree within DF's "
                            "run-to-run noise, never byte for byte"}
    with open(os.path.join(out_dir, "batch.json"), "w") as f:
        json.dump(meta, f, indent=1)
    title = f"dfbench local batch: {', '.join(meta['tasks'])} ({len(rows)} games)"
    cmd = (f'commons publish dataset {csv_path} "{title}" -t dfbench -t dwarf-fortress '
           f'--license CC0-1.0 --obtainability open --source "dfbench local run (public forts)" '
           f'-d "Per-game results; harness {digests[0][:19] if len(digests) == 1 else "several"}; '
           f'see batch.json"')
    return {"csv": csv_path, "meta": meta, "publish_cmd": cmd}
