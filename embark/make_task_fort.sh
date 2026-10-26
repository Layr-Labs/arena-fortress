#!/bin/bash
# make_task_fort.sh: a lab task's start fort from a seed, built and checked, saved as a scenario snapshot (no DF save
# is ever shipped: every train, test-public and private start is rebuilt from its seed; docs/SEED-FORTS.md).
#
#   embark/make_task_fort.sh <task|recipe> <seed> --out <dir> [--rules embark/rules/TEMPERATE_SOIL.json]
#                            [--embark <embark snapshot dir>] [--keep-embark <dir>]
#
#   <task|recipe>  a lab task id (LT01, LT02, LT03, LT05, LT08) or a recipe name / path under embark/forts/
#   <seed>         the world seed: train 1000-1999, test-public 2000-2099, test-private 9000+ (maintainers only)
#   --embark       reuse an embark snapshot of this seed (docker/embark.sh output) instead of making one
#   --keep-embark  also copy the fresh embark there (to build several recipes from one embark)
#
# 1. embark/make_embark.sh --seed <seed> --rules <rules> (world gen pinned to one CPU, site rules, "Play now!",
#    fort probe); or load the --embark snapshot. Either way the fresh 7-dwarf fort is loaded and paused.
# 2. embark/build_fort.py <recipe>: migrants, the tool calls the scripted policy makes (completed at once with
#    dig-now / build-now), a few settle days, exact stocks, orders, plugins, stress, caravan report, pending events.
# 3. embark/fort_summary.lua + embark/fort_check.py: the fort must match the recipe's `expect` ranges, else exit 1.
# 4. quicksave; <dir> gets the save folder and a SNAPSHOT.json with the embark recipe and fingerprints (copied from
#    the embark), the task-fort recipe, the build scripts' hashes, the summary and its layout, and the timings.
#    bench/key.py identifies the fort by the embark id + recipe + build-script hashes (not world.sav or the summary,
#    which differ run to run), so regenerating a pool keeps the task hash.
# Instance-aware (DF_INSTANCE) like make_embark.sh. Leaves DF running on the built fort, paused.
set -u
DFP=$(cd "$(dirname "$0")/.." && pwd -P)
. "$DFP/instance.sh" || exit 1
WHAT=${1:-}; SEED=${2:-}; shift 2 2>/dev/null
RULES=$DFP/embark/rules/TEMPERATE_SOIL.json; OUT=; EMBARK=; KEEP=
while [ $# -gt 0 ]; do
  case "$1" in
    --rules) RULES=$(realpath "$2"); shift 2;;
    --out) OUT=$(realpath -m "$2"); shift 2;;
    --embark) EMBARK=$(realpath "$2"); shift 2;;
    --keep-embark) KEEP=$(realpath -m "$2"); shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
[ -n "$WHAT" ] && [ -n "$SEED" ] && [ -n "$OUT" ] || { echo "usage: make_task_fort.sh <task|recipe> <seed> --out DIR"; exit 2; }
case "$SEED" in *[!0-9]*) echo "seed must be a non-negative integer"; exit 2;; esac
RECIPE=$(python3 - "$DFP/embark/forts" "$WHAT" <<'PY'
import glob, json, os, sys
d, w = sys.argv[1:]
if os.path.isfile(w):
    print(os.path.realpath(w)); sys.exit()
for p in sorted(glob.glob(os.path.join(d, "*.json"))):
    r = json.load(open(p))
    if w in (r["name"], os.path.basename(p)[:-5]) or w.split("-")[0].upper() in r.get("tasks", []):
        print(p); sys.exit()
sys.exit(1)
PY
) || { echo "FAIL: no recipe for '$WHAT' in embark/forts/"; exit 2; }
T0=$(date +%s); t() { echo "  [+$(( $(date +%s) - T0 ))s] $*" >&2; }
R() { timeout "${DFHACK_TIMEOUT:-120}" ./dfhack-run "$@" 2>/dev/null | sed 's/\x1b\[[0-9;]*[A-Za-z]//g'; }
WORK=$(mktemp -d "${TMPDIR:-/tmp}/taskfort.XXXX")
# the build and check logs are kept next to the output (<dir>.build.log), also on failure
cleanup() { mkdir -p "$(dirname "$OUT")"; cat "$WORK/build.log" "$WORK/check.log" > "$OUT.build.log" 2>/dev/null; rm -rf "$WORK"; }
trap cleanup EXIT

# --- 1. the embark ---------------------------------------------------------------------------------------------------
TE=$(date +%s)
if [ -n "$EMBARK" ]; then
  python3 -c 'import json,sys; e=json.load(open(sys.argv[1]))["embark"]; sys.exit(0 if e["seed"]==int(sys.argv[2]) else 1)' \
    "$EMBARK/SNAPSHOT.json" "$SEED" || { echo "FAIL: $EMBARK is not an embark of seed $SEED"; exit 1; }
  # the save's tick can be a few ticks past the probe's (DF ran on while saving): load whatever tick, 7 founders
  P=$(df_pids); [ -n "$P" ] && kill -9 $P 2>/dev/null
  for i in $(seq 1 60); do [ -z "$(df_pids)" ] && ! port_in_use && break; sleep 1; done
  READY=$(EXPECT_TICK=any SNAPSHOT=$EMBARK "$DFP/reset_fort.sh" 2>&1 | tail -1)
  case "$READY" in READY*|*"wrong start state"*"pop=7 "*) ;; *) echo "FAIL: embark load: $READY"; exit 1;; esac
  cp "$EMBARK/SNAPSHOT.json" "$WORK/embark.json"
else
  "$DFP/embark/make_embark.sh" --seed "$SEED" --rules "$RULES" --out "$WORK/embark" > "$WORK/embark.log" 2>&1 \
    || { tail -5 "$WORK/embark.log"; echo "FAIL: make_embark seed $SEED"; exit 1; }
  tail -1 "$WORK/embark.log" >&2
  cp "$WORK/embark/SNAPSHOT.json" "$WORK/embark.json"
  if [ -n "$KEEP" ]; then rm -rf "$KEEP"; mkdir -p "$(dirname "$KEEP")"; cp -a "$WORK/embark" "$KEEP"; fi
fi
EMBARK_S=$(( $(date +%s) - TE )); t "embark ready (${EMBARK_S}s)"
cd "$DF" || exit 1

# --- 2. build (up to 3 tries: a migrant wave that overshoots the recipe's population range can't be undone) -------
load_embark() {   # back to the fresh embark ($1 = its snapshot dir)
  local p; p=$(df_pids); [ -n "$p" ] && kill -9 $p 2>/dev/null
  for i in $(seq 1 60); do [ -z "$(df_pids)" ] && ! port_in_use && break; sleep 1; done
  local r; r=$(cd "$DFP" && EXPECT_TICK=any SNAPSHOT=$1 ./reset_fort.sh 2>&1 | tail -1)
  case "$r" in READY*|*"wrong start state"*"pop=7 "*) return 0;; *) echo "FAIL: embark load: $r"; return 1;; esac
}
EDIR=${EMBARK:-$WORK/embark}
TB=$(date +%s)
for TRY in 1 2 3; do
  ( cd "$DFP" && python3 embark/build_fort.py "$RECIPE" ) > "$WORK/build.log" 2>&1
  BRC=$?
  grep -E '^BUILD-(OK|FAIL)' "$WORK/build.log" | sed "s/^/  try $TRY: /" >&2
  [ "$BRC" = 0 ] && break
  grep -q '^BUILD-FAIL population' "$WORK/build.log" && [ "$TRY" -lt 3 ] || break
  load_embark "$EDIR" || exit 1
done
BUILD_S=$(( $(date +%s) - TB ))
[ "$BRC" = 0 ] || { tail -15 "$WORK/build.log"; echo "FAIL: build_fort.py rc=$BRC"; exit 1; }
t "built (${BUILD_S}s, $TRY tries)"
cd "$DF" || exit 1

# --- 3. check --------------------------------------------------------------------------------------------------------
R lua -f "$DFP/embark/fort_summary.lua" | grep '^{' > "$WORK/summary.json"
python3 "$DFP/embark/fort_check.py" "$WORK/summary.json" "$RECIPE" > "$WORK/check.log" 2>&1
CRC=$?
grep -E '^(FAIL|CHECK)' "$WORK/check.log" >&2
[ "$CRC" = 0 ] || { echo "FAIL: the built fort doesn't match $(basename "$RECIPE")'s expect"; exit 1; }

# --- 4. quicksave and copy (as make_embark.sh) -----------------------------------------------------------------------
TS=$(date +%s)
R lua "df.global.pause_state=true" >/dev/null
stamp() { for d in save/*/; do d=${d%/}; [ -f "$d/world.sav" ] && echo "$(basename "$d")|$(stat -c %Y:%s "$d/world.sav")"; done; }
BEFORE=$(stamp)
R quicksave >/dev/null
SRC=
for i in $(seq 1 60); do
  sleep 2
  CH=$(comm -13 <(echo "$BEFORE" | sort) <(stamp | sort) | cut -d'|' -f1 | head -1)
  if [ -n "$CH" ]; then A1=$(stamp | grep "^$CH|"); sleep 3; [ "$(stamp | grep "^$CH|")" = "$A1" ] && { SRC="save/$CH"; break; }; fi
done
[ -n "$SRC" ] || { echo "FAIL: quicksave wrote no save folder"; exit 1; }
TICK=$(R lua 'print(df.global.cur_year*403200+df.global.cur_year_tick)' | tr -dc 0-9)
rm -rf "$OUT"; mkdir -p "$(dirname "$OUT")"; cp -a "$SRC" "$OUT" || { echo "FAIL: copy"; exit 1; }
SAVE_S=$(( $(date +%s) - TS ))
python3 - "$OUT/SNAPSHOT.json" "$WORK/embark.json" "$RECIPE" "$WORK/summary.json" "$TICK" "$DFP" \
  "$EMBARK_S" "$BUILD_S" "$SAVE_S" "$(( $(date +%s) - T0 ))" "$(basename "$SRC")" "$( [ -n "$EMBARK" ] && echo reused || echo made)" "$TRY" <<'PY'
import hashlib, json, sys
(dst, emb, recipe, summ, tick, dfp, emb_s, build_s, save_s, tot_s, folder, how, tries) = sys.argv[1:]
e, r, s = json.load(open(emb)), json.load(open(recipe)), json.load(open(summ))
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
scripts = ["embark/build_fort.py", "embark/fort_events.lua", "embark/fort_stock.lua", "embark/fort_site.lua"]
json.dump({
    "abs_tick": int(tick), "citizens": s["pop"]["citizens"],
    "world_name": e["world_name"], "fort_name": e["fort_name"],
    "world_name_native": e.get("world_name_native"), "fort_name_native": e.get("fort_name_native"),
    "source": "embark/make_task_fort.sh", "save_folder": folder, "license": "terms-unclear",
    "obtainability": "licensed-obtainable", "embark": e["embark"],
    "task_fort": {"version": 1, "recipe": r["name"], "recipe_version": r.get("version"), "tasks": r.get("tasks"),
                  "recipe_sha256": sha(recipe),
                  "build_sha256": hashlib.sha256(b"".join(sha(dfp + "/" + p).encode() for p in scripts)).hexdigest(),
                  "embark": how, "build_tries": int(tries), "summary": s, "layout": s.get("layout"),
                  "timing_s": {"embark": int(emb_s), "build": int(build_s), "save": int(save_s), "total": int(tot_s)}},
}, open(dst, "w"), indent=1)
PY
echo "TASKFORT recipe=$(basename "$RECIPE" .json) seed=$SEED tile=$(python3 -c 'import json,sys; e=json.load(open(sys.argv[1]))["embark"]; print(*e["world_tile"], *e["local"])' "$OUT/SNAPSHOT.json") tick=$TICK citizens=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["citizens"])' "$OUT/SNAPSHOT.json") embark=${EMBARK_S}s build=${BUILD_S}s save=${SAVE_S}s total=$(( $(date +%s) - T0 ))s out=$OUT"
