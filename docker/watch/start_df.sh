#!/bin/bash
# Watch mode's start_df.sh (docker/Dockerfile.watch): DF rendered into Xvfb :99 instead of headless, and an ffmpeg
# recording of the display into /artifacts/video/ (the game's artifacts mount; the runner post-processes it).
# Xvfb and ffmpeg outlive DF restarts (the server resets DF at least once per game), so a game is one recording;
# if ffmpeg ever restarts, its segments are joined by finish.sh.
. "$(dirname "$0")/instance.sh" || exit 1
cd "$DF" || exit 1
export DISPLAY=:99
W=${DFWATCH_SIZE:-1200x800}
if ! pgrep -x Xvfb >/dev/null; then
  Xvfb :99 -screen 0 "${W}x24" -nolisten tcp > /tmp/xvfb.log 2>&1 &
  for _ in $(seq 1 50); do [ -e /tmp/.X11-unix/X99 ] && break; sleep 0.2; done
fi
if ! pgrep -x ffmpeg >/dev/null && [ ! -e /tmp/dfwatch.stopped ]; then
  mkdir -p /artifacts/video
  # fragmented mp4 with a keyframe every 2 s: the file is playable up to the last fragment even if ffmpeg is killed
  setsid ffmpeg -nostdin -loglevel error -f x11grab -draw_mouse 0 -framerate 10 -video_size "$W" -i :99 \
    -c:v libx264 -preset veryfast -crf 26 -g 20 -pix_fmt yuv420p -flush_packets 1 \
    -movflags +frag_keyframe+empty_moov+default_base_moof "/artifacts/video/rec-$(date +%s%N).mp4" \
    > /tmp/ffmpeg.log 2>&1 < /dev/null &
fi
exec env DFHACK_PORT="$DFHACK_PORT" ./dfhack < /dev/null > "$DF_LOG" 2>&1
