"""Brand Studio: tokens, contrast, applying to PDF / EPUB+HTML / website, assets, AI suggestions.

Runs on a throwaway book (BOOK_PROJECT) in fresh interpreters.
"""
import base64
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


class BrandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home, cls.book = Path(cls.tmp.name) / "home", Path(cls.tmp.name) / "Brand Book"
        cls.py(f"import registry as R, json; print(json.dumps(R.create('Brand Book', 'nonfiction', {str(cls.book)!r})))", None)

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

    def test_1_contrast_math(self):
        out = self.py("import brand as B, json; print(json.dumps([B.contrast('#000000', '#FFFFFF'), B.contrast('#777777', '#FFFFFF'), "
                      "B.contrast(B.darken_to('#7FD4D8', '#F7F6F2'), '#F7F6F2'), B.contrast(B.darken_to('#204060', '#151515'), '#151515')]))")
        self.assertEqual(out[0], 21.0)
        self.assertAlmostEqual(out[1], 4.48, places=1)
        self.assertGreaterEqual(out[2], 4.5)
        self.assertGreaterEqual(out[3], 4.5, "on dark paper the color is lightened instead")

    def test_2_defaults_mirror_the_template_so_applying_changes_nothing(self):
        typ = self.book / "assets/typst/callouts.typ"
        before = typ.read_bytes()
        r = self.py("import brand as B, json; B.save({}); print(json.dumps(B.apply(['pdf'])))")
        self.assertTrue(r["ok"], r)
        self.assertEqual(typ.read_bytes(), before)

    def test_3_save_validates_and_apply_updates_outputs(self):
        bad = self.py("import brand as B, json; print(json.dumps(B.save({'colors': {'accent': 'teal'}})))")
        self.assertFalse(bad["ok"])
        r = self.py("import brand as B, json; B.save({'colors': {'accent': '#336699', 'ink': '#111111'}, "
                    "'fonts': {'body': 'Source Sans 3'}, 'vibe': 'calm'}); print(json.dumps(B.apply(['pdf', 'ebook', 'website'])))")
        self.assertTrue(r["ok"], r)
        typ = (self.book / "assets/typst/callouts.typ").read_text()
        self.assertIn('#let teal = rgb("#336699")', typ)
        self.assertIn('#let body-font = "Source Sans 3"', typ)
        css = (self.book / "assets/css/brand.css").read_text()
        self.assertIn("--teal: #336699;", css)
        self.assertIn('@font-face { font-family: "Source Sans 3"', css)
        self.assertIn("--link:", css)
        args = self.py("import build, json; print(json.dumps([build.brand_css_args(), [p.name for p in build.brand_font_files()]]))")
        self.assertEqual(args[0][0], "--css")
        self.assertTrue(any(n.startswith("SourceSans3") for n in args[1]), "brand fonts are embedded in the EPUB")
        site = Path(self.tmp.name) / "public"
        web = self.py(f"import brand as B, json; from pathlib import Path; print(json.dumps(B.website_css(Path({str(site)!r}))))")
        self.assertIn("/brand-fonts/", web)
        self.assertTrue(list((site / "brand-fonts").glob("SourceSans3*")))

    def test_4_assets_reject_svg_and_keep_previous(self):
        r = self.py("import brand as B, json; print(json.dumps([B.save_asset('logo', 'x.svg', b'<svg onload=alert(1)/>')['ok'], "
                    f"B.save_asset('logo', 'a.png', {PNG!r})['ok'], B.save_asset('logo', 'b.png', {PNG!r})['ok']]))")
        self.assertEqual(r, [False, True, True])
        self.assertTrue((self.book / "assets/branding/logo.png").exists())
        self.assertTrue(list((self.book / "assets/branding/.previous").glob("*-logo.png")))

    def test_5_ai_suggestion_is_parsed_and_filtered(self):
        reply = 'Here you go:\n```json\n{"vibe": "warm", "colors": {"accent": "#AA5500", "ink": "red"}, "fonts": {"display": "Lora", "body": "<script>"}, "voice": {"tone": "kind", "hack": 1}}\n```\nWhy: ...'
        s = self.py(f"import brand as B, json; print(json.dumps(B.parse_suggestion({reply!r})))")
        self.assertEqual(s["colors"], {"accent": "#AA5500"})
        self.assertEqual(s["fonts"], {"display": "Lora"})
        self.assertEqual(s["voice"], {"tone": "kind"})
        p = self.py("import brand as B, json; print(json.dumps(B.strategy_prompt()))")
        self.assertIn("Brand Book", p)

    def test_6_voice_reaches_writing_prompts(self):
        v = self.py("import brand as B, packs, json; B.save({'voice': {'tone': 'gentle', 'avoid': 'jargon'}}); print(json.dumps(packs._brand_voice()))")
        self.assertIn("Tone: gentle", v)
        self.assertIn("Avoid: jargon", v)

    def test_7_home_book_is_unbranded_until_someone_applies_a_brand(self):
        self.assertFalse((ROOT / "brand.json").exists())
        self.assertFalse((ROOT / "assets/css/brand.css").exists())
        out = self.py("import build, json; print(json.dumps(build.brand_css_args()))", project=False)
        self.assertEqual(out, [])

    def test_8_each_book_builds_under_its_own_name_and_without_a_bibliography_if_it_has_none(self):
        bib = self.book / "references.bib"
        if bib.exists():
            bib.rename(self.book / "references.bib.off")
        out = self.py("import build, json; from pathlib import Path; "
                      "print(json.dumps([build.OUTPUT_STEM, build.pandoc_cmd('epub', Path('x.md'), Path('o.epub'), {})]))")
        self.assertEqual(out[0], "brand-book")
        self.assertNotIn("--citeproc", out[1])
        legacy = self.py("import build, json; from pathlib import Path; "
                         "print(json.dumps([build.OUTPUT_STEM, '--citeproc' in build.pandoc_cmd('pdf', Path('x.md'), Path('o.pdf'), {})]))", project=False)
        self.assertEqual(legacy, ["sample-book", True], "the home book's file names and citations are unchanged")


if __name__ == "__main__":
    unittest.main()
