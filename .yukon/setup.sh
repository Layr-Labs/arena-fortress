#!/bin/bash
# .yukon/setup.sh: what `yukon setup` runs on a competitor's machine (challenge/benchmark.json setupCommand).
# Builds the DF image from your own DF 53.16 + DFHack 53.16-r2 download, the trusted gateway image, the public
# start forts (labs, MY1, OP1), and checks that submission/ builds. Idempotent: finished steps are skipped.
#
# env: DFBENCH_DF_DL      dir with df_53_16_linux.tar.bz2 and dfhack-53.16-r2-Linux-64bit.tar.bz2 (default ~/df-dl)
#      DFBENCH_DF_BASE_IMAGE the plain DF image the fort builders use (docker/Dockerfile; default yukon-df:s0-base)
#      DFBENCH_GAME_IMAGE    the game server image the runner plays (docker/Dockerfile.game on the base; default
#                            yukon-df:s0, what .yukon/run.sh and `dfbench local run --stack real` expect)
#      DFBENCH_ALLOW_BUSY=1  build the MY1 forts even if other containers are running (dfpool refuses by default,
#                            because a busy host slows the 120 automation days; fine if your machine has room)
#      DFBENCH_PUBLIC_SEEDS  public pool seeds for the lab forts (default 2001,2002,2005)
#      DFBENCH_MY1_SEEDS     public seeds for the MY1 day-120 forts (default 2001,2002,2005; the MY1 task files name
#                            these three)
#      DFBENCH_SMOKE=0       skip the closing smoke game (real DF, fake model, 3 game-days of LT01, $0, a few minutes)
set -euo pipefail
cd "$(dirname "$0")/.."
DL=${DFBENCH_DF_DL:-$HOME/df-dl}
BASE=${DFBENCH_DF_BASE_IMAGE:-yukon-df:s0-base}
IMAGE=${DFBENCH_GAME_IMAGE:-yukon-df:s0}
SEEDS=${DFBENCH_PUBLIC_SEEDS:-2001,2002,2005}
say() { echo "[setup] $*"; }

command -v docker >/dev/null || { echo "docker is required" >&2; exit 2; }
docker compose version >/dev/null || { echo "docker compose v2 is required" >&2; exit 2; }
for f in df_53_16_linux.tar.bz2 dfhack-53.16-r2-Linux-64bit.tar.bz2; do
  [ -s "$DL/$f" ] || { echo "missing $DL/$f: download DF 53.16 and DFHack 53.16-r2 (docker/README.md)" >&2; exit 2; }
done

# an older setup tagged the plain DF image as $IMAGE: keep it as the base instead of rebuilding
if ! docker image inspect "$BASE" >/dev/null 2>&1 && docker image inspect "$IMAGE" >/dev/null 2>&1 \
   && ! docker run --rm --platform linux/amd64 --entrypoint test "$IMAGE" -d /root/dfprobe/df/save 2>/dev/null; then
  say "reusing the existing plain DF image $IMAGE as the base $BASE"
  docker tag "$IMAGE" "$BASE"
fi
if docker image inspect "$BASE" >/dev/null 2>&1 && [ -z "${DFBENCH_REBUILD:-}" ]; then
  say "DF base image $BASE exists (DFBENCH_REBUILD=1 to rebuild)"
else
  say "building the DF base image $BASE (linux/amd64)"
  docker buildx build --platform linux/amd64 --build-context dl="$DL" --build-context harness=. \
    -f docker/Dockerfile -t "$BASE" --load docker
fi
# the game server image the runner plays: the base plus gameapi/ and df/save (cheap; rebuilt each time so it
# picks up this checkout's server)
say "building the game server image $IMAGE (docker/Dockerfile.game on $BASE)"
docker buildx build -q --platform linux/amd64 --build-context harness=. --build-arg BASE="$BASE" \
  -f docker/Dockerfile.game -t "$IMAGE" --load docker >/dev/null

say "building the gateway image"
docker build -q -t dfbench-gateway:local gateway/ >/dev/null

say "public lab forts (seeds $SEEDS)"
docker/task_forts.sh --image "$BASE" --seeds "$SEEDS" --recipes worked-y1,neglected-y1 --out scenarios/snapshots

if [ ! -d scenarios/snapshots/embark-default-fort-12345 ]; then
  say "OP1 start fort (embark-default-fort-12345)"
  docker/embark.sh --image "$BASE" --rules DEFAULT_FORT --seeds 12345
fi

MY1_SEEDS=${DFBENCH_MY1_SEEDS:-2001,2002,2005}
BUSY=(); [ "${DFBENCH_ALLOW_BUSY:-}" = 1 ] && BUSY=(--allow-busy)
MY1_FAILED=()
for s in ${MY1_SEEDS//,/ }; do
  if [ -f "scenarios/snapshots/my1-d120-$s/world.sav" ]; then
    say "MY1 fort my1-d120-$s exists"
    continue
  fi
  # the seed's embark, then DFHack automation plays it to day 120 (one DF container; ~10-30 min per fort)
  say "MY1 fort my1-d120-$s (embark + 120 days of automation)"
  python3 pool/dfpool build-public --task MY1 --seeds "$s" --image "$BASE" --prefix dfbench-my1 \
    --out scenarios/snapshots ${BUSY[@]+"${BUSY[@]}"} || true
  [ -f "scenarios/snapshots/my1-d120-$s/world.sav" ] || MY1_FAILED+=("$s")
done

say "checking that submission/ builds (no secrets in the build env)"
env -u DFBENCH_PROVIDER_KEY -u OPENROUTER_API_KEY -u TOGETHER_API_KEY docker build -q -t dfbench-harness:local submission/ >/dev/null
if [ ${#MY1_FAILED[@]} -gt 0 ]; then
  echo "[setup] MY1 forts not built for seed(s) ${MY1_FAILED[*]}: see scenarios/snapshots/my1-d120-<seed>.log." >&2
  echo "[setup]   If dfpool said other containers are running, re-run with DFBENCH_ALLOW_BUSY=1 (or stop them)." >&2
  echo "[setup]   DF also varies run to run, so a fort can fail its stock check once: re-run setup to retry," >&2
  echo "[setup]   or skip MY1 with DFBENCH_MY1_SEEDS=<seeds that built>. Everything else is ready." >&2
  exit 1
fi
if [ "${DFBENCH_SMOKE:-1}" != 0 ]; then
  say "smoke game: real DF + fake model, 3 game-days of LT01, \$0 (DFBENCH_SMOKE=0 to skip)"
  DFBENCH_GAME_IMAGE="$IMAGE" python3 runner/dfbench local smoke --harness submission/ ||
    { echo "[setup] the smoke game failed: fix what it says above before spending model credits." >&2; exit 1; }
fi
say "done. Next: .yukon/run.sh (or: runner/dfbench local run --harness submission/ --task scenarios/season0/lt01-drought.json)"
