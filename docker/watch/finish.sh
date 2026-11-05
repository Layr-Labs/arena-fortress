#!/bin/bash
# finish.sh IN_DIR OUT_DIR NAME [--no-4x]: join IN_DIR/rec-*.mp4 (fragmented, from start_df.sh) into OUT_DIR/NAME.mp4
# (standard mp4, moov first: plays in browsers) and OUT_DIR/NAME-4x.mp4 (4x speed); then print one JSON line from
# ffprobe of NAME.mp4. The runner runs it in a throwaway container of the watch image (its own ffmpeg).
set -euo pipefail
in=$1 out=$2 name=$3 fast=${4:-}
mkdir -p "$out"
mapfile -t segs < <(ls "$in"/rec-*.mp4 2>/dev/null | sort)
[ ${#segs[@]} -gt 0 ] || { echo '{"error": "no recording"}'; exit 2; }
list=$(mktemp)
for s in "${segs[@]}"; do [ -s "$s" ] && printf "file '%s'\n" "$s" >> "$list"; done
ffmpeg -nostdin -loglevel error -y -f concat -safe 0 -i "$list" -c copy -movflags +faststart "$out/$name.mp4"
if [ "$fast" != "--no-4x" ]; then
  ffmpeg -nostdin -loglevel error -y -i "$out/$name.mp4" -vf "setpts=PTS/4,fps=20" -an -c:v libx264 -preset veryfast \
    -crf 26 -pix_fmt yuv420p -movflags +faststart "$out/$name-4x.mp4"
fi
ffprobe -v error -select_streams v:0 -count_packets \
  -show_entries stream=width,height,nb_read_packets:format=duration -of json "$out/$name.mp4" | tr -d '\n '
echo
