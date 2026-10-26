"""Output schemas (sent to the provider as strict JSON schemas where supported, always enforced locally) and a small
stdlib validator for the subset of JSON Schema they use, plus the semantic checks that bind each role's output to
its inputs (every signal and every prior submission must be addressed; a fatal finding must cite evidence)."""
import json, re


def S(t, **kw):
    return {"type": t, **kw}


def OBJ(props):
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


EVIDENCE = OBJ({"source": S("string", maxLength=300), "line": S(["integer", "null"]),
                "quote": S("string", maxLength=500)})
FINDING = OBJ({
    "id": S("string", maxLength=40),
    "check": {"type": "string", "enum": ["attribution", "fair_play", "contents"]},
    "severity": {"type": "string", "enum": ["fatal", "major", "minor"]},
    "rule": S("string", maxLength=120),
    "title": S("string", maxLength=200),
    "explanation": S("string", maxLength=3000),
    "evidence": S("array", items=EVIDENCE, maxItems=12),
})
SIGNAL_REVIEW = OBJ({"signal_id": S("string", maxLength=20),
                     "disposition": {"type": "string", "enum": ["benign", "concern", "fatal"]},
                     "reason": S("string", maxLength=1000)})
_BASE = {
    "assessment": {"type": "string", "enum": ["clean", "concerns", "cannot_assess"]},
    "summary": S("string", maxLength=3000),
    "findings": S("array", items=FINDING, maxItems=30),
    "signal_reviews": S("array", items=SIGNAL_REVIEW, maxItems=120),
    "injection_observed": S("boolean"),
}
INHERITANCE = OBJ({"context_id": S("string", maxLength=80),
                   "used": {"type": "string", "enum": ["yes", "no", "unclear"]},
                   "what": S("string", maxLength=1500)})

REVIEWER_SCHEMAS = {
    "attribution": OBJ({**_BASE, "inheritance": S("array", items=INHERITANCE, maxItems=40),
                        "note_states_changes": {"type": "string", "enum": ["yes", "partly", "no"]}}),
    "fair_play": OBJ(dict(_BASE)),
    "contents": OBJ(dict(_BASE)),
}
DEFENDER_SCHEMA = OBJ({"defenses": S("array", maxItems=60, items=OBJ({
    "finding_id": S("string", maxLength=60), "argument": S("string", maxLength=3000),
    "evidence": S("array", items=EVIDENCE, maxItems=12), "concedes": S("boolean")}))})
ADJUDICATOR_SCHEMA = OBJ({"summary": S("string", maxLength=3000), "rulings": S("array", maxItems=60, items=OBJ({
    "finding_id": S("string", maxLength=60),
    "ruling": {"type": "string", "enum": ["confirmed", "dismissed", "unresolved"]},
    "residual_severity": {"type": "string", "enum": ["none", "minor", "major"]},
    "reason": S("string", maxLength=3000),
    "evidence": S("array", items=EVIDENCE, maxItems=12)}))})


class SchemaError(Exception):
    pass


_TYPES = {"string": str, "boolean": bool, "object": dict, "array": list, "null": type(None)}


def _is(v, t):
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, _TYPES[t])


def validate(v, sch, path="$"):
    ts = sch.get("type")
    if ts is not None:
        ts = ts if isinstance(ts, list) else [ts]
        if not any(_is(v, t) for t in ts):
            raise SchemaError(f"{path}: expected {'/'.join(ts)}")
    if "enum" in sch and v not in sch["enum"]:
        raise SchemaError(f"{path}: {str(v)[:40]!r} not one of {sch['enum']}")
    if isinstance(v, str) and len(v) > sch.get("maxLength", 1 << 30):
        raise SchemaError(f"{path}: longer than {sch['maxLength']}")
    if isinstance(v, list):
        if len(v) > sch.get("maxItems", 1 << 30):
            raise SchemaError(f"{path}: more than {sch['maxItems']} items")
        for i, x in enumerate(v):
            validate(x, sch.get("items", {}), f"{path}[{i}]")
    if isinstance(v, dict):
        props = sch.get("properties", {})
        for k in sch.get("required", []):
            if k not in v:
                raise SchemaError(f"{path}: missing {k}")
        if sch.get("additionalProperties") is False:
            extra = [k for k in v if k not in props]
            if extra:
                raise SchemaError(f"{path}: unexpected field(s) {', '.join(map(str, extra))[:80]}")
        for k, x in v.items():
            if k in props:
                validate(x, props[k], f"{path}.{k}")


def _no_dupes(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise SchemaError(f"duplicate key {k!r}")
        d[k] = v
    return d


def parse_json(text):
    """Exactly one JSON object; tolerate a single ```json fence (some providers add one) but nothing else."""
    t = (text or "").strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", t, re.S)
    if m:
        t = m.group(1)
    try:
        v = json.loads(t, object_pairs_hook=_no_dupes, parse_constant=lambda c: (_ for _ in ()).throw(
            SchemaError(f"non-finite number {c}")))
    except SchemaError:
        raise
    except ValueError as e:
        raise SchemaError(f"not valid JSON ({e.msg} at {e.pos})")
    if not isinstance(v, dict):
        raise SchemaError("top level is not an object")
    return v


# ------------------------------------------------------------------------------------------ semantic checks

def _source_ok(src, known):
    s = (src or "").strip()
    if not s:
        return False
    if s in known:
        return True
    p = re.sub(r":\d+(?:-\d+)?$", "", s)
    if p in known:
        return True
    return any(s.startswith(k + ":") or s.startswith(k + "/") for k in known if k.startswith("context:"))


def check_reviewer(role, out, meta):
    """meta: signal_ids (required for fair_play), context_ids (required for attribution), known_sources."""
    known = meta["known_sources"]
    ids = [f["id"] for f in out["findings"]]
    if len(set(ids)) != len(ids):
        raise SchemaError("finding ids are not unique")
    for f in out["findings"]:
        if f["severity"] in ("fatal", "major"):
            if not f["evidence"]:
                raise SchemaError(f"finding {f['id']}: a {f['severity']} finding needs cited evidence")
            if not any(_source_ok(e["source"], known) for e in f["evidence"]):
                raise SchemaError(f"finding {f['id']}: no evidence cites a file of the submission, the NOTE, "
                                  "dependencies.json or a context submission (cite path:line)")
    serious = [f for f in out["findings"] if f["severity"] in ("fatal", "major")]
    if out["assessment"] == "clean" and serious:
        raise SchemaError("assessment is clean but there are fatal/major findings")
    if out["assessment"] == "concerns" and not out["findings"]:
        raise SchemaError("assessment is concerns but there are no findings")
    want = meta.get("signal_ids") or []
    got = [r["signal_id"] for r in out["signal_reviews"]]
    if want:
        missing = [s for s in want if s not in got]
        if missing or len(got) != len(set(got)):
            raise SchemaError(f"signal_reviews must address each listed signal exactly once; missing "
                              f"{', '.join(missing[:20]) or '(duplicates)'}")
    if any(r["disposition"] == "fatal" for r in out["signal_reviews"]) and not any(
            f["severity"] == "fatal" for f in out["findings"]):
        raise SchemaError("a signal was dispositioned fatal but there is no fatal finding")
    if role == "attribution":
        ctx = meta.get("context_ids") or []
        got = [i["context_id"] for i in out["inheritance"]]
        missing = [c for c in ctx if c not in got]
        if missing:
            raise SchemaError(f"inheritance must cover every context submission; missing {', '.join(missing[:20])}")
        declared = set(meta.get("declared_ids") or [])
        for i in out["inheritance"]:
            if i["used"] == "yes" and i["context_id"] not in declared and not any(
                    f["severity"] == "fatal" and f["check"] == "attribution" for f in out["findings"]):
                raise SchemaError(f"context {i['context_id']} is used and undeclared but there is no fatal "
                                  "attribution finding")
        if out["note_states_changes"] == "no" and not serious:
            raise SchemaError("note_states_changes is no but there is no fatal/major finding")


def check_cover(items, key, fatal_ids, what):
    got = [x[key] for x in items]
    if sorted(got) != sorted(fatal_ids):
        miss = sorted(set(fatal_ids) - set(got))
        extra = sorted(set(got) - set(fatal_ids))
        raise SchemaError(f"{what} must cover each challenged finding exactly once (missing {miss[:10]}, "
                          f"unexpected or duplicated {extra[:10] or [g for g in got if got.count(g) > 1][:10]})")
