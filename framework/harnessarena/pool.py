"""Private instance pools: the environment-agnostic part (docs/TEMPLATE-AGENT-HARNESS.md §3.5).

An environment supplies `build(task, seed) -> instance` and `accept(task, instance) -> (ok, reasons)`; the
framework does the rest: a salted commitment over the seeds and every input that shapes an instance (published
before the season opens), the selection rule (each task's pool = its first `forts` accepted seeds in ascending
order, rejected seeds committed too), deterministic staging, and the reveal check anyone can run after the season.
dfbench's `pool/dfpool` is the first user: DF fort building stays there; these functions are what it shares.
"""
import hashlib, json, os, tarfile

COMMIT_SCHEMA = "dfpool-commit/1"   # the preimage tag; kept for dfbench season 0 (the published commitment uses it)


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def lp_sha(*fields):
    """sha256 over length-prefixed fields (8-byte big-endian length + bytes)."""
    h = hashlib.sha256()
    for f in fields:
        b = f if isinstance(f, bytes) else str(f).encode()
        h.update(len(b).to_bytes(8, "big")); h.update(b)
    return h.hexdigest()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def preimage_fields(season, salt_hex, seeds, pub, schema=COMMIT_SCHEMA):
    """The commitment's preimage, in order. `pub` = the commitment's public_inputs."""
    return [schema, season, bytes.fromhex(salt_hex),
            canon({t: sorted(int(s) for s in v) for t, v in seeds.items()}),
            canon(pub["rules_sha256"]), pub["image_digest"], canon(pub["task_def_sha256"]),
            canon({k: pub[k] for k in ("spec_sha256", "repo_commit", "seed_mode", "seed_space", "forts", "candidates")})]


def commitment_of(season, salt_hex, seeds, pub, schema=COMMIT_SCHEMA):
    return "sha256:" + lp_sha(*preimage_fields(season, salt_hex, seeds, pub, schema))


def selection_check(candidates, attempts, need, used):
    """The selection rule, checked from a reveal's build ledger. `attempts`: [{seed, status}] for one task;
    `used`: the seeds the pool used. -> (accepted, n_rejected, ok): every candidate below the last used one was
    tried, and the used seeds are exactly the first `need` accepted in ascending order."""
    att = {e["seed"]: e for e in attempts if e["status"] in ("accepted", "rejected")}
    acc = [s for s in sorted(candidates) if att.get(s, {}).get("status") == "accepted"]
    last = acc[need - 1] if len(acc) >= need else None
    untried = [s for s in sorted(candidates) if last is not None and s < last and s not in att]
    ok = last is not None and not untried and sorted(used) == acc[:need] and len(acc) == need
    return acc, sum(e["status"] == "rejected" for e in att.values()), ok


def tar_add(tf, path, arc):
    """Deterministic tar members: sorted, uid/gid 0, mtime 0."""
    paths = [(path, arc)]
    if os.path.isdir(path):
        paths = []
        for d, ds, fs in os.walk(path):
            ds.sort()
            for f in sorted(fs):
                p = os.path.join(d, f)
                paths.append((p, os.path.join(arc, os.path.relpath(p, path))))
    for p, n in paths:
        ti = tarfile.TarInfo(n)
        ti.size, ti.mtime, ti.mode, ti.uid, ti.gid, ti.uname, ti.gname = os.path.getsize(p), 0, 0o644, 0, 0, "", ""
        with open(p, "rb") as f:
            tf.addfile(ti, f)
