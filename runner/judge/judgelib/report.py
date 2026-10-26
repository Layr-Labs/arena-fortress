"""dossier.json and the markdown summary (for the PR comment)."""
import re

from . import JUDGE_VERSION

ICON = {"pass": "PASS", "fail": "FAIL", "hold": "HOLD"}


def _md(s, n=300):
    """Untrusted text into markdown: one line, no HTML, no @-mentions, no links, no code-span breakouts."""
    s = " ".join(str(s or "").split())[:n]
    s = s.replace("`", "'").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|")
    s = re.sub(r"@(?=[A-Za-z0-9_-])", "@​", s)
    s = re.sub(r"(?i)\b(https?|ftp)://", r"\1[:]//", s)
    s = s.replace("[", "\\[").replace("]", "\\]")
    return s


def _ev(e):
    loc = e["source"] + (f":{e['line']}" if e.get("line") else "")
    return f"`{_md(loc, 120)}`"


def markdown(d):
    v = d["verdict"]
    lines = [f"### dfbench judge: **{ICON[v]}**", ""]
    lines.append({"pass": "Promotable: no fatal or major finding.",
                  "fail": "Not promoted: a fatal finding was confirmed by the adjudicator (reasons below). "
                          "Organisers can overturn this.",
                  "hold": "Not promoted until an organiser reviews it."}[v])
    lines.append("")
    for r in d["reasons"]:
        lines.append(f"- {_md(r, 600)}")
    fs = d.get("findings") or []
    if fs:
        lines += ["", "| id | check | severity | ruling | finding | evidence |", "|---|---|---|---|---|---|"]
        rul = d.get("rulings") or {}
        for f in sorted(fs, key=lambda f: ({"fatal": 0, "major": 1, "minor": 2}[f["severity"]], f["id"])):
            r = rul.get(f["id"], {}).get("ruling", "") if f["severity"] == "fatal" else ""
            lines.append(f"| {f['id']} | {f['check']} | {f['severity']} | {r} | {_md(f['title'], 160)} | "
                         + ", ".join(_ev(e) for e in f["evidence"][:4]) + " |")
        conf = [f for f in fs if f["id"] in (d.get("confirmed") or [])]
        for f in conf:
            r = rul.get(f["id"], {})
            lines += ["", f"**{f['id']}** ({_md(f['rule'], 80)}): {_md(f['explanation'], 900)}",
                      f"Adjudicator: {_md(r.get('reason', ''), 900)}"]
    sig = d.get("signals") or []
    high = [s for s in sig if s["level"] == "high"]
    if high:
        lines += ["", "Pre-scan signals that block promotion pending review: "
                  + ", ".join(f"{s['id']} {s['kind']} at `{_md(s['file'], 100)}" + (f":{s['line']}" if s.get('line') else "") + "`"
                              for s in high[:10])]
    u = d["usage"]
    lines += ["", f"<sub>{JUDGE_VERSION} · {d['config'].get('provider')} `{_md(d['config'].get('model'), 80)}` · "
              f"{u['calls']} calls · {u['prompt_tokens']} in / {u['completion_tokens']} out tokens · "
              f"${u['cost_usd']:.4f}{' (partial: some costs unknown)' if u['cost_unknown'] else ''} · "
              f"head `{d['inputs']['head'][:12]}` · rubric `{d['versions']['prompts_sha256'][:12]}`</sub>"]
    return "\n".join(lines) + "\n"
