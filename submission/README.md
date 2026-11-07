# The steward harness (season 0)

A deterministic playbook keeps the fort's essentials running every cycle, and glm-5.3-flash is consulted as an
overseer every few game days or on events. The image runs `python -m steward`. NOTE.md at the challenge repo's
root (the submission's public note) has the design, the findings from real DF and the measurements.

| file | what |
|---|---|
| `steward/harness.py` | the loop: observe, playbook actions, model consults, advances paced to the wall clock, crash recovery |
| `steward/playbook.py` | the rules: manager and office, automation, workshops, standing and one-off orders, digging, farms, beds, dormitory, dining hall, food emergencies, mood workshops, civilian alert; and the refusals for model actions |
| `steward/digest.py` | the observation as a short status report for the model |
| `steward/prompt.py` | the system prompt (identical for every call in a game, for prefix caching) and the model's tool list |
| `dfbench_client/` | the organiser's stdlib client, unchanged |
| `plain/` | the organiser's plain baseline, unchanged and unused (kept for reference) |
| `dependencies.json` | the declared dependency (see NOTE.md) |
| `Dockerfile` | `python:3.12-slim`, stdlib only |
