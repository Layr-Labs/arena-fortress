# The plain baseline harness (season 0)

This is where `submission/` starts: a language model playing the fort from the raw game API, up to 4 tool calls per
turn.
It is deliberately plain. It does what the contract needs and some basic hygiene, and nothing that interprets the
fort for the model.

| file (in `submission/`) | what |
|---|---|
| `plain/harness.py` | the loop and its guards (~300 lines) |
| `plain/prompt.py` | the system prompt: the role, the run's rules and what it is scored on, plus sections 4 and 6 of the game API's own manual. No DF strategy |
| `plain/__main__.py` | the entrypoint (`python -m plain`) |
| `dfbench_client/` | a small stdlib client for the game API and the model gateway (retries, the credit stop) |
| `Dockerfile` | the image: `dfbench_client/` and `plain/`, stdlib only |

(`baseline/plain/` holds the same package with its files at the top level, next to `baseline/dfbench_client/`.)

## What it does each turn

1. `GET /observe`. The observation goes to the model **as the API returns it** (compact JSON), with
   `days_left_in_run`, `hands_off_in_days`, the task's `goal` and `scenario`.
2. History: the system prompt and the last 12 messages. Older observations become a one-line stub, and older tool
   results are cut to 300 characters.
3. One chat call through the gateway: `tool_choice` required, temperature 0, `max_tokens` 4000, reasoning effort low.
4. The reply's tool calls run in order (`POST /act`), at most 4; each result goes back as JSON. A call that moves game
   time (an advance, or the day's action limit) ends the batch, and later calls are answered `not_run`.

Guards:
- **Time keeps moving:** after 10 actions in a row without an advance, or when the day's 40 actions are used up,
  the harness advances one day itself. `advance_days` is capped at 14 days.
- **Order churn**, refused locally with `order_churn`: cancelling an order the harness added under 2 days ago, and
  re-adding an order identical to one it cancelled in the last 3 days. Cancelling and re-adding restarts the
  manager's validation, and a model can loop on it until the credits are gone.
- **Credits:** it stops calling the model at 92% of the game's credits and exits; the server then runs the fort on
  unmanaged to the horizon. A hung provider call (`504 upstream_timeout`) is retried by `dfbench_client`.
- **A failing model:** after 5 failed model turns in a row it exits.

## What it doesn't do

Everything else is yours. The obvious directions, none of them done here:
- **Make the state legible.** The raw observation is long and flat. What matters this turn (drink running low, an
  order that isn't moving, a mood waiting for a workshop) is in there, but the model has to find it every turn.
- **Explain failures.** A rejected action comes back as the API's error code and text. Why an order isn't
  progressing (no manager, no workshop, no input, still waiting for validation) is for the harness to work out.
- **Remember.** The model sees only the last 12 messages, so it forgets what it tried and what failed.
- **Use the read-only queries** (`GET /query/...`: stocks, units, jobs, orders, buildings, zones, map). They're free:
  no actions, no game time.
- **Plan and pace.** When to call the model, how far to advance, several actions between advances, sub-calls,
  where to spend the credits.
- **Know DF.** The prompt says nothing about how DF works: what the manager does, what a workshop needs, how to
  keep drink and food coming, farming, moods, defence. The model plays from whatever it already knows.

The organiser's reference harness (score published at launch) gets above this baseline by working on these. How is
up to you.
