#!/usr/bin/env python3
"""runner/ci/bin/pool-install.py: install the season's staged private pool on a scoring host or job, without the
organiser's repo (D12). Mirrors `pool/dfpool unpack` (pool/dfpool cmd_unpack; keep the two in sync): refuse unsafe tar
members, check every file against MANIFEST.json (no changed, missing or unlisted file), rewrite suite.json's
task paths to this directory.

Input is the sealed bundle the organiser publishes (infra/RUNBOOK.md §1.4): `<season>-pool.tar.gz.enc`, made by
`runner/ci/bin/seal.sh seal` from dfpool stage's tarball. The plaintext tarball's sha256 must equal POOL.json's
`tarball_sha256` (passed as --expect-sha256; it's public, published at season open).

  pool-install.py --bundle s0-pool.tar.gz.enc --passphrase-file F --expect-sha256 HEX --into /srv/dfbench/s0
  pool-install.py --tar s0-pool.tar.gz --expect-sha256 HEX --into DIR       # already decrypted

Prints only counts and the commitment (never pool ids, task names or paths) so it is safe in any job log.
"""
import argparse, hashlib, json, os, subprocess, sys, tarfile, tempfile


def die(msg):
    sys.stderr.write(f"pool-install: {msg}\n"); sys.exit(1)


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle"); ap.add_argument("--passphrase-file"); ap.add_argument("--tar")
    ap.add_argument("--expect-sha256", required=True); ap.add_argument("--into", required=True)
    a = ap.parse_args()
    expect = a.expect_sha256.removeprefix("sha256:")
    into = os.path.realpath(a.into)
    if os.path.exists(os.path.join(into, "MANIFEST.json")):
        if open(os.path.join(into, ".tarball_sha256")).read().strip() == expect:
            print("pool-install: already installed (same tarball)"); return
        die(f"{into} holds a different pool; remove it first")
    if os.path.exists(into) and os.listdir(into):
        die(f"{into} isn't empty")
    tmp = tempfile.mkdtemp(prefix="pool-", dir=os.environ.get("RUNNER_TEMP") or None)
    tar = a.tar
    if a.bundle:
        if not a.passphrase_file:
            die("--bundle needs --passphrase-file")
        tar = os.path.join(tmp, "pool.tar.gz")
        here = os.path.dirname(os.path.realpath(__file__))
        seal = os.path.join(here, "seal.sh")              # runner/ci/bin/seal.sh, or /opt/dfbench/seal.sh on a host
        subprocess.run(["bash", seal, "open", a.bundle, tar, a.passphrase_file], check=True)
    if sha_file(tar) != expect:
        die("tarball sha256 differs from --expect-sha256 (POOL.json)")
    os.makedirs(into, mode=0o750, exist_ok=True)
    with tarfile.open(tar, "r:gz") as tf:
        members = tf.getmembers()
        for m in members:
            if not m.isfile() or m.name.startswith("/") or ".." in m.name.split("/"):
                die("unsafe tar member")
        for m in members:
            dst = os.path.join(into, m.name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with tf.extractfile(m) as src, open(dst, "wb") as out:
                while True:
                    b = src.read(1 << 20)
                    if not b:
                        break
                    out.write(b)
    if a.bundle:
        os.remove(tar)
    man = json.load(open(os.path.join(into, "MANIFEST.json")))
    bad = [r for r, f in man["files"].items()
           if not os.path.exists(os.path.join(into, r)) or sha_file(os.path.join(into, r)) != f["sha256"]]
    listed = set(man["files"]) | {"MANIFEST.json"}
    extra = [os.path.relpath(os.path.join(d, f), into) for d, _, fs in os.walk(into) for f in fs]
    extra = [r for r in extra if r not in listed]
    if bad or extra:
        die(f"manifest check failed: {len(bad)} changed or missing, {len(extra)} unlisted")
    suite_p = os.path.join(into, "suite.json")
    s = json.load(open(suite_p))
    for t in s["tasks"]:
        t["scenario"] = os.path.join(into, "tasks", os.path.basename(t["scenario"]))
    json.dump(s, open(suite_p, "w"), indent=1)
    open(os.path.join(into, ".tarball_sha256"), "w").write(expect + "\n")
    print(f"pool-install: OK, {len(man['files'])} files match the manifest (commitment {man.get('commitment')})")


if __name__ == "__main__":
    main()
