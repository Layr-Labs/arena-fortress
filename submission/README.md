# Fortress harness: public-facts advisor and recoverable failure memory

Starts from the organisers' plain baseline at main commit `75d40aa6adc8ee1b3f3b5ad1d74c3674f1ff3abf`.
Only `submission/` is modified. The task still supplies the fixed model and metered gateway.

## Changes

- Retains raw observations and adds bounded `harness_status`: manager/office and production prerequisites,
  distinct-time stock trends, built-furniture housing facts, dug soil rooms, and hands-off reminders.
- Remembers at most eight deterministic action failures beyond the conversation window. Refuses identical retries
  only while tick, public facts and successful-action epoch remain unchanged. Progress unlocks retries.
- Offers `inspect_fort` for the intersection of documented read-only query names and `/task` capabilities.
  Query arguments are allowlisted; output is bounded valid JSON with explicit truncation.
- Adds a public-manual-based production/verification checklist. The model still chooses all game actions.
- Adds a standing-guard doctrine and bounded public `defense` diagnostics: carried weapons, eligible adults,
  worker-preserving recruitment caps, immediate threat/shelter advice and relief for stressed or labor-starved guards.
  This API offers one squad and no training command. Stationing is not training; armor templates are not worn armor.
- Pins the Python Linux amd64 image digest; no extra Python dependencies.

## Verification status

38 regression/existing HTTP-fake integration tests pass, including twelve readiness cases added red-first.
The standing-guard candidate also completed a native-Z.ai real-DF 14-day public MY1 run: 15/15 survivors,
14 successful model calls, no provider errors, and $0.02184109 reference-price usage under a custom $0.05 cap.
That fort had zero free weapons throughout; no squad was formed, so armed deployment remains unverified.
See `NOTE.md` for the exact test reproducer. Fake games are not strategy or score evidence.

Rootless Docker setup, image builds and real DF smoke are complete. Before the military changes, the candidate
completed a seven-day OP1 game with native Z.ai GLM-5.3-Flash: 25 successful model calls, no provider errors,
horizon finish, exit 0, and $0.02140337 at reference token prices. A local-only gateway image translated model and
reasoning fields; it is not part of the submission and is not the pinned official Together provider. Neither that
short run nor unit tests establish a score gain. Matched public-suite comparisons remain outstanding.

`NOTE.md` is the candidate method note; `dependencies.json` declares material published-note inspiration.
Use these files directly with `--note-file submission/NOTE.md --dependencies-file submission/dependencies.json`
when a measured candidate is ready. Do not copy credentials into this directory.
