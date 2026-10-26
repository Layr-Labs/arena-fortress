"""DFHack I/O for the facts layer: `dfhack-run` in the DF directory (the same mechanism as harness.dfhack()).

Runs inside the game container, next to DF. Tests pass a fake with the same two methods (run, write_blueprint).
"""
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
LUA_DIR = os.path.join(HERE, "lua")
REPO = os.path.dirname(os.path.dirname(HERE))
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class DFHack:
    """dfhack-run in df_dir (default $DFBENCH_DF_DIR, else <repo>/df, the image's layout)."""

    def __init__(self, df_dir=None, timeout=None):
        self.df_dir = df_dir or os.environ.get("DFBENCH_DF_DIR") or os.path.join(REPO, "df")
        # harness.DFHACK_TIMEOUT: waiting is safer than retrying (a timed-out command may still run later)
        self.timeout = timeout or int(os.environ.get("DFHACK_TIMEOUT", "180"))
        self.blueprint_dir = os.path.join(self.df_dir, "dfhack-config", "blueprints")

    def run(self, *args, with_stderr=False):
        r = subprocess.run(["./dfhack-run", *map(str, args)], cwd=self.df_dir, capture_output=True, text=True,
                           timeout=self.timeout, errors="replace")
        out = r.stdout + ("\n" + r.stderr if with_stderr and r.stderr.strip() else "")
        return ANSI.sub("", out).strip()

    def write_blueprint(self, name, text):
        os.makedirs(self.blueprint_dir, exist_ok=True)
        with open(os.path.join(self.blueprint_dir, name), "w") as f:
            f.write(text)


def lua_json(df, script, *args):
    """Run lua/<script> with args; parse the one JSON object it prints. A broken probe is an internal_error dict."""
    raw = df.run("lua", "-f", os.path.join(LUA_DIR, script), *map(str, args))
    try:
        return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except ValueError:
        return {"ok": False, "error_code": "internal_error", "error": "the game-side script failed: " + raw[-300:]}


def compact(v):
    """JSON for a Lua argument: one argv element, no spaces."""
    return json.dumps(v, separators=(",", ":"))
