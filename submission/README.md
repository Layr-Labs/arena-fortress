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
- Pins the Python Linux amd64 image digest; no extra Python dependencies.

## Verification status

26 focused regression/existing HTTP-fake integration tests pass. See `NOTE.md` for the exact reproducer,
provenance, limitations and measurements still needed. Fake games are not strategy or score evidence.

Real DF smoke, Docker image build, paid hosted-model runs and baseline-vs-candidate public-suite comparisons
are pending: Docker socket access, participant-supplied DF/DFHack downloads and an OpenRouter key are needed.
No official submission or score has been produced.

`NOTE.md` is the candidate method note; `dependencies.json` declares material published-note inspiration.
Use these files directly with `--note-file submission/NOTE.md --dependencies-file submission/dependencies.json`
when a measured candidate is ready. Do not copy credentials into this directory.
