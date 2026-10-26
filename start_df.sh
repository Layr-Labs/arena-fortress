#!/bin/bash
# start DF+DFHack headless, memory-capped, portable mode. Blocks; run in background.
# Instance selected by DF_INSTANCE (see instance.sh); reset_fort.sh creates and syncs it first.
. "$(dirname "$0")/instance.sh" || exit 1
cd "$DF" || exit 1
. "$DFP/env.sh"
exec systemd-run --user --scope -q --unit="dfprobe-i$DF_INSTANCE-$(date +%s)" -p MemoryMax=3G -p MemorySwapMax=0 \
  env -u DISPLAY LD_LIBRARY_PATH="$LD_LIBRARY_PATH" DFHACK_HEADLESS=1 DFHACK_PORT="$DFHACK_PORT" ./dfhack < /dev/null > "$DF_LOG" 2>&1
