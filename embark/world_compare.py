#!/usr/bin/env python3
"""Compare two world probes of one seed stage by stage and name the first stage that differs.

  python3 embark/world_compare.py <probeA> <probeB>     probes from `make_embark.sh --probe DIR` (research/seed-portability.md)
  python3 embark/world_compare.py --host-info SEED CPU  (internal: host facts for a probe's host.json)
  python3 embark/world_compare.py --summary <probe>...  one fingerprint line per probe

Stages, in the order DF produces them: world-gen params -> terrain (region map: elevation, rainfall, vegetation,
temperature, evil, drainage, volcanism, savagery, salinity, biome, geology, soil) -> river flags and river paths ->
history (event/figure/entity counts, event-type sequence) -> sites (type, position, rectangle, owner race) and
site/road tiles -> names (not reproducible even on one host) -> the site screen's candidate list -> each tile's
mid-level details (biome, elevation, rivers) -> the rectangle site_select.lua picks.
"""
import glob, hashlib, json, os, platform, re, sys


def h(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()[:12]


def host_info(seed, cpu):
    i = open("/proc/cpuinfo").read()
    m = re.search(r"model name\s*:\s*(.*)", i)
    f = re.search(r"^flags\s*:\s*(.*)$", i, re.M)
    print(json.dumps({"seed": int(seed), "cpu_pinned": str(cpu), "cpu_model": m.group(1) if m else None,
                      "nproc": os.cpu_count(), "kernel": platform.release(),
                      "flags": sorted((f.group(1) if f else "").split())}, indent=1))


def load(d):
    w = json.load(open(os.path.join(d, "world.json")))
    p = {"dir": d, "w": w}
    gp = glob.glob(os.path.join(d, "*world_gen_param.txt"))
    p["params"] = open(gp[0], "rb").read() if gp else b""
    p["cands"] = [l.split()[1:4] for l in open(os.path.join(d, "candidates.txt")) if l.startswith("CAND")] \
        if os.path.exists(os.path.join(d, "candidates.txt")) else []
    p["rects"] = {tuple(l.split()[:2]): " ".join(l.split()[2:]) for l in open(os.path.join(d, "rects.txt"))} \
        if os.path.exists(os.path.join(d, "rects.txt")) else {}
    p["details"] = {}
    for f in glob.glob(os.path.join(d, "details-*.json")):
        x = json.load(open(f))
        p["details"][(str(x["wx"]), str(x["wy"]))] = x
    hj = os.path.join(d, "host.json")
    p["host"] = json.load(open(hj)) if os.path.exists(hj) else {}
    return p


def sites_noname(w):
    return sorted((s["type"], s["x"], s["y"], tuple(s["rect"]), s.get("civ_race") or "") for s in w["sites"])


def stages(p):
    w = p["w"]
    hist = w["history"]
    return [
        ("params", hashlib.sha256(p["params"]).hexdigest()[:12]),
        ("dims", h(w["dims"])),
        ("terrain", h(w["terrain"])),
        ("river_flags", h(w["river_flags"])),
        ("rivers", h(w["rivers"])),
        ("history_counts", h([hist["figures"], hist["events"], hist["entities"]])),
        ("history_event_types", h(hist["event_types"])),
        ("entities", h(hist["entity_kinds"])),
        ("sites", h(sites_noname(w))),
        ("site_road_tiles", h(w["sitemask"])),
        ("world_name", h(w["world_name"])),
        ("site_names", h(w["site_names"])),
        ("candidates", h(p["cands"])),
    ]


TERRAIN_FIELDS = ["wx", "wy", "elevation", "rainfall", "vegetation", "temperature", "evilness", "drainage",
                  "volcanism", "savagery", "salinity", "biome", "geo_index", "soil", "region_id", "landmass_id"]


def explain(name, a, b):
    wa, wb = a["w"], b["w"]
    if name == "terrain":
        diff = {}
        n = 0
        for ra, rb in zip(wa["terrain"], wb["terrain"]):
            if ra != rb:
                n += 1
                for k, (x, y) in enumerate(zip(ra, rb)):
                    if x != y:
                        diff.setdefault(TERRAIN_FIELDS[k], []).append(abs(x - y) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else 1)
        return f"{n} of {len(wa['terrain'])} world tiles differ; by field (tiles, max |delta|): " + \
            ", ".join(f"{k} ({len(v)}, {max(v)})" for k, v in sorted(diff.items()))
    if name == "history_counts":
        return f"A {wa['history']['figures']}/{wa['history']['events']}/{wa['history']['entities']} vs " \
               f"B {wb['history']['figures']}/{wb['history']['events']}/{wb['history']['entities']} (figures/events/entities)"
    if name == "history_event_types":
        ea, eb = wa["history"]["event_types"], wb["history"]["event_types"]
        k = next((i for i, (x, y) in enumerate(zip(ea, eb)) if x != y), min(len(ea), len(eb)))
        return f"event sequences agree for the first {k} of {len(ea)} / {len(eb)} events"
    if name == "sites":
        sa, sb = set(sites_noname(wa)), set(sites_noname(wb))
        return f"{len(sa)} vs {len(sb)} sites; only in A: {sorted(sa - sb)[:6]}; only in B: {sorted(sb - sa)[:6]}"
    if name == "site_road_tiles":
        d = [(ra[0], ra[1], ra[2:], rb[2:]) for ra, rb in zip(wa["sitemask"], wb["sitemask"]) if ra != rb]
        return f"{len(d)} tiles differ (x, y, [site, road] A, B): {d[:8]}"
    if name == "candidates":
        return f"A first 5 {a['cands'][:5]} | B first 5 {b['cands'][:5]}"
    return ""


def main(a, b):
    A, B = load(a), load(b)
    print(f"{a}  vs  {b}")
    for k in ("cpu_model", "nproc", "kernel", "cpu_pinned"):
        print(f"  host.{k}: {A['host'].get(k)}  |  {B['host'].get(k)}")
    fa, fb = set(A["host"].get("flags", [])), set(B["host"].get("flags", []))
    if fa != fb:
        print(f"  host.flags only A: {sorted(fa - fb)}\n  host.flags only B: {sorted(fb - fa)}")
    first = None
    for (name, x), (_, y) in zip(stages(A), stages(B)):
        same = x == y
        if not same and first is None and name not in ("site_names", "world_name"):
            first = name
        print(f"  {'ok  ' if same else 'DIFF'} {name:20} {x}" + ("" if same else f" | {y}   {explain(name, A, B)}"))
    common = sorted(set(A["details"]) & set(B["details"]))
    nd = 0
    for t in common:
        da, db = A["details"][t], B["details"][t]
        bad = [k for k in ("biome", "elevation", "rivers_v", "rivers_h") if da[k] != db[k]]
        ra, rb = A["rects"].get(t), B["rects"].get(t)
        if bad or ra != rb:
            nd += 1
            print(f"  DIFF details ({t[0]},{t[1]}): {bad or 'same'}; rect {ra} | {rb}")
    if common:
        print(f"  details: {len(common) - nd} of {len(common)} common tiles identical")
        if nd and first is None:
            first = "details"
    print("FIRST DIFFERING STAGE: " + (first or "none (names aside)"))
    return 0 if first is None else 1


def summary(dirs):
    for d in dirs:
        p = load(d)
        print(d, p["host"].get("cpu_model"), " ".join(f"{n}={v}" for n, v in stages(p)))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--host-info":
        host_info(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "--summary":
        summary(sys.argv[2:])
    elif len(sys.argv) == 3:
        sys.exit(main(sys.argv[1], sys.argv[2]))
    else:
        sys.exit(__doc__)
