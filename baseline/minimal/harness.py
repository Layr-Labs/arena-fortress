#!/usr/bin/env python3
"""A minimal harness for the DF harness challenge: the contract and nothing else (docs/GAME-API.md).

observe -> ask the model for one tool call -> act -> repeat; advance a day whenever the model doesn't, so game time
always moves. No status, no hints, no memory beyond the last few messages. stdlib only, one file.
It is an API demo, not a starting point: the plain baseline (`submission/`) is the one to build on. It sends only the
tool schemas and a one-line instruction (not the served manual), and stops calling the model at 90% of the game's
credits (GET /status on the gateway).
Input: DFBENCH_TASK (JSON). Network: the game API (task.game_url) and the gateway (task.model.base_url) only.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

TASK = json.loads(os.environ["DFBENCH_TASK"])
GAME = TASK["game_url"].rstrip("/")
MODEL = TASK["model"]


def http(url, body=None, timeout=900):
    """GET (body None) or POST JSON; returns the JSON reply. The game API puts errors in a JSON body, so an HTTP
    error with a JSON body is returned too. Connection errors are retried a few times (the server may restart)."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + MODEL.get("api_key", "placeholder")}
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read())
            except ValueError:
                raise RuntimeError(f"{url}: HTTP {e.code}") from None
        except urllib.error.URLError:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{url}: unreachable")


def chat(body):
    """One model call through the gateway. A 504 upstream_timeout (the provider hung; the gateway charged an
    estimate) or an unreachable provider is retried a few times with backoff; anything else is returned as is."""
    for attempt in range(4):
        reply = http(MODEL["base_url"].rstrip("/") + "/chat/completions", body)
        code = (reply.get("error") or {}).get("code") if isinstance(reply.get("error"), dict) else None
        if code not in ("upstream_timeout", "upstream_unreachable") or attempt == 3:
            return reply
        time.sleep(2 * 2 ** attempt)


def credits_nearly_spent(share=0.9):
    """True once the gateway's GET /status says this game has used `share` of its credits."""
    try:
        st = http(MODEL["base_url"].rstrip("/").removesuffix("/v1") + "/status", timeout=10)
        return float(st.get("spent_usd") or 0) >= share * float(st.get("budget_usd") or float("inf"))
    except Exception:
        return False


def act(tool, args):
    return http(GAME + "/act", {"tool": tool, "args": args})


def main():
    task = http(GAME + "/task")
    system = ("You manage a Dwarf Fortress fortress through the tools. Call exactly one tool per turn; "
              "advance_days lets time pass.")
    history = []
    while True:
        obs = http(GAME + "/observe")
        if obs.get("game_over") or credits_nearly_spent():
            break                                # the server runs the rest of the game unmanaged
        history.append({"role": "user", "content": "OBSERVATION " + json.dumps(obs, separators=(",", ":"))})
        history = history[-6:]
        while history and history[0]["role"] != "user":   # never start the window with a tool result
            history.pop(0)
        reply = chat({"model": MODEL["name"], "messages": [{"role": "system", "content": system}, *history],
                      "tools": task["tools"], "tool_choice": "required", "temperature": 0, "max_tokens": 4000})
        if not reply.get("choices"):            # the gateway refused (credits used up?) or the provider failed
            print(json.dumps({"model_error": reply})[:500], flush=True)
            if any(w in json.dumps(reply).lower() for w in ("budget", "credit", "gateway_blocked")):
                break                            # the server runs the rest of the game unmanaged
            r = act("advance_days", {"days": 1})
            if r.get("game_over") or r.get("error_code") in ("game_over", "hands_off"):
                break
            continue
        msg = reply["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        history.append({k: msg[k] for k in ("role", "content", "tool_calls") if k in msg})
        code = None
        for i, call in enumerate(calls):
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            r = act(name, args) if i == 0 else {"ok": False, "error": "one tool call per turn"}
            print(json.dumps({"day": r.get("day"), "tool": name, "args": args, "ok": r.get("ok"),
                              "error_code": r.get("error_code")}), flush=True)
            history.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(r)[:2000]})
            code = code or r.get("error_code")
        if code in ("game_over", "hands_off"):
            break
        if not calls or calls[0]["function"]["name"] != "advance_days":
            r = act("advance_days", {"days": 1})    # keep game time moving
            if r.get("game_over") or r.get("error_code") in ("game_over", "hands_off"):
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
