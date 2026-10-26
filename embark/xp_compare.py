#!/usr/bin/env python3
"""Compare two hosts' seed-portability bundles (embark/xp_check.sh) and say where they first differ.

  python3 embark/xp_compare.py <bundleA> <bundleB>

Sections: host (CPU model, SIMD flags, glibc isa level), libm (per-function hashes, default and SSE2-only),
every common probe (embark/world_compare.py's stages), and every common full embark (tile, rectangle, map/plants
fingerprints). research/seed-portability.md.
"""
import glob, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def host(d):
    t = open(os.path.join(d, "host.txt")).read()
    m = re.search(r"model name\s*:\s*(.*)", t)
    f = re.search(r"^flags\s*:\s*(.*)$", t, re.M)
    isa = re.search(r"isa_1=(\S+)", t)
    fl = set(f.group(1).split()) if f else set()
    return {"cpu": m.group(1) if m else "?", "isa_1": isa.group(1) if isa else "?",
            "simd": sorted(x for x in fl if re.match(r"(sse|ssse|avx|fma|f16c|bmi)", x))}


def main(a, b):
    ha, hb = host(a), host(b)
    print(f"A {a}: {ha['cpu']} isa_1={ha['isa_1']}\nB {b}: {hb['cpu']} isa_1={hb['isa_1']}")
    if ha["simd"] != hb["simd"]:
        print(f"  simd only A {sorted(set(ha['simd']) - set(hb['simd']))}, only B {sorted(set(hb['simd']) - set(ha['simd']))}")
    print("libm (A vs B):")
    for kind in ("libm.json", "libm-nofma.json"):
        la, lb = json.load(open(os.path.join(a, kind))), json.load(open(os.path.join(b, kind)))
        diff = [k for k in la["libm"] if la["libm"][k] != lb["libm"].get(k)]
        print(f"  {kind:16} " + ("identical" if not diff else f"DIFF in {diff}"))
    for pa in sorted(glob.glob(os.path.join(a, "probe-*"))):
        if not os.path.isdir(pa):
            continue
        pb = os.path.join(b, os.path.basename(pa))
        if not os.path.exists(os.path.join(pa, "world.json")) or not os.path.exists(os.path.join(pb, "world.json")):
            continue
        r = subprocess.run([sys.executable, os.path.join(HERE, "world_compare.py"), pa, pb], capture_output=True, text=True)
        lines = [l for l in r.stdout.splitlines() if "DIFF" in l or "FIRST" in l or "details:" in l]
        print(f"{os.path.basename(pa)}:")
        for l in lines:
            print("  " + l.strip()[:400])
    for ea in sorted(glob.glob(os.path.join(a, "embark-*/SNAPSHOT.json"))):
        eb = os.path.join(b, os.path.relpath(ea, a))
        if not os.path.exists(eb):
            continue
        sa, sb = (json.load(open(x))["embark"] for x in (ea, eb))
        fa, fb = sa["probe"]["fingerprint"], sb["probe"]["fingerprint"]
        rows = [("tile", sa["world_tile"], sb["world_tile"]), ("local", sa["local"], sb["local"]),
                ("map", fa["map"], fb["map"]), ("plants", fa["plants"], fb["plants"]),
                ("tried", [(c["wx"], c["wy"], c["result"]) for c in sa["candidates_tried"]],
                 [(c["wx"], c["wy"], c["result"]) for c in sb["candidates_tried"]])]
        print(f"embark seed {sa['seed']}: " + "; ".join(
            f"{n} {'ok' if x == y else f'DIFF {x} | {y}'}" for n, x, y in rows))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
