#!/usr/bin/env python3
"""Writes runner/fakes/tool_schemas.json from the real game server's tool schemas (gameapi/facts/tools.py), so the
fake game server (fake_game.py) takes exactly the argument shapes the real one does. The fakes image has no
gameapi/, so the schemas are vendored; runner/tests/test_runner.py checks the copy matches.

  python3 -I runner/fakes/gen_tool_schemas.py        # from the repo root, after changing gameapi/facts/tools.py
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "tool_schemas.json")


def current():
    sys.path.insert(0, ROOT)
    from gameapi.facts.tools import tool_schemas
    return tool_schemas()


if __name__ == "__main__":
    with open(OUT, "w") as f:
        json.dump(current(), f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"wrote {OUT}")
