# Changelog

## 0.1.0 (unreleased)

First version, for dfbench season 0.

- `inspect`: Markdown, HTML (inline SVG sparklines) or JSON reports of a local run or suite: the suite table (S,
  the 95% lower bound, per-task scores), and per game the timeline, outcome tier and which gate failed with its
  evidence, lab clauses, actions and rejections (K per day), model calls, tokens, latency, throttling, credits by
  phase, and DF's events.
- `compare`: S and lower-bound differences between runs, with a bootstrap CI of the difference (paired on shared
  forts and seeds when possible), a verdict and the number of games that would resolve it.
- `snapshot`: a day-N start fort from a public task, played by DFHack's automation or by nobody, and a task file
  that starts from it.
- `export --commons`: a per-game CSV and batch metadata for a research-commons dataset.
- Labels: a `dfbench local ... --watch` run (rendered and recorded DF) is labelled watch mode in reports, and
  `compare` lists `watch` among the labels that differ.
- Scores with the challenge's own scorer inside a challenge clone; a pinned copy of its aggregation (s0-score/1)
  otherwise.
