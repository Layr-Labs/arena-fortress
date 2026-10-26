# instance.sh: source me. Resolves which DF game directory + DFHack port this process drives.
#
#   DF_INSTANCE unset or 0 -> $DFP/df                  port 5000, log $DFP/df_run.log   (original single-instance layout)
#   DF_INSTANCE=N (N>=1)   -> $DFP/instances/N/df      port 5000+N, log $DFP/instances/N/df_run.log
#
# Instance dirs are synced from $DFP/df (minus fortress saves) by ensure_instance, so the base install stays the
# single source of truth and later prefs/config/DFHack changes reach every instance. Every DF process is told its
# port via DFHACK_PORT (honoured by both the DFHack server and dfhack-run), so instances never cross-talk.
# Linux only for N>=1 (/proc, rsync). In Docker use one container per instance instead (docker/batch.sh).
DFP=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)   # physical path: /proc/<pid>/cwd reports one too
DF_INSTANCE=${DF_INSTANCE:-0}
case "$DF_INSTANCE" in ''|*[!0-9]*) echo "DF_INSTANCE must be a non-negative integer, got '$DF_INSTANCE'" >&2; return 1 2>/dev/null || exit 1;; esac
if [ "$DF_INSTANCE" = 0 ]; then
  DF_HOME=$DFP
else
  DF_HOME=$DFP/instances/$DF_INSTANCE
fi
DF=$DF_HOME/df
DF_LOG=$DF_HOME/df_run.log
export DFP DF_INSTANCE DF DF_LOG
export DFHACK_PORT=$((5000 + DF_INSTANCE))

# ensure_instance: sync $DF from the base install (saves excluded, except the world region if the base has one).
# Idempotent, so an interrupted sync is finished by the next call. Call it only while this instance's DF is stopped.
ensure_instance() {
  [ "$DF_INSTANCE" = 0 ] && return 0
  [ -x "$DFP/df/dwarfort" ] || { echo "base install $DFP/df missing" >&2; return 1; }
  command -v rsync >/dev/null || { echo "rsync is required for DF_INSTANCE >= 1" >&2; return 1; }
  mkdir -p "$DF/save" &&
    rsync -a --delete --exclude '/save/' --exclude '/*.log' --exclude '/gamelog.txt' \
      --exclude '/dfhack-config/df-ai.json' "$DFP/df/" "$DF/" || return 1
  # region1 is only needed by gen.sh-style flows: fort_start_snapshot carries its own world.sav
  if [ -d "$DFP/df/save/region1" ]; then rsync -a --delete "$DFP/df/save/region1/" "$DF/save/region1/" || return 1; fi
}

# df_pids: dwarfort processes whose cwd is THIS instance's game dir (never another instance's).
df_pids() {
  local p
  for p in $(pgrep -x dwarfort); do
    [ "$(readlink -f "/proc/$p/cwd" 2>/dev/null)" = "$DF" ] && echo "$p"
  done
}

# port_in_use: something already listens on our DFHack port (bash /dev/tcp: no ss/netstat needed)
port_in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$DFHACK_PORT") 2>/dev/null; }
