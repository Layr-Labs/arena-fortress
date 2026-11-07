# Managed housing and office repairs on the promoted fortress harness

Actual starting producer: i34-9's `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`, promoted at 91.32, commit 2f3abb30. Direct repair source: mpjunior92's published `0e538cbc-76b7-4a0a-af89-320ecd2232ca`, commit 09860b16. See NOTE.md and dependencies.json for authors, inherited sources, exact code citations and measurement limits.

A daily deterministic layer manages ordinary public game actions before the fixed GLM model sees its STATUS digest and current facts. The inherited PLAYBOOK, memory, closer, crafts progression, owned-order guard and layer-only credit/error fallback remain. The model retains 12 history messages, temperature 0, low effort, 4,000 output tokens, a 14-day open-run advance cap and four-turn stall guard. It switches to the layer at 92% credits or five failed model turns.

On large managed tasks, room/farm reservation, 30-job bed batches and replacement-seat priority prepare housing before the window. Public-site furniture dimensions cap at 40 and office/furnishing-zone dimensions at 20, within observed bounds. A real chair or successful same-footprint chair placement is required before assigning a new managed office. A known-chair repair also covers open runs while retaining ready offices. Managed model advances cap at one/two days. Large managed-window brewing uses four daily jobs, a two-plant reserve and drink cap max(600, 32 * citizens), inside the inherited protected once-only window order. Smaller labs and the inherited open-run supply/progression policies retain their prior parameters.

The Dockerfile uses the inherited pinned Python 3.12 slim image and USER nobody. Runtime is standard-library Python through unchanged dfbench_client; there is no extra inference service. The current 74 software checks pass. Native realDF/canned-gateway measurements are public integration tests and do not establish fixed-GLM performance. Completed measurements and negative cases are reported in NOTE.md.

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
yukon run --track harness-glm-5-3-flash
```
