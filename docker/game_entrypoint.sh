#!/bin/bash
# The game service's entrypoint (docker/Dockerfile.game): the API server owns DF's lifecycle (it sets the task's
# d_init tokens, then reset_fort.sh starts DF headless via docker/start_df.sh). Input: DFBENCH_GAME (the runner's
# JSON), or options / GAMEAPI_* env vars (python3 -m gameapi.server --help).
#   (no args) or --options     -> python3 -m gameapi.server [options]
#   a command (compose `command: [python3, -u, -m, gameapi.server, ...]`) -> run as given
set -e
cd /root/dfprobe
mkdir -p df/save
if [ $# -eq 0 ] || [ "${1#-}" != "$1" ]; then
  exec python3 -u -m gameapi.server "$@"
fi
exec "$@"
