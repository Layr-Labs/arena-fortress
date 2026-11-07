"""snapshot: a mid-game start fort, so a harness can be iterated on a day-N state instead of replaying from day 0.

It wraps what the challenge repo already ships: `docker/batch.sh` runs `smoke.py` inside your DF image, plays a
public task's start fort for N days with a built-in arm (noop: nobody manages the fort; automation: DFHack's
automation plays it), and quicksaves at day N (`smoke.py --snapshot-days`). The toolkit then installs the save as a
start fort and writes a task file whose start is that fort, for `runner/dfbench local run --task`.

Local iteration only: a snapshot task has its own task hash, so its scores aren't comparable with the official
tasks (or with each other across different N).
"""
import glob, json, os, shlex, shutil, subprocess

from . import challenge

ARMS = ("noop", "automation")


def plan(task_path, day, arm="automation", fort=None, image="yukon-df", seed=12345, out=None, root=None):
    root = root or challenge.find_root()
    if root is None:
        raise SystemExit("run this inside a clone of the challenge repo (or set DFBENCH_CHALLENGE_DIR): the snapshot "
                         "is played by its docker/batch.sh and smoke.py in your DF image")
    if arm not in ARMS:
        raise SystemExit(f"--arm must be one of {ARMS}")
    tp = task_path if os.path.isabs(task_path) else os.path.join(root, task_path)
    with open(tp) as f:
        task = json.load(f)
    days = int(task.get("days") or 336)
    if not 1 <= day < days:
        raise SystemExit(f"--day must be between 1 and {days - 1} (the task's horizon is {days} days)")
    pool = task.get("snapshot_pool") or []
    pool = [pool] if isinstance(pool, str) else pool
    start = fort or (pool[0] if pool else task.get("snapshot") or "fort_start_snapshot")
    stem = os.path.splitext(os.path.basename(tp))[0]
    name = f"{stem}-{os.path.basename(start.rstrip('/'))}-{arm}-d{day}"
    out = out or os.path.join(root, "runs", "snapshots", name)
    build_task = {**{k: v for k, v in task.items() if k not in ("snapshot_pool", "snapshot_pool_private")},
                  "snapshot": start, "days": day}
    return {"root": root, "task_path": tp, "task": task, "start": start, "arm": arm, "day": day, "image": image,
            "seed": seed, "out": out, "name": name, "build_task": build_task,
            "build_task_path": os.path.join(out, "scen", f"{name}.build.json"),
            "snaps": snapshots_dir(root)}


IMAGE_REPO = "/root/dfprobe"   # where docker/Dockerfile puts the repo in the DF image (docker/batch.sh runs from it)


def batch_cmd(p):
    """docker/batch.sh runs smoke.py on the repo copy inside the image: mount the generated task file and the public
    start forts (built on the host by .yukon/setup.sh) into it, through batch.sh's DOCKER_RUN_EXTRA hook."""
    scen = os.path.dirname(p["build_task_path"])
    extra = (f"-v {shlex.quote(scen)}:{IMAGE_REPO}/scenarios/local:ro "
             f"-v {shlex.quote(p['snaps'])}:{IMAGE_REPO}/scenarios/snapshots:ro")
    cmd = ["bash", os.path.join(p["root"], "docker", "batch.sh"), "--out", p["out"], "--image", p["image"],
           "--arms", p["arm"], "--runs", "1", "--parallel", "1", "--seed", str(p["seed"]), "--",
           "--scenario", f"scenarios/local/{os.path.basename(p['build_task_path'])}",
           "--days", str(p["day"]), "--snapshot-days", str(p["day"])]
    return cmd, {"DOCKER_RUN_EXTRA": extra}


def snapshots_dir(root):
    return os.environ.get("DFBENCH_SNAPSHOTS_DIR") or os.path.join(root, "scenarios", "snapshots")


def derived_task(p):
    """The task that starts from the snapshot: the setup already ran, the horizon and any hands-off window shift."""
    t = {k: v for k, v in p["task"].items() if k not in ("snapshot_pool", "snapshot_pool_private", "seed_variant")}
    t.update(id=f"{p['task'].get('id', 'task')}-from-d{p['day']}", name=f"{p['task'].get('name', 'task')}-d{p['day']}",
             split="local", snapshot=f"scenarios/snapshots/{p['name']}", setup=[],
             days=int(p["task"].get("days") or 336) - p["day"],
             provenance=f"dfbench-tk snapshot: {os.path.relpath(p['task_path'], p['root'])} played {p['day']} days "
                        f"by the {p['arm']} arm from {p['start']}; local iteration only (not an official task)")
    notes = []
    if "active_days" in t:
        a = int(t["active_days"]) - p["day"]
        if a <= 0:
            notes.append("the snapshot is already inside the task's hands-off window: no actions will be accepted")
        t["active_days"] = max(0, a)
    t["_toolkit_notes"] = notes
    return t


def run(p, dry=False):
    os.makedirs(os.path.dirname(p["build_task_path"]), exist_ok=True)
    with open(p["build_task_path"], "w") as f:
        json.dump(p["build_task"], f, indent=1)
    cmd, env = batch_cmd(p)
    if dry:
        return {"cmd": cmd, "env": env}
    r = subprocess.run(cmd, cwd=p["root"], env={**os.environ, **env})
    if r.returncode != 0:
        raise SystemExit(f"docker/batch.sh failed (exit {r.returncode})")
    hits = sorted(glob.glob(os.path.join(p["out"], "**", "snapshots", f"*-d{p['day']}"), recursive=True))
    if not hits:
        raise SystemExit(f"no snapshot written under {p['out']} (see its logs)")
    dst = os.path.join(snapshots_dir(p["root"]), p["name"])
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(hits[-1], dst)
    t = derived_task(p)
    tdir = os.path.join(p["root"], "scenarios", "local")
    os.makedirs(tdir, exist_ok=True)
    tpath = os.path.join(tdir, f"{p['name']}.json")
    with open(tpath, "w") as f:
        json.dump(t, f, indent=1)
    return {"cmd": cmd, "env": env, "snapshot": dst, "task_file": tpath, "notes": t["_toolkit_notes"],
            "local_run": local_run_cmd(p["root"], tpath)}


def local_run_cmd(root, task_file):
    return ("runner/dfbench local run --harness submission/ --task "
            + shlex.quote(os.path.relpath(task_file, root)) + " --n 1")
