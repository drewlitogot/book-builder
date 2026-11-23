"""Phase 01: multi-book core. Two new books (A, B), the legacy book left untouched, isolation, structure editing.

Every check runs in a fresh interpreter with BOOK_PROJECT / BOOK_BUILDER_HOME set, like the real server.
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def tree_hash(root: Path, rels) -> str:
    h = hashlib.sha256()
    for r in sorted(rels):
        h.update(r.encode() + (root / r).read_bytes())
    return h.hexdigest()


class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.home, cls.a, cls.b = base / "home", base / "Book A", base / "Book B"
        legacy = [f for f in [str(p.relative_to(ROOT)) for p in (ROOT / "book").rglob("*.md")]] + ["book.yml", "website.yml"]
        cls.legacy_files = legacy
        cls.legacy_before = tree_hash(ROOT, legacy)
        cls.ra = cls.py(f"import registry as R, json; print(json.dumps(R.create('Alpha Novel', 'fiction', {str(cls.a)!r}, 'A. Writer')))")
        cls.rb = cls.py("import registry as R, json; print(json.dumps(R.create('Beta Guide', 'custom', %r, 'B. Author', 'A subtitle', "
                        "parts=[{'name': 'Basics', 'chapters': ['Start here', 'Second step']}, {'name': 'More', 'chapters': ['Third']}], "
                        "meta={'description': 'A guide.', 'keywords': 'one, two', 'lang': 'en-GB'}, brand={'accent': '#336699', 'titleFont': 'Lora'}, "
                        "cover=(%r, '.png'), formats=['pdf', 'docx'])))" % (str(cls.b), PNG))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def py(cls, code: str, project: Path | None = None):
        env = {**os.environ, "BOOK_BUILDER_HOME": str(cls.home), "PYTHONPATH": str(TOOLS)}
        env.pop("BOOK_PROJECT", None)
        if project:
            env["BOOK_PROJECT"] = str(project)
        r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=180, cwd=TOOLS)
        if r.returncode:
            raise AssertionError(r.stderr[-3000:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_1_wizard_creates_distinct_books_with_publishing_off(self):
        self.assertTrue(self.ra["ok"] and self.rb["ok"], (self.ra, self.rb))
        self.assertNotEqual(self.ra["id"], self.rb["id"])
        pb = json.loads((self.b / "project.json").read_text())
        self.assertEqual(pb["project_id"], self.rb["id"])
        self.assertFalse(pb["publishing"]["enabled"])
        self.assertEqual(pb["brand"]["accent"], "#336699")
        self.assertEqual(pb["outputs"], ["pdf", "docx"])
        self.assertTrue((self.b / "assets/branding/cover.png").exists())
        import yaml
        mb = yaml.safe_load((self.b / "book.yml").read_text())["metadata"]
        self.assertEqual((mb["title"], mb["subtitle"], mb["lang"], mb["keywords"]), ("Beta Guide", "A subtitle", "en-GB", ["one", "two"]))
        chapters_b = self.py("import chapter as C, json; print(json.dumps([c['title'] for c in C.parse_outline()[0]]))", self.b)
        chapters_a = self.py("import chapter as C, json; print(json.dumps([c['title'] for c in C.parse_outline()[0]]))", self.a)
        self.assertEqual(chapters_b, ["Start here", "Second step", "Third"])
        self.assertNotEqual(chapters_a, chapters_b)

    def test_2_switch_and_reopen_keep_ids_and_isolation(self):
        lib = self.py("import registry as R, json; from pathlib import Path; "
                      f"R.ensure(Path({str(self.a)!r}), opened=True); R.ensure(Path({str(self.b)!r}), opened=True); "
                      f"R.ensure(Path({str(self.a)!r}), opened=True); print(json.dumps(R.registry()))")
        ids = {e["path"]: e for e in lib}
        self.assertEqual(ids[str(self.a.resolve())]["id"], self.ra["id"], "the id survives reopening")
        self.assertFalse(ids[str(self.a.resolve())]["legacy"])
        a_title = self.py("import bookmeta, json; print(json.dumps(bookmeta.book_meta()['title']))", self.a)
        b_title = self.py("import bookmeta, json; print(json.dumps(bookmeta.book_meta()['title']))", self.b)
        self.assertEqual((a_title, b_title), ("Alpha Novel", "Beta Guide"))
        dist = self.py("import build, json; print(json.dumps(str(build.DIST)))", self.a)
        self.assertTrue(dist.startswith(str(self.a.resolve())), "builds write into the open book's own dist/")

    def test_3_legacy_book_is_adapted_without_rewriting(self):
        out = self.py("import registry as R, json, structure as ST; e = R.ensure(R.APP); ok, why = R.publishing_enabled(R.APP); "
                      "print(json.dumps({'id': e['id'], 'legacy': e['legacy'], 'pub': ok, 'edit': ST.editable()[0], "
                      "'save': ST.save([{'name': 'x', 'chapters': [{'title': 'y'}]}])['ok']}))")
        self.assertTrue(out["legacy"] and out["pub"] and out["id"].startswith("bk-"))
        self.assertFalse(out["edit"] or out["save"])
        self.assertFalse((ROOT / "project.json").exists(), "no project.json is written into the legacy book")
        self.assertEqual(tree_hash(ROOT, self.legacy_files), self.legacy_before)

    def test_4_new_books_cannot_publish_until_enabled(self):
        r = self.py("import webapp as W, json; print(json.dumps(W.website_action('publish', {'confirm': True})))", self.a)
        self.assertFalse(r["ok"])
        self.assertIn("Publishing is off", r["output"])
        r = self.py("import api_structure as S, json; print(json.dumps(S.set_publishing({'enabled': True})))", self.a)
        self.assertTrue(r["publishing"])
        r = self.py("import registry as R, json, chapter as C; print(json.dumps(R.publishing_enabled(C.ROOT)[0]))", self.a)
        self.assertTrue(r)
        self.py("import api_structure as S, json; print(json.dumps(S.set_publishing({'enabled': False})))", self.a)

    def test_5_folder_rules(self):
        bad = self.py("import registry as R, json; print(json.dumps([R.create('X', 'custom', str(R.APP / 'nested'))['ok'], "
                      f"R.create('Y', 'custom', {str(self.a / 'inside')!r})['ok'], R.create('Z', 'custom', {str(self.a)!r})['ok']]))")
        self.assertEqual(bad, [False, False, False])
        self.assertFalse((ROOT / "nested").exists())

    def test_6_structure_add_rename_reorder_remove_and_locks(self):
        cur = self.py("import structure as ST, json; print(json.dumps(ST.current()))", self.b)
        self.assertTrue(cur["editable"])
        p1, p2 = cur["parts"]
        start, second = p1["chapters"]
        third = p2["chapters"][0]
        # mark "Start here" as drafted: it must keep its place
        f = self.b / start["file"]
        f.write_text(f.read_text().replace("status: planned", "status: drafted") + "\nReal draft text.\n")
        new = [{"name": "Basics", "chapters": [{"id": start["id"], "title": "Start here"}, {"id": third["id"], "title": "Third, renamed"},
                                               {"title": "Brand new chapter"}]},
               {"name": "Extras", "chapters": [{"title": "Appendix"}]}]
        r = self.py("import structure as ST, json; print(json.dumps(ST.save(%r)))" % new, self.b)
        self.assertTrue(r["ok"], r)
        titles = self.py("import chapter as C, json; print(json.dumps([(c['n'], c['title']) for c in C.parse_outline()[0]]))", self.b)
        self.assertEqual(titles, [[1, "Start here"], [2, "Third, renamed"], [3, "Brand new chapter"], [4, "Appendix"]])
        self.assertIn("Real draft text.", f.read_text(), "the drafted chapter wasn't touched")
        self.assertTrue(list((self.b / "book" / ".removed").rglob("*.md")), "the removed placeholder is kept")
        self.assertTrue(Path(r["backup"]).exists())
        import yaml
        doc = yaml.safe_load((self.b / "book.yml").read_text())
        self.assertEqual(doc["metadata"]["title"], "Beta Guide")
        self.assertEqual(len([c for p in doc["parts"] for c in p["chapters"]]), 4)
        for p in doc["parts"]:
            for c in p["chapters"]:
                self.assertTrue((self.b / c).exists(), c)
        moved = [{"name": "Basics", "chapters": [{"title": "Brand new chapter"}, {"id": start["id"], "title": "Start here"}]}]
        cur2 = self.py("import structure as ST, json; print(json.dumps(ST.current()))", self.b)
        ids = {c["title"]: c["id"] for p in cur2["parts"] for c in p["chapters"]}
        moved[0]["chapters"][0] = {"id": ids["Brand new chapter"], "title": "Brand new chapter"}
        r = self.py("import structure as ST, json; print(json.dumps(ST.save(%r)))" % moved, self.b)
        self.assertFalse(r["ok"])
        self.assertIn("keeps its number", r["message"])

    def test_7_export_import_round_trip_as_a_new_book(self):
        (self.b / "research-library" / "sources").mkdir(parents=True, exist_ok=True)
        (self.b / "research-library" / "sources" / "1.json").write_text('{"id": 1}')
        (self.b / "research-library" / "index.sqlite").write_text("cache")
        (self.b / "dist").mkdir(exist_ok=True)
        (self.b / "dist" / "big.pdf").write_text("build output")
        (self.b / "sources-private").mkdir(exist_ok=True)
        (self.b / "sources-private" / "paper.pdf").write_text("copyrighted")
        out = Path(self.tmp.name) / "exports"
        r = self.py(f"import bookpack as B, json; from pathlib import Path; print(json.dumps(B.export(Path({str(self.b)!r}), Path({str(out)!r}))))")
        self.assertTrue(r["ok"], r)
        import zipfile
        names = zipfile.ZipFile(r["path"]).namelist()
        self.assertIn("book/research-library/sources/1.json", names)
        for gone in ("book/dist/big.pdf", "book/research-library/index.sqlite", "book/sources-private/paper.pdf"):
            self.assertNotIn(gone, names)
        dest = Path(self.tmp.name) / "Imported copy"
        imp = self.py(f"import bookpack as B, json; from pathlib import Path; print(json.dumps(B.import_book(Path({r['path']!r}), {str(dest)!r})))")
        self.assertTrue(imp["ok"], imp)
        self.assertNotEqual(imp["id"], self.rb["id"], "an imported book gets a new id")
        pf = json.loads((dest / "project.json").read_text())
        self.assertFalse(pf["publishing"]["enabled"])
        self.assertEqual(pf["imported_from"]["project_id"], self.rb["id"])
        self.assertEqual((dest / "book.yml").read_bytes(), (self.b / "book.yml").read_bytes())
        titles = self.py("import chapter as C, json; print(json.dumps([c['title'] for c in C.parse_outline()[0]]))", dest)
        self.assertTrue(titles)
        again = self.py(f"import bookpack as B, json; from pathlib import Path; print(json.dumps(B.import_book(Path({r['path']!r}), {str(dest)!r})))")
        self.assertFalse(again["ok"], "never imports over an existing book")

    def test_8_damaged_or_hostile_packages_are_refused(self):
        out = Path(self.tmp.name) / "exports2"
        r = self.py(f"import bookpack as B, json; from pathlib import Path; print(json.dumps(B.export(Path({str(self.a)!r}), Path({str(out)!r}))))")
        import zipfile
        src = zipfile.ZipFile(r["path"])
        entries = {i.filename: src.read(i.filename) for i in src.infolist()}
        bad = Path(self.tmp.name) / "bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            for k, v in entries.items():
                z.writestr(k, v + b"x" if k == "book/book.yml" else v)
        trav = Path(self.tmp.name) / "trav.zip"
        with zipfile.ZipFile(trav, "w") as z:
            for k, v in entries.items():
                z.writestr(k, v)
            z.writestr("book/../escape.txt", "x")
        res = self.py("import bookpack as B, json; from pathlib import Path\nout = []\n"
                      f"for p in ({str(bad)!r}, {str(trav)!r}):\n"
                      "    try:\n        B.inspect(Path(p)); out.append('accepted')\n"
                      "    except Exception as e:\n        out.append(type(e).__name__ + ': ' + str(e)[:60])\n"
                      "print(json.dumps(out))")
        self.assertTrue(res[0].startswith("ValueError: Checksum mismatch"), res)
        self.assertIn("Unsafe path", res[1])
        upd = self.py("import json\nfrom bbmanage import packages as PK\nfrom pathlib import Path\n"
                      f"try:\n    PK.inspect(Path({r['path']!r})); print(json.dumps('accepted'))\n"
                      "except PK.PackageError as e:\n    print(json.dumps(str(e)))")
        self.assertIn("book package", upd)

    def test_9_legacy_book_export_takes_book_data_not_app_source(self):
        files = self.py("import bookpack as B, json; print(json.dumps(B.book_files(B.BP.APP)))")
        self.assertIn("book.yml", files)
        self.assertTrue(any(f.startswith("book/") for f in files))
        self.assertTrue(any(f.startswith("assets/typst/") for f in files), "build templates travel with the book")
        self.assertFalse(any(f.startswith(("tools/", "tests/", "site/", "dist/", ".git/", "sources-private/")) for f in files))

    def test_10_titles_survive_the_background_job_wrapper(self):
        """Regression: the server used to take `title` as the progress label, so pages couldn't send a title."""
        import socket
        import time
        import urllib.request
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
        env = {**os.environ, "BOOK_BUILDER_HOME": str(self.home), "BOOK_PROJECT": str(self.a)}
        proc = subprocess.Popen([sys.executable, str(TOOLS / "webapp.py"), "--no-open", "--port", str(port), "--exact-port"],
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=0.5); break
                except OSError:
                    time.sleep(0.1)
            dest = Path(self.tmp.name) / "Via HTTP"
            body = json.dumps({"title": "Sent Over HTTP", "template": "custom", "folder": str(dest), "background": True}).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/projects/create", body, {"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=30).read())
            if "job" in r:
                for _ in range(100):
                    s = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/jobs/{r['job']}").read())
                    if s.get("done"):
                        r = s["result"]; break
                    time.sleep(0.1)
            self.assertTrue(r.get("ok"), r)
            self.assertIn("title: Sent Over HTTP", (dest / "book.yml").read_text())
        finally:
            proc.terminate(); proc.wait(timeout=10)

    def test_11_older_library_entries_get_ids_when_listed(self):
        out = self.py("import registry as R, json; items = R.registry(); "
                      "[e.pop('id', None) for e in items]; R._save_registry(items); "
                      "lib = R.library(R.APP); print(json.dumps([e.get('id') for e in lib]))")
        self.assertTrue(all(i and i.startswith("bk-") for i in out), out)


if __name__ == "__main__":
    unittest.main()
