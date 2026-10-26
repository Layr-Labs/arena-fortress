# The baseline harness, a minimal example, and the client (season 0)

A harness is a directory with a `Dockerfile` and an entrypoint. It reads its task from `DFBENCH_TASK` and talks to
two services only: the game API (`http://game:8090`, `docs/GAME-API.md` §3) and the model through the metering gateway
(`http://gateway:8080/v1`, OpenAI-compatible chat with tools).

| path | what |
|---|---|
| `plain/` | **the baseline**: the model plays the fort from the raw game API, one tool call per turn, with basic guards. `submission/` starts as a copy of it (`plain/README.md`) |
| `minimal/` | a ~110-line API demo that shows the contract and nothing else: observe, ask the model, act, advance; stops at 90% of the credits. Not a starting point: it plays poorly |
| `dfbench_client/` | a small stdlib Python client: `GameClient` (task, observe, act, query, events; typed errors), `ModelClient` (chat with tools, retries, usage and cost), `load_task()` |
| `tests/` | a fake game server and a fake gateway (`fakes.py`), and the tests |

## Budget and limits

`DFBENCH_TASK` carries `budget.credits` (USD per game at the pinned reference prices) and `limits` (`wall_s`,
`actions_per_game_day`, `max_advance_days`). The gateway meters every call and refuses calls once the credits are
gone; the server then runs the fort on unmanaged to the horizon. So spending the budget early is a real loss.

The baseline keeps its own tally (`usage.cost` from the gateway, else a token estimate at `model.prices` if the task
gives them) and stops calling the model at 92% of the credits.

Other limits: the harness container gets about 1 vCPU and 2 GB and shares the runner with DF (heavy local compute
slows the game clock and so the wall cap); game time moves only on `advance_days`, so model latency is wall time; the
wall cap (e.g. 90 min per game-year) scores the game where it stands, flagged `wall_capped`.

## Running it

Tests (no DF, no model, no network beyond localhost):

```sh
python3 -m unittest discover -s baseline/tests -t baseline
```

A dry run against the fakes, as a process or as the container:

```sh
cd baseline
python3 tests/fakes.py --days 30 > /tmp/task.json &          # fake game + fake gateway; prints a DFBENCH_TASK
sleep 1; DFBENCH_TASK="$(cat /tmp/task.json)" python3 -m plain

docker build -t my-harness -f plain/Dockerfile .
python3 tests/fakes.py --days 30 --host 0.0.0.0 --advertise host.docker.internal > /tmp/task.json &
sleep 1; docker run --rm --cpus 1 --memory 2g -e DFBENCH_TASK="$(cat /tmp/task.json)" my-harness
```

On the real stack, `runner/` provides the local run (one Docker Compose project per game: game, gateway, harness):

```sh
dfbench local run --harness submission/ --task scenarios/season0/op1-start-year.json --seed 2001
```

(`runner/README.md` has the flags; it needs the DF image and a model key for the gateway.)

Logs: the baseline writes one JSON line per event on stdout (`setup`, `act`, `harness_advance`, `model_error`,
`done` with stats, usage and spend). `DFBENCH_SEED` sets the chat seed (default 0).

## The client

```python
from dfbench_client import load_task, GameClient, ModelClient, ActionLimit, HandsOff, GameOver, BudgetExhausted

t = load_task()                                   # DFBENCH_TASK (JSON, or a path / @path for local use)
game = GameClient(t.game_url)
model = ModelClient(t.model_base_url, t.model_name, t.api_key)
info = game.task()                                # task, rules, tools (OpenAI format), queries, manual
obs = game.observe()                              # facts + envelope: day, tick, days_left, game_over
r = game.act("add_order", {"recipe": "brew_drink", "amount": 5})   # {"ok": False, "error_code", "error"} on failure
game.advance(3)                                   # act("advance_days", {"days": 3})
game.query("stocks"); game.events(since_tick=obs["tick"])
resp = model.chat(messages, tools=info["tools"], tool_choice="required")
model.usage                                       # calls, tokens, cost_usd
```

- `act` returns tool failures as results (the model should see them) and raises `ActionLimit`, `HandsOff` and
  `GameOver` (the loop must handle those). Tool failures may come with HTTP 200 or 4xx; both are results.
- Game requests are retried on connection errors only. A `POST /act` that may have reached the server (timeout,
  reset) is not retried, so an action never runs twice.
- Model calls are retried on connection errors, 5xx, 429 (Retry-After) and `504 upstream_timeout` (the provider
  hung; the gateway charged an estimate). `BudgetExhausted` (402, `gateway_blocked`, or a budget error) and
  `ContextTooLong` are not.
