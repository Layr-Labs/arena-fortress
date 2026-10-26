#!/bin/bash
# .yukon/run.sh: what `yukon run` runs on a competitor's machine (challenge/benchmark.json benchmarkCommand).
# Plays the public suite (runner/suites/season0-public.json) with submission/ through the same three-container stack
# as the verifier, scores it with the same trusted scorer, and writes .yukon/score.json. Local scores are a guide:
# public forts, not ranked.
#
# env: DFBENCH_PROVIDER_KEY or OPENROUTER_API_KEY   your model key (only the gateway container gets it)
#      DFBENCH_PARALLEL  games at once (default 1; budget ~3 GB + 1 vCPU per DF plus the harness's 1 vCPU / 2 GB)
#      DFBENCH_GAME_IMAGE  the DF image from .yukon/setup.sh (default yukon-df:s0)
# Extra arguments go to `dfbench local suite` (e.g. --games LT01 --n 1, --stages 1).
set -euo pipefail
cd "$(dirname "$0")/.."
export DFBENCH_GAME_IMAGE=${DFBENCH_GAME_IMAGE:-yukon-df:s0}
[ -n "${DFBENCH_PROVIDER_KEY:-}${OPENROUTER_API_KEY:-}" ] || {
  echo "set DFBENCH_PROVIDER_KEY (or OPENROUTER_API_KEY) to your model key" >&2; exit 2; }
OUT=.yukon/runs/$(date +%Y%m%d-%H%M%S)
python3 runner/dfbench local suite --harness submission/ --out "$OUT" --parallel "${DFBENCH_PARALLEL:-1}" "$@"
cp "$OUT/score.json" .yukon/score.json
echo "[run] score: $(python3 -c 'import json;s=json.load(open(".yukon/score.json"));print(s["score"], s["metrics"].get("stage"))')"
echo "[run] games and artifacts: $OUT"
