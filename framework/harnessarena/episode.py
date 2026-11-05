"""The episode artifacts manifest `episode.json` (docs/TEMPLATE-AGENT-HARNESS.md §3.3).

An episode server writes it into its artifacts dir when the episode ends; the framework reads only this manifest,
the gateway ledger and the files the manifest names. Adapters that predate the manifest (dfbench) derive it from
their own artifacts with `from_fields`.
"""
SCHEMA = "harnessarena-episode/1"
ENDED_BY = ("horizon", "harness_finish", "lost", "wall_cap", "crashed")
REQUIRED = ("schema", "task_id", "instance_id", "horizon", "ended_by")


def validate(m):
    """-> list of problems (empty = valid)."""
    out = [f"missing {k}" for k in REQUIRED if k not in m]
    if m.get("schema") not in (None, SCHEMA):
        out.append(f"schema {m.get('schema')!r}, expected {SCHEMA!r}")
    if "ended_by" in m and m["ended_by"] not in ENDED_BY:
        out.append(f"ended_by {m['ended_by']!r} not in {ENDED_BY}")
    for k in ("actions_used", "actions_rejected"):
        if k in m and m[k] is not None and not (isinstance(m[k], int) and m[k] >= 0):
            out.append(f"{k} must be a non-negative integer")
    if "files" in m and not isinstance(m["files"], dict):
        out.append("files must be an object")
    return out


def from_fields(task_id, instance_id, horizon, ended_by, **extra):
    m = {"schema": SCHEMA, "task_id": task_id, "instance_id": instance_id, "horizon": horizon, "ended_by": ended_by}
    m.update({k: v for k, v in extra.items() if v is not None})
    return m
