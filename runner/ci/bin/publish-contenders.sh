#!/usr/bin/env bash
# Organiser, on the organiser's box: regenerate CONTENDERS.md from the ops store (runner/ci/bin/band.py publish;
# aggregates only) and push it, as one signed commit, to the `contenders` branch of the challenge repo. That branch
# isn't part of the trusted tree (DFBENCH_TRUSTED_TREE covers main), so publishing never stales a submission.
# infra/RUNBOOK.md §2.7. Needs: gh (admin on BENCH), the ops repo readable with your gh token, the SSH signing key.
set -euo pipefail
R=${DFBENCH_BENCH_REPO:-Layr-Labs/dfbench-challenge}
SIGN=${DFBENCH_SIGNING_KEY:-$HOME/.ssh/vdi.pub}
HERE=$(cd "$(dirname "$0")" && pwd)
D=$(mktemp -d); trap 'rm -rf "$D"' EXIT
GH=(-c credential.helper= -c "credential.helper=!gh auth git-credential")
GITHUB_TOKEN=${GITHUB_TOKEN:-$(gh auth token)} DFBENCH_OPS_REPO=${DFBENCH_OPS_REPO:?set DFBENCH_OPS_REPO} \
  DFBENCH_SEASON=${DFBENCH_SEASON:?set DFBENCH_SEASON (s0-dev on Yukon dev, s0 on prod)} \
  python3 -I "$HERE/band.py" publish --out "$D/CONTENDERS.md" --repo "$R"
if git "${GH[@]}" clone -q --branch contenders "https://github.com/$R.git" "$D/repo" 2>/dev/null; then :; else
  git "${GH[@]}" clone -q "https://github.com/$R.git" "$D/repo"
  git -C "$D/repo" checkout -q --orphan contenders && git -C "$D/repo" rm -rq . >/dev/null
fi
cp "$D/CONTENDERS.md" "$D/repo/CONTENDERS.md"
cd "$D/repo"
git add CONTENDERS.md
if git diff --cached --quiet; then echo "CONTENDERS.md unchanged"; exit 0; fi
git -c gpg.format=ssh -c user.signingkey="$SIGN" commit -q -S -m "Contender band $(date -u +%Y-%m-%d)"
git "${GH[@]}" push -q origin HEAD:contenders
echo "published https://github.com/$R/blob/contenders/CONTENDERS.md"
