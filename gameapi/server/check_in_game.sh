#!/bin/bash
# In-game smoke test of the game server (results: gameapi/server/IN_GAME.md). Needs the image:
#   docker/Dockerfile then docker/Dockerfile.game (tag yukon-df:s0server-game, or IMAGE=...).
#
#   gameapi/server/check_in_game.sh [OUT]          # default runs/s0server-check
#
# 1. start-year, 10 days: drive the API with curl (task, observe, queries, events, a few acts, advances with and
#    without stop_on, a K overflow), then POST /finish (the harness "exits"), and score the artifacts with
#    bench/outcomes.py. Then smoke.py --only noop for the same 10 days in the same container: the reference row
#    and files the v3 artifacts are compared with field by field.
# 2. lt01-drought (hands-off window from day 39): advance to A, the server runs W, then bench/predicates.py LT01.
# One container at a time (s0server-check), --memory 2500m; removed at the end.
set -u
cd "$(dirname "$0")/../.."
OUT=${1:-runs/s0server-check}
IMAGE=${IMAGE:-yukon-df:s0server-game}
NAME=s0server-check
PORT=${PORT:-18090}
TOKEN=check-$$
URL=http://127.0.0.1:$PORT
mkdir -p "$OUT"
LOG=$OUT/check.log
[ "${PARTS:-12}" = 12 ] && : > "$LOG"
say() { echo "$*" | tee -a "$LOG"; }
c() { local m=$1 p=$2 d=${3:-}; say "> $m $p $d";
      if [ -n "$d" ]; then curl -s -X "$m" -H "X-Admin-Token: $TOKEN" "$URL$p" -d "$d"; else curl -s -X "$m" -H "X-Admin-Token: $TOKEN" "$URL$p"; fi \
        | tee -a "$LOG" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("  ", json.dumps({k: d[k] for k in ("day","tick","days_left","game_over","hands_off_in_days","ok","error_code","error","actions_left_today","result","phase","end_reason") if k in d})[:400])' | tee -a "$LOG"; echo >> "$LOG"; }

start() {   # $1 task, $2 extra env (space-separated KEY=VAL)
  docker rm -f $NAME >/dev/null 2>&1
  local envs=()
  for kv in $2; do envs+=(-e "$kv"); done
  docker run -d --init --name $NAME --platform linux/amd64 --security-opt seccomp=unconfined --memory 2500m --memory-swap 2500m \
    -p 127.0.0.1:$PORT:8090 -e GAMEAPI_TASK="$1" -e GAMEAPI_ADMIN_TOKEN=$TOKEN ${envs[@]+"${envs[@]}"} "$IMAGE" >/dev/null || exit 1
  local t0=$(date +%s)
  until curl -sf "$URL/task" -o /dev/null; do
    sleep 3
    ph=$(curl -s "$URL/health" | python3 -c 'import json,sys; print(json.load(sys.stdin)["phase"])' 2>/dev/null)
    [ "$ph" = failed ] && { say "start failed"; curl -s "$URL/health" | tee -a "$LOG"; docker logs $NAME | tail -20; exit 1; }
    [ $(( $(date +%s) - t0 )) -gt 600 ] && { say "not ready after 600 s"; docker logs $NAME | tail -20; exit 1; }
  done
  say "ready after $(( $(date +%s) - t0 )) s: $1"
}

wait_final() {
  for i in $(seq 1 400); do
    ph=$(curl -s "$URL/health" | python3 -c 'import json,sys; print(json.load(sys.stdin)["phase"])' 2>/dev/null)
    [ "$ph" = finalized ] && return 0
    sleep 3
  done
  say "never finalized"; return 1
}

collect() {   # $1 subdir
  rm -rf "$OUT/$1"; mkdir -p "$OUT/$1"
  docker cp $NAME:/root/dfprobe/runs/game/. "$OUT/$1/"
}

PARTS=${PARTS:-12}   # PARTS=2: only the lab task (and the scoring of whatever OUT holds)
# ---------------------------------------------------------------- 1. start-year, 10 days
if [[ $PARTS == *1* ]]; then
start scenarios/start-year.json "GAMEAPI_DAYS=10"
curl -s "$URL/task" > "$OUT/task.json"
python3 -c 'import json,sys; t=json.load(open(sys.argv[1])); print("tools:", [x["function"]["name"] for x in t["tools"]]); print("rules:", t["rules"]["actions_per_game_day"], t["rules"]["max_advance_days"], t["rules"]["wall_s"]); print("key:", t["key"])' "$OUT/task.json" | tee -a "$LOG"
c GET /observe
curl -s "$URL/observe" > "$OUT/observe.json"
c GET /query/stocks
c GET /query/workshop_types
c GET /query/nope
c GET "/query/units?limit=3"
c GET "/events?since_tick=0"
c POST /act '{"tool": "appoint_manager", "args": {}}'
c POST /act '{"tool": "enable_automation", "args": {"name": "autochop"}}'
c POST /act '{"tool": "add_order", "args": {"recipe": "brew_drink", "amount": 2}}'
c POST /act '{"tool": "cancel_order", "args": {"order_id": 999999}}'
c POST /act '{"tool": "dig_room", "args": {"site": "R999"}}'
c POST /act '{"tool": "slaughter", "args": {"unit_id": 1}}'
c POST /act '{"tool": "no_such_tool", "args": {}}'
c POST /act '{"tool": "advance_days", "args": {"days": 29}}'
c POST /act '{"tool": "advance_days", "args": {"days": 2, "stop_on": []}}'
c POST /act '{"tool": "advance_days", "args": {"days": 1, "stop_on": ["hostile_visible", "announcement:STRANGE_MOOD"]}}'
# K overflow: 40 actions on day 3, then the 41st is refused
say "> 40 x cancel_order (K overflow)"
for i in $(seq 1 40); do curl -s -X POST "$URL/act" -d '{"tool": "cancel_order", "args": {"order_id": 999999}}' > /dev/null; done
c POST /act '{"tool": "cancel_order", "args": {"order_id": 999999}}'
c POST /act '{"tool": "advance_days", "args": {"days": 3}}'
c POST /act '{"tool": "cancel_order", "args": {"order_id": 999999}}'
c POST /finish '{"reason": "harness_exited"}'
wait_final && c GET /health
collect start-year
# the reference: the frozen loop's noop row for the same task and horizon, in the same image
docker exec $NAME bash -c 'cd /root/dfprobe && python3 smoke.py --only noop --runs 1 --days 10 --scenario scenarios/start-year.json --out runs/ref' > "$OUT/ref.stdout" 2>&1
rm -rf "$OUT/ref"; mkdir -p "$OUT/ref"; docker cp $NAME:/root/dfprobe/runs/ref/. "$OUT/ref/"
docker rm -f $NAME >/dev/null
fi

# ---------------------------------------------------------------- 2. lt01-drought, hands-off
if [[ $PARTS == *2* ]]; then
start scenarios/lt01-drought.json ""
c GET /task
c POST /act '{"tool": "add_order", "args": {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [{"stock": "drink", "below": 100}]}}'
c POST /act '{"tool": "advance_days", "args": {"days": 28}}'
c POST /act '{"tool": "advance_days", "args": {"days": 28}}'
c POST /act '{"tool": "add_order", "args": {"recipe": "brew_drink", "amount": 1}}'
wait_final && c GET /health
collect lt01
docker rm -f $NAME >/dev/null
fi

# ---------------------------------------------------------------- scoring and the field comparison
say "== outcomes"
python3 bench/outcomes.py "$OUT/start-year" "$OUT/ref" "$OUT/lt01" 2>&1 | tee -a "$LOG"
say "== predicates LT01"
python3 bench/predicates.py LT01 "$OUT/lt01" 2>&1 | tee -a "$LOG"
say "== artifact fields vs the frozen loop (smoke.py noop)"
python3 - "$OUT" <<'PY' 2>&1 | tee -a "$LOG"
import json, os, sys
out = sys.argv[1]
v3 = json.loads(open(os.path.join(out, "start-year", "summary.jsonl")).read().splitlines()[-1])
ref = json.loads(open(os.path.join(out, "ref", "summary.jsonl")).read().splitlines()[-1])
print("summary: fields only in the frozen row:", sorted(set(ref) - set(v3)))
print("summary: fields only in the v3 row:", sorted(set(v3) - set(ref)))
same = [k for k in ref if k in v3 and type(ref[k]) is not type(v3[k]) and ref[k] is not None and v3[k] is not None]
print("summary: fields whose type differs:", same)
for ext in ("daily.json", "credit.json", "final.json"):
    a = json.load(open(os.path.join(out, "start-year", "harness-0." + ext)))
    b = json.load(open(os.path.join(out, "ref", "noop-0." + ext)))
    print(f"{ext}: top-level keys equal: {sorted(a) == sorted(b)}", "" if sorted(a) == sorted(b) else (sorted(set(a) ^ set(b))))
    if ext == "daily.json":
        sa, sb = a.get("samples") or [], b.get("samples") or []
        print(f"  samples {len(sa)} vs {len(sb)}; sample keys equal: {sorted(sa[0]) == sorted(sb[0]) if sa and sb else None}")
for k in ("days_played", "pop_start", "pop_final", "food_min", "drink_min", "days_sampled", "credited_value_final",
          "citizen_deaths", "wall_capped", "actions_used", "actions_rejected", "end_reason", "finish_reason", "cap_hit_day"):
    print(f"  {k}: v3={v3.get(k)!r} frozen={ref.get(k)!r}")
PY
say "done: $OUT"
