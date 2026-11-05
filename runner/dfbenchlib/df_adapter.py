"""The Dwarf Fortress environment adapter (framework/harnessarena/adapter.py): everything the trusted scorer knows
about DF, behind the framework's interface. The scorers themselves (bench/outcomes.py: the outcome score O;
bench/predicates.py: the lab predicates) are unchanged; this module only dispatches to them.
"""
import json, os, sys

from . import ROOT
from .game import last_summary_row

sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "framework"))
from bench import outcomes, predicates   # noqa: E402  the trusted scorers, unchanged
from harnessarena import adapter as A    # noqa: E402

PRED = {"LT01": predicates.lt01, "LT02": predicates.lt02, "LT03": predicates.lt03, "LT04": predicates.lt04,
        "LT05": predicates.lt05, "LT08": predicates.lt08, "LT09": predicates.lt09,
        "LT08-items": lambda r, d: predicates.lt08(r, d, items=True)}
ZERO_S = {"survival": 0.0, "supply": 0.0, "wellbeing": 0.0, "growth": 0.0}


class DFAdapter(A.Adapter):
    name = "dfbench"
    default_env_url = "http://game:8090"

    def read_episode(self, g):
        """The server's last summary row that isn't a crash marker."""
        p = os.path.join(g, "summary.jsonl")
        rows = []
        if os.path.exists(p):
            with open(p) as f:
                rows = [json.loads(l) for l in f if l.strip()]
        rows = [r for r in rows if not r.get("crashed")]
        return rows[-1] if rows else None

    def episode_fields(self, row):
        return dict(days=float(row.get("days_played") or 0), wall_s=row.get("wall_s"),
                    wall_capped=bool(row.get("wall_capped")), finished_by=row.get("finished_by"),
                    actions_used=row.get("actions_used"), actions_rejected=row.get("actions_rejected"),
                    harness_digest=row.get("harness_digest"), key=row.get("key"))

    def score_episode(self, g, row, spec):
        o = outcomes.for_run(g, row)
        if o is None:
            raise A.EpisodeInfra("no daily samples")
        out = dict(O=o["outcome"], tier=o["tier"], s=o["s"], notes=[])
        if spec.get("kind") == "lab":
            fn = PRED.get(spec.get("predicate") or spec["task_id"])
            got = [(r, dd) for r, dd in predicates.runs([g])]
            if fn is None or not got:
                raise A.EpisodeInfra("no predicate or no lab artifacts")
            try:
                c, part, info = fn(*got[-1])
                out.update(partial=round(part, 4), passed=all(x for x in c if x is not None), clauses=c)
            except (IndexError, KeyError, ZeroDivisionError) as e:
                # e.g. a wall-capped or lost fort that never reached day A: scored as no credit
                out.update(partial=0.0, passed=False, clauses=None)
                out["notes"].append(f"predicate error {type(e).__name__}: {e}; partial 0")
        return out

    def score_crashed(self, g, spec, rec):
        """DF crashed or hung twice: the state reached, from the server's last summary row (crashed or not) and its
        daily samples, like a wall-capped game; with no samples, a lost fort (O 0, partial 0)."""
        out = {"notes": []}
        row = last_summary_row(g)
        o = None
        if row is not None:
            try:
                o = outcomes.for_run(g, row)
            except (OSError, ValueError, KeyError, IndexError, ZeroDivisionError, TypeError) as e:
                out["notes"].append(f"outcome error {type(e).__name__}: {e}")
        if row is not None:
            out.update(days=float(row.get("days_played") or 0), wall_s=row.get("wall_s"),
                       finished_by="crashed", actions_used=row.get("actions_used"),
                       actions_rejected=row.get("actions_rejected"), harness_digest=row.get("harness_digest"),
                       key=row.get("key"))
        else:
            out.update(days=0.0, wall_s=rec.get("wall_s"), finished_by="crashed")
        if o is None:
            out["notes"].append("no daily samples: scored as a lost fort")
            out.update(O=0.0, tier=0, s=dict(ZERO_S))
        else:
            out.update(O=o["outcome"], tier=o["tier"], s=o["s"])
        if spec.get("kind") == "lab":
            fn = PRED.get(spec.get("predicate") or spec["task_id"])
            part, passed, c = 0.0, False, None
            stem = os.path.join(g, f"{row['arm']}-{row['k']}") if row else None
            if fn and o is not None and stem and os.path.exists(stem + ".daily.json"):
                try:
                    dd = json.load(open(stem + ".daily.json"))
                    if os.path.exists(stem + ".credit.json"):
                        dd["_credit"] = json.load(open(stem + ".credit.json"))
                    c, part, _ = fn(row, dd)
                    passed = all(x for x in c if x is not None)
                except (IndexError, KeyError, ZeroDivisionError, TypeError, ValueError) as e:
                    out["notes"].append(f"predicate error {type(e).__name__}: {e}; partial 0")
                    part, passed, c = 0.0, False, None
            out.update(partial=round(part, 4), passed=passed, clauses=c)
        return out

    def format_task(self, t, gs, value):
        n = len(gs)
        if t["kind"] == "lab":
            p = sum(g["partial"] for g in gs) / n
            return f"pass {sum(bool(g['passed']) for g in gs)}/{n}, partial {p:.2f}, z {value / 100:.2f}"
        tiers = [sum(g["tier"] == i for g in gs) for i in range(5)]
        return f"O {sum(g['O'] for g in gs) / n:.1f} (n {n}; tiers 0-4 {','.join(map(str, tiers))})"


DF = A.register(DFAdapter())
