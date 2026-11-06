# fort: a playbook-first harness

The fort is run by deterministic rules over the game API's facts. The model (`z-ai/glm-5.3-flash`) advises at
checkpoints and when the rules report problems; its calls are limited to additive tools. `NOTE.md` has the method
and the measurements.

| file | what |
|---|---|
| `fort/harness.py` | the loop: observe, playbook actions, advisor at checkpoints, advance with tripwires |
| `fort/state.py` | a read-only view of one observation: stocks, sites, workshops, zones, problems, a text summary |
| `fort/playbook.py` | the economy: manager, plugins, workshops, standing orders with stock conditions, pacing |
| `fort/layout.py` | stairs, a farm level and a living level, farm plots, furniture, zones, the manager's office |
| `fort/crisis.py` | strange moods (the workshop each mood skill claims), hostiles, food emergencies |
| `fort/advisor.py` | one model call with a compact brief; up to 4 tool calls from an allowed set |
| `fort/knowledge.py` | the advisor's system prompt: scoring order and the DF facts the tools touch |
| `fort/memory.py` | attempts, back-off, failures and notes across turns |
| `dfbench_client/` | the plain baseline's stdlib client for the game API and the gateway (unchanged) |

Environment switches for local testing only: `FORT_NO_ADVISOR=1` (no model calls), `FORT_MAX_DAY=N` (stop at day N).
