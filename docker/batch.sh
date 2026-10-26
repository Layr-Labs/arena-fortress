#!/bin/bash
# docker/batch.sh: run a smoke.py batch as one container per run, up to P at a time, and collect the results.
# The Docker counterpart of `smoke.py --workers`: works anywhere Docker runs linux/amd64 images, including
# macOS on Apple Silicon (Docker Desktop with Rosetta). Plain bash 3.2 (macOS default); no GNU tools needed.
#
# usage: docker/batch.sh --out runs/<batch> [--image yukon-df] [--arms noop,scripted] [--runs 5] [--parallel 3]
#                        [--memory 4g] [--seed 12345] [--tag dfb-<out basename>] [--entry smoke.py] [--k-start 0]
#                        [-- <extra smoke.py args, e.g. --days 60 --scenario ...>]
# --entry bench/labrun.py runs lab tasks (hands-off window, witness arm); --tag sets the container-name prefix.
# --k-start K runs k = K .. K+runs-1 (one runner per k, e.g. a CI matrix job).
# Result: <out>/<arm>-<k>/ per run (summary.jsonl, step log, daily file, snapshots), then
#         python3 analyze.py <out>/*/
# Re-running skips runs whose summary has a completed row (crashed runs are retried).
set -u
IMAGE=yukon-df; ARMS=noop,scripted; RUNS=5; PAR=3; MEM=4g; SEED=12345; OUT=; EXTRA=(); TAG=; ENTRY=smoke.py; K0=0
while [ $# -gt 0 ]; do
  case "$1" in
    --image) IMAGE=$2; shift 2;; --arms) ARMS=$2; shift 2;; --runs) RUNS=$2; shift 2;;
    --parallel) PAR=$2; shift 2;; --memory) MEM=$2; shift 2;; --seed) SEED=$2; shift 2;;
    --out) OUT=$2; shift 2;; --tag) TAG=$2; shift 2;; --entry) ENTRY=$2; shift 2;; --k-start) K0=$2; shift 2;;
    --) shift; EXTRA=("$@"); break;;
    *) echo "unknown arg $1" >&2; exit 2;;
  esac
done
[ -n "$OUT" ] || { echo "--out is required" >&2; exit 2; }
mkdir -p "$OUT"
# Memory guard: Docker Desktop's VM defaults to 8 GB, and an overcommitted VM stalls DF for minutes.
# Budget ~1 GB per DF container (it grows with the fort) plus 2 GB for the VM itself.
VM_MB=$(( $(docker info --format '{{.MemTotal}}') / 1048576 ))
NEED_MB=$(( PAR * 1024 + 2048 ))
if [ "$NEED_MB" -gt "$VM_MB" ] && [ -z "${BATCH_IGNORE_MEMORY:-}" ]; then
  echo "--parallel $PAR needs ~${NEED_MB} MB but the Docker VM has ${VM_MB} MB (minus other containers)." >&2
  echo "Lower --parallel, raise Docker Desktop > Settings > Resources > Memory, or set BATCH_IGNORE_MEMORY=1." >&2
  exit 2
fi
TAG=${TAG:-dfb-$(basename "$OUT" | tr -c 'a-zA-Z0-9_.-' '-')}
# host-side metadata: commit, dirty tree, image digest, this checkout's harness key (bench/batch_meta.py)
python3 "$(dirname "$0")/../bench/batch_meta.py" start "$OUT" --image "$IMAGE" --parallel "$PAR" --arms "$ARMS" \
  --runs "$RUNS" -- ${EXTRA[*]:-} || exit 2
# Scenario files and snapshots referenced with host paths must be inside the image (build it from this repo)
# or passed by an in-container path; this script only forwards EXTRA to smoke.py unchanged.

done_ok() {  # $1 = run dir: has a summary row without a crash
  [ -f "$1/summary.jsonl" ] && python3 -c 'import json,sys
rows=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]
sys.exit(0 if any(not r.get("crashed") for r in rows) else 1)' "$1/summary.jsonl"
}

running() { docker ps -q --filter "name=^$TAG-" | wc -l | tr -d ' '; }

collect() {  # $1 = container name, $2 = run dir: copy results out once the container's job has exited
  docker cp "$1:/root/dfprobe/runs/job/." "$2/" >/dev/null 2>&1
  docker cp "$1:/root/dfprobe/job.log" "$2/job.log" >/dev/null 2>&1
  docker rm -f "$1" >/dev/null 2>&1
}

finish_exited() {  # collect every container of this batch whose smoke.py has finished
  local fc frun   # local: the launch loop's $c/$run must survive this call
  for fc in $(docker ps -a --filter "name=^$TAG-" --format '{{.Names}}'); do
    if ! docker exec "$fc" pgrep -f "$(basename "$ENTRY")" >/dev/null 2>&1; then
      frun=${fc#$TAG-}; collect "$fc" "$OUT/$frun"; echo "[$(date +%T)] done $frun"
    fi
  done
}

trap 'echo "interrupted: removing containers"; docker rm -f $(docker ps -aq --filter "name=^$TAG-") >/dev/null 2>&1; exit 130' INT TERM

k=$K0
while [ $k -lt $((K0 + RUNS)) ]; do
  for arm in $(echo "$ARMS" | tr ',' ' '); do
    run=$arm-$k; dir=$OUT/$run
    if done_ok "$dir"; then echo "skip $run (done)"; continue; fi
    while [ "$(running)" -ge "$PAR" ]; do sleep 20; finish_exited; done
    mkdir -p "$dir"; c=$TAG-$run
    docker rm -f "$c" >/dev/null 2>&1
    # {run} in LLM_BASE_URL becomes the container name: bench/bedrock_proxy.py's /r/<tag>/v1 per-run cost meter
    URL=(-e LLM_BASE_URL); [ -n "${LLM_BASE_URL:-}" ] && URL=(-e "LLM_BASE_URL=${LLM_BASE_URL//\{run\}/$c}")
    docker run -d --name "$c" --platform linux/amd64 --security-opt seccomp=unconfined ${DOCKER_RUN_EXTRA:-} \
      --memory "$MEM" --memory-swap "$MEM" -e OPENROUTER_API_KEY "${URL[@]}" -e LLM_API_KEY -e LLM_TIMEOUT "$IMAGE" >/dev/null || { echo "docker run failed for $run"; exit 1; }
    # the job starts detached; `sleep infinity` (the image CMD) keeps the container up until we collect it
    docker exec -d "$c" bash -c "mkdir -p df/save && cd /root/dfprobe && python3 $ENTRY --only $arm --runs 1 \
      --k-start $k --seed $SEED --out runs/job ${EXTRA[*]:-} > job.log 2>&1"
    echo "[$(date +%T)] started $run in $c"
    sleep 5
  done
  k=$((k + 1))
done
while [ "$(docker ps -aq --filter "name=^$TAG-" | wc -l | tr -d ' ')" -gt 0 ]; do sleep 20; finish_exited; done
# every run's container wrote the key of the files in its image: check they match each other and this checkout
python3 "$(dirname "$0")/../bench/batch_meta.py" check "$OUT"
echo "BATCH DONE: python3 analyze.py $OUT/*/"
