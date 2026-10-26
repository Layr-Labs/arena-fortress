#!/usr/bin/env python3
"""runner/ci/bin/prior.py: the judge's context directory (docs/SCORING-INFRA.md §5.9; challenge/RULES.md §8a).

  prior.py --submitter-json submitter.json --out prior/ [--last 5] [--repo-dir .] [--max-diff-bytes 200000]
           [--fallback-base-producers ID,...] [--base REV --head REV] [--scan-max 500] [--scan-top 4]
           [--scan-timeout 300] [--no-scan]

For the base producer(s) (Yukon's incumbent; the leader file's if Yukon can't be read), every declared dependency of
the submission, the overlap-scan hits and the last N accepted submissions on this benchmark (newest promotion
first), writes prior/NN-<submission id>/ in runner/judge's context format (README "What the workflow must pass in"),
most important first:
  meta.json   submission_id, submitter, coauthors, status, produced_base, why it is here ("base_producer" |
              "dependency" | "overlap_scan" | "recent_accepted"), the dependency's declared rationale/evidence,
              the scan's overlap figures, Yukon's fields
  note.md     the public research note
  diff.patch  `git diff <commit>^ <commit> -- submission/` when the commit is in this repo (fetched from origin);
              absent for dependencies on other benchmarks
and prior/base_producers.txt (comma-separated; empty if main's submission/ is still the organiser's baseline).

The overlap scan: every published submission on the row (accepted or not; a closed, non-improving pull request is
still public and citable), newest first, up to --scan-max. Each one's added lines (its submissions/<id> commit
against its parent) are compared with this diff's (--base..--head) by the judge's own normalised line overlap
(runner/judge/judgelib/evidence.py). The top --scan-top undeclared ones at or above the floor go into the context,
where the judge's deterministic overlap signal applies to them like any other. The submitter's own earlier
submissions aren't scanned (RULES §8: reusing your own work isn't undeclared copying). prior/_scan.json records what
ran, what was skipped and why; the judge copies it into the dossier. If Yukon or git can't be read the scan degrades
to the fixed context above and says so there.
Everything here is public (Yukon's public API and the public benchmark repo). Prints counts only.
Env: DFBENCH_YUKON_API, YUKON_API_KEY (optional). Errors on individual entries are recorded in meta.json and
don't stop the run (the judge sees what was missing).
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "judge"))
from tier import Infra, http_json, yukon_headers  # noqa: E402
from judgelib import evidence as E  # noqa: E402

# A scan hit needs at least this much overlap: the judge's own "medium" floor (judgelib/signals.py), so every
# submission that would raise an overlap signal can reach the context.
SCAN_FLOOR_LINES, SCAN_FLOOR_FRACTION = 8, 0.1


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def diff_for(repo, sha, cap):
    if not sha:
        return None, "no commit"
    if git(repo, "cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
        git(repo, "fetch", "-q", "--depth", "2", "origin", sha)
    r = git(repo, "diff", f"{sha}^", sha, "--", "submission/")
    if r.returncode != 0:
        return None, "commit not in this repo"
    d = r.stdout
    return (d[:cap] + "\n[truncated]\n") if len(d) > cap else d, None


def submission_commit(repo, row):
    """The scored candidate commit of a listed submission: Yukon's submissionCommitSha if this clone has it, else
    the tip of its submissions/<id> branch (fetched by fetch_submission_branches)."""
    sha = row.get("submissionCommitSha")
    if sha and git(repo, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0:
        return sha
    ref = f"refs/remotes/origin/submissions/{row['id']}"
    r = git(repo, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}")
    return r.stdout.strip() if r.returncode == 0 else None


def fetch_submission_branches(repo):
    r = git(repo, "fetch", "-q", "--no-tags", "origin", "+refs/heads/submissions/*:refs/remotes/origin/submissions/*")
    return None if r.returncode == 0 else (r.stderr.strip()[-300:] or "git fetch failed")


def scan(sub, rows, exclude, repo, base, head, max_scan=500, top=4, cap=200_000, timeout=300.0, fetch=True,
         clock=time.monotonic):
    """The overlap scan (module docstring). Returns (hits [(row, overlap stats)], status for _scan.json)."""
    st = {"ran": False, "scanned": 0, "published": 0, "skipped": {}, "hits": [], "max_scan": max_scan, "top": top,
          "floor": {"shared_lines": SCAN_FLOOR_LINES, "fraction": SCAN_FLOOR_FRACTION}}
    me = (sub.get("username") or "").strip().lower()

    def skip(why, sid):
        st["skipped"].setdefault(why, []).append(sid)

    try:
        head_lines = E.collect_submission(repo, base, head)["scan_lines"]
    except (E.LimitHit, E.InputError) as e:
        st["degraded"] = f"this submission's diff: {e}"
        return [], st
    if fetch:
        err = fetch_submission_branches(repo)
        if err:
            st["fetch_error"] = err        # Yukon's submissionCommitSha may still be in the clone
    cands = []
    for r in rows:
        sid = r.get("id")
        if not sid or sid == sub["submission"] or sid in exclude:
            continue
        if me and (r.get("solverUsername") or "").strip().lower() == me:
            skip("own", sid)
            continue
        if not r.get("submissionCommitSha"):
            skip("unpublished", sid)
            continue
        cands.append(r)
    st["published"] = len(cands)
    cands.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
    for r in cands[max_scan:]:
        skip("over_scan_cap", r["id"])
    deadline = clock() + timeout
    found = []
    for i, r in enumerate(cands[:max_scan]):
        if clock() > deadline:
            for rest in cands[i:max_scan]:
                skip("timeout", rest["id"])
            break
        sha = submission_commit(repo, r)
        if not sha:
            skip("commit_not_found", r["id"])
            continue
        d = git(repo, "diff", "--no-color", "--no-ext-diff", "--no-textconv", f"{sha}^", sha, "--", "submission/")
        if d.returncode != 0:
            skip("diff_failed", r["id"])
            continue
        patch = d.stdout
        if len(patch) > cap:
            patch = patch[:cap]
            st.setdefault("truncated", []).append(r["id"])
        _, added = E.patch_added(patch)
        st["scanned"] += 1
        o = E.overlap(head_lines, [{"id": r["id"], "declared": False, "produced_base": False, "added_norm": added}])[0]
        if o["shared_lines"] >= SCAN_FLOOR_LINES or o["fraction"] >= SCAN_FLOOR_FRACTION:
            found.append((r, o))
    found.sort(key=lambda x: (x[1]["shared_lines"], x[1]["fraction"]), reverse=True)
    st["ran"] = True
    st["above_floor"] = len(found)
    st["hits"] = [{"id": r["id"], "shared_lines": o["shared_lines"], "fraction": o["fraction"]} for r, o in found[:top]]
    for r, _ in found[top:]:
        skip("below_top", r["id"])
    return found[:top], st


def build(sub, out, api, headers, repo=".", last=5, cap=200_000, http=http_json, fallback_producers=(),
          scan_opts=None):
    """Writes out/NN-<id>/ (the judge's context format, runner/judge/README.md) and out/base_producers.txt.
    Order (the judge reads at most 12, by directory name): base producer(s), declared dependencies, overlap-scan
    hits (only with scan_opts: base, head, and scan()'s limits), recent accepted.
    The base producer is Yukon's incumbent (promotionStatus "promoted"): in scalar mode, the submission whose harness
    is in main's submission/. If Yukon's list can't be read, fallback_producers (the leader file's) are used."""
    os.makedirs(out, exist_ok=True)
    errors = []
    try:
        rows = http(f"{api}/api/benchmarks/{sub['benchmark_id']}/submissions", headers).get("submissions") or []
    except Infra as e:
        rows = None
        errors.append(f"recent accepted: {e}")
    listed = rows is not None
    if rows is None:
        rows, base_producers = [], [x for x in fallback_producers if x]
    else:
        rows = [r for r in rows if r.get("id") != sub["submission"]]
        prom = sorted((r for r in rows if r.get("promotionStatus") == "promoted"),
                      key=lambda r: r.get("promotionFinishedAt") or "", reverse=True)
        base_producers = [prom[0]["id"]] if prom else []
    entries = {}
    for sid in base_producers:
        entries[sid] = {"why": "base_producer"}
    for dep in sub.get("dependencies") or []:
        e = entries.setdefault(dep["submissionId"], {"why": "dependency"})
        e.update(rationale=dep.get("rationale"), evidence=dep.get("evidence"), declared=True)
    if scan_opts is not None:
        if listed:
            hits, st = scan(sub, rows, set(entries), repo, cap=cap, **scan_opts)
            for r, o in hits:
                entries.setdefault(r["id"], {"why": "overlap_scan", "overlap_shared_lines": o["shared_lines"],
                                             "overlap_fraction": o["fraction"]})
        else:
            st = {"ran": False, "degraded": "Yukon's submission list couldn't be read: no overlap scan"}
        with open(os.path.join(out, "_scan.json"), "w") as f:
            json.dump(st, f, indent=1)
    acc = [r for r in rows if r.get("status") == "accepted"]
    acc.sort(key=lambda r: r.get("promotionFinishedAt") or r.get("updatedAt") or "", reverse=True)
    for r in acc[:last]:
        entries.setdefault(r["id"], {"why": "recent_accepted"})
    for n, (sid, why) in enumerate(entries.items()):
        d = os.path.join(out, f"{n:02d}-{sid}")
        os.makedirs(d, exist_ok=True)
        meta = {"submission_id": sid, "id": sid, "produced_base": sid in base_producers, **why}
        try:
            s = http(f"{api}/api/submissions/{sid}", headers)["submission"]
            meta.update({k: s.get(k) for k in ("benchmarkId", "solverUsername", "status", "promotionStatus",
                                                "officialScore", "submissionCommitSha", "promotedSourceRef",
                                                "createdAt")})
            meta["submitter"] = s.get("solverUsername") or ""
            meta["coauthors"] = s.get("coauthors") or []
            if s.get("promotionStatus") in ("promoted", "superseded"):
                meta["status"] = "promoted"
            with open(os.path.join(d, "note.md"), "w") as f:
                f.write(s.get("note") or "")
            if s.get("benchmarkId") == sub["benchmark_id"]:
                patch, err = diff_for(repo, s.get("submissionCommitSha"), cap)
                if patch is not None:
                    with open(os.path.join(d, "diff.patch"), "w") as f:
                        f.write(patch)
                else:
                    meta["diff_missing"] = err
            else:
                meta["diff_missing"] = "another benchmark"
        except Infra as e:
            meta["error"] = str(e)
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump(meta, f, indent=1)
    with open(os.path.join(out, "base_producers.txt"), "w") as f:
        f.write(",".join(base_producers))
    if errors:
        with open(os.path.join(out, "_errors.json"), "w") as f:
            json.dump({"why": "error", "error": "; ".join(errors)}, f)
    return len(entries)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--submitter-json", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--last", type=int, default=5); ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--max-diff-bytes", type=int, default=200_000)
    ap.add_argument("--fallback-base-producers", default="",
                    help="comma-separated ids (the leader file's), used only if Yukon can't be read")
    ap.add_argument("--base", default=None, help="this submission's base (default: merge-base of HEAD and origin/main)")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--scan-max", type=int, default=500, help="newest published submissions scanned")
    ap.add_argument("--scan-top", type=int, default=4, help="scan hits added to the context")
    ap.add_argument("--scan-timeout", type=float, default=300.0, help="seconds")
    ap.add_argument("--no-scan", action="store_true")
    a = ap.parse_args()
    sub = json.load(open(a.submitter_json))
    api = os.environ.get("DFBENCH_YUKON_API", "").rstrip("/")
    h = yukon_headers()
    opts = None
    if not a.no_scan:
        base = a.base or git(a.repo_dir, "merge-base", a.head, "origin/main").stdout.strip() or "origin/main"
        opts = {"base": base, "head": a.head, "max_scan": a.scan_max, "top": a.scan_top, "timeout": a.scan_timeout}
    n = build(sub, a.out, api, h, a.repo_dir, a.last, a.max_diff_bytes,
              fallback_producers=a.fallback_base_producers.split(","), scan_opts=opts)
    st = json.load(open(os.path.join(a.out, "_scan.json"))) if opts else {"ran": False}
    print(f"prior: {n} submissions ({len(sub.get('dependencies') or [])} declared dependencies) -> {a.out}; "
          f"scan: {'ran' if st.get('ran') else 'did not run'}, {st.get('scanned', 0)} scanned, "
          f"{len(st.get('hits') or [])} hits, skipped {({k: len(v) for k, v in (st.get('skipped') or {}).items()})}")


if __name__ == "__main__":
    main()
