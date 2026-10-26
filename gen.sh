#!/bin/bash
# usage: gen.sh <tag> <id> <seed> "<param title>" [display-mode: xvfb|none]
set -u
. "$(dirname "$0")/instance.sh" || exit 1
ensure_instance || exit 1
cd "$DF" || exit 1
. "$DFP/env.sh"
tag=$1; id=$2; seed=$3; title=$4; mode=${5:-none}
start=$(date +%s)
if [ "$mode" = xvfb ]; then
  runner=(xvfb-run -a -s "-screen 0 1280x800x24")
else
  runner=(env -u DISPLAY)
fi
timeout 1200 systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=0 \
  env LD_LIBRARY_PATH="$LD_LIBRARY_PATH" PATH="$PATH" "${runner[@]}" ./dwarfort -gen "$id" "$seed" "$title" > "$DF_HOME/gen_$tag.log" 2>&1
rc=$?
echo "tag=$tag rc=$rc secs=$(( $(date +%s) - start ))"
ls -la save/ "save/region$id" 2>&1 | head -30
ls -t | head -8
