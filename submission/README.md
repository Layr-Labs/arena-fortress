# Housing before excess farms

This retains the promoted hybrid harness from `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`:
a daily deterministic controller plus the model's STATUS digest and tool loop.
Sources and policy adaptations are declared in `dependencies.json`.

Changes reserve dormitory, dining and office room roles after two farms, and prevent
new F-site farms on levels reserved for housing. Existing farms remain. A larger migrant wave can reserve another dorm after four farms. During a
migrant bed deficit, model advances are capped at two days and dining production
and placement wait for beds; the manager's office chair keeps its normal path.
After actual bed `no_space`, placement can try up to two other observed indoor A
areas on different levels. Successful alternatives receive dormitory coverage.
A daily brew order has no drink ceiling when the public hands-off goal requires drink growth.
The pacing, bed-priority, drink-growth and alternative-area designs adapt the public notes of
`a9f894ea-c2db-4e37-9883-1ec1e14ec8d4` and
`5ef22a35-d413-4eb5-8332-1a80fbffa67f`; their archive code was not copied.

Migrant bed orders can queue up to 30 jobs; Carpenters scale to two through four shops with population.
The workshop-scaling idea credits `0bc9b753-d53c-4c1d-b23f-92e645821a02`.

The room size remains the inherited 9 by 7. A larger-room trial was inconclusive.
Public local tests use real DF with the canned model (`--stack mixed`), because
this development VM has no configured model API key. Those results do not measure
GLM performance or official private-pool scores. The public submission note records
the tested source versions, measurements and limitations.

Run regressions from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
```
