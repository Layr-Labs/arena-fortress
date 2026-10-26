#!/usr/bin/env python3
"""Host-side batch metadata for docker/batch.sh (docs/BENCHMARK-v1.md §1.3, pre-freeze).

  batch_meta.py start OUT --image IMG --parallel P [--arms A] [--runs N] -- <smoke.py args>
      writes OUT/BATCH.host.json: commit, dirty tree, image digest, docker version, the harness key of this
      checkout. DFBENCH_REQUIRE_CLEAN=1 refuses a dirty tree.
  batch_meta.py check OUT
      compares the key each container wrote (OUT/<arm>-<k>/BATCH.json, from the files inside the image) with this
      checkout's and with each other. Prints a warning when the image was built from a different tree. Exit 1 if
      the runs in OUT don't share one key.
stdlib only.
"""
import glob, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bench import key as BK


def sh(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=BK.ROOT, timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _ablate(extra):
    """The --ablate value in the smoke.py args (bench/ablate.py), as a sorted list; [] if none."""
    v = next((extra[i + 1] for i, x in enumerate(extra[:-1]) if x == "--ablate"), None)
    v = v or next((x.split("=", 1)[1] for x in extra if x.startswith("--ablate=")), "")
    return sorted({x.strip() for x in v.split(",") if x.strip()})


def start(out, image, parallel, arms, runs, extra):
    dirty = bool(sh("git", "status", "--porcelain", "--untracked-files=no"))
    if dirty and os.environ.get("DFBENCH_REQUIRE_CLEAN"):
        sys.exit("DFBENCH_REQUIRE_CLEAN is set and the working tree has uncommitted changes")
    host = {"schema": BK.SCHEMA, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "commit": sh("git", "rev-parse", "--short", "HEAD") or None, "dirty": dirty,
            "image": image, "image_digest": sh("docker", "image", "inspect", "--format", "{{.Id}}", image) or None,
            "docker": sh("docker", "version", "--format", "{{.Server.Version}}") or None,
            "parallel": parallel, "arms": arms, "runs": runs, "smoke_args": extra,
            "host_harness": BK.harness_part(BK.compute(ablate=_ablate(extra)))}
    if os.environ.get("DFB_CONDITION"):   # bench/teacher_batch.sh: the teacher's model id, effort, endpoint (bake-off)
        host["teacher_condition"] = json.loads(os.environ["DFB_CONDITION"])
    # the key of the files inside the image, before any run starts (each container's runs/job is fresh, so
    # smoke.py's own resume check can't see earlier runs of this batch)
    abl = _ablate(extra)
    raw = sh("docker", "run", "--rm", "--platform", "linux/amd64", "--entrypoint", "python3", image,
             "/root/dfprobe/bench/key.py", *(["--ablate", ",".join(abl)] if abl else []))
    try:
        host["image_harness"] = BK.harness_part(json.loads(raw))
    except ValueError:
        host["image_harness"] = None
        print("note: the image has no bench/key.py (built before it); its harness version can't be checked",
              file=sys.stderr)
    img = host["image_harness"]
    if img and img != host["host_harness"]:
        diff = [k for k in sorted(img) if img.get(k) != host["host_harness"].get(k)]
        print(f"WARNING: image {image} was built from a different tree than this checkout ({', '.join(diff)})",
              file=sys.stderr)
    if img:
        for bp in sorted(glob.glob(os.path.join(out, "*", "BATCH.json"))):
            prev = json.load(open(bp))["harness"]
            if prev != img:
                diff = [k for k in sorted(img) if img.get(k) != prev.get(k)]
                msg = (f"{os.path.dirname(bp)} was run by a different harness than image {image} ({', '.join(diff)}). "
                       "Use a new --out, or set DFBENCH_ALLOW_MIXED=1.")
                if not os.environ.get("DFBENCH_ALLOW_MIXED"):
                    sys.exit("refusing to resume: " + msg)
                print("WARNING: " + msg, file=sys.stderr)
    path = os.path.join(out, "BATCH.host.json")
    prev = json.load(open(path)) if os.path.exists(path) else None
    hist = (prev or {}).get("history", []) + ([{k: prev[k] for k in ("at", "commit", "dirty", "image_digest")}]
                                              if prev else [])
    host["history"] = hist   # earlier invocations of this batch (resumes)
    with open(path, "w") as f:
        json.dump(host, f, indent=1)
    if dirty:
        print("note: uncommitted changes in the working tree; recorded as dirty in BATCH.host.json", file=sys.stderr)


def check(out):
    path = os.path.join(out, "BATCH.host.json")
    host = json.load(open(path))["host_harness"] if os.path.exists(path) else BK.harness_part(BK.compute())
    keys, missing = {}, []
    for d in sorted(glob.glob(os.path.join(out, "*", ""))):
        bp = os.path.join(d, "BATCH.json")
        if not os.path.exists(bp):
            if os.path.exists(os.path.join(d, "summary.jsonl")):
                missing.append(os.path.basename(d.rstrip("/")))
            continue
        b = json.load(open(bp))
        for t, tk in b["tasks"].items():
            keys.setdefault(tk["key"], []).append(os.path.basename(d.rstrip("/")))
        if b["harness"] != host:
            diff = [k for k in sorted(set(host) | set(b["harness"])) if host.get(k) != b["harness"].get(k)]
            print(f"WARNING {os.path.basename(d.rstrip('/'))}: the image's harness differs from this checkout ({', '.join(diff)}); "
                  "it was built from a different tree", file=sys.stderr)
    if missing:
        print(f"note: {len(missing)} run(s) have no BATCH.json (image predates bench/key.py): {missing[:5]}", file=sys.stderr)
    for k, runs in keys.items():
        print(f"key {k}  ({len(runs)} runs)")
    if len(keys) > 1:
        print("ERROR: runs in this batch don't share one key; they aren't comparable", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("out"); s.add_argument("--image", required=True)
    s.add_argument("--parallel", type=int); s.add_argument("--arms"); s.add_argument("--runs", type=int)
    c = sub.add_parser("check"); c.add_argument("out")
    argv = sys.argv[1:]
    extra = argv[argv.index("--") + 1:] if "--" in argv else []   # smoke.py args, recorded as given
    a = p.parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    if a.cmd == "start":
        start(a.out, a.image, a.parallel, a.arms, a.runs, extra)
    else:
        check(a.out)
