#!/bin/bash
# vnc_stdio.sh PASSWORD: one --watch-live viewer over stdin/stdout. The runner's 127.0.0.1 listener runs this with
# `compose exec -T game` per connection, so no container port is ever published. x11vnc listens on the container's
# own loopback only (the harness can't reach it: other network namespace), view-only, password-protected.
pw=${1:?password}
if ! pgrep -x x11vnc >/dev/null; then
  x11vnc -display :99 -localhost -rfbport 5900 -forever -shared -viewonly -nossl -passwd "$pw" -quiet \
    -bg -o /tmp/x11vnc.log >/dev/null 2>&1 || exit 1
fi
exec python3 -c '
import os, select, socket, sys, time
for _ in range(50):
    try:
        s = socket.create_connection(("127.0.0.1", 5900)); break
    except OSError:
        time.sleep(0.2)
else:
    sys.exit(1)
fds = [0, s.fileno()]
while True:
    r, _, _ = select.select(fds, [], [])
    if 0 in r:
        b = os.read(0, 65536)
        if not b: break
        s.sendall(b)
    if s.fileno() in r:
        b = s.recv(65536)
        if not b: break
        os.write(1, b)
'
