"""dfbench-tk: analysis tools for dfbench local runs."""
import argparse, json, os, shlex, sys

from . import __version__, commons, compare as C, report, runs, snapshot as SN
from .analysis import game_report


def cmd_inspect(a):
    run = runs.Run(a.run, rescore=not a.no_rescore, suite=_suite_arg(a, a.run) if a.suite else None)
    games = [g for g in run.games if not a.game or g.id in a.game.split(",") or g.task in a.game.split(",")]
    reports = [] if a.summary_only else [game_report(run, g) for g in games]
    if a.json:
        out = json.dumps({"suite": report.suite_summary(run), "games": reports}, indent=1, default=str)
    elif a.html:
        out = report.html_report(run, reports)
    else:
        out = report.markdown(run, reports)
    _emit(out, a.out)


def _suite_arg(a, start):
    if a.suite == "run":
        return None
    return a.suite or runs.default_suite_path(start)


def cmd_compare(a):
    suite = _suite_arg(a, a.runs[0])
    base = runs.Run(a.runs[0], rescore=not a.no_rescore, suite=suite)
    outs = []
    for other in a.runs[1:]:
        r = C.compare(base, runs.Run(other, rescore=not a.no_rescore, suite=suite), resamples=a.resamples)
        outs.append(json.dumps(r, indent=1, default=str) if a.json else C.markdown(r))
    _emit("\n".join(outs), a.out)


def cmd_snapshot(a):
    p = SN.plan(a.task, a.day, a.arm, a.fort, a.image, a.seed, a.out_dir)
    r = SN.run(p, dry=a.dry_run)
    env = " ".join(f"{k}={shlex.quote(v)}" for k, v in r["env"].items())
    print(("would run: " if a.dry_run else "ran: ") + env + " " + " ".join(shlex.quote(x) for x in r["cmd"]))
    if not a.dry_run:
        print(f"snapshot: {r['snapshot']}\ntask:     {r['task_file']}")
        for n in r["notes"]:
            print(f"note: {n}")
        print(f"next:     {r['local_run']}")


def cmd_export(a):
    if not a.commons:
        raise SystemExit("export: only --commons is supported in v0")
    run = runs.Run(a.run, rescore=not a.no_rescore)
    r = commons.export(run, a.out_dir)
    print(f"wrote {r['csv']} and batch.json ({r['meta']['games']} games)\nthen, from your hub clone:\n  {r['publish_cmd']}")


def _emit(s, path):
    if path:
        with open(path, "w") as f:
            f.write(s)
        print(f"wrote {path}", file=sys.stderr)
    else:
        sys.stdout.write(s)


def main(argv=None):
    p = argparse.ArgumentParser(prog="dfbench-tk", description=__doc__)
    p.add_argument("--version", action="version", version=f"dfbench-toolkit {__version__}")
    sp = p.add_subparsers(dest="cmd", required=True)

    i = sp.add_parser("inspect", help="report on a local run or suite directory")
    i.add_argument("run")
    i.add_argument("--game", help="comma list of game ids or task ids (default: all)")
    i.add_argument("--summary-only", action="store_true", help="the suite table only")
    i.add_argument("--html", action="store_true", help="a self-contained HTML report with sparklines")
    i.add_argument("--json", action="store_true")
    i.add_argument("--out", "-o")
    i.add_argument("--no-rescore", action="store_true", help="use score_detail.json even inside a challenge clone")
    i.add_argument("--suite", help="score with this suite file's anchors and weights (default: the run's own)")
    i.set_defaults(fn=cmd_inspect)

    c = sp.add_parser("compare", help="is run B really different from run A? (B vs A; more runs: each vs A)")
    c.add_argument("runs", nargs="+")
    c.add_argument("--resamples", type=int, default=4000)
    c.add_argument("--json", action="store_true")
    c.add_argument("--out", "-o")
    c.add_argument("--no-rescore", action="store_true")
    c.add_argument("--suite", help="suite file whose anchors and weights score both runs (default: the challenge "
                   "clone's runner/suites/season0-public.json; 'run' = each run's own, which must then agree)")
    c.set_defaults(fn=cmd_compare)

    s = sp.add_parser("snapshot", help="a day-N start fort from a public task, for faster iteration")
    s.add_argument("--task", required=True, help="a public task file, e.g. scenarios/season0/op1-start-year.json")
    s.add_argument("--day", type=int, required=True)
    s.add_argument("--arm", default="automation", choices=SN.ARMS, help="who plays the first N days")
    s.add_argument("--fort", help="start fort (default: the task's first public fort)")
    s.add_argument("--image", default="yukon-df", help="your DF image (docker/README.md)")
    s.add_argument("--seed", type=int, default=12345)
    s.add_argument("--out-dir")
    s.add_argument("--dry-run", action="store_true", help="print the batch command, don't run it")
    s.set_defaults(fn=cmd_snapshot)

    e = sp.add_parser("export", help="package a run batch for research-commons")
    e.add_argument("run")
    e.add_argument("--commons", action="store_true")
    e.add_argument("--out-dir", default="commons-batch")
    e.add_argument("--no-rescore", action="store_true")
    e.set_defaults(fn=cmd_export)

    a = p.parse_args(argv)
    if a.cmd == "compare" and len(a.runs) < 2:
        p.error("compare needs at least two run directories")
    a.fn(a)


if __name__ == "__main__":
    main()
