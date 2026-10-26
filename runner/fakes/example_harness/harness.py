#!/usr/bin/env python3
"""A tiny example harness (the submission side of docs/GAME-API.md §2): reads DFBENCH_TASK, gets the tools from
GET /task, then loops observe -> one model call (tools offered) -> act each tool call -> until the game is over.
If the gateway refuses (credits spent) or keeps failing, it exits; the server then runs the fort on to the horizon.
stdlib only. Not a policy worth anything: it is the runner's end-to-end test harness.
"""
import json, os, sys, time, urllib.error, urllib.request


def http(method, url, body=None, headers=None, timeout=600):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def main():
    task = json.loads(os.environ["DFBENCH_TASK"])
    game, model = task["game_url"].rstrip("/"), task["model"]
    _, t = http("GET", game + "/task")
    tools = t["tools"]
    msgs = [{"role": "system", "content": "You run a Dwarf Fortress fort through tools.\n" + t.get("manual", "")},
            {"role": "user", "content": json.dumps(task["task"])}]
    failures = 0
    while True:
        _, obs = http("GET", game + "/observe")
        if obs.get("game_over"):
            print("game over at day", obs.get("day"), flush=True)
            return 0
        msgs = msgs[:2] + [{"role": "user", "content": "OBSERVATION " + json.dumps(obs)}]
        code, r = http("POST", model["base_url"].rstrip("/") + "/chat/completions",
                       {"model": model["name"], "messages": msgs, "tools": tools},
                       {"Authorization": "Bearer " + model.get("api_key", "placeholder")})
        if code in (402, 503):     # budget_exhausted, or gateway_blocked (fail closed)
            print("credits spent or gateway blocked; exiting so the server runs the fort on", flush=True)
            return 0
        if code != 200:
            failures += 1
            print("model call failed", code, r, file=sys.stderr, flush=True)
            if failures >= 5:
                return 1
            time.sleep(1)
            continue
        failures = 0
        calls = (r["choices"][0]["message"].get("tool_calls") or [])
        if not calls:
            calls = [{"function": {"name": "advance_days", "arguments": json.dumps({"days": 1})}}]
        for c in calls:
            f = c["function"]
            try:
                args = json.loads(f.get("arguments") or "{}")
            except ValueError:
                args = {}
            _, res = http("POST", game + "/act", {"tool": f["name"], "args": args})
            print(json.dumps({"day": res.get("day"), "tool": f["name"], "ok": res.get("ok"),
                              "error_code": res.get("error_code")}), flush=True)
            if res.get("error_code") == "action_limit":
                http("POST", game + "/act", {"tool": "advance_days", "args": {"days": 1}})


if __name__ == "__main__":
    sys.exit(main())
