"""The DF side of one game: reset, recorder and credit, scenario setup, score, advance, final reads.

It reuses smoke.py's functions (reset, score, advance with its popup and hang handling, daily_metrics, credit_start)
and copies run_one's setup and final-read steps, so a v3 game produces the same artifacts as the frozen loop.
The rules (gameapi/server/rules.py) only talk to a backend through these methods; tests use a fake one.
"""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DAY = 1200


def set_artifacts(df_dir, on):
    """[ARTIFACTS:YES|NO] in <df>/prefs/d_init.txt (DF reads it at start, so call this before reset_fort.sh).
    Returns the value written."""
    p = os.path.join(df_dir, "prefs", "d_init.txt")
    val = "YES" if on else "NO"
    with open(p, newline="") as f:
        text = f.read()
    new, n = re.subn(r"\[ARTIFACTS:[A-Z]+\]", f"[ARTIFACTS:{val}]", text)
    if n != 1:
        raise RuntimeError(f"{p}: expected one [ARTIFACTS:...] token, found {n}")
    if new != text:
        with open(p, "w", newline="") as f:
            f.write(new)
    return val


class DFBackend:
    """One DF instance (smoke.py's, selected by DF_INSTANCE). Import cost: smoke + harness modules."""

    def __init__(self):
        sys.path.insert(0, ROOT)
        import smoke as S, harness as H
        self.S, self.H = S, H

    def df_settings(self, task):
        return {"ARTIFACTS": "YES" if task.get("strange_moods") else "NO"}

    def prepare(self, task):
        """Settings, reset_fort.sh, recorder start. -> s0 = score.lua before the scenario setup (run_one's baseline)."""
        S, H = self.S, self.H
        dirs = {os.path.join(H.DFP, "df"), H.DF}   # the base install (instances sync from it) and this instance's
        for d in dirs:
            if os.path.isdir(os.path.join(d, "prefs")):
                set_artifacts(d, bool(task.get("strange_moods")))
        S.SCENARIO = task
        S.INTERRUPTIONS.clear(); S.INTERRUPTION_LOG.clear(); S.LAST_STOP.clear()
        S.reset()
        S.lua_json("recorder.lua", "start")
        return S.score()

    def setup(self, cmds):
        """run_one's scenario setup, verbatim: fails loudly (RuntimeError) on a failed command. -> outputs."""
        H = self.H
        outs = []
        for cmd in cmds:
            cmd = [os.path.join(H.DFP, c) if c.startswith("scenarios/") else c for c in cmd]
            r = subprocess.run(["./dfhack-run", *cmd], cwd=H.DF, capture_output=True, text=True,
                               timeout=H.DFHACK_TIMEOUT, errors="replace")
            out = H.ANSI.sub("", r.stdout + r.stderr).strip()
            outs.append(out[-200:])
            lua_failed = cmd[0] == "lua" and ("stack traceback" in out or re.search(r"^lua: ", out, re.M))
            if r.returncode != 0 or lua_failed:
                raise RuntimeError(f"scenario setup failed (rc={r.returncode}): {cmd}: {out[-200:]}")
        return outs

    def credit_start(self):
        return self.S.credit_start()

    def score(self):
        return self.S.score()

    def advance(self, ticks):
        """-> (ticks moved, tripwire stop dict or None, popups dismissed during it)."""
        S = self.S
        S.ADVANCE_STOP = None
        S.LAST_STOP.clear()
        n0 = len(S.INTERRUPTION_LOG)
        moved = S.advance(ticks)
        stop = dict(S.LAST_STOP) or None
        S.LAST_STOP.clear()
        S.INTERRUPTIONS.clear()
        return moved, stop, S.INTERRUPTION_LOG[n0:]

    def interrupt(self):
        """Pause DF now (wall cap): smoke.advance's poll sees the pause and returns."""
        try:
            self.H.dfhack("lua", "rawset(_G,'__adv_gen',(rawget(_G,'__adv_gen') or 0)+1) df.global.pause_state=true",
                          timeout=self.S.POLL_TIMEOUT)
        except subprocess.TimeoutExpired:
            pass

    def interruption_log(self):
        return list(self.S.INTERRUPTION_LOG)

    def final(self, outdir, stem, start, hung=False):
        """run_one's final reads: -> (sf, daily metrics, credit dump, error or None). Writes <stem>.daily.json and
        <stem>.credit.json as run_one does."""
        S = self.S
        sf, daily, credit, err = {}, {}, {}, None
        if hung:
            S.CALL_TIMEOUT = S.POLL_TIMEOUT
        try:
            sf = S.score()
            daily = S.daily_metrics(start, os.path.join(outdir, f"{stem}.daily.json"))
            credit = S.lua_json("credit.lua", "dump", "items")
            with open(os.path.join(outdir, f"{stem}.credit.json"), "w") as f:
                json.dump(credit, f)
        except Exception as e:   # noqa: BLE001  (as run_one: the row records it)
            err = f"final score failed: {e}"
        finally:
            S.CALL_TIMEOUT = None
        return sf, daily, credit, err

    def model_label(self):
        return {"provider_pin": self.H.PROVIDER, "instance": self.H.INSTANCE}
