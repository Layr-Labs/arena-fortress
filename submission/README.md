# Deterministic layer with owned craft stopping and lab-office repair

This revision retains the complete controller from my published `11ff6d2a-2c8e-4825-90e9-efbca40b3133` and uses the model-free branch of `d1febd13-b50c-4bec-84cd-e078d68a4156` by 0xplemonade. After setup it enters the existing `layer_only` loop. No playing-model requests are made. The fixed-model client remains in the package, unused while `NO_MODEL` is true. This is an adaptation of that published design, not a new claim of inventing model-free play. Its two tests are reused.

The retained controller cancels only its own repeating wood-crafts orders once observed created wealth reaches 5,500, can restart below target, and repairs a chairless manager office before lab hands-off windows. Cross-type workshop-site reservations, office-aware status parsing, shelter/hatch admission, thaw guard, goal policies, supply, dining and housing behavior remain. Dependencies and source citations are in `dependencies.json`.

The direct predecessor's official evaluation was full, real, 48 games: lower bound 91.29, point 94.62, not promoted against 96.02; fairness passed. Those are predecessor results, not this archive's score. The published model-free source scored 95.91, also below the frontier. Neither result proves this combination improves the benchmark.

The assembled revision passes 37 tests, including the no-model branch's zero-call and continued-game checks. Local games use real DF and the mixed stack. A model-free candidate makes no fake or real gateway requests; public-fort results still are not ranked private-pool evidence. Full measurements for this revision will be recorded in its public submission note before submission.

Dairy, sleeper-admission, bed-projection, and failed coordinate-workshop prototypes are separate experiments and are not part of this archive. Standard-library Python and ordinary game API tools only.

Run tests: `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s submission/tests`.
