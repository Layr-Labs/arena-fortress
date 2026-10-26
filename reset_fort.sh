#!/bin/bash
# reset_fort.sh: kill DF, restore the fixed starting fortress, relaunch headless, load it by clicks.
# Prints READY <tick> on success. Exit 1 on failure.
# Env overrides (load a smoke.py --snapshot-days snapshot instead): SNAPSHOT=<save dir>; EXPECT_TICK / EXPECT_POP
# default to the snapshot's SNAPSHOT.json if present, else to the starting fort (823201 / 7). The starting fort is
# fort_start_snapshot, or, if it has no world.sav, the seed-built scenarios/snapshots/embark-default-fort-12345
# (embark/make_default_fort.sh; 823200 / 7).
# Instance selected by DF_INSTANCE (see instance.sh); only THIS instance's process and saves are touched.
set -u
. "$(dirname "$0")/instance.sh" || exit 1
SNAP=$(realpath "${SNAPSHOT:-$DFP/fort_start_snapshot}") || exit 1   # before cd: SNAPSHOT may be relative
# no committed start save (a public checkout ships no DF save): the seed-built default fort (bench/key.py start_snapshot)
if [ "$SNAP" = "$(realpath "$DFP/fort_start_snapshot" 2>/dev/null)" ] && [ ! -f "$SNAP/world.sav" ]; then
  SNAP="$DFP/scenarios/snapshots/embark-default-fort-12345"
  [ -f "$SNAP/world.sav" ] || { echo "FAIL: no start fort. Build it from its seed (~1.5 min): embark/make_default_fort.sh" \
    "(inside the image), or docker/embark.sh --rules DEFAULT_FORT --seeds 12345 on the host and rebuild the image"; exit 1; }
fi
[ -f "$SNAP/world.sav" ] || { echo "FAIL: no save at $SNAP"; exit 1; }
T0=$(date +%s); t() { echo "  [+$(( $(date +%s) - T0 ))s] $*" >&2; }
R() { timeout "${DFHACK_TIMEOUT:-600}" ./dfhack-run "$@" 2>/dev/null | sed 's/\x1b\[[0-9;]*[A-Za-z]//g'; }  # see harness.DFHACK_TIMEOUT
focus() { R lua "print(table.concat(dfhack.gui.getCurFocus(true),','))" | head -1; }
visible() { R lua -f "$DFP/screen.lua" | grep -qF "$1"; }
click() { R lua -f "$DFP/clicktext.lua" "$1" >/dev/null; }

PIDS=$(df_pids); [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null
for i in $(seq 1 20); do [ -z "$(df_pids)" ] && break; sleep 0.5; done
[ -z "$(df_pids)" ] || { echo "FAIL: instance $DF_INSTANCE DF still running"; exit 1; }
# a non-DF listener (or another instance) on our port would make every dfhack-run hit the wrong game. A DF just
# killed (e.g. the one embark/make_embark.sh leaves running) can hold the port for a few seconds, so wait for that first
for i in $(seq 1 20); do port_in_use || break; sleep 0.5; done
port_in_use && { echo "FAIL: port $DFHACK_PORT already in use"; exit 1; }
ensure_instance || { echo "FAIL: could not create instance $DF_INSTANCE"; exit 1; }
cd "$DF" || exit 1
# wipe EVERY fortress save slot (in-game autosave rotates into autosave 2/3 and the
# save list then shows several "Scoureddike" rows); keep only the world + the snapshot
find save -mindepth 1 -maxdepth 1 -type d ! -name region1 -exec rm -rf {} +
if [ -f "$SNAP/SNAPSHOT.json" ]; then
  : "${EXPECT_TICK:=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["abs_tick"])' "$SNAP/SNAPSHOT.json")}"
  : "${EXPECT_POP:=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["citizens"])' "$SNAP/SNAPSHOT.json")}"
fi
if [ -n "${SNAPSHOT:-}" ] && [ -z "${EXPECT_TICK:-}" ]; then
  echo "FAIL: $SNAP has no SNAPSHOT.json; add one ({\"abs_tick\":..,\"citizens\":..}) or set EXPECT_TICK/EXPECT_POP"; exit 1
fi
EXPECT_TICK=${EXPECT_TICK:-823201}; EXPECT_POP=${EXPECT_POP:-7}
# world and fort names to click in the load menus: SNAPSHOT.json's (embark/make_embark.sh writes them), else the start fort's
WORLD_NAME="The Land of Destiny"; FORT_NAME="Scoureddike"
if [ -f "$SNAP/SNAPSHOT.json" ]; then
  W=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("world_name") or "")' "$SNAP/SNAPSHOT.json")
  F=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("fort_name") or "")' "$SNAP/SNAPSHOT.json")
  [ -n "$W" ] && WORLD_NAME=$W; [ -n "$F" ] && FORT_NAME=$F
fi
cp -a "$SNAP" "save/autosave 1" || { echo "FAIL: copy $SNAP"; exit 1; }
rm -f "save/autosave 1/SNAPSHOT.json"
setsid "$DFP/start_df.sh" >/dev/null 2>&1 < /dev/null &
for i in $(seq 1 60); do sleep 2; visible "Continue active game" && break; done; t "title"
# click TARGET until NEXT is visible
step() { for i in $(seq 1 20); do visible "$2" && return 0; click "$1"; sleep 1; done; echo "FAIL at '$1'"; exit 1; }
step "Continue active game" "$WORLD_NAME"; t "world list"
step "$WORLD_NAME" "$FORT_NAME";          t "save list"
# research/determinism.md: DF's RNG is seeded from the wall clock at startup and the load draws from it, so reseed it
# just before the load when asked (unset = unchanged behaviour)
if [ -n "${DET_RESEED_BEFORE_LOAD:-}" ]; then R lua -f "$DFP/embark/det_rng.lua" seed "$DET_RESEED_BEFORE_LOAD" >/dev/null; fi
click "$FORT_NAME"
for i in $(seq 1 90); do sleep 2; case "$(focus)" in dwarfmode*) break;; esac; done
case "$(focus)" in dwarfmode*) ;; *) echo "FAIL: fort never loaded (focus=$(focus))"; exit 1;; esac
t "fort loaded"
R lua "df.global.pause_state=true" >/dev/null
TICK=$(R lua 'print(df.global.cur_year*403200+df.global.cur_year_tick)' | tr -dc 0-9)
POP=$(R lua "local n=0 for _,u in ipairs(df.global.world.units.active) do if dfhack.units.isCitizen(u) then n=n+1 end end print(n)" | tr -dc 0-9)
# assert we loaded THE starting fort, not some other save
if [ "$TICK" != "$EXPECT_TICK" ] || [ "$POP" != "$EXPECT_POP" ]; then echo "FAIL: wrong start state abs_tick=$TICK pop=$POP (expected $EXPECT_TICK/$EXPECT_POP)"; exit 1; fi
echo "READY $TICK pop=$POP instance=$DF_INSTANCE port=$DFHACK_PORT"
