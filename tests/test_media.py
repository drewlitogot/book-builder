"""Images in builds: path rules, approval gating, website publishing and the build manifest."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import media  # noqa: E402


def png() -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 50, 50)).save(b, "PNG")
    return b.getvalue()


class MediaRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "book root"
        (self.root / "book" / "01-part").mkdir(parents=True)
        (self.root / "images" / "files").mkdir(parents=True)
        (self.root / "assets" / "branding").mkdir(parents=True)
        (self.root / "sources-private").mkdir()
        for p in ("images/files/img-a-v1.png", "images/files/img-b-v1.png", "assets/branding/logo.png", "sources-private/secret.png",
                  "book/01-part/local.png"):
            (self.root / p).write_bytes(png())
        (self.root / "images" / "registry.json").write_text(json.dumps({"images": [
            {"id": "img-a", "status": "approved", "versions": [{"path": "images/files/img-a-v1.png"}]},
            {"id": "img-b", "status": "imported", "versions": [{"path": "images/files/img-b-v1.png"}]}]}))
        self.chapter = self.root / "book" / "01-part" / "01-ch.md"
        Path(self.tmp.name, "outside.png").write_bytes(png())

    def tearDown(self):
        self.tmp.cleanup()

    def test_paths_are_resolved_and_refused_safely(self):
        body = ("![A](../../images/files/img-a-v1.png)\n![Local](local.png)\n![Logo](assets/branding/logo.png)\n"
                "![Out](../../../outside.png)\n![Priv](../../sources-private/secret.png)\n![Abs](/etc/x.png)\n"
                "![Web](https://example.com/a.png)\n![Inline](data:image/png;base64,AAAA)\n![Gone](missing.png)\n"
                '<img src="../../images/files/img-a-v1.png" alt="html one">')
        out, found, warns = media.resolve(body, self.chapter, self.root)
        self.assertEqual(found, ["images/files/img-a-v1.png", "book/01-part/local.png", "assets/branding/logo.png",
                                 "images/files/img-a-v1.png"])
        for alt in ("Out", "Priv", "Abs", "Web", "Inline", "Gone"):
            self.assertIn(f"*[Image: {alt}]*", out, alt)
        self.assertEqual(len(warns), 6)
        self.assertIn("outside the book", " ".join(warns))
        self.assertIn("sources-private", " ".join(warns))

    def test_unapproved_studio_images_never_go_public(self):
        body = "![B](../../images/files/img-b-v1.png)"
        draft, found, warns = media.resolve(body, self.chapter, self.root, published=False)
        self.assertEqual(found, ["images/files/img-b-v1.png"])
        self.assertIn("isn't approved", warns[0])
        pub, found, warns = media.resolve(body, self.chapter, self.root, published=True)
        self.assertEqual(found, [])
        self.assertIn("*[Image: B]*", pub)

    def test_website_publish_copies_and_rewrites(self):
        public = Path(self.tmp.name) / "public"
        html = '<p><img src="images/files/img-a-v1.png" alt="x"><img src="https://cdn/x.png"></p>'
        out, copied = media.publish(html, self.root, public, "/my-book/")
        self.assertEqual(len(copied), 1)
        self.assertIn(f'src="/my-book/book-media/{copied[0]}"', out)
        self.assertIn('src="https://cdn/x.png"', out, "external URLs in already-rendered HTML are left as they are")
        self.assertTrue((public / "book-media" / copied[0]).exists())


class BuildManifestTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
    def test_docx_build_embeds_images_and_records_the_artifact(self):
        tmp = tempfile.TemporaryDirectory()
        home, book = Path(tmp.name) / "home", Path(tmp.name) / "Build Book"
        env = {**os.environ, "BOOK_BUILDER_HOME": str(home), "PYTHONPATH": str(TOOLS)}
        subprocess.run([sys.executable, "-c", f"import registry as R; R.create('Build Book', 'fiction', {str(book)!r})"],
                       env=env, cwd=TOOLS, check=True, capture_output=True)
        ch = sorted((book / "book").rglob("01-*.md"))[0]
        (ch.parent / "pic.png").write_bytes(png())
        ch.write_text(ch.read_text() + "\n\n![A picture](pic.png)\n\n![Gone](nope.png)\n")
        out = Path(tmp.name) / "out"
        r = subprocess.run([sys.executable, str(TOOLS / "build.py"), "build", "docx", "--outdir", str(out)],
                           env={**env, "BOOK_PROJECT": str(book)}, cwd=book, capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertIn("Gone", r.stderr)
        docx = out / "build-book.docx"
        self.assertTrue(any(n.startswith("word/media/") for n in zipfile.ZipFile(docx).namelist()))
        mf = json.loads((out / "build-manifest.json").read_text())["artifacts"]["build-book.docx"]
        self.assertEqual(len(mf["sha256"]), 64)
        self.assertTrue(mf["project_id"].startswith("bk-"))
        self.assertEqual(len(mf["preflight"]), 1)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
