"""A model tool for documented read-only queries, constrained by /task's advertised capabilities."""
import json
from dfbench_client import GameAPIError, GameOver, HandsOff

# Arguments from the public manual, not arbitrary endpoints or a generic URL fetcher.
PARAMS = {
    "stocks": {"item_type", "limit"}, "units": {"kind", "id", "limit"},
    "jobs": {"limit"}, "orders": {"limit"}, "buildings": {"type", "limit"},
    "zones": {"limit"}, "map": {"x", "y", "z", "radius", "z2"},
    "manager_order_types": set(), "workshop_types": set(),
}
LIMIT = 3400


def advertised(queries):
    if isinstance(queries, dict):
        return sorted(set(queries) & PARAMS.keys())
    if not isinstance(queries, list):
        return []
    names = [q if isinstance(q, str) else q.get("name") if isinstance(q, dict) else None for q in queries]
    return sorted(q for q in set(names) if isinstance(q, str) and q in PARAMS)


def tool(names):
    props = {"name": {"type": "string", "enum": names}}
    for name in ("item_type", "kind", "type"):
        props[name] = {"type": "string"}
    for name in ("id", "x", "y", "z", "z2"):
        props[name] = {"type": "integer"}
    props["limit"] = {"type": "integer", "minimum": 1, "maximum": 1000}
    props["radius"] = {"type": "integer", "minimum": 1, "maximum": 20}
    return {"type": "function", "function": {
        "name": "inspect_fort", "description": (
            "Read public game facts without advancing time: stocks (item_type/limit), units (kind/id/limit), "
            "jobs, orders, zones (limit), buildings (type/limit), map (x/y/z/radius/z2), or "
            "manager_order_types / workshop_types (no arguments). Omit irrelevant arguments. "
            "Results are bounded; if truncated, use filters/smaller limits. Never an action."),
        "parameters": {"type": "object", "properties": props, "required": ["name"],
                       "additionalProperties": False}}}


def compact(payload):
    result = {"ok": True, "result": payload}
    raw = json.dumps(result, ensure_ascii=False, default=str)
    if len(raw) <= LIMIT:
        return result
    # Explicitly mark a preview; never slice the JSON serialization into invalid JSON.
    totals = {k: payload[k] for k in ("total", "items", "dropped") if isinstance(payload, dict)
              and isinstance(payload.get(k), (int, float, bool))}
    result = {"ok": True, "truncated": True, "totals": totals,
              "notice": "Partial JSON-text preview, not a complete result; narrow the query to inspect more.",
              "preview": raw[:2600]}
    while len(json.dumps(result, ensure_ascii=False)) > LIMIT:
        result["preview"] = result["preview"][:len(result["preview"]) // 2]
    return result


def run(game, args, names):
    name = args.get("name")
    if not isinstance(name, str) or name not in names:
        return {"ok": False, "error_code": "unknown_query", "error": "Query not advertised by /task."}
    params = {k: v for k, v in args.items() if k != "name" and v is not None}
    if params.keys() - PARAMS[name]:
        return {"ok": False, "error_code": "bad_arguments", "error": "Unsupported arguments for this query."}
    for k, v in params.items():
        expected = str if k in ("item_type", "kind", "type") else int
        if not isinstance(v, expected) or isinstance(v, bool):
            return {"ok": False, "error_code": "bad_arguments", "error": f"Invalid type for {k}."}
    try:
        return compact(game.query(name, **params))
    except (HandsOff, GameOver):
        raise
    except GameAPIError as exc:
        return {"ok": False, "error_code": "query_failed", "error": str(exc)[:240]}
