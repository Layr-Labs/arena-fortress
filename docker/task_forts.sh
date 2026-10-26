#!/bin/bash
# docker/task_forts.sh: build lab-task start forts from seeds (embark/make_task_fort.sh) in throwaway containers.
# What `yukon setup` runs for the train and test-public pools, and what the verifier runs for its private pool.
# Plain bash 3.2 (macOS default).
#
# usage: docker/task_forts.sh --seeds 2000,2001 [--recipes worked-y1,neglected-y1] [--image yukon-df]
#                             [--out scenarios/snapshots] [--parallel 2] [--memory 3g] [--prefix tf]
#   --seeds    world seeds. Train 1000-1999, test-public 2000-2099; test-private (9000+) only on the verifier,
#              written outside any repo (scenarios/README.md, "Task forts")
#   --recipes  embark/forts/<name>.json, comma separated; every recipe is built on the same embark of each seed
# Result: <out>/fort-<recipe>-<seed>/ (a DF save folder + SNAPSHOT.json, never committed), <out>/fort-<recipe>-<seed>.build.log,
# and one TASKFORT / FAILED line per fort. A seed with no acceptable embark site fails all its recipes (the pool then
# takes the next seed). The image must contain embark/ (build it from this repo).
set -u
IMAGE=yukon-df; RECIPES=worked-y1,neglected-y1; SEEDS=; OUT=scenarios/snapshots; PREFIX=tf; PAR=2; MEM=3g
RULES=embark/rules/TEMPERATE_SOIL.json
while [ $# -gt 0 ]; do
  case "$1" in
    --image) IMAGE=$2; shift 2;; --recipes) RECIPES=$2; shift 2;; --seeds) SEEDS=$2; shift 2;;
    --out) OUT=$2; shift 2;; --parallel) PAR=$2; shift 2;; --memory) MEM=$2; shift 2;; --prefix) PREFIX=$2; shift 2;;
    --rules) RULES=$2; shift 2;;
    *) echo "unknown arg $1" >&2; exit 2;;
  esac
done
[ -n "$SEEDS" ] || { echo "--seeds is required" >&2; exit 2; }
mkdir -p "$OUT"
NCPU=$(docker info --format '{{.NCPU}}' 2>/dev/null || echo 4)

one() {  # $1 = seed, $2 = slot (container name; the CPU world gen is pinned to)
  local s=$1 c="$PREFIX-$1" t0 first=1 r dst rc=0
  t0=$(date +%s)
  docker rm -f "$c" >/dev/null 2>&1
  docker run -d --name "$c" --platform linux/amd64 --security-opt seccomp=unconfined \
    --memory "$MEM" --memory-swap "$MEM" "$IMAGE" >/dev/null || return 1
  for r in $(echo "$RECIPES" | tr ',' ' '); do
    dst="$OUT/fort-$r-$s"
    if [ -n "$first" ]; then
      args="--keep-embark /tmp/embark-$s"; first=
    else
      args="--embark /tmp/embark-$s"
    fi
    docker exec -e EMBARK_CPU=$(( (NCPU - 1 - $2) % NCPU )) "$c" bash -c \
      "mkdir -p df/save && embark/make_task_fort.sh $r $s --rules $RULES --out /tmp/fort $args" > "$dst.log" 2>&1
    if [ $? = 0 ]; then
      rm -rf "$dst"; docker cp "$c:/tmp/fort" "$dst" >/dev/null && echo "[$(date +%T)] $(tail -1 "$dst.log")"
    else
      echo "[$(date +%T)] seed $s $r: FAILED (see $dst.log)"; rc=1
      [ -n "$first" ] || docker exec "$c" test -f "/tmp/embark-$s/SNAPSHOT.json" || break   # no embark: skip the rest
    fi
    docker cp "$c:/tmp/fort.build.log" "$dst.build.log" >/dev/null 2>&1
  done
  echo "[$(date +%T)] seed $s: done in $(( $(date +%s) - t0 )) s wall"
  docker rm -f "$c" >/dev/null 2>&1
  return $rc
}

FAILED=0; SLOT=0
for s in $(echo "$SEEDS" | tr ',' ' '); do
  one "$s" "$SLOT" &
  SLOT=$((SLOT + 1))
  if [ "$SLOT" -ge "$PAR" ]; then wait; SLOT=0; fi
done
wait
grep -l "^FAIL" "$OUT"/fort-*.log 2>/dev/null | sed 's/^/failed: /'
exit 0
