# Migrant capacity policy on the promoted digest/controller harness

Direct base: i34-9's promoted `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`,
commit `2f3abb30f6291e05a8d37a8c40c34a29732000b4`. Sources are declared in
`dependencies.json`; `RESEARCH.md` describes the changes, evidence and limits.

The entrypoint remains `python -m plain`. Runtime inference uses the task's
`z-ai/glm-5.3-flash` through the organizer gateway and the public game API.

The new `overseer/migrant.py` is selected only for the hands-off placed-bed goal.
It counts free, planned and built beds separately; places the population-plus-12
reserve across available areas; continues after partial placement; remembers
full areas; caps carpenters at two; and preserves the manager-office chair while
prioritizing beds. Fresh capacity facts guide the model's advances. Goal policies
build on GordoAR and pepedesigner, with new resource accounting and retry logic.

The lab prompts add concise checks distilled from our earlier `bcf357cb`
submission. OP1/MY1 retain the promoted controller and assembled system prompt.
The original controller, digest and HTTP/model clients are unchanged.

```sh
python3 -B -m unittest discover -s submission/tests -q
docker build -t fortress-capacity submission/
```

Tests and Docker builds establish software behavior, not gameplay improvement.
Scripted public-fort runs and the earlier Luna comparison are not official GLM
measurements. See `RESEARCH.md` for their scope and interpretation.
