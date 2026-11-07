# Reserve living space and produce migrant beds early

Builds on i34-9's promoted `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4` and its declared controller/digest lineage. The inherited hybrid loop, ownership guard, closer and progression policy remain. See `dependencies.json` for the retained sources.

The digging controller establishes two farms, then reserves missing dormitory, dining and office rooms before expanding farms further. Dormitory dimensions account for population and arrivals, within the API's 20-tile dimension limit. This avoids allocating every soil room to farms and subsequently excluding every underground floor from furniture placement.

For a task whose goal announces migrants, bed orders cover up to 30 of the shortfall at once. Extra dining furniture waits until the bed-item target is secured; a fort with no chair can still request chairs for its manager. Other tasks retain the existing routine furniture batch limits.

Validation: 49 unit tests pass. Real DF with the runner's canned model (mixed stack), public seed 2001 LT08: baseline partial 0.7354, zero installed beds; reservation alone about 0.88; larger rooms about 0.89; early bed batch 0.9896 with the bed condition met. Seed 2002 early-bed run about 0.98. Neither final candidate run passed every LT08 condition. These are local diagnostic runs, not GLM measurements or official scores; migrant counts differ across runs.

Run tests from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
```

The image entrypoint remains `python -m plain`, using the predecessor's pinned Python base and unprivileged user.

Full-year local mixed OP1 check: candidate outcome 87.5 (tier 3), original controller 44.9 (tier 0). The original had one citizen death and the candidate none; nondeterministic population histories confound attribution of the outcome difference. Both completed 336 days.
