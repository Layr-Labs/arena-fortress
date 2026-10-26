#!/bin/bash
# docker/embark.sh: make embark snapshots (embark/make_embark.sh) in throwaway containers and copy them out.
# Plain bash 3.2 (macOS default).
#
# usage: docker/embark.sh --rules TEMPERATE_SOIL --seeds 1000,1001 [--image yukon-df] [--out scenarios/snapshots]
#                         [--prefix emb] [--parallel 2] [--memory 3g] [--check]
#   --rules    a name under embark/rules/ (or a path to a rules JSON inside the image)
#   --seeds    world seeds, comma separated. Train pools use 1000-1999; test-private seeds (9000+) are made the same
#              way by maintainers and never written into the repo (scenarios/README.md, "Embark snapshots")
#   --check    make each seed twice, in two containers, and compare the fingerprints (embark/compare.py)
# Result: <out>/embark-<rules>-<seed>/ (a DF save folder + SNAPSHOT.json), which a scenario names as its
# `snapshot` or in its `snapshot_pool`. The image must contain embark/ (build it from this repo).
set -u
IMAGE=yukon-df; RULES=; SEEDS=; OUT=scenarios/snapshots; PREFIX=emb; PAR=1; MEM=3g; CHECK=
while [ $# -gt 0 ]; do
  case "$1" in
    --image) IMAGE=$2; shift 2;; --rules) RULES=$2; shift 2;; --seeds) SEEDS=$2; shift 2;;
    --out) OUT=$2; shift 2;; --prefix) PREFIX=$2; shift 2;; --parallel) PAR=$2; shift 2;;
    --memory) MEM=$2; shift 2;; --check) CHECK=1; shift;;
    *) echo "unknown arg $1" >&2; exit 2;;
  esac
done
[ -n "$RULES" ] && [ -n "$SEEDS" ] || { echo "--rules and --seeds are required" >&2; exit 2; }
case "$RULES" in */*|*.json) RPATH=$RULES;; *) RPATH=embark/rules/$RULES.json;; esac
RTAG=$(basename "$RPATH" .json | tr 'A-Z_' 'a-z-')
mkdir -p "$OUT"
NCPU=$(docker info --format '{{.NCPU}}' 2>/dev/null || echo 4)

one() {  # $1 = seed, $2 = slot (picks the container name and the CPU world gen is pinned to), $3 = dest dir
  local c="$PREFIX-$RTAG-$1-$2" t0; t0=$(date +%s)
  docker rm -f "$c" >/dev/null 2>&1
  docker run -d --name "$c" --platform linux/amd64 --security-opt seccomp=unconfined \
    --memory "$MEM" --memory-swap "$MEM" "$IMAGE" >/dev/null || return 1
  docker exec -e EMBARK_CPU=$(( (NCPU - 1 - $2) % NCPU )) "$c" bash -c \
    "mkdir -p df/save && embark/make_embark.sh --seed $1 --rules $RPATH --out /tmp/embark-out" > "$3.log" 2>&1
  local rc=$?
  if [ "$rc" = 0 ]; then
    rm -rf "$3"; docker cp "$c:/tmp/embark-out" "$3" >/dev/null && echo "[$(date +%T)] seed $1: $(tail -1 "$3.log") ($(( $(date +%s) - t0 )) s wall)"
  else
    echo "[$(date +%T)] seed $1: FAILED rc=$rc (see $3.log)"
  fi
  docker rm -f "$c" >/dev/null 2>&1
  return $rc
}

FAILED=0; SLOT=0
for s in $(echo "$SEEDS" | tr ',' ' '); do
  dst="$OUT/embark-$RTAG-$s"
  if [ -n "$CHECK" ]; then
    one "$s" "$SLOT" "$dst" & one "$s" $((SLOT + 1)) "$dst.check" &
    wait
    if [ -f "$dst/SNAPSHOT.json" ] && [ -f "$dst.check/SNAPSHOT.json" ]; then
      python3 "$(dirname "$0")/../embark/compare.py" "$dst" "$dst.check" || FAILED=$((FAILED + 1))
    else
      FAILED=$((FAILED + 1))
    fi
  else
    one "$s" "$SLOT" "$dst" &
    SLOT=$((SLOT + 1))
    if [ "$SLOT" -ge "$PAR" ]; then wait; SLOT=0; fi
  fi
done
wait
[ "$FAILED" = 0 ] || { echo "$FAILED seed(s) failed (embark error or determinism check)" >&2; exit 1; }
