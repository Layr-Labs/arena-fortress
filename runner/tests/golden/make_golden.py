"""Record (or check) golden score.json outputs of stored public-fort runs, to prove refactors of the scorer keep DF
results identical. Run from the repo root:  python3 -I runner/tests/golden/make_golden.py [--check]"""
import hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "runner"))
from dfbenchlib import score as S   # noqa: E402
from dfbenchlib.suite import load_suite   # noqa: E402

RUNS = ["runs/s0-rc2-2026-10-26/plain", "runs/s0-plain-2026-10-23/minimal", "runs/s0-rc-2026-10-23/labs",
        "runs/s0-rc-2026-10-23/my1-lean", "toolkit/tests/fixtures/plain-a", "toolkit/tests/fixtures/plain-b"]
SUITES = ["runner/suites/season0-public.json", "runner/suites/season0.json", "runner/suites/season0-int.json"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden.json")


def compute():
    res = {}
    for r in RUNS:
        for s in SUITES:
            if not os.path.isdir(os.path.join(ROOT, r)):
                continue
            suite = load_suite(os.path.join(ROOT, s))
            score, detail = S.score_dir(os.path.join(ROOT, r), suite, write=False)
            blob = json.dumps({"score": score, "games": detail.get("games"), "families": detail.get("families"),
                               "weights": detail.get("weights")}, sort_keys=True)
            res[f"{r}|{s}"] = {"score": score["score"], "sha256": hashlib.sha256(blob.encode()).hexdigest()}
    return res


if __name__ == "__main__":
    got = compute()
    if "--check" in sys.argv:
        want = json.load(open(OUT))
        bad = [k for k in want if want[k] != got.get(k)]
        print("golden: OK" if not bad else f"golden: MISMATCH {bad}")
        sys.exit(1 if bad else 0)
    json.dump(got, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"golden: wrote {len(got)} entries")
