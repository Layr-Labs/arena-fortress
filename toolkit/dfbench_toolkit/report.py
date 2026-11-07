"""inspect: Markdown and self-contained HTML reports."""
import html, statistics

from . import analysis, scoring

DAYS_PER_YEAR = 336


def suite_summary(run):
    tv, sv, bs, src = scoring.agg(run.dir)
    by_task = run.by_task()
    rows = []
    for t in run.tasks:
        gs = by_task.get(t["id"]) or []
        allg = [g for g in run.games if g.task == t["id"]]
        if not allg:
            continue
        row = {"task": t["id"], "kind": t["kind"], "n_ok": len(gs), "n": len(allg)}
        if gs:
            row["value"] = round(tv(t, gs, run.anchors), 1)
            if t["kind"] == "lab":
                ps = [g["partial"] for g in gs]
                row.update(partial_mean=round(statistics.mean(ps), 3),
                           partial_sd=round(statistics.stdev(ps), 3) if len(ps) > 1 else None,
                           passed=sum(bool(g.get("passed")) for g in gs))
            else:
                os_ = [g["O"] for g in gs]
                row.update(O_mean=round(statistics.mean(os_), 1),
                           O_sd=round(statistics.stdev(os_), 1) if len(os_) > 1 else None,
                           tiers=[sum(g.get("tier") == i for g in gs) for i in range(5)])
        cost = [float(((r := run.records.get(g.id)) or {}).get("ledger", {}).get("cost_usd") or 0) for g in allg]
        wall = [float(g.rec.get("wall_s") or 0) for g in allg]
        row.update(cost_per_game=round(statistics.mean(cost), 4) if cost else None,
                   wall_min_per_game=round(statistics.mean(wall) / 60, 1) if wall else None)
        rows.append(row)
    point, fam = sv(by_task, run.tasks, run.weights, run.anchors)
    lb = ub = None
    if point is not None:
        b = run.bootstrap_cfg
        lb, ub = bs(by_task, run.tasks, run.weights, run.anchors, int(b.get("resamples", 10000)),
                    int(b.get("seed", 0)), float(b.get("alpha", 0.05)))
    days = sum(float(g.summary.get("days_played") or 0) for g in run.games)
    cost = sum(float((run.records.get(g.id) or {}).get("ledger", {}).get("cost_usd") or 0) for g in run.games)
    return {"rows": rows, "point": point, "lb95": lb, "ub95": ub, "families": fam, "source": src,
            "scored_by": run.scored_by, "complete": all(t["id"] in by_task for t in run.tasks),
            "credits_per_game_year": round(cost / (days / DAYS_PER_YEAR), 4) if days else None,
            "games": len(run.games), "ok": len(run.ok_records())}


def _f(v, d=1):
    if v is None:
        return "–"
    return f"{v:.{d}f}" if isinstance(v, float) else str(v)


# ---------------------------------------------------------------- Markdown

def md_suite(run, s):
    L = [f"# dfbench run report: `{run.label}`", "",
         f"{s['games']} games, {s['ok']} scored. Scores by the {s['source']}; per-game records from the "
         f"{s['scored_by']}.", ""]
    if s["point"] is not None:
        tag = "" if s["complete"] else " (subset of the suite: the bound covers the families present)"
        L += [f"**S = {_f(s['point'], 2)}**, one-sided 95% lower bound **{_f(s['lb95'], 2)}** "
              f"(upper {_f(s['ub95'], 2)}){tag}. Families: "
              + ", ".join(f"{k} {v:.1f}" for k, v in s["families"].items()) + ".", ""]
    L += ["| task | n | score | detail | credits/game | wall min/game |", "|---|---|---|---|---|---|"]
    for r in s["rows"]:
        if r["kind"] == "lab":
            det = (f"pass {r.get('passed', 0)}/{r['n_ok']}, partial {_f(r.get('partial_mean'), 2)}"
                   f" ± {_f(r.get('partial_sd'), 2)}") if r["n_ok"] else "no scored games"
        else:
            det = (f"O {_f(r.get('O_mean'))} ± {_f(r.get('O_sd'))}, tiers 0-4 "
                   f"{','.join(map(str, r.get('tiers', [])))}") if r["n_ok"] else "no scored games"
        L.append(f"| {r['task']} | {r['n_ok']}/{r['n']} | {_f(r.get('value'))} | {det} | "
                 f"${_f(r.get('cost_per_game'), 3)} | {_f(r.get('wall_min_per_game'))} |")
    if s["credits_per_game_year"] is not None:
        L += ["", f"Model credits: ${s['credits_per_game_year']:.3f} per game-year (cap $0.50)."]
    return L


def md_game(g):
    o = g["outcome"]
    L = ["", f"## {g['id']}  (task {g['task']}, k {g['k']}, seed {g['seed']})", "",
         f"- status **{o.get('status')}**, finished by {g['finished_by'] or '–'}; days {_f(g['days'])} of "
         f"{g['days_target']}; wall {_f(g['wall_s'])} s of {_f(g['wall_cap_s'])} s"
         + (" (**wall-capped**)" if g["wall_capped"] else "")
         + f"; harness {g['harness'].get('status', '–')} (exit {g['harness'].get('exit_code', '–')})"]
    if o.get("notes"):
        L.append(f"- notes: {'; '.join(map(str, o['notes']))}")
    if "O" in o:
        s = o.get("s") or {}
        L.append(f"- outcome **O {o['O']}**, tier {o.get('tier')}/4: survival {_f(s.get('survival'), 2)}, "
                 f"supply {_f(s.get('supply'), 2)}, wellbeing {_f(s.get('wellbeing'), 2)}, "
                 f"growth {_f(s.get('growth'), 2)}")
        if o.get("gates"):
            L.append("- gates: " + " ".join(f"G{i + 1} {'✓' if x else '✗'}" for i, x in enumerate(o["gates"])))
        if o.get("failed_gate"):
            L.append(f"- first gate not passed: {o['failed_gate']}")
        for w in o.get("gate_why") or []:
            L.append(f"  - {w}")
    if "partial" in o:
        cl = o.get("clauses")
        cls = " ".join(("✓" if c else "✗" if c is not None else "·") for c in cl) if cl else "–"
        L.append(f"- lab: **{'PASS' if o.get('passed') else 'fail'}**, partial {_f(o['partial'], 3)}; clauses {cls}")
    if g["firsts"]:
        L.append("- " + "; ".join(f"{k} day {v}" for k, v in g["firsts"].items()))
    tl = g["timeline"]
    if tl:
        step = max(1, len(tl) // 10)
        pick = tl[::step] + ([tl[-1]] if tl[-1] is not tl[::step][-1] else [])
        L += ["", "| day | citizens | drink | food | stressed | died | beds | seats |",
              "|---|---|---|---|---|---|---|---|"]
        L += [f"| {r['day']:g} | {_f(r['citizens'])} | {_f(r['drink'])} | {_f(r['food'])} | {_f(r['stressed'])} | "
              f"{_f(r['died'])} | {_f(r['beds'])} | {_f(r['seats'])} |" for r in pick]
    a = g["actions"]
    L += ["", f"**Actions:** {a['total']} calls ({a['rejected']} rejected); {a['advance_calls']} advances covering "
              f"{a['advanced_days']} days; actions on {a['days_with_actions']} days, at most {a['max_per_day']} a day "
              f"(K hit on {a['days_at_K']} days); {a['observes']} observes, {a['queries']} queries."]
    if a["by_tool"]:
        L.append("- by tool: " + ", ".join(f"{t} {n}" for t, n in a["by_tool"]))
    if a["error_codes"]:
        L.append("- rejections: " + ", ".join(f"{c} {n}" for c, n in a["error_codes"])
                 + " (by tool: " + ", ".join(f"{t} {n}" for t, n in a["rejected_by_tool"]) + ")")
    m = g["model"]
    L += ["", f"**Model:** {m['calls']} calls (" + ", ".join(f"{k} {v}" for k, v in m["outcomes"]) + f"); "
              f"${m['cost_usd']:.4f} of ${_f(m['budget_usd'], 3)}"
              + (f", **blocked: {m['blocked_reason']}**" if m["blocked_reason"] else "")
              + f"; tokens: prompt {m['prompt_tokens']:,} ({m['cached_tokens']:,} cached), completion "
              f"{m['completion_tokens']:,} ({m['reasoning_tokens']:,} reasoning); latency p50 {_f(m['latency_s_p50'])} s, "
              f"p90 {_f(m['latency_s_p90'])} s, max {_f(m['latency_s_max'])} s, total {_f(m['latency_s_total'])} s; "
              f"throttled {m['throttle_wait_s']} s (+{m['throttle_wait_harness_s']} s your own parallel calls), "
              f"queued {m['queue_wait_s']} s, upstream timeouts {m['upstream_timeouts']}."]
    if g["credits_by_phase"]:
        L.append("- credits by phase: " + ", ".join(
            f"days {c['from_day']}-{c['to_day']} ${c['cost_usd']:.3f} ({c['share']:.0%}, {c['calls']} calls)"
            for c in g["credits_by_phase"]))
    ev = [e for e in g["events"] if e["notable"]][:8] + [e for e in g["events"] if not e["notable"]][:6]
    if ev:
        L += ["", "| event | n | first day | first text |", "|---|---|---|---|"]
        L += [f"| {'**' + e['type'] + '**' if e['notable'] else e['type']} | {e['n']} | {_f(e['first_day'])} | "
              f"{e['first_text'].replace('|', '/')} |" for e in ev]
    return L


def labels_line(lab):
    official = "**officially comparable**" if lab.get("official_comparable") else "**not an official result**"
    if lab.get("watch"):
        official += " (**watch mode**: rendered DF, not comparable with headless runs)"
    return (f"> {official}: {lab.get('result_kind')} run, stack **{lab.get('stack') or '?'}**, scope "
            f"**{lab.get('scope') or '?'}** ({lab.get('tasks_played') or '-'}), suite {lab.get('suite') or '?'}, "
            f"anchors {lab.get('anchors_id') or '?'}")


def markdown(run, games):
    s = suite_summary(run)
    L = [labels_line(run.labels()), ""] + md_suite(run, s)
    for g in games:
        L += md_game(g)
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- HTML

def spark(values, w=220, h=36, color="#3b6ea5"):
    pts = [(i, v) for i, v in enumerate(values) if isinstance(v, (int, float))]
    if len(pts) < 2:
        return ""
    lo = min(v for _, v in pts)
    hi = max(v for _, v in pts)
    span = (hi - lo) or 1
    n = max(i for i, _ in pts) or 1
    xy = " ".join(f"{i / n * (w - 4) + 2:.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}" for i, v in pts)
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img"><polyline fill="none" '
            f'stroke="{color}" stroke-width="1.5" points="{xy}"/></svg>'
            f'<span class="rng">{lo:g}–{hi:g}</span>')


CSS = """body{font:14px/1.45 system-ui,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em;color:#1d2433}
table{border-collapse:collapse;margin:.6em 0}td,th{border:1px solid #d6dae3;padding:3px 8px;text-align:left}
th{background:#f3f5f9}h2{margin-top:2em;border-top:1px solid #d6dae3;padding-top:1em}.rng{color:#6b7385;
font-size:12px;margin-left:6px}.bad{color:#a33}.ok{color:#2a7a3b}code{background:#f3f5f9;padding:0 3px}"""


def _md_inline(s):
    s = html.escape(s)
    out, bold = [], False
    for part in s.split("**"):
        out.append(part if not bold else f"<b>{part}</b>")
        bold = not bold
    return "".join(out).replace("`", "")


def html_report(run, games):
    s = suite_summary(run)
    body = []
    lines = md_suite(run, s)
    body.append(f"<h1>{_md_inline(lines[0][2:])}</h1>")
    rows = [l for l in lines[1:] if l.startswith("|")]
    for l in lines[1:]:
        if l and not l.startswith("|"):
            body.append(f"<p>{_md_inline(l)}</p>")
    body.append(_table(rows))
    for g in games:
        gl = md_game(g)
        body.append(f"<h2>{html.escape(gl[1][3:])}</h2>")
        tl = g["timeline"]
        if tl:
            body.append("<table><tr><th>series</th><th>over the game</th></tr>" + "".join(
                f"<tr><td>{k}</td><td>{spark([r[k] for r in tl], color=c)}</td></tr>"
                for k, c in (("citizens", "#3b6ea5"), ("drink", "#2a7a8c"), ("food", "#7a6a2a"),
                             ("stressed", "#a33"), ("died", "#555")))
                + "</table>")
        buf = []
        for l in gl[3:]:
            if l.startswith("|"):
                buf.append(l)
                continue
            if buf:
                body.append(_table(buf)); buf = []
            if l.startswith("- "):
                body.append(f"<li>{_md_inline(l[2:])}</li>")
            elif l:
                body.append(f"<p>{_md_inline(l)}</p>")
        if buf:
            body.append(_table(buf))
    return (f"<!doctype html><meta charset='utf-8'><title>dfbench report</title><style>{CSS}</style>"
            + "\n".join(body))


def _table(rows):
    rows = [r for r in rows if not set(r.replace("|", "").strip()) <= set("-")]
    if not rows:
        return ""
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head = "".join(f"<th>{_md_inline(c)}</th>" for c in cells[0])
    body = "".join("<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in r) + "</tr>" for r in cells[1:])
    return f"<table><tr>{head}</tr>{body}</table>"
