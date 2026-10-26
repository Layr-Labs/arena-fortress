#!/usr/bin/env python3
"""Exact model requests and responses, stored content-addressed (docs/HARNESS-PLAN.md 0.2, BENCHMARK-v1.md §5.3).

The step log (<arm>-<k>.jsonl) keeps the tool call and its result, but not what the model saw. For SFT and for
debugging a decision, each model2 call also records `prompt_ref`: the sha256 of each message, of the tools and of
the request settings, stored once each under <out>/prompts/<sha[:2]>/<sha>.json. Messages repeat across calls
(the 12-message window slides), so this costs ~1 observation per decision, not a full prompt.
`response_ref` stores the full assistant message as returned, including any reasoning the provider sent.

  python3 bench/prompts.py show <run dir> <step index>   # print the request of one step as JSON
  python3 bench/prompts.py stats <run dir>                # calls with refs, unique objects, bytes
stdlib only.
"""
import hashlib, json, os, sys


class Store:
    def __init__(self, root):
        self.root = root

    def put(self, obj):
        b = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        h = hashlib.sha256(b).hexdigest()
        p = os.path.join(self.root, h[:2], h + ".json")
        if not os.path.exists(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "wb") as f:
                f.write(b)
            os.replace(tmp, p)
        return h

    def get(self, h):
        return json.load(open(os.path.join(self.root, h[:2], h + ".json")))

    def request(self, model, messages, tools, settings):
        """-> refs for one request: {"model", "messages": [sha...], "tools": sha, "settings": sha}"""
        return {"model": model, "messages": [self.put(m) for m in messages], "tools": self.put(tools),
                "settings": self.put(settings)}

    def rebuild(self, ref):
        """refs -> the request body as sent (before endpoint-specific fields like `provider` were added)."""
        return {"model": ref["model"], "messages": [self.get(h) for h in ref["messages"]],
                "tools": self.get(ref["tools"]), **self.get(ref["settings"])}


def _steps(run_dir):
    logs = [f for f in sorted(os.listdir(run_dir)) if f.endswith(".jsonl") and f != "summary.jsonl"]
    for f in logs:
        for i, line in enumerate(open(os.path.join(run_dir, f))):
            yield f, i, json.loads(line)


def _store_for(run_dir):
    for d in (run_dir, os.path.dirname(os.path.normpath(run_dir))):
        if os.path.isdir(os.path.join(d, "prompts")):
            return Store(os.path.join(d, "prompts"))
    sys.exit(f"no prompts/ dir in {run_dir} or its parent")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("show", "stats"):
        sys.exit(__doc__)
    run_dir = sys.argv[2]
    st = _store_for(run_dir)
    if sys.argv[1] == "show":
        want = int(sys.argv[3])
        for f, i, rec in _steps(run_dir):
            if i == want and rec.get("prompt_ref"):
                out = {"step_log": f, "i": i, "request": st.rebuild(rec["prompt_ref"])}
                if rec.get("response_ref"):
                    out["response"] = st.get(rec["response_ref"])
                print(json.dumps(out, indent=1, ensure_ascii=False))
                break
        else:
            sys.exit(f"no step {want} with a prompt_ref")
    else:
        n = sum(1 for _, _, rec in _steps(run_dir) if rec.get("prompt_ref"))
        files = [os.path.join(d, f) for d, _, fs in os.walk(st.root) for f in fs]
        print(f"{n} calls with prompt_ref; {len(files)} stored objects; {sum(map(os.path.getsize, files)) / 1e6:.2f} MB")
