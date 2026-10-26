# Roadmap (non-binding)

This is what we are considering for later seasons, so you can see where the challenge is heading. **Nothing here
is a commitment.** Each season's scope is announced in full at its start (as `README.md` does for season 0), and
only that announcement binds.

## Season 1 candidates

| candidate | what it would add | why it's not in season 0 |
|---|---|---|
| **Trade** | a trade tool for caravans (trade depot, offering and requesting goods, export wealth) | a large new tool surface, and export wealth feeds the progression score; it needs its own validation |
| **Stone-bearing sites** | embark rules that guarantee reachable stone (and with it stone furniture, masonry and stone moods) | the season-0 site class is soil-heavy; a new site class changes every task's pool and references |
| **Mood tools** | tools around strange moods (seeing and steering what a mood needs, fetching or making the materials) | moods are off outside the mood task in season 0; tools come with stone sites, since stone moods depend on both |
| **Longer horizons** | multi-year games (e.g. a 3-year task, or a top-K re-check over several years at season close) | a year-long game already takes ~15–30 min; longer games need more runner time per submission |
| **Budget tiers / Pareto board** | score against model credits, or several credit tiers (e.g. $0.10 and $1 per game-year) | season 0 has one cap and reports credits used; the board mode depends on the platform |
| **More task families** | sieges and defence (with a validated raid task), floods, nobles and justice | the raid task isn't admitted yet: its reference solution doesn't hold reliably |
| **Richer game API** | more queries, finer-grained designations (mining, channels, constructions), checkpoint forks for the dev loop | season 0 keeps the API close to the frozen tool set so the reference harnesses carry over |

## Longer term

- A public season, with the season-0 harnesses (published at its close) as starting points.
- Other fixed models, or a track where competitors bring their own model under a receipt scheme.
