#!/usr/bin/env python3
"""Fingerprint this host's libm on the functions dwarfort imports (atan2, cos, pow, sincos -> sin/cos, sqrt).

  python3 embark/libm_fp.py [--n 200000] [--examples]

CPython's math module calls glibc's libm, so inside the image this measures the same code DF calls, through the same
ifunc dispatch (glibc picks an FMA/AVX2 or SSE2 variant from the CPU flags it sees). Prints one JSON line: a hash per
function over n deterministic inputs, and the host CPU facts. Two hosts with the same hashes compute these functions
bit-identically; a differing hash means DF's float maths can diverge there (research/seed-portability.md).
"""
import hashlib, json, math, os, platform, random, re, struct, sys

n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 200000
rng = random.Random(12345)
# inputs in the ranges world gen plausibly uses: angles, unit-ish values, map coordinates, exponents
xs = [rng.uniform(-1e3, 1e3) for _ in range(n)]
ys = [rng.uniform(-1e3, 1e3) for _ in range(n)]
us = [rng.uniform(0.0, 1.0) for _ in range(n)]
es = [rng.uniform(-4.0, 4.0) for _ in range(n)]

out, examples = {}, {}


def run(name, f, args):
    h = hashlib.sha256()
    for a in zip(*args):
        v = f(*a)
        h.update(struct.pack("<d", v))
    out[name] = h.hexdigest()[:12]
    examples[name] = [struct.pack("<d", f(*a)).hex() for a in list(zip(*args))[:3]]


run("atan2", math.atan2, (xs, ys))
run("cos", math.cos, (xs,))
run("sin", math.sin, (xs,))
run("pow", math.pow, (us, es))
run("sqrt", math.sqrt, ([abs(x) for x in xs],))
run("exp", math.exp, (es,))
run("log", math.log, ([abs(x) + 1e-9 for x in xs],))
info = open("/proc/cpuinfo").read() if os.path.exists("/proc/cpuinfo") else ""
m = re.search(r"model name\s*:\s*(.*)", info)
f = re.search(r"^flags\s*:\s*(.*)$", info, re.M)
fl = set(f.group(1).split()) if f else set()
res = {"n": n, "libm": out, "cpu_model": m.group(1) if m else None, "glibc": platform.libc_ver(),
       "simd": sorted(x for x in fl if re.match(r"(sse|ssse|avx|fma|f16c|bmi)", x)),
       "tunables": os.environ.get("GLIBC_TUNABLES")}
if "--examples" in sys.argv:
    res["examples"] = examples
print(json.dumps(res, sort_keys=True))
