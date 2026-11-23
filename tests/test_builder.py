"""Book Builder: project registry, new projects, project isolation, metadata saving and settings.

Every test uses a temporary BOOK_BUILDER_HOME and temporary project folders; the real book and
the real ~/.book-builder are never touched.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
PY = sys.executable


def run_py(code: str, home: Path, project: Path | None = None) -> dict:
    """Run code in a fresh interpreter (modules read BOOK_PROJECT/BOOK_BUILDER_HOME at import)."""
    env = {**os.environ, "BOOK_BUILDER_HOME": str(home), "PYTHONPATH": str(TOOLS)}
    if project:
        env["BOOK_PROJECT"] = str(project)
    else:
        env.pop("BOOK_PROJECT", None)
    r = subprocess.run([PY, "-c", code], env=env, capture_output=True, text=True, timeout=120, cwd=TOOLS)
    if r.returncode:
        raise AssertionError(r.stderr[-2000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"

    def tearDown(self):
        self.tmp.cleanup()

    def test_home_project_is_registered_without_migration(self):
        out = run_py("import json, registry as R; lib = R.library(R.APP); print(json.dumps([b['path'] for b in lib]))",
                     self.home)
        self.assertIn(str(ROOT), out)

    def test_create_project_and_refuse_nonempty_folder(self):
        dest = Path(self.tmp.name) / "novel"
        code = (f"import json, registry as R; a = R.create('My Novel', 'fiction', {str(dest)!r}, 'A. Writer'); "
                f"b = R.create('Again', 'fiction', {str(dest)!r}); print(json.dumps([a, b]))")
        a, b = run_py(code, self.home)
        self.assertTrue(a["ok"], a)
        self.assertFalse(b["ok"])
        self.assertTrue((dest / "book.yml").exists())
        self.assertTrue((dest / "research/03-content-outline.md").exists())
        self.assertTrue((dest / "assets/typst/callouts.typ").exists(), "build templates are copied")

    def test_new_project_parses_and_is_isolated(self):
        dest = Path(self.tmp.name) / "guide"
        run_py(f"import json, registry as R; print(json.dumps(R.create('Guide', 'nonfiction', {str(dest)!r})))", self.home)
        out = run_py("import json, chapter as C; ch = C.parse_outline()[0]; "
                     "print(json.dumps({'root': str(C.ROOT), 'n': len(ch), 'titles': [c['title'] for c in ch]}))",
                     self.home, dest)
        self.assertEqual(out["root"], str(dest.resolve()))
        self.assertEqual(out["n"], 6)                       # only the template's chapters
        self.assertNotIn("Glossary", out["titles"])

    def test_home_project_still_has_all_items(self):
        out = run_py("import json, chapter as C; print(json.dumps(len(C.parse_outline()[0])))", self.home)
        self.assertEqual(out, 4)   # the sample book's four chapters

    def test_import_requires_book_yml(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        out = run_py(f"import json, registry as R; print(json.dumps(R.import_folder({str(empty)!r})))", self.home)
        self.assertFalse(out["ok"])

    def test_forget_never_deletes_the_folder(self):
        dest = Path(self.tmp.name) / "keep"
        run_py(f"import json, registry as R; R.create('Keep', 'custom', {str(dest)!r}); "
               f"print(json.dumps(R.forget({str(dest)!r})))", self.home)
        self.assertTrue((dest / "book.yml").exists())

    def test_settings_ignore_unknown_keys_and_stay_out_of_projects(self):
        out = run_py("import json, registry as R; s = R.save_settings({'theme': 'dark', 'title': 'Hacked', 'privacy': {'fetchFontCatalog': False, 'x': 1}}); "
                     "print(json.dumps(s))", self.home)
        self.assertEqual(out["theme"], "dark")
        self.assertNotIn("title", out)
        self.assertNotIn("x", out["privacy"])
        self.assertFalse(out["privacy"]["fetchFontCatalog"])
        self.assertTrue((self.home / "settings.json").exists())


class MetadataSaveTests(unittest.TestCase):
    """save_book_meta keeps comments and the chapter list, and only rewrites changed fields."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.proj = Path(self.tmp.name) / "book"
        run_py(f"import json, registry as R; print(json.dumps(R.create('Meta Test', 'nonfiction', {str(self.proj)!r})))", self.home)
        text = (self.proj / "book.yml").read_text()
        (self.proj / "book.yml").write_text(text.replace("  lang: en-US\n", "  # keep this comment\n  lang: en-US\n"))

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, data: dict) -> dict:
        return run_py(f"import json, webapp as W; print(json.dumps(W.save_book_meta({data!r})))", self.home, self.proj)

    def test_roundtrip_new_and_changed_fields(self):
        import yaml
        before = yaml.safe_load((self.proj / "book.yml").read_text())
        r = self.save({"subtitle": "A: tricky subtitle", "keywords": "one, two", "description": "Line one\nLine two",
                       "margin.top": "1in", "editor": "Ed Itor"})
        self.assertTrue(r["ok"], r)
        text = (self.proj / "book.yml").read_text()
        after = yaml.safe_load(text)
        self.assertIn("# keep this comment", text)
        self.assertEqual(after["parts"], before["parts"])
        m = after["metadata"]
        self.assertEqual(m["subtitle"], "A: tricky subtitle")
        self.assertEqual(m["keywords"], ["one", "two"])
        self.assertEqual(m["description"], "Line one\nLine two")
        self.assertEqual(m["margin"]["top"], "1in")
        self.assertEqual(m["editor"], "Ed Itor")

    def test_unchanged_save_writes_nothing(self):
        before = (self.proj / "book.yml").read_bytes()
        r = self.save({"title": "Meta Test"})
        self.assertEqual(r["message"], "Nothing changed.")
        self.assertEqual((self.proj / "book.yml").read_bytes(), before)

    def test_required_fields_cannot_be_emptied(self):
        r = self.save({"title": "   "})
        self.assertFalse(r["ok"])


class InsightsTests(unittest.TestCase):
    def test_health_never_reports_unrun_checks_as_passed(self):
        tmp = tempfile.TemporaryDirectory()
        home, proj = Path(tmp.name) / "home", Path(tmp.name) / "b"
        run_py(f"import json, registry as R; print(json.dumps(R.create('H', 'fiction', {str(proj)!r})))", home)
        out = run_py("import json, insights as I; "
                     "chs = [{'code': 'research', 'serious': 0, 'status': 'planned', 'words': 0, 'part': 1, 'partName': 'x'}]; "
                     "print(json.dumps(I.health(chs, 'h', {'configured': False})))", home, proj)
        items = {i["label"]: i["status"] for cat in out["categories"].values() for i in cat}
        self.assertEqual(items["Formatting check (build.py check)"], "unchecked")
        self.assertEqual(items["EPUB validation"], "unchecked")
        self.assertEqual(items["Cover"], "fail")
        self.assertEqual(items["Citation keys"], "na")       # fiction template has no bibliography
        tmp.cleanup()


class PageScriptTests(unittest.TestCase):
    def test_builder_js_parses_and_has_every_route(self):
        r = subprocess.run(["node", "--check", str(TOOLS / "web" / "builder.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        js = (TOOLS / "web" / "builder.js").read_text()
        import re
        navs = re.findall(r'\{ id: "([\w-]+)", label: "[^"]+", icon: "[\w-]+"(?:, key: "\d")?(?:, sidebar: "\w+")?, subs: \[(.*?)\] \}', js, re.S)
        self.assertEqual(len(navs), 13)                      # 5 global + 8 project sections
        for sec, subs in navs:
            for sub in re.findall(r'\["([\w-]+)", "[^"]+", "[\w-]+"(, "\w+")?\]', subs):
                key, view = sub
                if not view:
                    self.assertIn(f'PAGES["{sec}/{key}"]', js, f"no page for {sec}/{key}")

    def test_every_nav_icon_is_in_the_sprite(self):
        import re
        js = (TOOLS / "web" / "builder.js").read_text()
        sprite = (TOOLS / "web" / "icons.svg").read_text()
        navs = js[js.index("const APP_NAV"):js.index("const LEGACY")]
        used = set(re.findall(r'icon: "([\w-]+)"', js)) | set(re.findall(r'\["[\w-]+", "[^"]+", "([\w-]+)"', navs)) \
            | set(re.findall(r'ic\("([\w-]+)"\)', js))
        missing = sorted(n for n in used if f'id="{n}"' not in sprite)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
