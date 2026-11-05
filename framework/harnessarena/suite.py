"""Suite-file accessors (docs/TEMPLATE-AGENT-HARNESS.md §3.4): every value an environment used to hardcode comes from
the suite file. The legacy defaults below are dfbench season 0's, kept only so suite files written before these
fields existed keep scoring identically; new suites should set every field.
"""
LEGACY_WEIGHTS = {"OP1": 0.5, "MY1": 0.3, "labs": 0.2}   # dfbench s0 (D21), for suites without "weights"
LEGACY_CONFIRM_TASKS = ["MY1", "OP1"]                     # dfbench s0 (D24), for suites without "confirm_tasks"


def weights(suite):
    """-> the family weights of S."""
    return suite.get("weights") or dict(LEGACY_WEIGHTS)


def confirm_tasks(suite):
    """-> the task ids a confirmation batch replays (the long, noisy ones)."""
    t = suite.get("confirm_tasks")
    return list(t) if t else list(LEGACY_CONFIRM_TASKS)


def stage2_tasks(suite):
    """-> the task ids of stage 2 (played only if stage 1 could still lead)."""
    return [t["id"] for t in suite["tasks"] if int(t.get("stage", 1)) >= 2]


def anchors(suite):
    """-> {task id: {"noop": p, "witness": p}} for the lab tasks that have one."""
    return {t["id"]: t["anchor"] for t in suite["tasks"] if t.get("anchor")}


def environment(suite, default="dfbench"):
    """-> the adapter name that scores this suite."""
    return suite.get("environment") or default
