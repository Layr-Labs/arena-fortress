#!/bin/bash
# xp_check.sh: the cross-host seed-portability bundle, run inside the image (research/seed-portability.md).
#
#   embark/xp_check.sh --out DIR [--probe-seeds 1000,2001,2002,2005] [--embark-seeds 1000,2001,2002]
#                      [--nofma-seed 1000] [--repeat 1] [--seed-in-params]
#
# Writes to DIR: host.txt (cpuinfo model/flags, glibc's cpu-feature diagnostics), libm.json and libm-nofma.json
# (embark/libm_fp.py with glibc's default and SSE2-only libm), probe-<seed>[-r<k>]/ (make_embark.sh --probe-only:
# world stages + candidate tiles' details), probe-nofma-<seed>/ (the same with FMA/AVX libm variants disabled), and
# embark-<seed>[-r<k>]/ (a full embark's SNAPSHOT.json; its world dump in embark-<seed>[-r<k>]-probe/).
# --repeat N makes every probe and embark N times (k = 2..N get the -r<k> suffix), for within-host reproducibility.
# --seed-in-params sets EMBARK_SEED_IN_PARAMS=1 (the full seed in the param set instead of `-gen`'s 8-bit seed).
# Compare two bundles with embark/xp_compare.py.
set -u
DFP=$(cd "$(dirname "$0")/.." && pwd -P)
OUT= PSEEDS=1000,2001,2002,2005 ESEEDS=1000,2001,2002 NOFMA=1000 REPEAT=1
RULES=$DFP/embark/rules/TEMPERATE_SOIL.json
NOFMA_TUN=glibc.cpu.hwcaps=-AVX2,-FMA,-AVX
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT=$(realpath -m "$2"); shift 2;; --probe-seeds) PSEEDS=$2; shift 2;;
    --embark-seeds) ESEEDS=$2; shift 2;; --nofma-seed) NOFMA=$2; shift 2;;
    --repeat) REPEAT=$2; shift 2;; --seed-in-params) export EMBARK_SEED_IN_PARAMS=1; shift;;
    *) echo "unknown arg $1" >&2; exit 2;;
  esac
done
[ -n "$OUT" ] || { echo "usage: xp_check.sh --out DIR" >&2; exit 2; }
mkdir -p "$OUT" "$DFP/df/save"
{ grep -m1 'model name' /proc/cpuinfo; grep -m1 '^flags' /proc/cpuinfo; nproc; uname -r
  /lib64/ld-linux-x86-64.so.2 --list-diagnostics 2>&1 | grep -E 'cpu_features\.(basic|isa_1|preferred)'
  echo "seed_in_params=${EMBARK_SEED_IN_PARAMS:-0}"; } > "$OUT/host.txt"
python3 "$DFP/embark/libm_fp.py" --examples > "$OUT/libm.json"
GLIBC_TUNABLES=$NOFMA_TUN python3 "$DFP/embark/libm_fp.py" --examples > "$OUT/libm-nofma.json"
for k in $(seq 1 "$REPEAT"); do
  sfx=; [ "$k" -gt 1 ] && sfx=-r$k
  for s in $(echo "$PSEEDS" | tr ',' ' '); do
    "$DFP/embark/make_embark.sh" --seed "$s" --rules "$RULES" --probe "$OUT/probe-$s$sfx" --probe-only --max-candidates 6 \
      > "$OUT/probe-$s$sfx.log" 2>&1 || echo "probe $s$sfx failed" >&2
  done
done
for s in $(echo "$NOFMA" | tr ',' ' '); do
  GLIBC_TUNABLES=$NOFMA_TUN "$DFP/embark/make_embark.sh" --seed "$s" --rules "$RULES" --probe "$OUT/probe-nofma-$s" \
    --probe-only --max-candidates 6 > "$OUT/probe-nofma-$s.log" 2>&1 || echo "nofma probe $s failed" >&2
done
for k in $(seq 1 "$REPEAT"); do
  sfx=; [ "$k" -gt 1 ] && sfx=-r$k
  for s in $(echo "$ESEEDS" | tr ',' ' '); do
    "$DFP/embark/make_embark.sh" --seed "$s" --rules "$RULES" --probe "$OUT/embark-$s$sfx-probe" --out "/tmp/xp-embark-$s" \
      > "$OUT/embark-$s$sfx.log" 2>&1
    mkdir -p "$OUT/embark-$s$sfx"
    cp "/tmp/xp-embark-$s/SNAPSHOT.json" "$OUT/embark-$s$sfx/" 2>/dev/null || echo "embark $s$sfx failed" >&2
    rm -rf "/tmp/xp-embark-$s"
  done
done
echo "XP_CHECK_DONE $OUT"
