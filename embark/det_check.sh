#!/bin/bash
# det_check.sh: the determinism bundle, run inside the image (research/determinism.md).
#
#   embark/det_check.sh --out DIR --shim SO [--gen-seeds 1000] [--gen-k 6] [--gen-modes base,aslr,fix,aslr_fix]
#                       [--embark-seed 1000] [--embark-k 3] [--embark-modes base,aslr_fix]
#                       [--replay-k 3] [--replay-days 28] [--replay-modes base,reseed,fix,fix_reseed,fix_reseed_1cpu] [--skip gen,embark,replay]
#
# World gen (full seed in the param set, EMBARK_SEED_IN_PARAMS=1, the recommended pool form), per mode:
#   base      as make_embark.sh runs it today (ASLR on for the gen process)
#   aslr      GEN_WRAP="setarch x86_64 -R"
#   fix       GEN_WRAP="env LD_PRELOAD=SO DET_MODE=fix" (random_device, time, gettimeofday made deterministic)
#   aslr_fix  both
# gen-<mode>-<seed>-k<k>/ are --probe-only world dumps (compare with world_compare.py); embark-<mode>-<seed>-k<k>/ hold
# full embarks' SNAPSHOT.json (the embark id). gen-count.jsonl / replay-count.jsonl: what DF calls (shim count mode).
# Replays of fort_start_snapshot (dfhack's launcher already runs DF under setarch -R), per mode:
#   base        as smoke.py does today
#   reseed      DF's main RNG buffer refilled from a fixed seed right after load (embark/det_rng.lua)
#   fix         the shim in fix mode
#   fix_reseed  both
# replay-<mode>.jsonl: embark/det_replay.py rows; summarise with det_replay.py --compare.
set -u
DFP=$(cd "$(dirname "$0")/.." && pwd -P)
OUT= SHIM= GSEEDS=1000 GK=6 GMODES=base,aslr,fix,aslr_fix ESEED=1000 EK=3 EMODES=base,aslr_fix
RK=3 RDAYS=28 RMODES=base,reseed,fix,fix_reseed,fix_reseed_1cpu SKIP=
RULES=$DFP/embark/rules/TEMPERATE_SOIL.json
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT=$(realpath -m "$2"); shift 2;; --shim) SHIM=$(realpath "$2"); shift 2;;
    --gen-seeds) GSEEDS=$2; shift 2;; --gen-k) GK=$2; shift 2;; --gen-modes) GMODES=$2; shift 2;;
    --embark-seed) ESEED=$2; shift 2;; --embark-k) EK=$2; shift 2;; --embark-modes) EMODES=$2; shift 2;;
    --replay-k) RK=$2; shift 2;; --replay-days) RDAYS=$2; shift 2;; --replay-modes) RMODES=$2; shift 2;;
    --skip) SKIP=$2; shift 2;;
    *) echo "unknown arg $1" >&2; exit 2;;
  esac
done
[ -n "$OUT" ] && [ -f "$SHIM" ] || { echo "usage: det_check.sh --out DIR --shim det_shim.so" >&2; exit 2; }
mkdir -p "$OUT" "$DFP/df/save"
export EMBARK_SEED_IN_PARAMS=1
{ grep -m1 'model name' /proc/cpuinfo; nproc; uname -r; echo "aslr=$(cat /proc/sys/kernel/randomize_va_space)"
  setarch x86_64 -R true && echo "setarch -R ok" || echo "setarch -R FAILED"; } > "$OUT/host.txt" 2>&1
wrap() {   # GEN_WRAP for a world-gen mode
  case "$1" in
    base) echo "";; aslr) echo "setarch x86_64 -R";;
    fix) echo "env LD_PRELOAD=$SHIM DET_MODE=fix DET_SEED=1";;
    aslr_fix) echo "setarch x86_64 -R env LD_PRELOAD=$SHIM DET_MODE=fix DET_SEED=1";;
    count) echo "env LD_PRELOAD=$SHIM DET_MODE=count DET_LOG=$OUT/gen-count.jsonl";;
  esac
}
t0=$(date +%s); t() { echo "[+$(( $(date +%s) - t0 ))s] $*"; }

case ",$SKIP," in *,gen,*) ;; *)
  s1=$(echo "$GSEEDS" | cut -d, -f1)
  GEN_WRAP=$(wrap count) "$DFP/embark/make_embark.sh" --seed "$s1" --rules "$RULES" --probe "$OUT/gen-count-$s1" \
    --probe-only --max-candidates 6 > "$OUT/gen-count-$s1.log" 2>&1 || echo "gen count failed" >&2
  t "gen count"
  for s in $(echo "$GSEEDS" | tr ',' ' '); do
    for k in $(seq 1 "$GK"); do
      for m in $(echo "$GMODES" | tr ',' ' '); do   # modes interleaved, so drift over time hits every mode alike
        GEN_WRAP=$(wrap "$m") "$DFP/embark/make_embark.sh" --seed "$s" --rules "$RULES" --probe "$OUT/gen-$m-$s-k$k" \
          --probe-only --max-candidates 6 > "$OUT/gen-$m-$s-k$k.log" 2>&1 || echo "gen $m $s k$k failed" >&2
      done
      t "gen seed $s k$k"
    done
  done;;
esac

case ",$SKIP," in *,embark,*) ;; *)
  for k in $(seq 1 "$EK"); do
    for m in $(echo "$EMODES" | tr ',' ' '); do
      GEN_WRAP=$(wrap "$m") "$DFP/embark/make_embark.sh" --seed "$ESEED" --rules "$RULES" --out "/tmp/det-embark" \
        > "$OUT/embark-$m-$ESEED-k$k.log" 2>&1
      mkdir -p "$OUT/embark-$m-$ESEED-k$k"
      cp /tmp/det-embark/SNAPSHOT.json "$OUT/embark-$m-$ESEED-k$k/" 2>/dev/null || echo "embark $m k$k failed" >&2
      rm -rf /tmp/det-embark
    done
    t "embark k$k"
  done;;
esac

case ",$SKIP," in *,replay,*) ;; *)
  python3 -u "$DFP/embark/det_replay.py" --out "$OUT/replay-count.jsonl" --label count --k 1 --days 3 \
    --shim "$SHIM" --shim-mode count > "$OUT/replay-count.log" 2>&1 || echo "replay count failed" >&2
  cp /tmp/det_log_count_0.jsonl "$OUT/replay-count-threads.jsonl" 2>/dev/null
  t "replay count"
  for k in $(seq 1 "$RK"); do
    for m in $(echo "$RMODES" | tr ',' ' '); do   # interleaved, one replay per mode per round
      P=()
      case "$m" in
        base) A=();; reseed) A=(--reseed 12345);; fix) A=(--shim "$SHIM" --shim-mode fix);;
        fix_reseed) A=(--shim "$SHIM" --shim-mode fix --reseed 12345);;
        fix_reseed_1cpu) A=(--shim "$SHIM" --shim-mode fix --reseed 12345); P=(taskset -c 0);;   # DF + its threads on one core
      esac
      "${P[@]}" python3 -u "$DFP/embark/det_replay.py" --out "$OUT/replay-$m.jsonl" --label "$m" --k 1 --days "$RDAYS" \
        "${A[@]}" >> "$OUT/replay-$m.log" 2>&1 || echo "replay $m round $k failed" >&2
      cp "/tmp/det_log_${m}_0.jsonl" "$OUT/replay-$m-threads-r$k.jsonl" 2>/dev/null; rm -f "/tmp/det_log_${m}_0.jsonl"
    done
    t "replay round $k"
  done
  python3 "$DFP/embark/det_replay.py" --compare "$OUT"/replay-*.jsonl > "$OUT/replay-summary.txt" 2>&1;;
esac
case ",$SKIP," in *,split,*) ;; *)
  # RNG split (det_shim.c DET_TRANDOM): learn which DF call sites draw while paused (UI/render), then replay with UI
  # draws routed to a private stream. Modes: fix_reseed (baseline), split_libg (libg_src_lib + paused draws),
  # split_learn (also the learned dwarfort sites).
  python3 -u "$DFP/embark/det_replay.py" --out "$OUT/split-learn.jsonl" --label learn --k 1 --days 3 --reseed 12345 \
    --shim "$SHIM" --shim-mode fix --trandom count --idle-paused 20 > "$OUT/split-learn.log" 2>&1 || echo "learn failed" >&2
  SITES=$(python3 - "$OUT/split-learn-trandom-k0.jsonl" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
head, sites = rows[0], rows[1:]
lo, hi = int(head["libg_lo"], 16), int(head["libg_hi"], 16)
ui = [s["pc"] for s in sites if s["paused"] > 0 and not (lo <= int(s["pc"], 16) < hi)]
print(",".join(ui[:256]))
PY
)
  echo "$SITES" > "$OUT/split-ui-sites.txt"
  t "split learn: $(echo "$SITES" | tr ',' '\n' | grep -c .) dwarfort UI sites"
  for k in $(seq 1 "$RK"); do
    for m in fix_reseed split_libg split_learn; do
      case "$m" in
        fix_reseed) A=();; split_libg) A=(--trandom split --ui-paused);;
        split_learn) A=(--trandom split --ui-paused --ui-sites "$SITES");;
      esac
      python3 -u "$DFP/embark/det_replay.py" --out "$OUT/split-$m.jsonl" --label "$m" --k 1 --days "$RDAYS" \
        --shim "$SHIM" --shim-mode fix --reseed 12345 "${A[@]}" >> "$OUT/split-$m.log" 2>&1 || echo "split $m round $k failed" >&2
    done
    t "split round $k"
  done
  python3 "$DFP/embark/det_replay.py" --compare "$OUT"/split-fix_reseed.jsonl "$OUT"/split-split_*.jsonl \
    > "$OUT/split-summary.txt" 2>&1;;
esac
case ",$SKIP," in *,trace,*) ;; *)
  # tick trace: after the reseed, single ticks with RNG + state fingerprints after each (first divergent tick)
  for k in $(seq 1 "$RK"); do
    for m in reseed fix_reseed; do
      case "$m" in reseed) A=();; fix_reseed) A=(--shim "$SHIM" --shim-mode fix);; esac
      python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-$m.jsonl" --label "trace_$m" --k 1 --days 0 \
        --reseed 12345 --tick-trace "${TRACE_TICKS:-120}" "${A[@]}" >> "$OUT/trace-$m.log" 2>&1 || echo "trace $m round $k failed" >&2
    done
    t "trace round $k"
  done;;
esac
case ",$SKIP," in *,gran,*) ;; *)
  # advance granularity: does RPC polling while ticks run, or running many ticks unpaused, break determinism?
  for k in $(seq 1 "$RK"); do
    for m in poll1200 quiet1200 quiet100; do
      case "$m" in
        poll1200) A=(--advance smoke);; quiet1200) A=(--advance quiet --chunk 1200);;
        quiet100) A=(--advance quiet --chunk 100);;
      esac
      python3 -u "$DFP/embark/det_replay.py" --out "$OUT/gran-$m.jsonl" --label "gran_$m" --k 1 \
        --days "${GRAN_DAYS:-5}" --reseed 12345 "${A[@]}" >> "$OUT/gran-$m.log" 2>&1 || echo "gran $m round $k failed" >&2
    done
    t "gran round $k"
  done
  python3 "$DFP/embark/det_replay.py" --compare "$OUT"/gran-*.jsonl > "$OUT/gran-summary.txt" 2>&1;;
esac
case ",$SKIP," in *,trace2,*) ;; *)
  # a whole day traced in steps of 1, 10 and 100 ticks (RNG + state after each step)
  for k in $(seq 1 "$RK"); do
    for s in 1 10 100; do
      python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace2-s$s.jsonl" --label "trace2_s$s" --k 1 --days 0 \
        --reseed 12345 --tick-trace "${TRACE2_TICKS:-1200}" --trace-step "$s" >> "$OUT/trace2-s$s.log" 2>&1 \
        || echo "trace2 s$s round $k failed" >&2
    done
    t "trace2 round $k"
  done;;
esac
case ",$SKIP," in *,perturb,*) ;; *)
  # uninitialized heap reads: glibc fills malloc'd and freed memory with a fixed byte, then a whole-day trace
  for k in $(seq 1 "$RK"); do
    python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-perturb.jsonl" --label "trace_perturb_s100" --k 1 --days 0 \
      --reseed 12345 --tick-trace 1200 --trace-step 100 --env GLIBC_TUNABLES=glibc.malloc.perturb=165 \
      >> "$OUT/trace-perturb.log" 2>&1 || echo "perturb round $k failed" >&2
    t "perturb round $k"
  done;;
esac

case ",$SKIP," in *,perturb2,*) ;; *)
  # glibc's tcache fast path skips the perturb fill (malloc.c: tcache_get has no alloc_perturb), so disable tcache too.
  # fn 0x2072000 (on the divergent path) new[]s 8 arrays and memsets 2.
  for k in $(seq 1 "$RK"); do
    for m in perturb_notc notc; do
      case "$m" in
        perturb_notc) T=glibc.malloc.tcache_count=0:glibc.malloc.perturb=165;; notc) T=glibc.malloc.tcache_count=0;;
      esac
      python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-$m.jsonl" --label "trace_${m}_s100" --k 1 --days 0 \
        --reseed 12345 --tick-trace 1200 --trace-step 100 --env "GLIBC_TUNABLES=$T" \
        >> "$OUT/trace-$m.log" 2>&1 || echo "$m round $k failed" >&2
    done
    t "perturb2 round $k"
  done;;
esac

case ",$SKIP," in *,plugins,*) ;; *)
  # DFHack's default-enabled plugins (hack/init/dfhack.tools.init) run on their own cycles; disable them after the load
  for k in $(seq 1 "$RK"); do
    python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-plugins_off.jsonl" --label "trace_plugins_off_s100" --k 1 \
      --days 0 --reseed 12345 --tick-trace 1200 --trace-step 100 --record-plugins \
      --post-load "disable buildingplan" --post-load "disable burrow" --post-load "disable logistics" \
      --post-load "disable preserve-rooms" --post-load "disable overlay" \
      >> "$OUT/trace-plugins.log" 2>&1 || echo "plugins round $k failed" >&2
    t "plugins round $k"
  done;;
esac

case ",$SKIP," in *,deep,*) ;; *)
  # hidden state set during the load: deep unit fingerprints at day 0 (before any tick), then a short trace
  for k in $(seq 1 "$RK"); do
    python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-deep.jsonl" --label "trace_deep_s100" --k 1 --days 0 \
      --reseed 12345 --deep --tick-trace 600 --trace-step 100 >> "$OUT/trace-deep.log" 2>&1 || echo "deep round $k failed" >&2
    t "deep round $k"
  done;;
esac

case ",$SKIP," in *,preload,*) ;; *)
  # reseed DF's RNG in the save list, just before the load (reset_fort.sh DET_RESEED_BEFORE_LOAD); with and without a
  # second reseed after the load. Whole-day traces with the deep fingerprint, then 7-day replays through smoke.advance.
  for k in $(seq 1 "$RK"); do
    python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-pre.jsonl" --label "trace_pre_s100" --k 1 --days 0 \
      --reseed-before-load 777 --deep --tick-trace 1200 --trace-step 100 >> "$OUT/trace-pre.log" 2>&1 || echo "pre $k failed" >&2
    python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-prepost.jsonl" --label "trace_prepost_s100" --k 1 --days 0 \
      --reseed-before-load 777 --reseed 12345 --deep --tick-trace 1200 --trace-step 100 \
      >> "$OUT/trace-prepost.log" 2>&1 || echo "prepost $k failed" >&2
    python3 -u "$DFP/embark/det_replay.py" --out "$OUT/replay-prepost.jsonl" --label "prepost" --k 1 \
      --days "${PRE_DAYS:-7}" --reseed-before-load 777 --reseed 12345 >> "$OUT/replay-prepost.log" 2>&1 || echo "prepost replay $k failed" >&2
    t "preload round $k"
  done;;
esac

case ",$SKIP," in *,view,*) ;; *)
  # the fix under test: camera to empty sky + unit caches cleared after the load, then the reseed (embark/det_view.lua)
  for k in $(seq 1 "$RK"); do
    python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-view.jsonl" --label "trace_view_s100" --k 1 --days 0 \
      --quiet-view --reseed 12345 --deep --tick-trace 2400 --trace-step 100 >> "$OUT/trace-view.log" 2>&1 || echo "view $k failed" >&2
    python3 -u "$DFP/embark/det_replay.py" --out "$OUT/replay-view.jsonl" --label "view" --k 1 \
      --days "${VIEW_DAYS:-14}" --quiet-view --reseed 12345 >> "$OUT/replay-view.log" 2>&1 || echo "view replay $k failed" >&2
    t "view round $k"
  done;;
esac

case ",$SKIP," in *,cache,*) ;; *)
  # when do the unit caches get computed? per-step cache bits; and does sitting paused 30 s first make them complete?
  for k in $(seq 1 "$RK"); do
    for m in base idle30 view_idle30; do
      case "$m" in base) A=();; idle30) A=(--idle-paused 30);; view_idle30) A=(--quiet-view --idle-paused 30);; esac
      python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-cache-$m.jsonl" --label "trace_cache_${m}_s100" --k 1 \
        --days 0 --reseed 12345 --tick-trace 1200 --trace-step 100 "${A[@]}" >> "$OUT/trace-cache.log" 2>&1 \
        || echo "cache $m $k failed" >&2
    done
    t "cache round $k"
  done;;
esac

case ",$SKIP," in *,addr,*) ;; *)
  # are game objects at the same heap addresses in every replay? (pointer-ordered containers)
  for k in $(seq 1 "$RK"); do
    for m in base idle30; do
      case "$m" in base) A=();; idle30) A=(--idle-paused 30);; esac
      python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-addr-$m.jsonl" --label "trace_addr_${m}_s100" --k 1 \
        --days 0 --addr --reseed 12345 --tick-trace 600 --trace-step 100 "${A[@]}" >> "$OUT/trace-addr.log" 2>&1 \
        || echo "addr $m $k failed" >&2
    done
    t "addr round $k"
  done;;
esac

case ",$SKIP," in *,site,*) ;; *)
  # which call sites draw differently at the divergent tick: single ticks with a draw histogram at every pause
  for k in $(seq 1 "$RK"); do
    python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-site.jsonl" --label "trace_site_s1" --k 1 --days 0 \
      --reseed 12345 --tick-trace "${SITE_TICKS:-460}" --trace-step 1 --shim "$SHIM" --shim-mode count --trandom count \
      --pause-dump "$OUT/site-r$k" >> "$OUT/trace-site.log" 2>&1 || echo "site round $k failed" >&2
    t "site round $k"
  done;;
esac
case ",$SKIP," in *,simroot,*) ;; *)
  # the fix under test: UI draws on rendered frames go to a private stream (det_shim.c DET_TRANDOM=simroot)
  for k in $(seq 1 "$RK"); do
    python3 -u "$DFP/embark/det_replay.py" --out "$OUT/trace-simroot.jsonl" --label "trace_simroot_s100" --k 1 --days 0 \
      --reseed 12345 --tick-trace 1200 --trace-step 100 --shim "$SHIM" --trandom simroot \
      >> "$OUT/trace-simroot.log" 2>&1 || echo "simroot trace round $k failed" >&2
    python3 -u "$DFP/embark/det_replay.py" --out "$OUT/replay-simroot.jsonl" --label "simroot" --k 1 \
      --days "${SIMROOT_DAYS:-7}" --reseed 12345 --shim "$SHIM" --trandom simroot \
      >> "$OUT/replay-simroot.log" 2>&1 || echo "simroot replay round $k failed" >&2
    cp /tmp/det_trandom_simroot_0.jsonl "$OUT/replay-simroot-ui-r$k.jsonl" 2>/dev/null
    t "simroot round $k"
  done;;
esac
echo "DET_CHECK_DONE $OUT"
