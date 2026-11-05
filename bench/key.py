#!/usr/bin/env python3
"""The comparability key (docs/BENCHMARK-v1.md §1.1).

Two results are comparable only if their keys match. The agent-visible harness (tools, observation, manual, loop
and history policy) froze as `dfbench/v1` on 2026-10-10 (main 8661b358, docs/HARNESS-PLAN.md Phase 4); any change
to it is a major bump (§1.2). Tasks still change by suite minor and score_version. Keys before the freeze read
`dfbench/v0-dev` and are provisional. The v2 line (docs/BENCHMARK-v2.md) read `dfbench/v2-dev` until it froze as
`dfbench/v2` on 2026-10-14 (main 7adb4959c, #61; tag `harness-v2`): any agent-visible change now is a major bump
(dfbench/v3). v2 was superseded on 2026-10-14 by `dfbench/v2.1` (main 93f1cb36f, #65; tag `harness-v2.1`) before
any results were published on it. v2-dev and v2.1-dev rows are provisional and never compared with v1 or v2 rows.
`dfbench/v2.2-dev` (branch obs-leaks, 2026-10-16) closes hidden-information leaks in the observation, the advance
tripwires and the tool results (docs/BENCHMARK-v2.md §7.8); its rows are provisional until it freezes. The frozen v1 harness is tag
`harness-v1`. It is computed from file contents, not git, because the Docker image
deletes .git.

  python3 bench/key.py [--scenario scenarios/x.json] [--decision-cap 500] [--days N] [--ablate hints,...]   # prints the key as JSON

smoke.py writes it to <out>/BATCH.json and refuses to add runs to an out dir with a different key;
docker/batch.sh adds the host fields (commit, dirty tree, image digest). stdlib only.
"""
import ast, hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = "dfbench/v2.2-dev"
SCHEMA = "dfbench-batch/0"
OBS_SCHEMA = 5          # 2: observe2.lua plus the harness additions (frozen v1). 3 (v2): hands_off_in_days,
                        #   administrators.manager_office / manager_needs_office, zones[].owner / furniture.
                        # 4 (v2): moods, water_on_fort_levels, threats.invaders_dead visible deaths only
                        # 5 (v2.2-dev): threats requires isVisible as well as isHidden (explicit; isHidden already
                        #   hid hostiles on unrevealed tiles, runs/obs-leaks-2026-10-16);
                        #   recent_events / recent_cancellations drop non-announcement reports on unrevealed tiles;
                        #   map.doorways no longer reads the shape of unrevealed neighbours
SCORE_VERSION = 7       # 1 (2026-10-10): LT05 partial goblin_raid_v2 (survival only); score.lua thefts/thieves (LT06)
                        # 2 (2026-10-10): lab predicates bench/predicates.py (LT08, LT04, LT03); recorder ev / moods /
                        #   beds and S0/S from final_state.lua. Rows under 1 keep their scores (nothing they use changed)
                        # 3 (2026-10-13): credited_value_dr, per-class diminishing returns (bench/dr.py, §3.4), the
                        #   open-play headline; gross credited_value kept alongside. Rescored from the item logs
                        #   (scripts/rescore_dr.py); every other score is unchanged
                        # 4 (v2, 2026-10-13): LT01/LT02/LT05 predicates in bench/predicates.py; credit.lua items carry
                        #   `tick` (LT01's drink-in-W clause); final_state farm_plots[].planted (LT02)
                        # 5 (2026-10-13): outcome fields (outcome.lua: recorder wb / home / prog / pop / cit_log,
                        #   final_state) and the gated outcome score bench/outcomes.py (docs/SUCCESS.md); deaths from
                        #   the citizen ledger; LT02/LT09 supply-over-W clauses
                        # 6 (2026-10-23): food counts edible items only (score.lua, recorder.lua): ANY_GOOD_FOOD's seeds
                        #   (planted ones too), empty bags and raw fish no longer count (runs/s0-compute-2026-10-23)
                        # 7 (2026-11-05): wellbeing no longer scores the share of needs met at H (OUTCOME_VERSION 2):
                        #   ~half the needs can't be met through the game API, and the share steps with time since
                        #   arrival, not with play (runs/s0-wellbeing-needs-2026-11-05)
REFS_VERSION = 4        # 1 (2026-10-10): policies.Random no longer draws create_burrow / civilian_alert
                        # 2 (2026-10-11): policies.Scripted re-picks its farm stair when the room gives no soil farm site
                        # 3 (v2, 2026-10-13): manager_office_step (scripted, automation, witnesses); no HandsOff shim
                        # 4 (v2.1, 2026-10-14): Scripted/witness defence counts a stationed squad as sheltered
RENDER = ("render_obs", "obs_text", "_at", "_cap", "_site", "_action", "_cancel", "_counted",   # harness2: obs -> text
          "_ids", "_box", "_hostile_groups", "_squad", "_dwarf", "_dist")
HISTORY_POLICY = ("window", "_stub")
# The default start fort: the committed save if this checkout has it, else its seed-built replacement (world seed 12345,
# PINNED POCKET, the same embark site; docker/embark.sh --rules DEFAULT_FORT --seeds 12345; docs/SEED-FORTS.md §6)
LEGACY_START = "fort_start_snapshot"
SEED_START = "scenarios/snapshots/embark-default-fort-12345"


def start_snapshot(path=None):
    """The start snapshot to load for `path` (default: the default start fort). fort_start_snapshot without its
    world.sav (a public checkout, which ships no DF save) resolves to the seed-built default fort; anything else is
    returned as given (absolute). reset_fort.sh applies the same rule when SNAPSHOT is unset."""
    legacy = os.path.join(ROOT, LEGACY_START)
    p = path or legacy
    p = p if os.path.isabs(p) else os.path.join(ROOT, p)
    if os.path.realpath(p) == os.path.realpath(legacy) and not os.path.exists(os.path.join(legacy, "world.sav")):
        return os.path.join(ROOT, SEED_START)
    return p


def _sha(*parts):
    h = hashlib.sha256()
    for p in parts:
        b = p if isinstance(p, bytes) else (p if isinstance(p, str) else json.dumps(p, sort_keys=True,
                                                                                  separators=(",", ":"))).encode()
        h.update(len(b).to_bytes(8, "big")); h.update(b)   # length-prefixed, so ("ab","c") != ("a","bc")
    return h.hexdigest()


def _file(rel):
    p = os.path.join(ROOT, rel)
    return open(p, "rb").read() if os.path.exists(p) else b"<missing:" + rel.encode() + b">"


def _tree(rel):
    """All files under a directory, in sorted order, as (name, bytes) pairs."""
    base = os.path.join(ROOT, rel)
    out = []
    for d, _, fs in sorted(os.walk(base)):
        for f in sorted(fs):
            if f.endswith((".pyc",)) or "__pycache__" in d:
                continue
            p = os.path.join(d, f)
            out += [os.path.relpath(p, ROOT), open(p, "rb").read()]
    return out


def _funcs(rel, names=None, exclude=()):
    """Source of top-level functions/classes in a Python file (all of them if names is None), parsed, not imported."""
    src = _file(rel).decode()
    out = []
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and (names is None or node.name in names) \
                and node.name not in exclude:
            out += [node.name, ast.get_source_segment(src, node)]
    return out


def _consts(rel, names):
    """Values of top-level constant assignments (literals only), parsed, not imported."""
    out = {}
    for node in ast.parse(_file(rel).decode()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in names:
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                out[node.targets[0].id] = ast.unparse(node.value)
    return out


def _snapshot_id(d):
    """What identifies a start snapshot: world.sav's bytes, except for a generated embark (embark/make_embark.sh),
    whose save differs run to run in fields DF randomizes at embark. It is identified by its recipe and the
    reproducible fingerprints instead (embark/compare.py), so everyone who regenerates the pool gets the same task hash."""
    meta = os.path.join(d, "SNAPSHOT.json")
    m = json.load(open(meta)) if os.path.exists(meta) else {}
    e = m.get("embark")
    if e:
        fp = e["probe"]["fingerprint"]
        ident = {"seed": e["seed"], "paramset": e["paramset"], "rules_sha256": e["rules_sha256"],
                 "world_tile": e["world_tile"], "local": e["local"],
                 "fingerprint": {k: fp[k] for k in ("map", "plants", "loadout")}}
        # a task fort (embark/make_task_fort.sh) is that embark plus a recipe and the scripts that build it; the
        # migrants, settle days and world.sav differ per build, so they are not part of the id (docs/SEED-FORTS.md)
        tf = m.get("task_fort")
        if tf:
            ident["task_fort"] = {k: tf[k] for k in ("version", "recipe", "recipe_sha256", "build_sha256")}
        return json.dumps(ident, sort_keys=True)
    w = os.path.join(d, "world.sav")
    return open(w, "rb").read() if os.path.exists(w) else b"<missing:" + w.encode() + b">"


def scenario_fields(path):
    """Task hash: the scenario JSON, its start snapshot's world.sav, and the setup scripts it runs."""
    if not path:
        start = start_snapshot()
        if start == os.path.join(ROOT, LEGACY_START):   # the committed save: the hash every existing row has
            return "start-default", _sha(_file("fort_start_snapshot/world.sav"))
        return "start-default-seed", _sha(_snapshot_id(start))
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    sc = json.load(open(p))
    parts = [open(p, "rb").read()]
    # a snapshot pool (LT09/LT10 embark sites) hashes every member, in pool order
    for snap in sc.get("snapshot_pool") or [sc.get("snapshot") or "fort_start_snapshot"]:
        parts.append(_snapshot_id(start_snapshot(snap)))
    for cmd in sc.get("setup", []):
        parts += [_file(c) for c in cmd if isinstance(c, str) and c.startswith("scenarios/")]
    return sc.get("name") or os.path.splitext(os.path.basename(p))[0], _sha(*parts)


def compute(scenario=None, decision_cap=500, days=None, history=12, action_log=8, ablate=(), old_obs="stub"):
    c2 = _consts("harness2.py", {"MANUAL", "TOOLS", "_INT", "_SITE", "RECIPES", "WORKSHOPS", "AUTOMATION", "MAX_DAYS",
                                    "CHAT_EXTRA", "OBS_CAPS", "OBS_ORDER", "TOOL_RESULT_OLD",
                                    "ERROR_CODES", "ERROR_HINTS", "SITE_LISTS", "SITE_KINDS", "_USED_BY"})
    cs = _consts("smoke.py", {"FORCE_AFTER", "MAX_API_STREAK", "DAY", "STUCK_S", "HANG_S"})
    c1 = _consts("harness.py", {"SYSTEM"})
    task, task_hash = scenario_fields(scenario)
    f = {
        "bench": BENCH, "track": "fixed",
        # what the model is told it can do
        "tools_hash": _sha([c2.get(k) for k in ("TOOLS", "_INT", "_SITE", "RECIPES", "WORKSHOPS", "AUTOMATION")],
                           *_funcs("harness2.py", {"_recipes_by_workshop"})),
        # what the tools do: the act/validate code, the Lua it runs, and the errors (codes, hints) it returns
        "tool_semantics_hash": _sha(*_funcs("harness2.py", exclude=("diagnose", "observe", "plugin_state", *RENDER)),
                                    *_funcs("harness.py", {"act", "validate", "_int", "dfhack"}),
                                    *[_file(x) for x in ("act2.lua", "place.lua", "digplan.lua", "advance.lua", "wo_lib.lua")],
                                    *[c2.get(k) for k in ("ERROR_CODES", "ERROR_HINTS", "SITE_LISTS", "SITE_KINDS", "_USED_BY")]),
        # every text the model sees that isn't the observation (task briefs and goals are in task_hash, with the scenario)
        "manual_hash": _sha(c2.get("MANUAL"), c1.get("SYSTEM"), *_funcs("harness2.py", {"diagnose"})),
        "obs_schema": OBS_SCHEMA,
        # observe2.lua, the harness's additions, and what the agent is told about the task (goal + brief, not metrics)
        # ... and how it is rendered for the model (render_obs: compact text, caps, key order)
        "obs_schema_hash": _sha(_file("observe2.lua"), *_funcs("harness2.py", {"observe", "plugin_state", *RENDER}),
                                *_funcs("smoke.py", {"task_obs"}), c2.get("OBS_CAPS"), c2.get("OBS_ORDER")),
        # the decision loop (until it moves to bench/loop.py): run_one and its constants
        # ... and the history policy: the window and how older observations and tool results are shortened
        "loop_hash": _sha(*_funcs("smoke.py", {"run_one", "advance", "_poll", "dismiss_popups", "hands_off_tick",
                                               "hands_off_in_days"}), cs,
                          c2.get("MAX_DAYS"), *_funcs("harness2.py", HISTORY_POLICY), c2.get("TOOL_RESULT_OLD")),
        "score_version": SCORE_VERSION,
        "score_hash": _sha(*[_file(x) for x in ("score.lua", "credit.lua", "recorder.lua", "final_state.lua",
                                                 "outcome.lua", "bench/predicates.py", "bench/dr.py", "bench/outcomes.py")]),
        "task": task, "task_hash": task_hash,
        "df": "53.16", "dfhack": "53.16-r2",
        # run settings that change what the model sees (history window, action log) are part of the budget
        "budget": {"decision_cap": decision_cap, "days": days, "max_output_tokens": (c2.get("CHAT_EXTRA") or {}).get("max_tokens"),
                   "history": history, "action_log": action_log, "old_obs": old_obs},
    }
    f["budget_hash"] = _sha(f["budget"])
    f["refs_version"] = REFS_VERSION
    f["refs_hash"] = _sha(_file("policies.py"), *_tree("automation"), _file("docker/dfai/df-ai.json"),
                          _file("bench/labrun.py"))   # labrun: the reference arms' hands-off window and witnesses
    ablate = sorted(set(ablate or ()))
    if ablate:   # scaffolding ablations (bench/ablate.py); absent from the default key, so it stays as it was
        f["ablate"] = ablate
        f["ablate_hash"] = _sha(ablate, _file("bench/ablate.py"))
    variant = os.environ.get("DFBENCH_VARIANT")
    if variant:   # a baseline-harness variant run through its own entry (bench/variants/<name>.py); absent by default
        f["variant"] = variant
        src = f"bench/variants/{variant}.py"
        # extra files a variant runs (a Lua probe): named on a "# variant-files: a.lua b.lua" line in its source
        with open(os.path.join(ROOT, src)) as fh:
            extra = [w for line in fh if line.startswith("# variant-files:") for w in line.split(":", 1)[1].split()]
        f["variant_hash"] = _sha(_file(src), *[_file(f"bench/variants/{x}") for x in extra])
    s = lambda k: f[k][:8]
    f["key"] = (f"{BENCH}|track=fixed|tools={s('tools_hash')}|sem={s('tool_semantics_hash')}|"
                f"manual={s('manual_hash')}|obs={OBS_SCHEMA}:{s('obs_schema_hash')}|loop={s('loop_hash')}|"
                f"score={SCORE_VERSION}:{s('score_hash')}|task={task}:{s('task_hash')}|df=53.16|dfhack=53.16-r2|"
                f"budget={s('budget_hash')}" + (f"|ablate={'+'.join(ablate)}:{s('ablate_hash')}" if ablate else "") +
                (f"|variant={variant}:{s('variant_hash')}" if variant else ""))
    return f


TASK_FIELDS = ("task", "task_hash", "budget", "budget_hash", "key")


def harness_part(f):
    """The fields every task in one out dir must share (one out dir may hold several scenarios)."""
    return {k: v for k, v in f.items() if k not in TASK_FIELDS}


class KeyMismatch(SystemExit):
    pass


def record_batch(out, f, condition, argv):
    """Write or extend <out>/BATCH.json. Refuses (KeyMismatch) to add runs made by a different harness, or a different
    version of the same task, to an out dir: resumed batches must not silently mix versions.
    DFBENCH_ALLOW_MIXED=1 records the new key alongside instead (the rows are then not comparable with each other)."""
    import time
    path = os.path.join(out, "BATCH.json")
    b = json.load(open(path)) if os.path.exists(path) else {
        "schema": SCHEMA, "note": f.get("bench", BENCH) + {"dfbench/v1": ": agent-visible harness frozen 2026-10-10",
                                             "dfbench/v2": ": agent-visible harness frozen 2026-10-14",
                                             "dfbench/v2.1": ": agent-visible harness frozen 2026-10-14 (v2.1)",
                                             "dfbench/v2.1.1": ": harness frozen 2026-10-14 (v2.1.1: v2.1 plus the hang fixes)",
                                             V3_BENCH: ": game API v0 (docs/GAME-API.md); the harness is the submission"}.get(
                     f.get("bench", BENCH), ": in development, provisional (docs/BENCHMARK-v2.md)"),
        "harness": harness_part(f), "tasks": {}, "invocations": []}
    problems = []
    if b["harness"] != harness_part(f):
        problems.append("harness: " + ", ".join(k for k in sorted(set(b["harness"]) | set(harness_part(f)))
                                                  if b["harness"].get(k) != f.get(k)))
    old = b["tasks"].get(f["task"])
    if old and old["key"] != f["key"]:
        problems.append(f"task {f['task']}: " + ", ".join(k for k in TASK_FIELDS if old.get(k) != f.get(k)))
    if problems:
        msg = (f"{path}: this out dir holds runs from a different harness or task version ({'; '.join(problems)}). "
               "Use a new --out, or set DFBENCH_ALLOW_MIXED=1 to record both (rows won't be comparable).")
        if not os.environ.get("DFBENCH_ALLOW_MIXED"):
            raise KeyMismatch(msg)
        print("WARNING: " + msg, file=sys.stderr)
        b.setdefault("other_keys", []).append(f)
    else:
        b["tasks"].setdefault(f["task"], {k: f[k] for k in TASK_FIELDS})
    b["invocations"].append({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "key": f["key"],
                             "condition": condition, "argv": argv})
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(b, fh, indent=1)
    os.replace(tmp, path)
    return b



# ---------------------------------------------------------------------------------------------------------------
# dfbench/v3: the game API (docs/GAME-API.md §1). A different line: v3 keys are never comparable with v2.x rows, and
# compute() above (the v2.x key) is unchanged. The key covers the game side only; the harness is the submission
# and is identified by its source digest in each row (harness_digest).
V3_BENCH = "dfbench/v3"
V3_API = "v0"
V3_SERVER_FILES = ("gameapi/server/rules.py", "gameapi/server/backend.py", "gameapi/server/artifacts.py",
                   "gameapi/server/task.py", "advance.lua", "recorder.lua", "credit.lua")
V3_SMOKE_FUNCS = {"advance", "_poll", "dismiss_popups", "reset", "daily_metrics", "credit_start", "ambient_automation",
                  "lua_json", "score"}


def _facts_files(prefer=None):
    """-> (facts name, tool files, obs files): what defines the tools' semantics and the observation/queries, as the
    server's facts adapter names them (gameapi/facts when present: its Python and lua/; else the legacy adapter over
    harness2). No DF needed."""
    sys.path.insert(0, ROOT)
    from gameapi.server.adapter import key_files
    return key_files(prefer)


def _v3_surface(s1=None):
    """The tool schemas and query list as the server serves them (imports the facts layer; no DF needed).
    s1: a season-1 rules version adds its tools, queries and obs schema suffix (gameapi/season1)."""
    sys.path.insert(0, ROOT)
    from gameapi.server import adapter, rules
    if adapter.facts_available():   # static schemas: build_workshop's DF enum is pinned by the df version
        facts = adapter.Facts.__new__(adapter.Facts)
        facts.F = __import__("importlib").import_module("gameapi.facts")
    else:
        facts = adapter.Legacy()
    tools, queries, obs = facts.key_tools(), facts.queries(), getattr(facts, "OBS_SCHEMA", None)
    if s1:
        from gameapi import season1
        t1, q1, suffix = season1.key_surface()
        tools, queries, obs = tools + t1, queries + q1, f"{obs}{suffix}"
    tools = [t for t in tools if t["function"]["name"] != "advance_days"] + [rules.advance_tool()]
    return tools, queries, obs


def df_settings(strange_moods=False):
    """The DF settings a v3 game runs with: the image's init/d_init token edits plus what the server sets per task."""
    c = _consts("docker/prefs_overrides.py", {"OVERRIDES"}).get("OVERRIDES") or {}
    d = {name: dict(edits) for name, (_, edits) in c.items()} if isinstance(c, dict) else {"raw": c}
    d.setdefault("d_init.txt", {})["ARTIFACTS"] = "YES" if strange_moods else "NO"
    return d


def price_table_hash(path="gateway/prices.json"):
    """The gateway's price table id: "sha256:" + sha256 of the file's bytes (it holds the provider pin too)."""
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    return "sha256:" + hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None


def compute_v3(scenario=None, days=None, *, k_actions=40, max_advance_days=28, wall_s=5400, model=None,
               price_table_hash=None, budget=None, strange_moods=None, tools=None, queries=None,
               obs_schema=None, facts_impl=None):
    """The dfbench/v3 key. model + price_table_hash: the model condition (docs/GAME-API.md §1; the price table
    holds the provider pin; default: this tree's gateway/prices.json); budget: e.g. {"credits": 0.5, "unit":
    "USD at the pinned reference prices", "per": "game"}.
    strange_moods defaults to the scenario's field (default false). tools/queries default to what the server
    serves (computed by importing gameapi.server)."""
    if price_table_hash is None:
        price_table_hash = globals()["price_table_hash"]()
    sc = {}
    if scenario:
        p = scenario if os.path.isabs(scenario) else os.path.join(ROOT, scenario)
        sc = json.load(open(p))
    if strange_moods is None:
        strange_moods = bool(sc.get("strange_moods", False))
    days = days or sc.get("days", 336)
    s1 = sc.get("rules_version")   # season 1 (gameapi/season1): absent on every season-0 task, so their key is unchanged
    s1_files = {}
    if s1:
        sys.path.insert(0, ROOT)
        from gameapi import season1
        season1.rules_version(sc)
        s1_files = season1.key_files()
    if tools is None or queries is None or obs_schema is None:
        t, q, o = _v3_surface(s1)
        tools, queries, obs_schema = tools if tools is not None else t, queries if queries is not None else q, \
            obs_schema if obs_schema is not None else o
    facts_name, tool_files, obs_files = _facts_files(facts_impl)
    tool_files, obs_files = tool_files + s1_files.get("sem", []), obs_files + s1_files.get("obs", [])
    task, task_hash = scenario_fields(scenario)
    api = V3_API + (f"+{s1}" if s1 else "")
    settings = df_settings(strange_moods)
    rules = {"actions_per_game_day": k_actions, "max_advance_days": max_advance_days, "wall_s": wall_s}
    f = {
        "bench": V3_BENCH, "api": api, "facts": facts_name,
        "tools_hash": _sha(tools),
        # what the tools do: the facts layer's act code and Lua (or the legacy adapter's), plus the server's checks
        "tool_semantics_hash": _sha(*[x for r in tool_files for x in (r, _file(r))]),
        "obs_schema": obs_schema,
        "obs_schema_hash": _sha(queries, *[x for r in obs_files for x in (r, _file(r))]),
        "df_settings": settings,
        "df_settings_hash": _sha(settings, _file("docker/dfhack-onMapLoad.init")),
        "rules": rules,
        "rules_hash": _sha(rules, *[x for r in V3_SERVER_FILES + tuple(s1_files.get("rules", ())) for x in (r, _file(r))],
                           *_funcs("smoke.py", V3_SMOKE_FUNCS), _consts("smoke.py", {"DAY", "STUCK_S", "HANG_S",
                                                                                     "POLL_TIMEOUT"})),
        "score_version": SCORE_VERSION,
        "score_hash": _sha(*[_file(x) for x in ("score.lua", "credit.lua", "recorder.lua", "final_state.lua",
                                                 "outcome.lua", "bench/predicates.py", "bench/dr.py", "bench/outcomes.py")
                             + tuple(s1_files.get("score", ()))]),
        "task": task, "task_hash": task_hash,
        "df": "53.16", "dfhack": "53.16-r2",
        "model": {"model": model, "price_table_hash": price_table_hash},
        "budget": {**(budget or {}), "days": days},
    }
    f["model_hash"] = _sha(f["model"])
    f["budget_hash"] = _sha(f["budget"])
    s = lambda k: f[k][:8]
    if s1:
        f["rules_version"] = s1
    f["key"] = (f"{V3_BENCH}|api={api}|tools={s('tools_hash')}|sem={s('tool_semantics_hash')}|"
                f"obs={obs_schema}:{s('obs_schema_hash')}|dfset={'art' if strange_moods else 'noart'}:"
                f"{s('df_settings_hash')}|rules=K{k_actions}.A{max_advance_days}.W{wall_s}:{s('rules_hash')}|"
                f"score={SCORE_VERSION}:{s('score_hash')}|task={task}:{s('task_hash')}|df=53.16|dfhack=53.16-r2|"
                f"model={model}:{s('model_hash')}|budget={s('budget_hash')}")
    return f


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--scenario")
    p.add_argument("--decision-cap", type=int, default=500)
    p.add_argument("--days", type=int)
    p.add_argument("--ablate", default="", help="comma list of bench/ablate.py ablations (manual, hints, sites)")
    p.add_argument("--v3", action="store_true", help="the dfbench/v3 game-API key (compute_v3) instead of v2.x")
    p.add_argument("--model"); p.add_argument("--price-table-hash")
    p.add_argument("--credits", type=float)
    a = p.parse_args()
    if a.v3:
        print(json.dumps(compute_v3(a.scenario, a.days, model=a.model, price_table_hash=a.price_table_hash,
                                    budget={"credits": a.credits, "unit": "USD at the pinned reference prices",
                                            "per": "game"} if a.credits is not None else None), indent=1))
        sys.exit(0)
    days = a.days or (json.load(open(a.scenario)).get("days", 336) if a.scenario else 336)
    print(json.dumps(compute(a.scenario, a.decision_cap, days,
                             ablate=[x.strip() for x in a.ablate.split(",") if x.strip()]), indent=1))
