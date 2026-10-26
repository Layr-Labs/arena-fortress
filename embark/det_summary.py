#!/usr/bin/env python3
"""Summarise det_check.sh bundles (research/determinism.md).

  python3 embark/det_summary.py BUNDLE [BUNDLE...]

Per bundle and world-gen mode: for each stage, the number of distinct fingerprints across the k repeats, and how many
repeats match the modal fingerprint on every stage ("full repeats"). Per embark mode: distinct embark ids (tile,
rectangle, map/plants/loadout fingerprints). Per replay mode: the first divergent day per field (det_replay.compare).
With two or more bundles: whether each mode's modal world / embark id / day-28 replay state agrees across bundles.
"""
import collections, glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import det_replay as R  # noqa: E402

STAGES = ("params", "dims", "terrain", "river_flags", "rivers", "history_counts", "history_event_types", "entities",
          "sites", "site_road_tiles", "world_name", "site_names", "candidates")


def summary_fallback(d):
    """{stage: hash} for one probe dir (world_compare.py --summary's fingerprint line)."""
    import subprocess
    out = subprocess.run([sys.executable, "-I", os.path.join(HERE, "world_compare.py"), "--summary", d],
                         capture_output=True, text=True).stdout.strip()
    return dict(kv.split("=", 1) for kv in out.split() if "=" in kv)


def embark_id(snap):
    e = json.load(open(snap))["embark"]
    fp = e["probe"]["fingerprint"]
    return f"tile={tuple(e['world_tile'])} local={tuple(e['local'])} map={fp['map']} plants={fp['plants']} loadout={fp['loadout']}"


def gen_table(b):
    by = collections.defaultdict(list)
    for d in sorted(glob.glob(os.path.join(b, "gen-*-k*"))):
        m = re.match(r"gen-(.+)-(\d+)-k(\d+)$", os.path.basename(d))
        if m and os.path.exists(os.path.join(d, "world.json")):
            by[(m.group(1), int(m.group(2)))].append(summary_fallback(d))
    out = {}
    for (mode, seed), rows in sorted(by.items()):
        distinct = {s: len({r.get(s) for r in rows}) for s in STAGES}
        modal = {s: collections.Counter(r.get(s) for r in rows).most_common(1)[0][0] for s in STAGES}
        full = sum(all(r.get(s) == modal[s] for s in STAGES) for r in rows)
        first = next((s for s in STAGES if distinct[s] > 1), None)
        out[(mode, seed)] = {"k": len(rows), "full_repeats": full, "first_varying_stage": first,
                             "distinct": {s: v for s, v in distinct.items() if v > 1}, "modal": modal}
    return out


def embark_table(b):
    by = collections.defaultdict(list)
    for snap in sorted(glob.glob(os.path.join(b, "embark-*-k*", "SNAPSHOT.json"))):
        m = re.match(r"embark-(.+)-(\d+)-k(\d+)$", os.path.basename(os.path.dirname(snap)))
        if m:
            by[(m.group(1), int(m.group(2)))].append(embark_id(snap))
    return {k: collections.Counter(v) for k, v in by.items()}


def replay_table(b):
    rows = collections.defaultdict(list)
    for f in glob.glob(os.path.join(b, "replay-*.jsonl")) + glob.glob(os.path.join(b, "split-*.jsonl")):
        if "-trandom-" in f:
            continue
        for line in open(f):
            r = json.loads(line)
            if "label" in r:
                rows[r["label"]].append(r)
    return {lab: (R.compare(rs), rs) for lab, rs in rows.items()}


def trace_table(b):
    """Tick traces (det_replay --tick-trace): per label, the first step at which replays differ, per field."""
    rows = collections.defaultdict(list)
    for f in glob.glob(os.path.join(b, "trace*.jsonl")):
        for line in open(f):
            r = json.loads(line)
            if "tick_trace" in r:
                rows[r["label"]].append(r)
    out = {}
    for lab, rs in rows.items():
        n = min(len(r["tick_trace"]) for r in rs)
        first = {}
        for fld in ("rng", "index0", "all", "units", "items", "jobs", "caches"):
            i = next((i for i in range(n) if len({json.dumps(r["tick_trace"][i][fld]) for r in rs}) > 1), None)
            first[fld] = None if i is None else rs[0]["tick_trace"][i]["tick"] - rs[0]["tick_trace"][0]["tick"] + 1
        out[lab] = {"n": len(rs), "steps": n, "ticks": rs[0]["tick_trace"][n - 1]["tick"] - rs[0]["tick_trace"][0]["tick"] + 1
                    if n else 0, "first_divergent_tick": first,
                    "day0_identical": len({json.dumps(r.get("day0"), sort_keys=True) for r in rs}) == 1}
    return out


def main(bundles):
    gens, embs, reps = {}, {}, {}
    for b in bundles:
        name = os.path.basename(os.path.normpath(b))
        host = open(os.path.join(b, "host.txt")).read().splitlines()[0] if os.path.exists(os.path.join(b, "host.txt")) else "?"
        print(f"## {name}: {host}")
        gens[name], embs[name], reps[name] = gen_table(b), embark_table(b), replay_table(b)
        print("world gen (EMBARK_SEED_IN_PARAMS=1): mode seed k full_repeats first_varying_stage distinct>1")
        for (mode, seed), t in gens[name].items():
            print(f"  {mode:9} {seed} k={t['k']} full={t['full_repeats']}/{t['k']} first_varying={t['first_varying_stage']} {t['distinct']}")
        print("embark ids: mode seed -> distinct ids (count)")
        for (mode, seed), c in sorted(embs[name].items()):
            print(f"  {mode:9} {seed} {len(c)} distinct: " + "; ".join(f"{n}x {i}" for i, n in c.most_common()))
        tt = trace_table(b)
        if tt:
            print("tick traces: label -> first divergent tick (from the reseed) per field; None = identical throughout")
            for lab, t in sorted(tt.items()):
                print(f"  {lab:16} n={t['n']} ticks={t['ticks']} day0_identical={t['day0_identical']} {t['first_divergent_tick']}")
        print("replays: mode -> first divergent day per field (None = identical through the last day)")
        for lab, (cmp, rs) in sorted(reps[name].items()):
            errs = [r["error"] for r in rs if "error" in r]
            print(f"  {lab:16} n={cmp.get('n_replays', len(rs))} days={cmp.get('days')} any={cmp.get('any')} "
                  f"load_rng_identical={cmp.get('load_rng_identical')} " +
                  " ".join(f"{f}={cmp.get(f)}" for f in ('rng', 'units', 'items', 'jobs', 'reports_n')) +
                  (f" errors={errs}" if errs else ""))
    if len(bundles) > 1:
        names = list(gens)
        print("## cross-bundle agreement (modal fingerprints)")
        for key in sorted(set().union(*[set(g) for g in gens.values()])):
            ms = [gens[n].get(key, {}).get("modal") for n in names]
            if all(ms):
                diff = [s for s in STAGES if len({m[s] for m in ms}) > 1]
                print(f"  gen {key}: " + ("ALL STAGES AGREE" if not diff else f"differ at {diff}"))
        for key in sorted(set().union(*[set(e) for e in embs.values()])):
            ids = [embs[n].get(key) for n in names]
            if all(ids):
                print(f"  embark {key}: modal ids " + ("AGREE" if len({c.most_common(1)[0][0] for c in ids}) == 1 else "DIFFER"))
        for lab in sorted(set().union(*[set(r) for r in reps.values()])):
            ends = []
            for n in names:
                rs = [r for r in reps[n].get(lab, ({}, []))[1] if "days" in r]
                if rs:
                    last = rs[0]["days"][-1]
                    ends.append(json.dumps({f: last.get(f) for f in ("units", "items", "jobs", "rng")}, sort_keys=True))
            if len(ends) == len(names):
                print(f"  replay {lab}: final-day state (replay 0) " + ("AGREES" if len(set(ends)) == 1 else "DIFFERS") + " across bundles")


if __name__ == "__main__":
    main(sys.argv[1:])
