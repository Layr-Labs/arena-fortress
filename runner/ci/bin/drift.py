#!/usr/bin/env python3
"""runner/ci/bin/drift.py: provider-drift evidence for every scored run (challenge/SCORING.md §6.1, D26). Report only:
nothing here changes a score.

Findings behind it (runs/drift-probe-2026-10-28): the provider pin holds (one model snapshot, one Together endpoint,
no fallbacks), but the deployment behind Together's endpoint can't be pinned; a fixed tiny probe can't see changes;
the run's own calls on identical requests are the best evidence.

  drift.py fingerprint --games DIR [--k 8] [--reference REF] > route.json
      Samples k generation ids spread over the games' gateway ledgers and asks OpenRouter's generation endpoint
      (key: DFBENCH_PROVIDER_KEY or OPENROUTER_API_KEY) which model snapshot, endpoint, provider and edge region
      served them. Fails soft: route_unknown=true if nothing could be read.
  drift.py check --games DIR [--reference REF] [--n-first 5] > drift.json
      Reasoning tokens and the tool mix of the run's early calls against the season reference: matched by request
      digest (identical requests), or, when the run's harness is the reference harness, its first N calls per game.
  drift.py reference --games DIR [--route route.json] --season S --run ID > drift_reference.json
      The season reference, from the import baseline (score.yml writes it once; first write wins).
  drift.py merge --scored scored.json route.json drift.json
      Adds the flat metrics to scored.json.
  drift.py rescore --games DIR --submission ID --run ID
      What rescore.yml runs per re-scored pick: compares the run with that harness's OWN reference
      (seasons/<season>/drift_refs/<submission>.json, written by its first scoring run; the baseline's is
      drift_reference.json), writing the reference from this run if there is none yet. Prints the flat metrics as
      JSON; never fails.
  drift.py evidence --games DIR --scored scored.json --run ID [--write-reference] [--submission ID]
      What score.yml runs: reads seasons/<season>/drift_reference.json from the ops store (ledger.py's env), takes
      the fingerprint and the check, merges both into scored.json, and with --write-reference (the import baseline)
      writes the reference if none exists yet (first write wins; an organiser resets it by deleting the file).
      Never fails the run: any error becomes drift_flag=n/a / route_unknown=true.

Thresholds (power from the probe: a ×1.15 shift in reasoning tokens is caught 35% of the time with 100 calls, 93%
with 300; Together's own medians moved ×1.4 within two hours, so `watch` is expected now and then):
  drift_flag = alert  if KS p < 0.001 or tool-mix p < 0.001 (with >= 20 matched calls)
             = watch  if KS p < 0.01 or tool-mix p < 0.01, or the median ratio is outside [0.8, 1.25] while the
                      larger median is >= 100 reasoning tokens and the medians differ by >= 20 tokens (on short
                      early calls a 64 -> 90 token swing is a x1.4 ratio and nothing else: the first weekly
                      re-scores of mmurrs, runs/s0-rescore-noise-2026-10-29, flagged watch twice on the ratio alone
                      with KS p 0.16-0.76)
             = none   otherwise; n/a below 20 matched calls or without a reference;
             drift_basis = same-harness | matched:<n> | no-matching-requests | no-reference
  route_consistent = every sample shows one snapshot, one endpoint, one provider, one attempt, and they match the
                     reference's snapshot and endpoint (if a reference is set)
"""
import argparse, datetime, glob, hashlib, json, math, os, sys, urllib.error, urllib.request

MIN_N = 20
ALERT_P, WATCH_P = 0.001, 0.01
RATIO_BAND = (0.8, 1.25)
RATIO_MIN_MEDIAN, RATIO_MIN_DIFF = 100, 20     # the ratio band needs a median big enough to mean something


# ---- ledgers ----

def ledgers(games_dir):
    """-> [(game_id, [rows])] of the ok gateway calls per game, in call order."""
    out = []
    for p in sorted(glob.glob(os.path.join(games_dir, "**", "gateway", "usage.jsonl"), recursive=True)):
        gdir = os.path.dirname(os.path.dirname(p))
        if os.path.basename(gdir).startswith("attempt-"):
            continue                                   # an infra attempt; the game's final ledger is the one above
        rows = []
        with open(p, errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("outcome") == "ok":
                    rows.append(r)
        rows.sort(key=lambda r: r.get("seq") or 0)
        out.append((os.path.basename(gdir), rows))
    return out


def harness_digests(games_dir):
    """The harness source digests the games ran (the game server's summary rows record it)."""
    ds = set()
    for p in glob.glob(os.path.join(games_dir, "**", "summary.jsonl"), recursive=True):
        try:
            with open(p, errors="replace") as f:
                for line in f:
                    d = json.loads(line).get("harness_digest")
                    if d:
                        ds.add(d)
        except (OSError, ValueError):
            continue
    return sorted(ds)


# ---- statistics (stdlib) ----

def ks_2samp(a, b):
    """-> (D, p): two-sample Kolmogorov–Smirnov, asymptotic p (Kolmogorov distribution)."""
    if not a or not b:
        return None, None
    a, b = sorted(a), sorted(b)
    n, m = len(a), len(b)
    i = j = 0
    d = 0.0
    while i < n and j < m:
        x = min(a[i], b[j])
        while i < n and a[i] == x:
            i += 1
        while j < m and b[j] == x:
            j += 1
        d = max(d, abs(i / n - j / m))
    en = math.sqrt(n * m / (n + m))
    lam = (en + 0.12 + 0.11 / en) * d
    if lam < 0.3:                                      # Q_KS(0.3) > 0.99999; the alternating series fails near 0
        return d, 1.0
    p = 0.0
    for k in range(1, 101):
        p += 2 * (-1) ** (k - 1) * math.exp(-2 * k * k * lam * lam)
    return d, max(0.0, min(1.0, p))


def _gammainc_upper(s, x):
    """Regularised upper incomplete gamma Q(s, x) (series / continued fraction, Numerical Recipes)."""
    if x <= 0:
        return 1.0
    if x < s + 1:
        term = total = 1.0 / s
        a = s
        for _ in range(500):
            a += 1
            term *= x / a
            total += term
            if abs(term) < abs(total) * 1e-12:
                break
        return max(0.0, 1.0 - total * math.exp(-x + s * math.log(x) - math.lgamma(s)))
    b = x + 1 - s
    c, d = 1e300, 1 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - s)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        h *= d * c
        if abs(d * c - 1) < 1e-12:
            break
    return min(1.0, math.exp(-x + s * math.log(x) - math.lgamma(s)) * h)


def chi2_2xk(c1, c2):
    """-> p of a chi-square test of homogeneity between two count dicts (categories pooled if an expected count is
    below 1 would be better, but small tables are reported as-is with df = k-1)."""
    cats = sorted(set(c1) | set(c2))
    n1, n2 = sum(c1.values()), sum(c2.values())
    if len(cats) < 2 or not n1 or not n2:
        return None
    x2 = 0.0
    for c in cats:
        tot = c1.get(c, 0) + c2.get(c, 0)
        for obs, n in ((c1.get(c, 0), n1), (c2.get(c, 0), n2)):
            e = tot * n / (n1 + n2)
            if e > 0:
                x2 += (obs - e) ** 2 / e
    return _gammainc_upper((len(cats) - 1) / 2, x2 / 2)


def median(v):
    v = sorted(v)
    n = len(v)
    return None if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


# ---- the reference and the check ----

def early_calls(games_dir, n_first):
    """-> [{d, r, t}] of each game's first n_first ok calls: request digest, reasoning tokens, first tool called."""
    out = []
    for _, rows in ledgers(games_dir):
        for r in rows[:n_first]:
            t = (r.get("tools_called") or [None])[0]
            out.append({"d": r.get("request_digest"), "r": int(r.get("reasoning_tokens") or 0), "t": t})
    return out


def build_reference(games_dir, season, run, route=None, n_first=5):
    return {"schema": "dfbench-drift-reference/1", "season": season, "source_run": run,
            "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "harness_digests": harness_digests(games_dir), "n_first": n_first,
            "calls": early_calls(games_dir, n_first),
            "route": {k: (route or {}).get(k) for k in ("route_model_snapshot", "route_endpoint_id")}}


def ratio_out(ma, mb, ratio):
    """The median-ratio band, only where the medians are big enough for a ratio to mean something."""
    if ratio is None or ma is None or mb is None:
        return False
    if max(ma, mb) < RATIO_MIN_MEDIAN or abs(ma - mb) < RATIO_MIN_DIFF:
        return False
    return not RATIO_BAND[0] <= ratio <= RATIO_BAND[1]


def check(games_dir, ref, n_first=5):
    if not ref or not ref.get("calls"):
        return {"drift_flag": "n/a", "drift_basis": "no-reference", "drift_calls": 0}
    n_first = int(ref.get("n_first") or n_first)
    run = early_calls(games_dir, n_first)
    refd = {}
    for c in ref["calls"]:
        refd.setdefault(c["d"], []).append(c)
    matched_run = [c for c in run if c["d"] in refd]
    matched_ref = [x for d in sorted({c["d"] for c in matched_run}) for x in refd[d]]
    # drift_basis: what the comparison rests on. The check compares the model's behaviour on the SAME requests, so
    # it is meant for re-scores of one harness (the baseline, the weekly re-scores); a different submission sends
    # different requests and gets no-matching-requests (it is protected by the paired same-window confirmation).
    basis = f"matched:{len(matched_run)}"
    if len(matched_run) < MIN_N and set(harness_digests(games_dir)) & set(ref.get("harness_digests") or []):
        matched_run, matched_ref, basis = run, ref["calls"], "same-harness"
    n = len(matched_run)
    if n < MIN_N and basis != "same-harness":
        basis = "no-matching-requests"
    out = {"drift_basis": basis, "drift_calls": n}
    if n < MIN_N:
        return {**out, "drift_flag": "n/a"}
    ra, rb = [c["r"] for c in matched_run], [c["r"] for c in matched_ref]
    ma, mb = median(ra), median(rb)
    ratio = (ma / mb) if mb else None
    _, ks_p = ks_2samp(ra, rb)
    cnt = lambda cs: {k: sum(1 for c in cs if c["t"] == k) for k in {c["t"] for c in cs}}
    tool_p = chi2_2xk(cnt(matched_run), cnt(matched_ref))
    ps = [p for p in (ks_p, tool_p) if p is not None]
    if any(p < ALERT_P for p in ps):
        flag = "alert"
    elif any(p < WATCH_P for p in ps) or ratio_out(ma, mb, ratio):
        flag = "watch"
    else:
        flag = "none"
    r = lambda v, d=4: None if v is None else round(v, d)
    return {**out, "drift_reasoning_median": ma, "drift_reasoning_ratio": r(ratio, 3), "drift_ks_p": r(ks_p),
            "drift_tool_mix_p": r(tool_p), "drift_flag": flag}


# ---- the routing fingerprint ----

def http_json(url, key, timeout=20):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "User-Agent": "dfbench-drift"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def sample_ids(games_dir, k):
    """k generation ids spread over the games: one from the middle of each game's calls, round-robin."""
    per = [[r["generation_id"] for r in rows if r.get("generation_id")] for _, rows in ledgers(games_dir)]
    per = [p for p in per if p]
    out, i = [], 0
    while len(out) < k and any(per):
        p = per[i % len(per)]
        if p:
            out.append(p.pop(len(p) // 2))
        i += 1
        if i > 10 * k:
            break
    return out


def parse_generation(rec):
    """OpenRouter generation record -> {snapshot, endpoint, provider, attempts, region, providers}."""
    x = rec.get("data", rec) or {}
    pr = x.get("provider_responses") or []
    ok = [p for p in pr if p.get("status") == 200] or pr
    last = ok[-1] if ok else {}
    up = str(x.get("upstream_id") or last.get("id") or "")
    region = up.rsplit("-", 1)[-1] if "-" in up else None
    return {"snapshot": last.get("model_permaslug") or x.get("model"), "endpoint": last.get("endpoint_id"),
            "provider": x.get("provider_name") or last.get("provider_name"), "attempts": len(pr) or 1,
            "region": region, "providers": sorted({p.get("provider_name") for p in pr if p.get("provider_name")})}


def fingerprint(games_dir, k=8, key=None, ref=None, fetch=http_json):
    key = key or os.environ.get("DFBENCH_PROVIDER_KEY") or os.environ.get("OPENROUTER_API_KEY")
    ids = sample_ids(games_dir, k)
    recs = []
    if key:
        for gid in ids:
            try:
                recs.append(parse_generation(fetch(f"https://openrouter.ai/api/v1/generation?id={gid}", key)))
            except (urllib.error.URLError, OSError, ValueError, KeyError):
                continue
    if not recs:
        return {"route_unknown": True, "route_samples": 0, "route_consistent": None}
    snaps = sorted({r["snapshot"] for r in recs if r["snapshot"]})
    ends = sorted({r["endpoint"] for r in recs if r["endpoint"]})
    provs = sorted({p for r in recs for p in (r["providers"] or [r["provider"]]) if p})
    regs = sorted({r["region"] for r in recs if r["region"]})
    att = max(r["attempts"] for r in recs)
    eh = lambda e: "sha256:" + hashlib.sha256(e.encode()).hexdigest()[:16]
    out = {"route_unknown": False, "route_samples": len(recs),
           "route_model_snapshot": ",".join(snaps) or None,
           "route_endpoint_id": ",".join(eh(e) for e in ends) or None,
           "route_providers": ",".join(provs) or None, "route_regions": ",".join(regs) or None,
           "route_attempts_max": att, "route_fallbacks": len(provs) > 1 or att > 1}
    cons = len(snaps) == 1 and len(ends) == 1 and len(provs) == 1 and att == 1
    rr = (ref or {}).get("route") or {}
    if cons and rr.get("route_model_snapshot"):
        cons = out["route_model_snapshot"] == rr["route_model_snapshot"]
    if cons and rr.get("route_endpoint_id"):
        cons = out["route_endpoint_id"] == rr["route_endpoint_id"]
    out["route_consistent"] = cons
    return out


def merge(scored_path, *parts):
    with open(scored_path) as f:
        s = json.load(f)
    for p in parts:
        try:
            with open(p) as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                continue                                   # Yukon shows one row per flat key
            s["metrics"][k] = v
    json.dump(s, open(scored_path, "w"), indent=1)


REF_NAME = "drift_reference.json"


def own_ref_name(submission):
    """Each harness's own reference (its first scoring run), for same-harness re-scores; the baseline's is REF_NAME."""
    return REF_NAME if submission in (None, "", "baseline") else f"drift_refs/{submission}.json"


def _store():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ledger as L
    return L.load, L.save


def write_own_reference(games_dir, submission, run, route=None, store=None):
    """First write wins: the harness's first scored run becomes its reference. -> True if written."""
    load, save = store or _store()
    name = own_ref_name(submission)
    try:
        cur, _ = load(name)
    except SystemExit:
        return False
    if cur is not None:
        return False
    season = os.environ.get("DFBENCH_SEASON", "s0")
    try:
        return bool(save(name, build_reference(games_dir, season, run, route), None,
                         f"drift reference for {submission or 'baseline'} from run {run}"))
    except SystemExit:
        return False


def rescore(games_dir, submission, run, store=None):
    """A same-harness re-score against the harness's own reference. -> flat metrics (report only)."""
    load, save = store or _store()
    try:
        ref, _ = load(own_ref_name(submission))
    except SystemExit:
        ref = None
    route = fingerprint(games_dir, ref=ref)
    if ref is None:
        wrote = write_own_reference(games_dir, submission, run, route, (load, save))
        return {**route, "drift_flag": "n/a", "drift_basis": "no-reference", "drift_calls": 0,
                "drift_reference_written": wrote}
    return {**route, **check(games_dir, ref)}


def evidence(games_dir, scored_path, run, write_reference=False, store=None, submission=None):
    """-> the metrics merged into scored.json. `store` = (load, save) of the ops store (ledger.py by default)."""
    if store is None:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import ledger as L
        store = (L.load, L.save)
    load, save = store
    try:
        ref, sha = load(REF_NAME)
    except SystemExit:
        ref, sha = None, None
    route = fingerprint(games_dir, ref=ref)
    chk = check(games_dir, ref)
    if write_reference and ref is None:
        season = os.environ.get("DFBENCH_SEASON", "s0")
        try:
            wrote = save(REF_NAME, build_reference(games_dir, season, run, route), None,
                         f"drift reference from run {run} (the import baseline)")
        except SystemExit:
            wrote = False
        chk["drift_reference_written"] = bool(wrote)
    if submission and submission != "baseline":
        chk["drift_own_reference_written"] = write_own_reference(games_dir, submission, run, route, store)
    s = json.load(open(scored_path))
    for k, v in {**route, **chk}.items():
        if not isinstance(v, (dict, list)):
            s["metrics"][k] = v
    json.dump(s, open(scored_path, "w"), indent=1)
    return {**route, **chk}


def _ref(path):
    try:
        return json.load(open(path)) if path else None
    except (OSError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("fingerprint"); f.add_argument("--games", required=True); f.add_argument("--k", type=int, default=8)
    f.add_argument("--reference", default="")
    c = sp.add_parser("check"); c.add_argument("--games", required=True); c.add_argument("--reference", default="")
    c.add_argument("--n-first", type=int, default=5)
    r = sp.add_parser("reference"); r.add_argument("--games", required=True); r.add_argument("--route", default="")
    r.add_argument("--season", required=True); r.add_argument("--run", required=True)
    r.add_argument("--n-first", type=int, default=5)
    m = sp.add_parser("merge"); m.add_argument("--scored", required=True); m.add_argument("parts", nargs="*")
    e = sp.add_parser("evidence"); e.add_argument("--games", required=True); e.add_argument("--scored", required=True)
    e.add_argument("--run", required=True); e.add_argument("--write-reference", action="store_true")
    e.add_argument("--submission", default="")
    q = sp.add_parser("rescore"); q.add_argument("--games", required=True); q.add_argument("--submission", required=True)
    q.add_argument("--run", required=True)
    a = ap.parse_args()
    if a.cmd == "evidence":
        try:
            got = evidence(a.games, a.scored, a.run, a.write_reference, submission=a.submission or None)
            print("drift", got.get("drift_flag"), "route_consistent", got.get("route_consistent"),
                  "snapshot", got.get("route_model_snapshot"))
        except Exception as ex:                       # report only: never fail the run
            print(f"drift: evidence unavailable ({type(ex).__name__})")
        return
    if a.cmd == "rescore":
        try:
            got = rescore(a.games, a.submission, a.run)
        except Exception as ex:                       # report only: never fail the run
            got = {"drift_flag": "n/a", "drift_basis": f"unavailable ({type(ex).__name__})", "route_unknown": True}
        print(json.dumps({k: v for k, v in got.items() if not isinstance(v, (dict, list))}))
        return
    if a.cmd == "fingerprint":
        print(json.dumps(fingerprint(a.games, a.k, ref=_ref(a.reference)), indent=1))
    elif a.cmd == "check":
        print(json.dumps(check(a.games, _ref(a.reference), a.n_first), indent=1))
    elif a.cmd == "reference":
        print(json.dumps(build_reference(a.games, a.season, a.run, _ref(a.route), a.n_first), indent=1))
    else:
        merge(a.scored, *a.parts)


if __name__ == "__main__":
    main()
