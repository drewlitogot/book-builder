"""Website hosting: settings in website.yml, custom domain rules, and the portable website ZIP."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

WEBSITE_YML = """# Public website publishing (keep this comment)
repo: someone/somebook
branch: main
url: https://someone.github.io/somebook/
"""


class HostingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home, cls.book = Path(cls.tmp.name) / "home", Path(cls.tmp.name) / "Host Book"
        cls.py(f"import registry as R, json; print(json.dumps(R.create('Host Book', 'fiction', {str(cls.book)!r})))", False)
        (cls.book / "website.yml").write_text(WEBSITE_YML)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def py(cls, code, project=True):
        env = {**os.environ, "BOOK_BUILDER_HOME": str(cls.home), "PYTHONPATH": str(TOOLS)}
        env.pop("BOOK_PROJECT", None)
        if project:
            env["BOOK_PROJECT"] = str(cls.book)
        r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120, cwd=TOOLS)
        if r.returncode:
            raise AssertionError(r.stderr[-3000:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_1_settings_keep_the_rest_of_website_yml(self):
        r = self.py("import hosting as H, json; print(json.dumps(H.save({'provider': 'netlify', 'domain': 'Books.Example.com', 'zip_base': 'books//host-book'})))")
        self.assertTrue(r["ok"], r)
        text = (self.book / "website.yml").read_text()
        self.assertIn("# Public website publishing (keep this comment)", text)
        self.assertIn("url: https://someone.github.io/somebook/", text, "the address only changes when asked")
        s = r["settings"]
        self.assertEqual((s["provider"], s["domain"], s["zip_base"]), ("netlify", "books.example.com", "/books/host-book/"))
        again = self.py("import hosting as H, json; print(json.dumps(H.save({'provider': 'github-pages', 'domain': 'books.example.com', 'use_domain_url': True})))")
        text = (self.book / "website.yml").read_text()
        self.assertEqual(text.count("hosting:"), 1, "the block is replaced, not repeated")
        self.assertIn("url: https://books.example.com/", text)
        self.assertEqual(self.py("import hosting as H, json; print(json.dumps(H.cname_for_publish()))"), "books.example.com")

    def test_2_bad_input_is_refused(self):
        bad = self.py("import hosting as H, json; print(json.dumps([H.save({'provider': 'x'})['ok'], H.save({'domain': 'not a domain'})['ok'], "
                      "H.save({'zip_base': '/../etc/'})['ok'], H.save({'domain': 'evil.com/path'})['ok']]))")
        self.assertEqual(bad, [False, False, False, False])

    def test_3_zip_packages_the_checked_site_with_a_guide(self):
        code = ("import json, hosting as H, website as W\n"
                "dist = W.DIST\n"
                "def fake_build(**kw):\n"
                "    dist.mkdir(parents=True, exist_ok=True)\n"
                "    (dist / 'index.html').write_text('<html>home</html>')\n"
                "    (dist / 'read').mkdir(exist_ok=True); (dist / 'read' / 'index.html').write_text('<html>read</html>')\n"
                "    fake_build.kw = kw\n"
                "W.build = fake_build\n"
                "W.load_book = lambda: {'metadata': {'title': 'Host Book'}}\n"
                "r = H.make_zip('/books/host-book/', log=lambda *a: None)\n"
                "print(json.dumps({**r, 'kw': {k: v for k, v in fake_build.kw.items() if k != 'log'}}))")
        r = self.py(code)
        self.assertTrue(r["ok"])
        self.assertEqual(r["kw"]["base_override"], "/books/host-book/")
        self.assertFalse(r["kw"]["preview"], "only approved content goes in a ZIP")
        names = zipfile.ZipFile(r["path"]).namelist()
        for n in ("site/index.html", "site/read/index.html", "HOSTING-GUIDE.md", "README.txt", "website-manifest.json"):
            self.assertIn(n, names)
        m = json.loads(zipfile.ZipFile(r["path"]).read("website-manifest.json"))
        self.assertFalse(m["installable"])
        self.assertEqual(len(m["files"]["index.html"]), 64)
        if r["guide_pdf"]:
            self.assertIn("HOSTING-GUIDE.pdf", names)

    def test_4_a_website_zip_is_not_an_update(self):
        z = Path(self.tmp.name) / "w.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("website-manifest.json", "{}")
            f.writestr("site/index.html", "x")
        msg = self.py("import json\nfrom bbmanage import packages as PK\nfrom pathlib import Path\n"
                      f"try:\n    PK.inspect(Path({str(z)!r})); print(json.dumps('accepted'))\n"
                      "except PK.PackageError as e:\n    print(json.dumps(str(e)))")
        self.assertIn("Not a Book Builder update package", msg)


if __name__ == "__main__":
    unittest.main()
