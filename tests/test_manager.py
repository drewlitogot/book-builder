"""Tests for the Book Manager core: background jobs with progress, and prompt packs."""
import io
import sys
import time
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import jobs as J  # noqa: E402
import promptpack as P  # noqa: E402


class JobTests(unittest.TestCase):
    def test_spans_map_nested_progress_and_result_is_kept(self):
        seen = []

        def work():
            with J.span(0.5, 1.0):
                J.report(0.5, "halfway through the second half")
                seen.append(J.current().progress)
            return {"ok": True}

        job = J.start("t", work)
        self.assertTrue(J.wait(job, 2))
        self.assertEqual(seen, [0.75])
        d = job.to_dict()
        self.assertEqual((d["done"], d["progress"], d["result"]), (True, 1.0, {"ok": True}))
        self.assertIn("halfway through the second half", d["log"])

    def test_errors_are_reported_not_raised(self):
        job = J.start("t", lambda: 1 / 0)
        J.wait(job, 2)
        self.assertIn("division", job.error)

    def test_child_process_progress_markers(self):
        code = ("import sys; sys.path.insert(0, %r); import jobs; jobs.report(0.4, 'step'); print('plain line')"
                % str(ROOT / "tools"))
        out = {}

        def work():
            with J.span(0.0, 0.5):
                out["r"] = J.run_cmd([sys.executable, "-c", code])
            out["p"] = J.current().progress

        J.wait(J.start("t", work), 10)
        self.assertEqual(out["r"], (True, "plain line"))  # markers are removed from the output
        self.assertAlmostEqual(out["p"], 0.2)

    def test_creep_moves_without_reaching_the_end(self):
        def work():
            with J.creep(0.0, 1.0, 2):
                time.sleep(1.3)
            return J.current().progress

        job = J.start("t", work)
        J.wait(job, 5)
        self.assertTrue(0.2 < job.result < 1.0, job.result)


class PackTests(unittest.TestCase):
    def pack(self, files=True):
        return P.Pack("research", "Ch 05 · Masking", "Do the research.\n",
                      {"charter.md": "rules"} if files else {}, {"charter.md": "the rules"})

    def test_clipboard_text_is_self_contained_and_lists_the_zip(self):
        text = self.pack().text()
        self.assertTrue(text.startswith("Do the research."))
        self.assertIn("If nothing is attached, don't ask for it", text)
        self.assertIn("`reference/charter.md`: the rules", text)
        self.assertEqual(self.pack(files=False).text(), "Do the research.\n")

    def test_zip_holds_the_same_prompt_and_references(self):
        p = self.pack()
        z = zipfile.ZipFile(io.BytesIO(p.to_zip()))
        self.assertEqual(sorted(z.namelist()), ["README.md", "prompt.md", "reference/charter.md"])
        self.assertEqual(z.read("prompt.md").decode(), p.text())
        self.assertEqual(p.filename, "ch-05-masking-research-pack.zip")

    def test_registry_lists_this_books_kinds(self):
        import packs  # noqa: F401  (registers kinds)
        ids = {k["id"] for k in P.kinds()}
        self.assertTrue({"research", "write", "revise", "game", "game-update", "image-style", "pen-name"} <= ids)
        self.assertIn("Image style for Book Builder games", P.make("image-style").text())



class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from unittest import mock
        import workspace as W
        self.W = W
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(W, "SETTINGS", self.tmp / "workspace.yml")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_instructions_fit_and_follow_the_form(self):
        W = self.W
        text = W.instructions()
        self.assertLess(len(text), W.INSTRUCTIONS_LIMIT)
        self.assertIn("NON-NEGOTIABLE RULES", text)
        s = {**W.load(), "assistant_name": "Quill", "role": "Author only (research comes from you)",
             "images": False, "citations": "No citations"}
        text = W.instructions(s)
        self.assertTrue(text.startswith("You are Quill, author only"))
        self.assertNotIn("RESEARCH prompt", text)
        self.assertNotIn("EVIDENCE", text)
        self.assertIn("don't make images", text)

    def test_save_keeps_only_changes(self):
        W = self.W
        W.save({**W.load(), "assistant_name": "Quill", "unknown": 1})
        saved = (self.tmp / "workspace.yml").read_text()
        self.assertIn("assistant_name: Quill", saved)
        self.assertNotIn("rules:", saved)
        self.assertNotIn("unknown", saved)
        self.assertEqual(W.load()["assistant_name"], "Quill")

    def test_initial_prompt_options(self):
        W = self.W
        s = W.load()
        self.assertIn("Summarize the project back", W.initial_prompt(s))
        p = W.initial_prompt({**s, "kickoff": "Something else (below)", "custom_kickoff": "Plan chapter 61.", "ask_first": False})
        self.assertIn("Plan chapter 61.", p)
        self.assertNotIn("ask me up to five", p)

    def test_project_files_fit_the_limit_and_start_with_an_index(self):
        W = self.W
        files = W.project_files()
        self.assertLessEqual(len(files), W.FILES_LIMIT)
        self.assertEqual(next(iter(files)), "00-start-here.md")
        for name in ("writing-guide.md", "game-api.md", "image-style.md", "sources-library.md"):
            self.assertIn(name, files)
            self.assertIn(name, files["00-start-here.md"])
        fewer = W.project_files({**W.load(), "file_book": False, "file_research": False, "file_games": False})
        self.assertNotIn("book-so-far.md", fewer)
        self.assertNotIn("game-api.md", fewer)

    def test_every_field_has_a_default(self):
        W = self.W
        d = W.defaults()
        for f in W.FIELDS:
            self.assertIn(f["key"], d, f["key"])



class TocTests(unittest.TestCase):
    def test_simple_contents_only_changes_the_pdf(self):
        import build as B
        from unittest import mock
        out = Path("/tmp/x")
        with mock.patch.object(B, "TOC_MODE", "simple"):
            self.assertIn("--toc-depth=1", B.pandoc_cmd("pdf", out, out, {}))
            for fmt in ("epub", "html", "docx"):
                self.assertIn("--toc-depth=2", B.pandoc_cmd(fmt, out, out, {}))
        with mock.patch.object(B, "TOC_MODE", "detailed"):
            self.assertIn("--toc-depth=2", B.pandoc_cmd("pdf", out, out, {}))

    def test_typst_header_uses_the_flags(self):
        typ = (ROOT / "assets" / "typst" / "callouts.typ").read_text(encoding="utf-8")
        self.assertIn("#set heading(bookmarked: pdf-bookmarks)", typ)
        self.assertIn("toc-links", typ)
        self.assertIn('target.supplement == [Part]', typ)


class PageScriptTests(unittest.TestCase):
    def test_book_manager_script_parses(self):
        import shutil
        import subprocess
        import tempfile
        node = shutil.which("node")
        if not node:
            self.skipTest("node isn't installed")
        page = (ROOT / "tools" / "web" / "index.html").read_text(encoding="utf-8")
        import re
        # Inline scripts share one global scope, so check them together (plus builder.js between them).
        blocks = re.findall(r"<script>(.*?)</script>", page, re.S)
        self.assertGreaterEqual(len(blocks), 1)
        builder = (ROOT / "tools" / "web" / "builder.js").read_text(encoding="utf-8")
        script = blocks[0] + "\n;\n" + builder + "\n;\n" + "\n;\n".join(blocks[1:])
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(script)
        r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
        Path(f.name).unlink()
        self.assertEqual(r.returncode, 0, r.stderr[-800:])


if __name__ == "__main__":
    unittest.main()
