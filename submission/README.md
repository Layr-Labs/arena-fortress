# Migrant housing on the a9f894ea harness

This harness retains pepedesigner's a9f894ea model loop, digest and ordinary-task
policy. The migrant policy adds early bed orders up to the API limit of 30,
a deeper dormitory reserved against farm placement, a third carpenter when
beds are short, and bounded overflow for a confirmed unplaced remainder.
It places an available office chair immediately after creating the office,
before later furniture consumes its floor.

The office-first sequence comes from i34-9's fa9c13cc. GordoAR's 5ef22a35
supplies the inherited goal policies, bed-focused queue and original overflow
route. Our earlier v4 contributes the transferred LT08 mechanisms. Full
source declarations and citations are in dependencies.json.

The runtime uses the game API and fixed GLM gateway, standard-library Python,
and the inherited pinned Dockerfile. Tests run with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests
```

The final runtime passed two local real-DF games with a canned model. The
preceding revision passed two fixed-GLM LT08 games; that hosted result is not
claimed for this exact revision. No new full-suite result is claimed.
