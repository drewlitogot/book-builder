"""Image Studio: prompts grounded in the chapter and research, proposals, safe imports, review rules, packs.

Runs on a throwaway book in fresh interpreters; no chapter text is ever modified.
"""
import io
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


def png(w=40, h=20, color=(10, 120, 130)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home, cls.book = Path(cls.tmp.name) / "home", Path(cls.tmp.name) / "Image Book"
        cls.py(f"import registry as R, json; print(json.dumps(R.create('Image Book', 'nonfiction', {str(cls.book)!r})))", False)
        ch = sorted((cls.book / "book").rglob("01-*.md"))[0]
        ch.write_text(ch.read_text().replace("*Planned.*", "## Why sleep matters\nSleep helps memory.\n## How much\nAdults need 7 hours."))
        cls.chapter_file, cls.chapter_before = ch, ch.read_bytes()
        cls.py("import research_library as RL, json; print(json.dumps(RL.add(b'Adults need at least 7 hours of sleep (CDC, 2024).', "
               "'cdc.txt', chapters=[1])['id']))")

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

    def test_1_prompts_read_the_chapter_and_its_research(self):
        plan = self.py("import images as I, json; print(json.dumps(I.plan_prompt()))")
        self.assertIn("Chapter 1:", plan)
        self.assertIn("Why sleep matters", plan)
        c = self.py("import images as I, json; print(json.dumps(I.chapter_prompt(1)))")
        self.assertIn("Adults need 7 hours.", c["text"])
        self.assertIn("[Source 1,", c["text"], "research comes from the Research Library with source ids")
        self.assertIn("not instructions", c["text"])
        self.assertIn('"kind": "diagram"', c["text"])

    def test_2_proposals_are_parsed_safely(self):
        reply = ('Plan:\n```json\n[{"chapter": 1, "kind": "diagram", "title": "Sleep hours", "sources": ["Source 1"], '
                 '"prompt": "Bar chart", "alt": "Adults need 7+ hours", "caption": "Source: CDC"}, '
                 '{"chapter": "x", "kind": "hologram", "title": "Odd"}]\n```')
        out = self.py(f"import images as I, json; p = I.parse_proposals({reply!r}); r = I.add(p, 'test'); print(json.dumps(r))")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["kind"], "diagram")
        self.assertEqual(out[1]["kind"], "illustration", "unknown kinds fall back safely")
        self.assertIsNone(out[1]["chapter"])

    def test_3_uploads_are_validated(self):
        res = self.py("import images as I, json\nrid = I.records()[0]['id']\nout = []\n"
                      "for data in (b'<svg onload=alert(1)>', b'\\x89PNG\\r\\n\\x1a\\nnot really', %r):\n"
                      "    try:\n        I.add_version(rid, data, 'x'); out.append('ok')\n"
                      "    except ValueError as e:\n        out.append(str(e)[:40])\n"
                      "print(json.dumps(out))" % png())
        self.assertIn("Only PNG", res[0])
        self.assertIn("readable image", res[1])
        self.assertEqual(res[2], "ok")

    def test_4_approval_needs_alt_credit_license_sources_and_checks(self):
        code = ("import images as I, json\nr = I.records()[0]\n"
                "a = I.approve(r['id'])\n"
                "I.update(r['id'], {'credit': 'Made with ChatGPT', 'license': 'Author owns'})\n"
                "b = I.approve(r['id'])\n"
                "I.update(r['id'], {'checks': {c: True for c in I.checklist(r['kind'])}})\n"
                "c = I.approve(r['id'])\n"
                f"I.add_version(r['id'], {png(50, 30)!r}, 'v2.png')\n"
                "d = I.get(r['id'])['status']\n"
                "print(json.dumps([a['ok'], b['ok'], c['ok'], d, I.markdown(I.get(r['id']))]))")
        a, b, c, status_after_new_version, md = self.py(code)
        self.assertFalse(a)
        self.assertFalse(b, "checklist still unticked")
        self.assertTrue(c)
        self.assertEqual(status_after_new_version, "imported", "a new file needs a fresh review")
        self.assertIn("images/files/", md)
        self.assertIn("fig-alt=", md)

    def test_5_generation_pack_and_return_import(self):
        ids = self.py("import images as I, json; print(json.dumps([r['id'] for r in I.records()]))")
        dest = Path(self.tmp.name) / "req.zip"
        r = self.py(f"import images as I, json; from pathlib import Path; print(json.dumps(I.generation_pack({ids!r}, Path({str(dest)!r}))))")
        names = zipfile.ZipFile(r["path"]).namelist()
        self.assertIn("manifest.json", names)
        self.assertIn(f"prompts/{ids[1]}.md", names)
        ret = Path(self.tmp.name) / "return.zip"
        with zipfile.ZipFile(ret, "w") as z:
            z.writestr(f"{ids[1]}.png", png(64, 64))
            z.writestr("img-unknown.png", png())
            z.writestr(f"{ids[0]}.png", b"not an image")
            z.writestr("return-manifest.json", json.dumps({"images": [{"id": ids[1], "tool": "ChatGPT", "notes": "check colors"}]}))
        out = self.py(f"import images as I, json; from pathlib import Path; print(json.dumps(I.import_return(Path({str(ret)!r}))))")
        self.assertEqual(out["added"], [ids[1]])
        self.assertEqual(len(out["skipped"]), 2)
        rec = self.py(f"import images as I, json; print(json.dumps(I.get({ids[1]!r})))")
        self.assertEqual(rec["credit"], "Made with ChatGPT")
        self.assertEqual(rec["versions"][-1]["width"], 64)

    def test_6_export_approved_and_chapters_untouched(self):
        dest = Path(self.tmp.name) / "export.zip"
        r = self.py(f"import images as I, json; from pathlib import Path; print(json.dumps(I.export_approved(Path({str(dest)!r}))))")
        names = zipfile.ZipFile(r["path"]).namelist()
        self.assertIn("credits.csv", names)
        self.assertEqual(self.chapter_file.read_bytes(), self.chapter_before, "no chapter text was changed")


if __name__ == "__main__":
    unittest.main()
