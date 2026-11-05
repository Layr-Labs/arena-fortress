#!/bin/bash
# Stop the recording cleanly before teardown (the runner calls it with `compose exec game`): SIGINT lets ffmpeg write
# its last fragment; it is killed after 10 s. No new recording starts after this (DF restarts don't re-arm it).
touch /tmp/dfwatch.stopped
pkill -INT -x ffmpeg || exit 0
for _ in $(seq 1 50); do pgrep -x ffmpeg >/dev/null || exit 0; sleep 0.2; done
pkill -KILL -x ffmpeg
exit 0
