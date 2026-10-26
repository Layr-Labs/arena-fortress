#!/bin/bash
# fake_ncpu.sh N CMD...: run CMD with the machine's CPU count faked to N (research/seed-portability.md).
# Needs a privileged container (bind mounts over /sys and /proc). Replaces what glibc's get_nprocs() /
# sysconf(_SC_NPROCESSORS_*) read (/sys/devices/system/cpu/{online,possible,present}, /proc/stat, /proc/cpuinfo) with an
# N-CPU view, so a host can be made to look like another host's CPU count. The affinity mask is left alone (world gen
# stays pinned by make_embark.sh). Test only: the mounts last for the container's life.
set -eu
N=$1; shift
d=$(mktemp -d)
echo "0-$((N - 1))" > "$d/online"
awk -v n="$N" 'BEGIN{RS=""; ORS="\n\n"} NR==1{b=$0} END{for(i=0;i<n;i++){x=b; sub(/processor[ \t]*: [0-9]+/, "processor\t: " i, x); print x}}' /proc/cpuinfo > "$d/cpuinfo"
awk -v n="$N" 'NR==1{print; c=$0; next} /^cpu[0-9]/{if(!done){for(i=0;i<n;i++){l=c; sub(/^cpu /, "cpu" i " ", l); print l}; done=1}; next} {print}' /proc/stat > "$d/stat"
for f in online possible present; do mount --bind "$d/online" /sys/devices/system/cpu/$f; done
mount --bind "$d/cpuinfo" /proc/cpuinfo
mount --bind "$d/stat" /proc/stat
echo "fake_ncpu: getconf=$(getconf _NPROCESSORS_ONLN) conf=$(getconf _NPROCESSORS_CONF) nproc=$(nproc) python=$(python3 -c 'import os; print(os.cpu_count())')" >&2
exec "$@"
