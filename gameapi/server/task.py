"""Load a task (scenario JSON) the way smoke.py does: load_scenario (snapshot resolution, pool paths), setup_for
({seed} -> setup_seeds[0] + k) and pick_snapshot (pool[(seed + k) mod n]). stdlib only; no DF needed."""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_task(path, k=0, seed=12345, days=None):
    sys.path.insert(0, ROOT)
    from bench import key as BK
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    sc = json.load(open(p))
    sc.setdefault("name", os.path.splitext(os.path.basename(p))[0])
    sc["_path"] = p
    snap = sc.get("snapshot")
    if snap:
        sc["snapshot"] = BK.start_snapshot(snap if os.path.isabs(snap) else os.path.join(ROOT, snap))
    sc["snapshot_pool"] = [x if os.path.isabs(x) else os.path.join(ROOT, x) for x in sc.get("snapshot_pool") or []]
    setup = sc.get("setup", [])
    if any("{seed}" in c for cmd in setup for c in cmd):
        if not sc.get("setup_seeds"):
            raise ValueError(f"{path}: setup uses {{seed}} but the scenario has no setup_seeds [lo, hi]")
    if sc.get("setup_seeds"):
        lo, hi = sc["setup_seeds"]
        if not lo <= lo + k <= hi:
            raise ValueError(f"k={k}: setup seed {lo + k} is outside setup_seeds [{lo}, {hi}]")
        setup = [[c.replace("{seed}", str(lo + k)) for c in cmd] for cmd in setup]
    sc["_setup"], sc["setup"] = sc.get("setup", []), setup
    if sc["snapshot_pool"]:
        sc["snapshot"] = sc["snapshot_pool"][(seed + k) % len(sc["snapshot_pool"])]
    if days:
        sc["days"] = int(days)
    sc.setdefault("days", 336)
    sc.setdefault("strange_moods", False)
    return sc
