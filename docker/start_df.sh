#!/bin/bash
# Container replacement for upstream start_df.sh: no systemd-run (memory cap comes from `docker run --memory`).
. "$(dirname "$0")/instance.sh" || exit 1
cd "$DF" || exit 1
exec env -u DISPLAY DFHACK_HEADLESS=1 DFHACK_PORT="$DFHACK_PORT" ./dfhack < /dev/null > "$DF_LOG" 2>&1
