"""Per-game analysis: timeline, events, actions, model use, credits by phase, outcome gates."""
import collections, statistics

DAY_TICKS = 1200

GATES = {  # bench/outcomes.py: the tier reached = the number of consecutive gates passed
    1: "G1 survival: nobody died or went insane, the fort stands, no raider left on the map",
    2: "G2 supply: drink and food in stock every day of the final window, with enough days of stock left",
    3: "G3 wellbeing: no breakdown or failed mood, at most 10% of citizen-days stressed",
    4: "G4 growth: beds for every citizen and dining seats for half of them at the horizon (+ progression on full years)",
}
NOTABLE = ("CITIZEN_DEATH", "STRANGE_MOOD", "MOOD", "BERSERK", "TANTRUM", "MIGRANT", "CARAVAN", "AMBUSH", "SIEGE",
           "INVASION", "MERCHANT", "DIPLOMAT", "INSANE", "MEGABEAST", "CAVE_COLLAPSE", "FLOOD")


def pct(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return xs[i]


def timeline(game):
    """-> list of per-sample dicts with day and the series the reports plot."""
    s = game.samples
    if not s:
        return []
    t0 = s[0].get("abs_tick") or 0
    out = []
    for x in s:
        pop = x.get("pop") or {}
        out.append({"day": round(((x.get("abs_tick") or t0) - t0) / DAY_TICKS, 1),
                    "citizens": x.get("citizens"), "drink": x.get("drink"), "food": x.get("food"),
                    "stressed": x.get("stressed"), "died": pop.get("died"), "insane": pop.get("insane"),
                    "in_mood": x.get("in_mood"), "hostiles": x.get("hostiles"), "idle": x.get("idle"),
                    "beds": x.get("beds_placed"), "seats": (x.get("home") or {}).get("dining_seats")})
    return out


def firsts(tl):
    """Notable first occurrences in the timeline (day numbers)."""
    f = {}
    for r in tl:
        for key, cond in (("first drink out", (r["drink"] == 0)), ("first food out", (r["food"] == 0)),
                          ("first death", (r["died"] or 0) > 0), ("first insanity", (r["insane"] or 0) > 0),
                          ("first stressed citizen", (r["stressed"] or 0) > 0),
                          ("first hostile seen", (r["hostiles"] or 0) > 0), ("first mood", (r["in_mood"] or 0) > 0)):
            if cond and key not in f:
                f[key] = r["day"]
    return f


def events(game, t0=None):
    s = game.samples
    t0 = t0 if t0 is not None else (s[0].get("abs_tick") if s else 0)
    rows = []
    for name, e in game.events.items():
        if not isinstance(e, dict):
            continue
        ft = e.get("first_tick")
        rows.append({"type": name, "n": e.get("n", 1),
                     "first_day": round((ft - t0) / DAY_TICKS, 1) if isinstance(ft, (int, float)) else None,
                     "first_text": (e.get("first_text") or "")[:140],
                     "notable": any(k in name for k in NOTABLE)})
    rows.sort(key=lambda r: (not r["notable"], -(r["n"] or 0)))
    return rows


def actions(game):
    acts = [r for r in game.api if r.get("method") == "POST" and str(r.get("path", "")).startswith("/act")]
    by_tool = collections.Counter()
    rejected = collections.Counter()
    errors = collections.Counter()
    per_day = collections.Counter()
    adv_days = 0
    k_hits = set()
    for r in acts:
        req = r.get("request") or {}
        tool = req.get("tool") or "?"
        resp = r.get("response") or {}
        by_tool[tool] += 1
        if tool == "advance_days":
            try:
                adv_days += int((req.get("args") or {}).get("days") or 0) if resp.get("ok") else 0
            except (TypeError, ValueError):
                pass
        else:
            per_day[r.get("day")] += 1
        if not resp.get("ok"):
            rejected[tool] += 1
            errors[resp.get("error_code") or f"http {r.get('status')}"] += 1
            if resp.get("error_code") == "action_limit":
                k_hits.add(r.get("day"))
        elif tool != "advance_days" and resp.get("actions_left_today") == 0:
            k_hits.add(r.get("day"))
    counts = list(per_day.values())
    lat = [r.get("latency_ms") for r in game.api if isinstance(r.get("latency_ms"), (int, float))]
    queries = sum(1 for r in game.api if str(r.get("path", "")).startswith("/query"))
    observes = sum(1 for r in game.api if str(r.get("path", "")).startswith("/observe"))
    return {"total": len(acts), "by_tool": by_tool.most_common(), "rejected": sum(rejected.values()),
            "rejected_by_tool": rejected.most_common(), "error_codes": errors.most_common(),
            "advance_calls": by_tool.get("advance_days", 0), "advanced_days": adv_days,
            "days_with_actions": len(per_day), "max_per_day": max(counts) if counts else 0,
            "mean_per_active_day": round(statistics.mean(counts), 1) if counts else 0,
            "days_at_K": len(k_hits), "observes": observes, "queries": queries,
            "api_latency_ms_p50": pct(lat, .5), "api_latency_ms_p90": pct(lat, .9)}


def model_use(game):
    u = game.usage
    out = collections.Counter(x.get("outcome") or "?" for x in u)
    lat = [x["upstream_latency_s"] for x in u if isinstance(x.get("upstream_latency_s"), (int, float))]
    tok = lambda k: sum(int(x.get(k) or 0) for x in u)
    cost = sum(float(x.get("cost_usd") or 0) for x in u)
    gs = game.gateway_status
    return {"calls": len(u), "outcomes": out.most_common(), "cost_usd": round(cost, 4),
            "budget_usd": gs.get("budget_usd") or game.spec.get("budget_usd"),
            "blocked_reason": gs.get("blocked_reason"),
            "prompt_tokens": tok("prompt_tokens"), "cached_tokens": tok("cached_tokens"),
            "completion_tokens": tok("completion_tokens"), "reasoning_tokens": tok("reasoning_tokens"),
            "latency_s_p50": pct(lat, .5), "latency_s_p90": pct(lat, .9), "latency_s_max": max(lat) if lat else None,
            "latency_s_total": round(sum(lat), 1),
            "throttle_wait_s": round(sum(float(x.get("throttle_wait_s") or 0) for x in u), 1),
            "throttle_wait_harness_s": round(sum(float(x.get("throttle_wait_harness_s") or 0) for x in u), 1),
            "queue_wait_s": round(sum(float(x.get("queue_wait_s") or 0) for x in u), 1),
            "upstream_timeouts": out.get("upstream_timeout", 0)}


def credits_by_phase(game, phase_days=28):
    """Model spend per phase of the game: each gateway call is placed at the game day of the latest API call that
    preceded it (the game is paused while the harness thinks)."""
    marks = sorted((r["t"], r.get("day") or 0) for r in game.api if isinstance(r.get("t"), (int, float)))
    if not marks or not game.usage:
        return []
    buckets = collections.OrderedDict()
    j = 0
    for x in sorted(game.usage, key=lambda x: x.get("t_start") or 0):
        t = x.get("t_start") or 0
        while j + 1 < len(marks) and marks[j + 1][0] <= t:
            j += 1
        day = marks[j][1] if marks[j][0] <= t else 0
        b = int(day // phase_days)
        c = buckets.setdefault(b, {"from_day": b * phase_days, "to_day": (b + 1) * phase_days, "calls": 0,
                                   "cost_usd": 0.0, "prompt_tokens": 0})
        c["calls"] += 1
        c["cost_usd"] += float(x.get("cost_usd") or 0)
        c["prompt_tokens"] += int(x.get("prompt_tokens") or 0)
    tot = sum(c["cost_usd"] for c in buckets.values()) or 1.0
    out = []
    for c in buckets.values():
        c["cost_usd"] = round(c["cost_usd"], 4)
        c["share"] = round(c["cost_usd"] / tot, 3)
        out.append(c)
    return out


def outcome_detail(run, game):
    """The scorer's record for this game, plus gate details from bench/outcomes.py when a challenge clone is found."""
    rec = run.records.get(game.id) or {}
    det = {"status": rec.get("status") or game.rec.get("status"), "notes": rec.get("notes") or game.rec.get("notes")}
    for k in ("O", "tier", "s", "partial", "passed", "clauses"):
        if k in rec:
            det[k] = rec[k]
    if run.outcomes is not None and game.summary:
        try:
            o = run.outcomes.for_run(f"{game.dir}/game", game.summary)
            if o:
                det.update(gates=o.get("gates"), parts=o.get("parts"), inputs=o.get("inputs"))
        except Exception:
            pass
    t = det.get("tier")
    if isinstance(t, int) and t < 4:
        det["failed_gate"] = GATES[t + 1]
    det["gate_why"] = gate_why(det)
    return det


def gate_why(det):
    """Short evidence for each failed gate, from bench/outcomes.py's parts and inputs (challenge clone only)."""
    gates, parts, inp = det.get("gates"), det.get("parts") or {}, det.get("inputs") or {}
    if not gates:
        return []
    out = []
    if not gates[0]:
        out.append(f"G1: deaths {inp.get('deaths')}, insane lost {inp.get('insane_lost')}, fort lost "
                   f"{inp.get('fort_lost')}, raiders left {inp.get('invaders_alive_end')}")
    if len(gates) > 1 and not gates[1]:
        sup = parts.get("supply") or {}
        bits = []
        for res in ("drink", "food"):
            x = sup.get(res) or {}
            if x:
                bits.append(f"{res}: in stock {x.get('coverage', 0):.0%} of the final days, "
                            f"{x.get('days_left') if x.get('days_left') is not None else 'n/a'} days of stock left, "
                            f"score {x.get('score')}")
        out.append("G2: " + "; ".join(bits) + f" (final window days {inp.get('final_stretch')})")
    if len(gates) > 2 and not gates[2]:
        out.append(f"G3: breakdowns {inp.get('breakdowns')}, stressed share of citizen-days "
                   f"{inp.get('stressed_share_F')}, failed moods (strange moods {inp.get('strange_moods')}, "
                   f"artifacts {inp.get('artifacts')})")
    if len(gates) > 3 and not gates[3]:
        out.append(f"G4: beds {inp.get('beds_placed')} for {inp.get('citizens_end')} citizens, dining seats "
                   f"{inp.get('dining_seats')} (need {-(-(inp.get('citizens_end') or 0) // 2)}), progression steps "
                   f"{inp.get('progression_steps')}")
    return out


def game_report(run, game):
    tl = timeline(game)
    return {"id": game.id, "task": game.task, "k": game.k, "seed": game.seed,
            "status": game.rec.get("status"), "finished_by": game.rec.get("finished_by"),
            "days": game.summary.get("days_played"), "days_target": game.spec.get("days"),
            "wall_s": game.rec.get("wall_s"), "wall_cap_s": game.spec.get("wall_s"),
            "wall_capped": bool(game.summary.get("wall_capped")),
            "harness": game.rec.get("harness") or {},
            "outcome": outcome_detail(run, game), "timeline": tl, "firsts": firsts(tl),
            "events": events(game), "actions": actions(game), "model": model_use(game),
            "credits_by_phase": credits_by_phase(game)}
