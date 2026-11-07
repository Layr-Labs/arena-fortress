"""Lossless, model-visible tables for repeated public observation records.

Only the named paths are encoded; all other facts pass through. Consecutive
records with the same keys form a table, so heterogeneous/missing fields retain
their meaning without null padding. No game-state inference or tool selection.
"""
import json

PATHS = (("dwarves",), ("map", "sites"))
EXPLANATION = ("LOSSLESS TABLES at {paths}: each value is a list of tables with columns and rows. "
               "Read each row as an object mapping columns to its values; concatenate tables in order. "
               "Null is null; a column absent from a table is absent from those records. "
               "All other observation fields are unchanged.\n")


def dumps(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _tables(records):
    if not isinstance(records, list) or not records:
        return None
    tables = []
    keys = None
    for record in records:
        if not isinstance(record, dict) or not record or not all(isinstance(k, str) for k in record):
            return None
        if keys is None or set(record) != set(keys):
            keys = list(record)
            tables.append({"columns": keys, "rows": []})
        tables[-1]["rows"].append([record[k] for k in keys])
    return tables


def pack_observation(obs):
    """Return (copy-on-write observation, explicit encoded paths).

    The path sidecar makes decoding unambiguous even if a future raw API object
    itself resembles a table. A conversion must pay for its entire explanation
    alone, plus a 64-character margin; therefore combinations also save space.
    Nested cell values are preserved, not recursively interpreted as tables.
    """
    if not isinstance(obs, dict):
        return obs, []
    packed = obs
    paths = []
    for path in PATHS:
        parent = obs if len(path) == 1 else obs.get(path[0])
        if not isinstance(parent, dict):
            continue
        records = parent.get(path[-1])
        tables = _tables(records)
        name = ".".join(path)
        if tables is None or len(dumps(records)) - len(dumps(tables)) <= len(
                EXPLANATION.format(paths=name)) + 64:
            continue
        if packed is obs:
            packed = dict(obs)
        if len(path) == 1:
            packed[path[0]] = tables
        else:
            packed[path[0]] = {**obs[path[0]], path[-1]: tables}
        paths.append(name)
    return packed, paths


def unpack_observation(packed, paths):
    """Exact semantic inverse for the explicit paths emitted by pack_observation."""
    obs = dict(packed) if paths else packed
    for name in paths:
        path = name.split(".")
        parent = obs if len(path) == 1 else obs[path[0]]
        records = [dict(zip(table["columns"], row))
                   for table in parent[path[-1]] for row in table["rows"]]
        if len(path) == 1:
            obs[path[0]] = records
        else:
            obs[path[0]] = {**parent, path[-1]: records}
    return obs


def observation_message(obs):
    packed, paths = pack_observation(obs)
    if paths:
        # Keep the established prefix so window() still stubs older observations.
        return "OBSERVATION " + dumps(packed) + "\n" + EXPLANATION.format(paths=", ".join(paths))
    return "OBSERVATION " + dumps(obs)
