"""Season-0 code must run without gameapi/season1: the season-0 challenge export leaves season-1 paths out
(scripts/public_export.py CHALLENGE_EXCLUDE; docs/season1/BRIEF.md ground rule 1). On 2026-10-29 a hard import of
gameapi.season1 in the server crashed every game image built from a challenge clone. Any import of it outside
gameapi/season1/ must sit inside a `try:` that catches ImportError, or under a season-1-only condition (`if s1:`)."""
import ast, os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _guarded(tree, node):
    for t in ast.walk(tree):     # only reached for a season-1 task (`if s1:` / rules_version): fine in a season-0 export
        if isinstance(t, ast.If) and any(node is n or node in ast.walk(n) for n in t.body):
            test = ast.unparse(t.test)
            if test in ("s1",) or "rules_version" in test or test.startswith("s1 "):
                return True
        if isinstance(t, ast.Try) and any(node is n or node in ast.walk(n) for n in t.body):
            for h in t.handlers:
                names = [h.type] if not isinstance(h.type, ast.Tuple) else list(h.type.elts)
                if any(isinstance(n, ast.Name) and n.id in ("ImportError", "ModuleNotFoundError", "Exception")
                       for n in names if n is not None):
                    return True
    return False


class NoHardSeason1Import(unittest.TestCase):
    def test_season0_code_does_not_hard_import_season1(self):
        bad = []
        for base in ("gameapi", "runner", "bench", "gateway"):
            for dp, dn, fn in os.walk(os.path.join(ROOT, base)):
                if os.sep + "season1" in dp or "/tests" in dp:
                    continue
                for f in fn:
                    if not f.endswith(".py"):
                        continue
                    p = os.path.join(dp, f)
                    tree = ast.parse(open(p).read(), p)
                    for node in ast.walk(tree):
                        mod = None
                        if isinstance(node, ast.ImportFrom):
                            mod = (node.module or "") + "." + ".".join(a.name for a in node.names)
                        elif isinstance(node, ast.Import):
                            mod = ".".join(a.name for a in node.names)
                        if mod and "season1" in mod and not _guarded(tree, node):
                            bad.append(f"{os.path.relpath(p, ROOT)}:{node.lineno}")
        self.assertEqual(bad, [], "unguarded season-1 imports in season-0 code")


if __name__ == "__main__":
    unittest.main()
