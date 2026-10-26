#!/bin/bash
# pool/fort_in_container.sh: build ONE pool fort from a seed inside the DF image (run by `pool/dfpool build` through
# `docker exec`; the host copies this file into the container, so the image doesn't need to contain pool/).
#
#   bash fort_in_container.sh task_fort <recipe> <seed> --rules R.json --out /tmp/fort --keep-embark /tmp/embark
#   bash fort_in_container.sh embark    -        <seed> --rules R.json --out /tmp/fort
#   bash fort_in_container.sh my1       -        <seed> --rules R.json --out /tmp/fort --keep-embark /tmp/embark
#                                       [--day 120] [--arm automation] [--run-seed 12345] [--min-pop 7]
#                                       [--min-drink-days 60] [--min-food-days 60] [--drink-rate 0.07] [--food-rate 0.10]
#
# kinds:
#   task_fort  embark/make_task_fort.sh <recipe> <seed> (embark + recipe + check + save; docs/SEED-FORTS.md)
#   embark     embark/make_embark.sh: the fresh 7-dwarf "Play now!" fort (OP1's start)
#   my1        the embark, then <arm> plays it for <day> days with [ARTIFACTS:NO] (the season-0 run-time setting) and
#              a quicksave at day <day> (smoke.py --snapshot-days); the save is the MY1 start (hand-over happens at run
#              time: scenarios/lua/handover.lua, scenarios/lua/trim_stocks.lua). Not reproducible run to run (DF's
#              simulation), so the pool builds it once and identifies it by world.sav's bytes (bench/key.py).
# Env: EMBARK_SEED_IN_PARAMS=1 (full seed in the param set; the private pool always sets it), EMBARK_CPU.
# Exit: 0 built (last line "POOLFORT ..."); 3 the seed is rejected by the rules (last line "REJECT <reason>"; the pool
# takes its next candidate); anything else is an infrastructure failure (the pool stops; the seed is NOT skipped).
set -u
KIND=${1:-}; RECIPE=${2:-}; SEED=${3:-}; shift 3 2>/dev/null || { echo "usage: see header"; exit 2; }
RULES=embark/rules/TEMPERATE_SOIL.json; OUT=; KEEP=; DAY=120; ARM=automation; RUNSEED=12345; MINPOP=7
MIN_DRINK_DAYS=60; MIN_FOOD_DAYS=60; DRINK_RATE=0.07; FOOD_RATE=0.10
while [ $# -gt 0 ]; do
  case "$1" in
    --rules) RULES=$2; shift 2;; --out) OUT=$2; shift 2;; --keep-embark) KEEP=$2; shift 2;;
    --day) DAY=$2; shift 2;; --arm) ARM=$2; shift 2;; --run-seed) RUNSEED=$2; shift 2;; --min-pop) MINPOP=$2; shift 2;;
    --min-drink-days) MIN_DRINK_DAYS=$2; shift 2;; --min-food-days) MIN_FOOD_DAYS=$2; shift 2;;
    --drink-rate) DRINK_RATE=$2; shift 2;; --food-rate) FOOD_RATE=$2; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
[ -n "$OUT" ] || { echo "--out is required"; exit 2; }
cd /root/dfprobe || exit 1
mkdir -p df/save
LOG=/tmp/poolfort.log; : > "$LOG"

# A rules rejection is a property of the seed (the pool moves on); everything else is infra (the pool stops).
reject_or_fail() {   # $1 = log file
  local why
  why=$(grep -aoE 'no world tile passes the region rules|no candidate accepted in [0-9]+ tried|doesn.t match [^ ]+ expect|BUILD-FAIL population[^"]*' "$1" | tail -1)
  if [ -n "$why" ]; then echo "REJECT $why"; exit 3; fi
  tail -5 "$1"; echo "INFRA: build failed (see the log)"; exit 1
}

embark() {   # $1 = out dir
  embark/make_embark.sh --seed "$SEED" --rules "$RULES" --out "$1" >> "$LOG" 2>&1 || reject_or_fail "$LOG"
  tail -1 "$LOG"
}

case "$KIND" in
  task_fort)
    args=(); [ -n "$KEEP" ] && args=(--keep-embark "$KEEP")
    embark/make_task_fort.sh "$RECIPE" "$SEED" --rules "$RULES" --out "$OUT" "${args[@]}" >> "$LOG" 2>&1 \
      || reject_or_fail "$LOG"
    tail -1 "$LOG"
    ;;
  embark)
    embark "$OUT"
    [ -n "$KEEP" ] && { rm -rf "$KEEP"; cp -a "$OUT" "$KEEP"; }
    ;;
  my1)
    E=${KEEP:-/tmp/my1-embark}
    embark "$E"
    # the embark's SNAPSHOT.json has the probe's tick; the save can be a few ticks later (make_task_fort.sh loads with
    # EXPECT_TICK=any for that reason). smoke.py's reset needs the exact tick, so load once and record the real one.
    SRC=/tmp/my1-src; rm -rf "$SRC"; cp -a "$E" "$SRC"
    R=$(EXPECT_TICK=0 SNAPSHOT=$SRC ./reset_fort.sh 2>&1 | tail -1)
    T=$(echo "$R" | grep -oE '(abs_tick=|READY )[0-9]+' | grep -oE '[0-9]+' | head -1)
    [ -n "$T" ] || { echo "$R"; echo "INFRA: could not load the embark"; exit 1; }
    python3 - "$SRC/SNAPSHOT.json" "$T" <<'PY'
import json, sys
p, t = sys.argv[1], int(sys.argv[2]); s = json.load(open(p)); s["abs_tick"] = t; json.dump(s, open(p, "w"), indent=1)
PY
    # season-0 run-time setting: strange moods off (docs/HARNESS-CHALLENGE.md D11), so no mood is running at hand-over
    sed -i 's/\[ARTIFACTS:[A-Z]*\]/[ARTIFACTS:NO]/' df/prefs/d_init.txt
    python3 - "$SRC" "$DAY" > /tmp/my1-src.json <<'PY'
import json, sys
print(json.dumps({"name": "my1-pool-source", "snapshot": sys.argv[1], "setup": [], "days": int(sys.argv[2]),
                  "description": "pool/fort_in_container.sh: the MY1 pool's source run (an arm plays the embark)"}))
PY
    RUN=/tmp/my1-run; rm -rf "$RUN"
    TS=$(date +%s)
    python3 smoke.py --arms "$ARM" --runs 1 --k-start 0 --seed "$RUNSEED" --scenario /tmp/my1-src.json \
      --days "$DAY" --snapshot-days "$DAY" --out "$RUN" >> "$LOG" 2>&1 || { tail -5 "$LOG"; echo "INFRA: smoke.py"; exit 1; }
    PLAY_S=$(( $(date +%s) - TS ))
    D="$RUN/snapshots/$ARM-0-d$DAY"
    [ -f "$D/SNAPSHOT.json" ] && [ -f "$D/world.sav" ] || { echo "INFRA: no day-$DAY snapshot in $RUN"; exit 1; }
    rm -rf "$OUT"; cp -a "$D" "$OUT"
    # SNAPSHOT.json: no top-level `embark` block, so bench/key.py identifies the fort by world.sav's bytes (it isn't
    # reproducible); the source embark's id is kept under my1.source_embark for `dfpool verify`
    python3 - "$OUT" "$E/SNAPSHOT.json" "$RUN" "$ARM" "$DAY" "$RUNSEED" "$PLAY_S" "$MINPOP" "$MIN_DRINK_DAYS" \
      "$MIN_FOOD_DAYS" "$DRINK_RATE" "$FOOD_RATE" <<'PY'
import glob, hashlib, json, os, sys
out, emb, run, arm, day, rseed, play_s, minpop, mdd, mfd, dr, fr = sys.argv[1:]
s = json.load(open(os.path.join(out, "SNAPSHOT.json")))
e = json.load(open(emb))
rows = [json.loads(l) for f in glob.glob(os.path.join(run, "**", "summary.jsonl"), recursive=True)
        for l in open(f) if l.strip()]
r = rows[-1] if rows else {}
s.update({"world_name": e["world_name"], "fort_name": e["fort_name"], "source": "pool/fort_in_container.sh my1",
          "license": "terms-unclear",
          "my1": {"version": 1, "arm": arm, "day": int(day), "run_seed": int(rseed), "k": 0, "play_s": int(play_s),
                  "source_embark": e["embark"], "source_abs_tick": e["abs_tick"],
                  "world_sav_sha256": hashlib.sha256(open(os.path.join(out, "world.sav"), "rb").read()).hexdigest(),
                  "at_day": {k: r.get(k) for k in ("pop_start", "pop_final", "drink_final", "food_final",
                                                   "citizen_deaths", "crashed", "survived_horizon")}}})
json.dump(s, open(os.path.join(out, "SNAPSHOT.json"), "w"), indent=1)
a = s["my1"]["at_day"]
pop = a.get("pop_final") or s.get("citizens") or 0
why = []
if a.get("crashed"): why.append(f"crashed {a['crashed']}")
if (a.get("citizen_deaths") or 0) > 0: why.append(f"{a['citizen_deaths']} deaths by day {day}")
if pop < int(minpop): why.append(f"population {pop} < {minpop}")
# the lean hand-over trims to N days of stock: the fort must hold at least that much, else there is nothing to trim
if (a.get("drink_final") or 0) < pop * float(dr) * int(mdd): why.append(f"drink {a.get('drink_final')} < {mdd} days for {pop}")
if (a.get("food_final") or 0) < pop * float(fr) * int(mfd): why.append(f"food {a.get('food_final')} < {mfd} days for {pop}")
open("/tmp/my1-accept", "w").write("; ".join(why))
PY
    WHY=$(cat /tmp/my1-accept)
    [ -z "$WHY" ] || { echo "REJECT my1 day-$DAY fort: $WHY"; exit 3; }
    echo "POOLFORT kind=my1 day=$DAY citizens=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["citizens"])' "$OUT/SNAPSHOT.json") play=${PLAY_S}s out=$OUT"
    exit 0
    ;;
  *) echo "unknown kind $KIND"; exit 2;;
esac
echo "POOLFORT kind=$KIND out=$OUT"
