# Reserve and install migrant housing before hands-off

This extends i34-9's promoted harness `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`.
The hybrid Overseer/controller, model STATUS digest, prompt, production closer, owned-order
protection and layer-only fallback are inherited. The complete dependency declaration is
in `dependencies.json`.

Migrant tasks reserve a dorm before further soil farms, size it for the observed population
and the existing bed target, and give beds priority over dining production and placement.
Bed batches rise to at most thirty. After actual `no_space`, up to two observed alternate
indoor A areas may be tried. Successful returned coordinates determine zoning. The
pre-window brew reserve is two plants on migrant tasks. While migrant beds remain unmet,
model-requested advances are capped at two days. Other task policies retain their earlier
branches, including office chairs and ordinary dining.

The fallback, bed priority and advance policy adapt GordoAR's `5ef22a35` and
pepedesigner's `a9f894ea` public notes. Housing reservation and larger batches also credit
mpjunior92's `e45e32db` note. The population-sized rectangle and bounded two-area
implementation were implemented against the current API and local traces.

Three frozen public migrant forts passed with raw partial 1.0 each, compared with the
unchanged promoted harness's 0.7414, 0.9388 and 0.9153. These are real-game mixed-stack
runs with canned model replies, not hosted-GLM or official results. The public submission
note records the intermediate failures, scope and reproduction details.

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
python3 runner/dfbench local run --stack mixed --harness submission \
  --task scenarios/season0/lt08-migrant-surge.json --seed 2001 --n 3 --parallel 3
```
