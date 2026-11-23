"""Module registry (MODULES.json) and route composition stay consistent with the code."""
import fnmatch
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


class ModuleRegistryTests(unittest.TestCase):
    def setUp(self):
        self.reg = json.loads((ROOT / "MODULES.json").read_text())
        from bbmanage import paths as P
        self.files = P.source_files(ROOT)

    def test_every_source_file_has_exactly_one_owner(self):
        orphans, multi = [], []
        for f in self.files:
            owners = [m["id"] for m in self.reg["modules"] if any(fnmatch.fnmatch(f, g) for g in m["files"] + m.get("tests", []))]
            mods = {o for o in owners}
            if not mods:
                orphans.append(f)
            elif len([m for m in self.reg["modules"] if any(fnmatch.fnmatch(f, g) for g in m["files"])]) > 1:
                multi.append(f)
        self.assertEqual(orphans, [], "add these files to a module in MODULES.json")
        self.assertEqual(multi, [], "files claimed by more than one module")

    def test_dependencies_and_tests_exist(self):
        ids = {m["id"] for m in self.reg["modules"]}
        for m in self.reg["modules"]:
            self.assertTrue(set(m["depends"]) <= ids, m["id"])
            for t in m["tests"]:
                if "*" not in t:
                    self.assertTrue((ROOT / t).exists(), t)

    def test_feature_routes_register_without_importing_webapp(self):
        import subprocess
        code = ("import json, sys, routes; routes.load(); "
                "print(json.dumps({'get': sorted(routes.GET), 'post': sorted(routes.POST), "
                "'webapp': 'webapp' in sys.modules, 'none': routes.handle_get('/api/nope', {}) is None}))")
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT / "tools", capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertIn("/api/git", out["get"])
        self.assertIn("/api/projects/open", out["post"])
        self.assertFalse(out["webapp"], "feature modules must not import webapp")
        self.assertTrue(out["none"])

if __name__ == "__main__":
    unittest.main()
