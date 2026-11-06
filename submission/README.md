# Persistent fortress care

The controller maintains labor, workshops, standing production, the manager's office, farms and
placed furniture. GLM-5.3-Flash handles occasional diagnosis through the task's model gateway.
Every action uses the game API. No planning interpreter, search engine or neural evaluator is
part of this release.

`plain/controller.py` selects routine actions from observations and remembers failures.
`plain/harness.py` owns observation, execution, model consultation and time advancement. The
organiser's `dfbench_client` package and module entrypoint are retained. The Python image is
pinned by digest and the runtime uses only the standard library.

Run with `python -m plain` and the runner-provided `DFBENCH_TASK`. From the repository root,
run tests with `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s submission/tests -v`.
Tests use the repository's public HTTP fakes and are not copied into the game image.

See `NOTE.md` for provenance, experiments, limitations and reproduction details.
Population-scaled workshops, pre-window drink targets and standing-order replacement adapt
mpjunior92's submission `afd1d5b6-b2c0-4790-a7b8-c1e71e3dab4a`, declared in `dependencies.json`.
