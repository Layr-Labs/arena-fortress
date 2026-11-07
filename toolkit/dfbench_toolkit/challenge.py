"""Finding a challenge clone and its trusted scorer.

The toolkit reads run artifacts on its own. Inside a clone of the challenge repo (or with DFBENCH_CHALLENGE_DIR set)
it also uses the challenge's own scorer: per-game gates and parts from bench/outcomes.py, and the suite aggregation
and bootstrap from runner/dfbenchlib/score.py, so its numbers are the official method's.
"""
import importlib, os, sys, warnings

from . import PINNED_SCORE_VERSION


def find_root(start=None):
    """-> the challenge root (has runner/dfbenchlib/score.py and bench/outcomes.py), or None."""
    cands = []
    if os.environ.get("DFBENCH_CHALLENGE_DIR"):
        cands.append(os.environ["DFBENCH_CHALLENGE_DIR"])
    d = os.path.abspath(start or os.getcwd())
    while True:
        cands.append(d)
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    for c in cands:
        if os.path.isfile(os.path.join(c, "runner", "dfbenchlib", "score.py")) and \
                os.path.isfile(os.path.join(c, "bench", "outcomes.py")):
            return os.path.abspath(c)
    return None


_cache = {}


def scorer(start=None):
    """-> (score module, outcomes module) from the challenge clone, or (None, None). Warns if the challenge's
    SCORE_VERSION differs from the one this toolkit's vendored aggregation was copied from."""
    root = find_root(start)
    if root is None:
        return None, None
    if root in _cache:
        return _cache[root]
    for p in (root, os.path.join(root, "runner")):
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        score = importlib.import_module("dfbenchlib.score")
        outcomes = importlib.import_module("bench.outcomes")
    except Exception as e:  # a broken or partial clone: fall back to the artifacts alone
        warnings.warn(f"challenge scorer at {root} not importable ({type(e).__name__}: {e}); using the vendored copy")
        _cache[root] = (None, None)
        return None, None
    v = getattr(score, "SCORE_VERSION", None)
    if v != PINNED_SCORE_VERSION:
        warnings.warn(f"challenge SCORE_VERSION {v!r} differs from the toolkit's pinned {PINNED_SCORE_VERSION!r}; "
                      "using the challenge's scorer")
    _cache[root] = (score, outcomes)
    return score, outcomes
