"""dfbench-toolkit: analysis tools for Yukon Arena: Fortress local runs (the game Dwarf Fortress).

inspect: per-game and per-suite reports from `dfbench local run` / `local suite` outputs.
compare: is a change real, or within DF's run-to-run noise?
snapshot: a mid-game start fort from a public fort, for faster iteration.
export:   package a run batch as a research-commons dataset.
"""
__version__ = "0.1.0"
# The challenge scorer this toolkit's aggregation was copied from (runner/dfbenchlib/score.py SCORE_VERSION).
PINNED_SCORE_VERSION = "s0-score/1"
