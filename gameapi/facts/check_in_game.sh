#!/bin/bash
# check_in_game.sh: the facts layer's in-game check. Builds the DF image from this checkout (docker/README.md),
# starts one container, loads scenarios/snapshots/scripted-y1, runs gameapi/facts/check_in_game.py in it, prints
# its JSON lines (also saved to $OUT) and removes the container.
#   gameapi/facts/check_in_game.sh [--no-build]     env: TAG (image tag), NAME (container), OUT (log file), DL (~/df-dl)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
TAG=${TAG:-yukon-df:s0facts-$(git -C "$ROOT" rev-parse --short HEAD)}
NAME=${NAME:-s0facts-check}
OUT=${OUT:-$ROOT/gameapi/facts/in_game.jsonl}
DL=${DL:-$HOME/df-dl}
if [ "${1:-}" != "--no-build" ]; then
  docker buildx build --platform linux/amd64 --build-context dl="$DL" --build-context harness="$ROOT" \
    -f "$ROOT/docker/Dockerfile" -t "$TAG" --load "$ROOT/docker"
fi
docker rm -f "$NAME" >/dev/null 2>&1 || true
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$NAME" --platform linux/amd64 --security-opt seccomp=unconfined \
  --memory 2500m --memory-swap 2500m "$TAG" >/dev/null
docker exec "$NAME" bash -c 'mkdir -p df/save && SNAPSHOT=scenarios/snapshots/scripted-y1 ./reset_fort.sh'
set +e
docker exec "$NAME" bash -c 'python3 -m unittest discover -s gameapi/facts/tests 2>&1 | tail -3; python3 gameapi/facts/check_in_game.py' | tee "$OUT"
rc=${PIPESTATUS[0]}
echo "check_in_game: exit $rc, log $OUT"
exit $rc
