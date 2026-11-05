#!/usr/bin/env bash
# runner/ci/bin/judge_run.sh: the judge's two steps, shared by score.yml's early-judge job (before any game) and its
# judge job (after scoring), so the two can't drift apart. Run from the checkout of the submission (fetch-depth 0).
#
#   judge_run.sh prior DIR               prior work for the judge (public data only) -> DIR/prior, DIR/who/deps.json
#       env: DFBENCH_YUKON_API YUKON_API_KEY GITHUB_TOKEN DFBENCH_OPS_REPO DFBENCH_SEASON; reads DIR/who/submitter.json
#   judge_run.sh judge DIR [SCORE_JSON]  runner/judge -> DIR/dossier.json, DIR/summary.md (SCORE_JSON is context only)
#       env: DFBENCH_JUDGE_OPENROUTER_KEY DFBENCH_JUDGE_MODEL (the judge's own key: only the judge step gets it)
set -euo pipefail
cmd=${1:?prior|judge}; d=${2:?dir}
base=$(git merge-base HEAD origin/main)
case "$cmd" in
  prior)
    # base producer: Yukon's incumbent (promoted); the leader file's submission only if Yukon can't be read.
    # The overlap scan compares each published submission's added lines with this diff; if Yukon or git fail it
    # degrades to the fixed context and says so in DIR/prior/_scan.json. Declared dependencies: Yukon shows them to the
    # organiser only once the submission is published, so re-read them now; never fatal.
    sub=$(python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["submission"])' "$d/who/submitter.json")
    python3 -I runner/ci/bin/tier.py attribution --submission "$sub" --out-dir "$d/who" || true
    python3 -I runner/ci/bin/prior.py --submitter-json "$d/who/submitter.json" --out "$d/prior" --last 5 --repo-dir . \
      --base "$base" --head HEAD --scan-max 500 --scan-top 4 --scan-timeout 300 \
      --fallback-base-producers "$(python3 -I runner/ci/bin/ledger.py leader-get --field submission || true)"
    ;;
  judge)
    producers=$(cat "$d/prior/base_producers.txt" 2>/dev/null || true)
    python3 -I - "$d/who/submitter.json" > "$d/who/args.env" <<'PY'
import json, shlex, sys
r = json.load(open(sys.argv[1]))
print("COAUTHORS=" + shlex.quote(",".join(r.get("coauthors") or [])))
print("SUBMITTER=" + shlex.quote(r["username"]))
PY
    . "$d/who/args.env"
    score=(); [ -n "${3:-}" ] && score=(--score-json "$3")
    python3 -I runner/judge/judge.py --repo-dir . --base "$base" --head HEAD \
      --note "$d/who/note.md" --dependencies "$d/who/deps.json" --coauthors "$COAUTHORS" --submitter "$SUBMITTER" \
      --context-dir "$d/prior" --base-producers "$producers" ${score[@]+"${score[@]}"} \
      --out "$d/dossier.json" --md "$d/summary.md"
    # the verdict is read from the dossier (emit_score.py / early_judge.py), never from the exit code
    ;;
  *) echo "judge_run.sh: unknown command $cmd" >&2; exit 2 ;;
esac
