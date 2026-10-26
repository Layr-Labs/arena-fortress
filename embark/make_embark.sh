#!/bin/bash
# make_embark.sh: a fresh fort from a world seed + a world-gen parameter set + site rules, saved as a scenario snapshot.
#
#   embark/make_embark.sh --seed 1000 --rules embark/rules/TEMPERATE_SOIL.json --out <dir> [--max-candidates 12]
#                         [--probe DIR] [--probe-only]
#   --probe DIR   also dump the world in stages to DIR (embark/world_probe.lua: terrain, rivers, sites, history counts;
#                 the candidate list; the legends dumps), for comparing hosts with embark/world_compare.py
#                 (research/seed-portability.md)
#   --probe-only  stop after the dump and the first --max-candidates tiles' mid-level details and rects: no embark
#
# 1. world gen: `dwarfort -gen <id> <seed> "<paramset>"` (headless, ~5-7 s at DIM 17x17). Param sets not in
#    df/prefs/world_gen.txt are appended from embark/world_gen.txt.
# 2. DF starts and is clicked to "Start new game in existing world" -> the new world -> Fortress -> the site screen.
# 3. embark/site_select.lua lists the world tiles that pass the rules' `region` filters (best first) and picks a 4x4
#    embark rectangle in each (`rect` rules). The first candidate whose embark raises no rejected warning
#    (`reject_warn`: aquifer, salt water, savage, evil...) is embarked with "Play now!" (the standard 7-dwarf loadout).
#    A rules file with a `site` ({"world_tile": [wx, wy], "local": [lx, ly]}) skips the search and embarks exactly
#    there (embark/rules/DEFAULT_FORT.json: the default start fort, docs/SEED-FORTS.md §6).
# 4. embark/fort_probe.lua checks the real map (`accept` rules: soil depth near the wagon, trees, surface water, no
#    aquifer) and fingerprints it. A rejected fort is discarded and the next candidate is tried.
# 5. quicksave; the save folder is copied to <dir> with a SNAPSHOT.json (abs_tick, citizens, world/fort names for
#    reset_fort.sh, and the full recipe: seed, rules hash, site, probe, fingerprint, timings).
# Everything is a pure function of (seed, paramset, rules) except world-gen *history* (see scenarios/README.md,
# "Embark snapshots": the map, site and party are reproducible; sites' names and populations elsewhere are not).
# Instance-aware like reset_fort.sh (DF_INSTANCE). Leaves this instance's DF running on the new fort, paused.
set -u
DFP=$(cd "$(dirname "$0")/.." && pwd -P)
. "$DFP/instance.sh" || exit 1
SEED= RULES= OUT= MAXC=40 PROBE= PROBE_ONLY= REGID=${EMBARK_REGION_ID:-7}
# world gen and the embark run on ONE cpu: with several, DF 53.16 world-gen history (sites, names, populations)
# differs run to run; pinned, two gens of a seed match (scenarios/README.md, "Embark snapshots")
CPU=${EMBARK_CPU:-$(( $(nproc) - 1 ))}
while [ $# -gt 0 ]; do
  case "$1" in
    --seed) SEED=$2; shift 2;;
    --rules) RULES=$(realpath "$2"); shift 2;;
    --out) OUT=$(realpath -m "$2"); shift 2;;
    --max-candidates) MAXC=$2; shift 2;;
    --probe) PROBE=$(realpath -m "$2"); shift 2;;
    --probe-only) PROBE_ONLY=1; shift;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
[ -n "$PROBE_ONLY" ] && { [ -n "$PROBE" ] || { echo "--probe-only needs --probe DIR"; exit 2; }; OUT=${OUT:-/dev/null}; }
[ -n "$SEED" ] && [ -f "$RULES" ] && [ -n "$OUT" ] || { echo "usage: make_embark.sh --seed N --rules R.json --out DIR"; exit 2; }
case "$SEED" in *[!0-9]*) echo "seed must be a non-negative integer"; exit 2;; esac
jget() { python3 -c 'import json,sys; v=json.load(open(sys.argv[1])); [v:=v[k] for k in sys.argv[2:]]; print(v if not isinstance(v,(list,dict)) else json.dumps(v))' "$RULES" "$@"; }
PARAMSET=$(jget paramset); RNAME=$(jget name); REJECT=$(jget reject_warn)
# DF keeps only the low byte of -gen's seed argument (12345 -> "9", 1000 -> 0xE8), so numeric seeds give 256 worlds.
# Rules with "gen_seed": "paramset" pass RANDOM instead, which makes DF use the param set's own *_SEED fields; --seed
# must then equal the param set's SEED (DEFAULT_FORT: PINNED POCKET's 12345, fort_start_snapshot's world)
GENARG=$SEED
if [ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("gen_seed", ""))' "$RULES")" = paramset ]; then
  GENARG=RANDOM
fi
T0=$(date +%s); t() { echo "  [+$(( $(date +%s) - T0 ))s] $*" >&2; }
R() { timeout "${DFHACK_TIMEOUT:-120}" ./dfhack-run "$@" 2>/dev/null | sed 's/\x1b\[[0-9;]*[A-Za-z]//g'; }
focus() { R lua "print(table.concat(dfhack.gui.getCurFocus(true),','))" | head -1; }
visible() { R lua -f "$DFP/screen.lua" | grep -qF "$1"; }
click() { R lua -f "$DFP/clicktext.lua" "$1" >/dev/null; }
clicklast() { R lua -f "$DFP/embark/clicktext_last.lua" "$1" >/dev/null; }
step() { for i in $(seq 1 20); do visible "$2" && return 0; click "$1"; sleep 1; done; echo "FAIL at '$1'"; return 1; }
stop_df() {
  local p; p=$(df_pids); [ -n "$p" ] && kill -9 $p 2>/dev/null
  for i in $(seq 1 20); do [ -z "$(df_pids)" ] && return 0; sleep 0.5; done; echo "FAIL: DF still running"; exit 1
}

stop_df
ensure_instance || { echo "FAIL: could not create instance $DF_INSTANCE"; exit 1; }
cd "$DF" || exit 1
[ -f "$DFP/env.sh" ] && . "$DFP/env.sh"

# --- 1. world gen ---------------------------------------------------------------------------------------------------
if ! grep -qF "[TITLE:$PARAMSET]" prefs/world_gen.txt; then
  python3 - "$DFP/embark/world_gen.txt" "$PARAMSET" prefs/world_gen.txt <<'PY' || { echo "FAIL: param set $PARAMSET not found"; exit 1; }
import sys, re
src, title, dst = sys.argv[1:]
t = open(src, encoding='latin-1').read()
blocks = re.split(r'(?=\[WORLD_GEN\])', t)
b = next((x for x in blocks if f'[TITLE:{title}]' in x), None)
if b is None: sys.exit(1)
open(dst, 'a', encoding='latin-1').write('\n' + b.rstrip() + '\n')
PY
fi
GEN_SEED=$GENARG GEN_PARAMSET=$PARAMSET   # $GENARG: the seed, or RANDOM for "gen_seed": "paramset" rules
if [ -n "${EMBARK_SEED_IN_PARAMS:-}" ]; then
  # DF 53.16's `-gen <id> <seed>` keeps only the seed's low 8 bits (seed 1256 makes seed 1000's world; the param dump
  # shows [SEED:<one byte>]), so a CLI seed has 256 values. Opt-in fix (research/seed-portability.md): write the full
  # seed into a per-seed copy of the param set ([SEED], [HISTORY_SEED], [NAME_SEED], [CREATURE_SEED]) and pass RANDOM.
  # Changes every embark id, so it's a new pool version, not a drop-in.
  GEN_PARAMSET="$PARAMSET S$SEED"; GEN_SEED=RANDOM
  grep -qF "[TITLE:$GEN_PARAMSET]" prefs/world_gen.txt || python3 - "$PARAMSET" "$GEN_PARAMSET" "$SEED" prefs/world_gen.txt <<'PY' || { echo "FAIL: seeded param set"; exit 1; }
import re, sys
title, new, seed, dst = sys.argv[1:]
t = open(dst, encoding='latin-1').read()
b = next(x for x in re.split(r'(?=\[WORLD_GEN\])', t) if f'[TITLE:{title}]' in x)
b = re.sub(r'\s*\[(SEED|HISTORY_SEED|NAME_SEED|CREATURE_SEED):[^\]]*\]', '', b)
b = b.replace(f'[TITLE:{title}]', f'[TITLE:{new}]' + ''.join(f'\n\t[{k}:{seed}]' for k in ('SEED', 'HISTORY_SEED', 'NAME_SEED', 'CREATURE_SEED')))
open(dst, 'a', encoding='latin-1').write('\n' + b.rstrip() + '\n')
PY
fi
rm -rf "save/region$REGID" region$REGID-* save/current
TG=$(date +%s%N)
# GEN_WRAP (research/determinism.md): a command prefix for the world-gen process only, e.g. `setarch x86_64 -R` (ASLR
# off, as dfhack's launcher already does for play) or `env LD_PRELOAD=embark/det_shim.so DET_MODE=fix`. Empty = as before.
timeout 1200 taskset -c "$CPU" ${GEN_WRAP:-} env -u DISPLAY ./dwarfort -gen "$REGID" "$GEN_SEED" "$GEN_PARAMSET" > "$DF_HOME/embark_gen.log" 2>&1
GEN_RC=$?; GEN_MS=$(( ($(date +%s%N) - TG) / 1000000 ))
if [ -n "$PROBE" ]; then rm -rf "$PROBE"; mkdir -p "$PROBE"; cp -a region$REGID-* "$DF_HOME/embark_gen.log" "$PROBE"/ 2>/dev/null; fi
rm -f region$REGID-*      # legends dumps (world_history, sites_and_pops, bmp): not needed for the snapshot
[ "$GEN_RC" = 0 ] && [ -f "save/region$REGID/world.dat" ] || { echo "FAIL: world gen rc=$GEN_RC"; tail -5 "$DF_HOME/embark_gen.log"; exit 1; }
GOT_SEED=$(grep -a '^ *Seed: ' gamelog.txt 2>/dev/null | tail -1 | tr -d '\r' | sed 's/^ *Seed: //')
if [ "$GEN_SEED" = RANDOM ] && [ "$GOT_SEED" != "$SEED" ]; then echo "FAIL: world gen used seed '$GOT_SEED', not the param set's $SEED"; exit 1; fi
t "world gen seed=$SEED (arg $GEN_SEED) paramset='$GEN_PARAMSET' ${GEN_MS} ms"

# --- 2./3. site screen, candidates, embark ------------------------------------------------------------------------------
to_site_screen() {
  stop_df
  rm -rf save/current
  taskset -c "$CPU" ${EMBARK_WRAP:-} setsid "$DFP/start_df.sh" >/dev/null 2>&1 < /dev/null &
  for i in $(seq 1 60); do sleep 2; visible "Start new game in existing world" && break; done
  step "Start new game in existing world" "Folder: region$REGID" || return 1
  for i in $(seq 1 10); do visible "Select a game type" && break; R lua -f "$DFP/embark/clickrow_above.lua" "Folder: region$REGID" >/dev/null; sleep 2; done
  # "Fortress", then DF may offer the tutorial ("Skip tutorial") or go straight to the site screen
  for i in $(seq 1 20); do
    [ "$(focus)" = "choose_start_site" ] && break
    if visible "Skip tutorial"; then click "Skip tutorial"; else click "Fortress"; fi
    sleep 2
  done
  [ "$(focus)" = "choose_start_site" ] || { echo "FAIL: not on the site screen (focus=$(focus))"; return 1; }
}
goto_tile() {   # centre the site screen on world tile (wx, wy) and wait for its mid-level details to load
  # (zoom_cent is in mid-level tiles, 16 per world tile; DF loads region details around it as it renders)
  R lua "local v=dfhack.gui.getDFViewscreen(true) v.location.region_pos.x=$1 v.location.region_pos.y=$2 v.zoomed_in=true v.zoom_cent_x=$1*16+8 v.zoom_cent_y=$2*16+8 v.region_cent_x=$1 v.region_cent_y=$2" >/dev/null
  for i in $(seq 1 10); do
    sleep 1
    visible "On your own" && click "Okay"
    visible "Quick start and short tutorial" && click "Skip tutorial"   # the tutorial offer can pop up late, over the map
    [ "$(R lua -f "$DFP/embark/site_select.lua" loaded "$1" "$2")" = LOADED ] && return 0
  done
  return 1
}

TE=$(date +%s)
to_site_screen || exit 1
t "site screen"
SITE=$(python3 -c 'import json,sys; s=json.load(open(sys.argv[1])).get("site"); print(*(s["world_tile"] + s["local"]) if s else "")' "$RULES")
if [ -n "$SITE" ]; then   # a pinned site: one candidate, its rectangle given
  read -r SWX SWY SLX SLY <<< "$SITE"
  CANDS="CAND $SWX $SWY 0 PINNED"
else
  CANDS=$(R lua -f "$DFP/embark/site_select.lua" list "$RULES")
fi
if [ -n "$PROBE" ]; then
  R lua -f "$DFP/embark/world_probe.lua" world "$PROBE/world.json" >&2
  echo "$CANDS" > "$PROBE/candidates.txt"
  python3 "$DFP/embark/world_compare.py" --host-info "$SEED" "$CPU" > "$PROBE/host.json"
fi
if [ -n "$PROBE_ONLY" ]; then
  I=0
  while read -r _ WX WY _; do
    I=$((I + 1)); [ "$I" -gt "$MAXC" ] && break
    goto_tile "$WX" "$WY" || { echo "$WX $WY NOTLOADED" >> "$PROBE/rects.txt"; continue; }
    R lua -f "$DFP/embark/world_probe.lua" details "$WX" "$WY" "$PROBE/details-$WX-$WY.json" >/dev/null
    echo "$WX $WY $(R lua -f "$DFP/embark/site_select.lua" rect "$RULES" "$WX" "$WY")" >> "$PROBE/rects.txt"
  done <<< "$(echo "$CANDS" | grep '^CAND')"
  t "probe-only: world dump + $I tile(s) in $PROBE"
  stop_df; exit 0
fi
NC=$(echo "$CANDS" | grep -c '^CAND'); t "candidates: $NC ($(echo "$CANDS" | grep '^REJECTED'))"
[ "$NC" -gt 0 ] || { echo "FAIL: no world tile passes the region rules"; exit 1; }
TRIED="[]"; PROBE=; I=0; ACCEPTED=
note() { TRIED=$(python3 -c 'import json,sys; t=json.loads(sys.argv[1]); t.append(dict(zip(("wx","wy","lx","ly","result"),sys.argv[2:]))); print(json.dumps(t))' "$TRIED" "$@"); }
while read -r _ WX WY SCORE BIOME REST; do
  I=$((I + 1)); [ "$I" -gt "$MAXC" ] && break
  if [ "$(focus)" != "choose_start_site" ]; then to_site_screen || exit 1; fi
  goto_tile "$WX" "$WY" || { note "$WX" "$WY" - - details_not_loaded; continue; }
  if [ -n "$SITE" ]; then RECT="RECT $SLX $SLY 0 -"; else RECT=$(R lua -f "$DFP/embark/site_select.lua" rect "$RULES" "$WX" "$WY"); fi
  case "$RECT" in RECT*) ;; *) note "$WX" "$WY" - - "${RECT#NORECT }"; t "cand $I ($WX,$WY) $BIOME: ${RECT}"; continue;; esac
  read -r _ LX LY RCELLS ER <<< "$RECT"
  # the "On your own!" and tutorial popups can still be coming up (a pinned site gets here within a second)
  for i in 1 2 3; do
    visible "Quick start and short tutorial" && { click "Skip tutorial"; sleep 2; }
    visible "On your own" && { click "Okay"; sleep 1; }
    clicklast Embark; sleep 2
    visible "Click on the map to embark" && break
  done
  visible "Click on the map to embark" || { note "$WX" "$WY" "$LX" "$LY" no_placement_mode; [ -n "${EMBARK_DEBUG:-}" ] && R lua -f "$DFP/screen.lua" >&2; continue; }
  if [ -z "$SITE" ]; then
    R lua "local v=dfhack.gui.getDFViewscreen(true) local l=v.location l.region_pos.x=$WX l.region_pos.y=$WY l.embark_pos_min.x=$((WX*16+LX)) l.embark_pos_min.y=$((WY*16+LY)) l.embark_pos_max.x=$((WX*16+LX+3)) l.embark_pos_max.y=$((WY*16+LY+3))" >/dev/null
    # DF embarks at the rectangle in the struct, not under the mouse (research/scenario-toolkit.md §5b)
    R lua "local gui=require('gui') df.global.gps.mouse_x=74 df.global.gps.mouse_y=31 gui.simulateInput(dfhack.gui.getDFViewscreen(true),'_MOUSE_L')" >/dev/null
    sleep 3
  else
    # A pinned site comes here within seconds of the map drawing, and then DF moves the struct's rectangle to the
    # one under the mouse before the click lands (the first click is also often lost). So click where the pinned
    # rectangle is drawn: its corner is at the screen centre (64, 32 on the 128x64 text screen) plus its offset from
    # the view's centre (zoom_cent, mid-level tiles; one per screen cell when zoomed in). The probe below checks it.
    read -r ZX ZY <<< "$(R lua "local v=dfhack.gui.getDFViewscreen(true) print(v.zoom_cent_x, v.zoom_cent_y)" | head -1)"
    MX=$((64 + WX*16 + LX - ZX)) MY=$((32 + WY*16 + LY - ZY))
    for i in 1 2 3; do
      R lua "local gui=require('gui') local v=dfhack.gui.getDFViewscreen(true) local l=v.location l.region_pos.x=$WX l.region_pos.y=$WY l.embark_pos_min.x=$((WX*16+LX)) l.embark_pos_min.y=$((WY*16+LY)) l.embark_pos_max.x=$((WX*16+LX+3)) l.embark_pos_max.y=$((WY*16+LY+3)) df.global.gps.mouse_x=$MX df.global.gps.mouse_y=$MY gui.simulateInput(v,'_MOUSE_L')" >/dev/null
      sleep 3
      [ -n "${EMBARK_DEBUG:-}" ] && { echo "DBG mouse $MX,$MY zoom $ZX,$ZY" >&2; R lua -f "$DFP/screen.lua" | head -10 >&2; }
      visible "Click on the map to embark" || break
    done
  fi
  WARN=$(R lua -f "$DFP/embark/site_select.lua" warn); WARN=$(echo ${WARN#WARN})
  BAD=$(python3 -c 'import json,sys; print(" ".join(w for w in sys.argv[2].split() if w in json.loads(sys.argv[1])))' "$REJECT" "$WARN")
  if [ -n "$BAD" ]; then
    click "Abort"; sleep 1; clicklast "Abort"; sleep 1
    note "$WX" "$WY" "$LX" "$LY" "warn:$BAD"; t "cand $I ($WX,$WY)+($LX,$LY) $BIOME: rejected warn $BAD"; continue
  fi
  if [ -z "$WARN" ] && visible "Click on the map to embark"; then   # DF refused the spot (e.g. "Cannot embark on another site.")
    [ -n "${EMBARK_DEBUG:-}" ] && R lua -f "$DFP/screen.lua" >&2
    clicklast "Abort"; sleep 1
    note "$WX" "$WY" "$LX" "$LY" refused; t "cand $I ($WX,$WY)+($LX,$LY) $BIOME: refused by DF"; continue
  fi
  for i in $(seq 1 120); do      # warnings we accept -> "Confirm"; then "Play now!"; then DF builds the map (~30 s)
    case "$(focus)" in dwarfmode*) break;; esac
    if visible "Confirm"; then click "Confirm"; elif visible "Play now!"; then click "Play now!"; fi
    sleep 2
  done
  case "$(focus)" in dwarfmode*) ;; *) echo "FAIL: never reached dwarfmode (focus=$(focus))"; exit 1;; esac
  R lua "df.global.pause_state=true" >/dev/null
  PROBE_RAW=$(R lua -f "$DFP/embark/fort_probe.lua" "$RULES"); PROBE=$(echo "$PROBE_RAW" | grep '^{')
  [ -n "$PROBE" ] || echo "$PROBE_RAW" | tail -8 >&2
  if [ -n "$SITE" ]; then   # a pinned site must be where the fort actually is; there is no next candidate
    GOT=$(python3 -c 'import json,sys; s=json.loads(sys.argv[1])["site"]; print(s["wx"], s["wy"], *s["rect"])' "$PROBE" 2>/dev/null)
    WANT="$WX $WY $((WX*16+LX)) $((WY*16+LY)) $((WX*16+LX+3)) $((WY*16+LY+3))"
    [ "$GOT" = "$WANT" ] || { echo "FAIL: embarked at '$GOT', not the pinned site '$WANT'"; exit 1; }
  fi
  if python3 -c 'import json,sys; sys.exit(0 if json.loads(sys.argv[1])["accept"] else 1)' "$PROBE" 2>/dev/null; then
    note "$WX" "$WY" "$LX" "$LY" accepted; ACCEPTED="$WX $WY $LX $LY"; t "cand $I ($WX,$WY)+($LX,$LY) $BIOME: accepted"; break
  fi
  WHY=$(python3 -c 'import json,sys; print(",".join(json.loads(sys.argv[1]).get("why") or ["probe_failed"]))' "$PROBE" 2>/dev/null || echo probe_failed)
  note "$WX" "$WY" "$LX" "$LY" "probe:$WHY"; t "cand $I ($WX,$WY)+($LX,$LY) $BIOME: rejected probe $WHY"
  echo "$PROBE" >> "$DF_HOME/embark_rejected.jsonl"
  to_site_screen || exit 1      # a fort can't be un-embarked: restart DF on the site screen
done <<< "$(echo "$CANDS" | grep '^CAND')"
EMBARK_S=$(( $(date +%s) - TE ))
if [ -z "$ACCEPTED" ]; then
  echo "FAIL: no candidate accepted in $((I > MAXC ? MAXC : I)) tried: $TRIED"; exit 1
fi

# --- 5. quicksave and copy -------------------------------------------------------------------------------------------
TS=$(date +%s)
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
rm -rf "$OUT"; mkdir -p "$(dirname "$OUT")"; cp -a "$SRC" "$OUT" || { echo "FAIL: copy"; exit 1; }
SAVE_S=$(( $(date +%s) - TS ))
NAMES=$(R lua "local s=df.world_site.find(df.global.plotinfo.site_id) print(dfhack.translation.translateName(df.global.world.world_data.name,true)) print(dfhack.translation.translateName(s.name,true)) print(dfhack.translation.translateName(df.global.world.world_data.name,false)) print(dfhack.translation.translateName(s.name,false))")
GENARG=$GENARG python3 - "$OUT/SNAPSHOT.json" "$RULES" "$SEED" "$PARAMSET" "$ACCEPTED" "$PROBE" "$TRIED" "$NAMES" "$GEN_MS" "$EMBARK_S" "$SAVE_S" "$(( $(date +%s) - T0 ))" "$(basename "$SRC")" <<'PY'
import hashlib, json, sys
(dst, rules, seed, paramset, acc, probe, tried, names, gen_ms, emb_s, save_s, tot_s, folder) = sys.argv[1:]
def host():
    import os, platform
    cpu = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), "")
    return {"machine": platform.machine(), "cpu": cpu, "nproc": os.cpu_count(),
            "rosetta": "VirtualApple" in cpu, "gen_seed_arg": os.environ.get("GENARG", "")}
probe = json.loads(probe); names = names.splitlines()
wx, wy, lx, ly = map(int, acc.split())
json.dump({
    "abs_tick": probe["abs_tick"], "citizens": probe["citizens"],
    "world_name": names[0], "fort_name": names[1], "world_name_native": names[2], "fort_name_native": names[3],
    "source": "embark/make_embark.sh", "save_folder": folder, "license": "terms-unclear",
    "embark": {"version": 1, "seed": int(seed), "paramset": paramset, "rules": json.load(open(rules))["name"],
               **({"seed_in_params": True} if __import__("os").environ.get("EMBARK_SEED_IN_PARAMS") else {}),
               "rules_sha256": hashlib.sha256(open(rules, "rb").read()).hexdigest(),
               "world_tile": [wx, wy], "local": [lx, ly], "probe": probe, "candidates_tried": json.loads(tried),
               "timing_s": {"world_gen": int(gen_ms) / 1000, "embark": int(emb_s), "save": int(save_s), "total": int(tot_s)}},
    "build_host": host(),   # world gen differs between host types (docs/SEED-FORTS.md §2); not part of any hash
}, open(dst, "w"), indent=1)
PY
echo "EMBARKED seed=$SEED rules=$RNAME tile=$ACCEPTED abs_tick=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["abs_tick"])' "$OUT/SNAPSHOT.json") gen=${GEN_MS}ms embark=${EMBARK_S}s save=${SAVE_S}s fp=$(python3 -c 'import json,sys; f=json.load(open(sys.argv[1]))["embark"]["probe"]["fingerprint"]; print(",".join(f"{k}:{v}" for k,v in sorted(f.items())))' "$OUT/SNAPSHOT.json") out=$OUT"
