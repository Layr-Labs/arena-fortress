"""Configuration names: generic `HA_<NAME>` first, then the legacy `DFBENCH_<NAME>`, then the default.

The ~450 DFBENCH_* references stay as they are for season 0 (docs/TEMPLATE-AGENT-HARNESS.md §5.2 step 5 renames
them with aliases for one season). New framework code reads configuration only through `get`, so a second
environment can use HA_* names without touching DF's variables.
"""
import os

PREFIXES = ("HA_", "DFBENCH_")


def get(name, default=None, environ=None):
    """-> the value of HA_<name> or DFBENCH_<name> (first non-empty), else `default`. `name` has no prefix."""
    e = os.environ if environ is None else environ
    for p in PREFIXES:
        v = e.get(p + name)
        if v not in (None, ""):
            return v
    return default


def names(name):
    """-> the variable names `get` reads for `name`, in order (for docs and error messages)."""
    return [p + name for p in PREFIXES]
