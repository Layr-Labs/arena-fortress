"""docker/task_forts.sh --skip-existing (issue #211: `yukon setup` rebuilt finished lab forts on every re-run).
No Docker: a stub `docker` on PATH records the calls; the forts are fake folders with real hashes.
Run: python3 -m unittest runner.tests.test_task_forts
"""
import hashlib, json, os, stat, subprocess, tempfile, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPTS = ["embark/build_fort.py", "embark/fort_events.lua", "embark/fort_stock.lua", "embark/fort_site.lua"]
RECIPES = ("worked-y1", "neglected-y1")


def sha(p):
    return hashlib.sha256(open(os.path.join(ROOT, p), "rb").read()).hexdigest()


def build_sha():
    return hashlib.sha256(b"".join(sha(p).encode() for p in SCRIPTS)).hexdigest()


class SkipExisting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "snapshots")
        self.log = os.path.join(self.tmp, "docker.log")
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir)
        stub = os.path.join(bindir, "docker")
        with open(stub, "w") as f:   # every call succeeds; `docker info` answers the CPU count
            f.write(f'#!/bin/bash\necho "$*" >> {self.log}\n[ "$1" = info ] && echo 4\nexit 0\n')
        os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
        self.env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"])

    def fort(self, seed, recipe, recipe_sha=None, build=None, world=True):
        d = os.path.join(self.out, f"fort-{recipe}-{seed}")
        os.makedirs(d, exist_ok=True)
        if world:
            open(os.path.join(d, "world.sav"), "wb").write(b"x")
        json.dump({"task_fort": {"recipe": recipe,
                                 "recipe_sha256": recipe_sha or sha(f"embark/forts/{recipe}.json"),
                                 "build_sha256": build or build_sha()}},
                  open(os.path.join(d, "SNAPSHOT.json"), "w"))

    def run_tf(self, *extra):
        p = subprocess.run(["bash", "docker/task_forts.sh", "--seeds", "2001", "--out", self.out, *extra],
                           cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        calls = open(self.log).read().splitlines() if os.path.exists(self.log) else []
        return p.stdout, [c for c in calls if c.startswith("run ")]

    def test_complete_current_forts_are_skipped(self):
        for r in RECIPES:
            self.fort(2001, r)
        out, runs = self.run_tf("--skip-existing")
        self.assertIn("seed 2001: forts exist", out)
        self.assertEqual(runs, [])
        self.assertTrue(os.path.exists(os.path.join(self.out, "fort-worked-y1-2001", "world.sav")))

    def test_a_missing_recipe_rebuilds_the_whole_seed(self):
        self.fort(2001, "worked-y1")          # neglected-y1 missing: both rebuilt on one shared embark
        out, runs = self.run_tf("--skip-existing")
        self.assertNotIn("forts exist", out)
        self.assertEqual(len(runs), 1)

    def test_incomplete_fort_is_rebuilt(self):
        self.fort(2001, "worked-y1")
        self.fort(2001, "neglected-y1", world=False)
        _, runs = self.run_tf("--skip-existing")
        self.assertEqual(len(runs), 1)

    def test_stale_recipe_or_build_is_rebuilt(self):
        for stale in ({"recipe_sha": "0" * 64}, {"build": "0" * 64}):
            with self.subTest(**stale):
                os.path.exists(self.log) and os.remove(self.log)
                self.fort(2001, "worked-y1", **stale)
                self.fort(2001, "neglected-y1")
                _, runs = self.run_tf("--skip-existing")
                self.assertEqual(len(runs), 1)

    def test_without_the_flag_it_always_builds(self):   # the verifier's behaviour is unchanged
        for r in RECIPES:
            self.fort(2001, r)
        _, runs = self.run_tf()
        self.assertEqual(len(runs), 1)


class SetupPassesIt(unittest.TestCase):
    def test_setup_keeps_forts_unless_asked_to_rebuild(self):
        src = open(os.path.join(ROOT, "runner", "yukon", "setup.sh")).read()
        self.assertIn("KEEP=(--skip-existing)", src)
        self.assertIn('[ "${DFBENCH_REBUILD_FORTS:-}" = 1 ] && KEEP=()', src)
        self.assertIn('${KEEP[@]+"${KEEP[@]}"}', src)   # bash 3.2-safe empty-array expansion


if __name__ == "__main__":
    unittest.main()
