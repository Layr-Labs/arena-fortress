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
CATALOGUES = {
    "manager_order_types": {"job_types", "reactions", "material_categories", "condition_flags",
                            "item_types", "recipes", "when_stocks"},
    "workshop_types": {"workshop_types"},
}
SELECTORS = {"section", "search", "offset", "limit"}


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
    props["section"] = {"type": "string", "enum": sorted(set.union(*CATALOGUES.values()))}
    props["search"] = {"type": "string", "maxLength": 160}
    props["offset"] = {"type": "integer", "minimum": 0}
    return {"type": "function", "function": {
        "name": "inspect_fort", "description": (
            "Read public game facts without advancing time: stocks (item_type/limit), units (kind/id/limit), "
            "jobs, orders, zones (limit), buildings (type/limit), map (x/y/z/radius/z2), or "
            "manager_order_types / workshop_types. For catalogues, omit section to list section sizes; then "
            "select section and optional case-insensitive search, offset (default 0), limit (1-50, default 10). "
            "Follow next_offset until null. Catalogue selectors are local, not API arguments. "
            "Omit irrelevant arguments. Other results are bounded previews: use filters/smaller limits. Never an action."),
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


def catalogue(payload, name, args):
    """Page complete public entries; a raw prefix can hide every job and reaction behind the flags."""
    body = payload.get("result", payload) if isinstance(payload, dict) else None
    if not isinstance(body, dict) or payload.get("ok") is False or body.get("ok") is False:
        return {"ok": False, "error_code": "query_failed", "error": "Catalogue query returned an error or non-object."}
    sections = {k: len(v) for k, v in body.items() if k in CATALOGUES[name] and isinstance(v, (list, dict))}
    section = args.get("section")
    if section is None:
        return {"ok": True, "result": {"query": name, "sections": sections,
                "notice": "Select a section; optional search filters entries. Follow next_offset until null."}}
    if section not in sections:
        return {"ok": False, "error_code": "bad_arguments", "error": "Section not present in this catalogue."}
    values = body[section]
    entries = [{"key": k, "value": v} for k, v in values.items()] if isinstance(values, dict) else values
    search = args.get("search", "").casefold()
    matches = [e for e in entries if search in json.dumps(e, ensure_ascii=False).casefold()]
    offset = args.get("offset", 0)
    page = {"query": name, "section": section, "total": len(entries), "matches": len(matches),
            "offset": offset, "entries": matches[offset:offset + args.get("limit", 10)]}
    result = {"ok": True, "result": page}
    while True:
        end = offset + len(page["entries"])
        page["next_offset"] = end if end < len(matches) else None
        if len(json.dumps(result, ensure_ascii=False)) <= LIMIT:
            return result
        if len(page["entries"]) <= 1:
            return {"ok": False, "error_code": "catalogue_entry_too_large",
                    "error": "One catalogue entry exceeds the result bound; it was not silently truncated.",
                    "section": section, "offset": offset}
        page["entries"] = page["entries"][:-1]


def run(game, args, names):
    name = args.get("name")
    if not isinstance(name, str) or name not in names:
        return {"ok": False, "error_code": "unknown_query", "error": "Query not advertised by /task."}
    params = {k: v for k, v in args.items() if k != "name" and v is not None}
    if name in CATALOGUES:
        section, search = params.get("section"), params.get("search", "")
        if (params.keys() - SELECTORS or
            (section is not None and (not isinstance(section, str) or section not in CATALOGUES[name])) or
            not isinstance(search, str) or len(search) > 160 or
            (section is None and any(k in params for k in ("search", "offset")))):
            return {"ok": False, "error_code": "bad_arguments", "error": "Invalid catalogue selectors; select a section before search/offset."}
        for key, default, low, high in (("offset", 0, 0, None), ("limit", 10, 1, 50)):
            value = params.get(key, default)
            if not isinstance(value, int) or isinstance(value, bool) or value < low or (high and value > high):
                return {"ok": False, "error_code": "bad_arguments", "error": f"Invalid catalogue {key}."}
    else:
        if params.keys() - PARAMS[name]:
            return {"ok": False, "error_code": "bad_arguments", "error": "Unsupported arguments for this query."}
        for k, v in params.items():
            expected = str if k in ("item_type", "kind", "type") else int
            if not isinstance(v, expected) or isinstance(v, bool):
                return {"ok": False, "error_code": "bad_arguments", "error": f"Invalid type for {k}."}
    try:
        payload = game.query(name, **({} if name in CATALOGUES else params))
        return catalogue(payload, name, params) if name in CATALOGUES else compact(payload)
    except (HandsOff, GameOver):
        raise
    except GameAPIError as exc:
        return {"ok": False, "error_code": "query_failed", "error": str(exc)[:240]}
