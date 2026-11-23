"""Tests for website export, filtering and output validation (tools/website.py)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import games as G  # noqa: E402
import website as W  # noqa: E402
from test_games import fixture_files, make_zip, edited  # noqa: E402

APPROVED = "book/01-planning/01-choosing-a-topic.md"
REAL_LOAD_BOOK = W.load_book


def fake_book() -> dict:
    real = REAL_LOAD_BOOK()
    approved = next(e for e in real["entries"] if e["source"] == APPROVED)
    planned = dict(approved, slug="02-unwritten", title="Unwritten", n=2, status="draft", published=False,
                   body="Secret draft text that must never be published.")
    return {"metadata": real["metadata"], "entries": [approved, planned]}


class WebsiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        site = self.tmp / "site"
        games = self.tmp / "games"
        self.patches = [
            mock.patch.object(W, "SITE", site), mock.patch.object(W, "GEN", site / "src" / "generated"),
            mock.patch.object(W, "DIST", site / "dist"), mock.patch.object(W, "CACHE", self.tmp / "cache"),
            mock.patch.object(W, "PUBLIC_GEN", [site / "public" / "games", site / "public" / "downloads", site / "public" / "brand"]),
            mock.patch.object(W, "CONFIG", self.tmp / "website.yml"),
            mock.patch.object(W, "load_book", fake_book),
            mock.patch.object(G, "GAMES", games), mock.patch.object(G, "PACKAGES", games / "packages"),
            mock.patch.object(G, "STAGING", games / ".staging"), mock.patch.object(G, "REGISTRY", games / "registry.json"),
        ]
        for p in self.patches:
            p.start()
        chapters = {1: {"path": APPROVED, "title": "Brains", "status": "approved", "part": "P"},
                    2: {"path": "x", "title": "Unwritten", "status": "draft", "part": "P"}}
        self.cp = mock.patch.object(G, "book_chapters", lambda: dict(chapters))
        self.cp.start()
        # One approved game for chapter 1, one in review, one for the unapproved chapter.
        G.install(make_zip(fixture_files()))
        G.set_status("fixture-kitchen-sink", "approved")
        G.install(make_zip(edited(manifest=lambda m: m.update(id="fixture-in-review"))))
        G.install(make_zip(edited(manifest=lambda m: m.update(id="fixture-other-chapter", chapter=2))))
        G.set_status("fixture-other-chapter", "approved")

    def tearDown(self) -> None:
        self.cp.stop()
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_includes_only_approved_content(self):
        summary = W.export(downloads=False, log=lambda *a: None)
        self.assertEqual(summary["chapters"], 1)
        self.assertEqual(summary["games"], ["fixture-kitchen-sink"])
        book = json.loads((W.GEN / "book.json").read_text())
        unwritten = next(e for e in book["entries"] if e["slug"] == "02-unwritten")
        self.assertEqual((unwritten["status"], unwritten["games"]), ("coming-soon", []))
        self.assertFalse((W.GEN / "chapters" / "02-unwritten.html").exists())
        generated = "".join(p.read_text(errors="ignore") for p in W.GEN.rglob("*") if p.is_file() and p.suffix in (".json", ".html"))
        self.assertNotIn("Secret draft text", generated)
        published = sorted(p.name for p in (W.SITE / "public" / "games").iterdir())
        self.assertEqual(published, ["fixture-kitchen-sink"])
        # Only the runtime's files are copied: no README or registry.
        files = sorted(p.relative_to(W.SITE / "public" / "games" / "fixture-kitchen-sink").as_posix()
                       for p in (W.SITE / "public" / "games" / "fixture-kitchen-sink").rglob("*") if p.is_file())
        self.assertEqual(files, ["activity.json", "assets/dot.png", "game.json"])
        brains = next(e for e in book["entries"] if e["n"] == 1)
        self.assertEqual(brains["games"], ["fixture-kitchen-sink"])
        html = (W.GEN / "chapters" / f"{brains['slug']}.html").read_text()
        self.assertIn('class="callout', html)
        self.assertTrue(brains["hasRefs"])
        self.assertIn('class="csl-entry"', (W.GEN / "chapters" / f"{brains['slug']}.refs.html").read_text())

    def test_guides_use_only_existing_text_and_real_anchors(self):
        W.export(downloads=False, log=lambda *a: None)
        book = json.loads((W.GEN / "book.json").read_text())
        guides = json.loads((W.GEN / "guides.json").read_text())
        self.assertEqual([g["n"] for g in guides], [1])  # only published numbered chapters
        g = guides[0]
        toc_ids = {t["id"] for t in next(e for e in book["entries"] if e["n"] == 1)["toc"]}
        self.assertTrue(3 <= len(g["sections"]) <= 6)
        self.assertTrue({s["id"] for s in g["sections"]} <= toc_ids)
        gloss = {e["term"]: e["definition"] for e in W.glossary_entries()}
        for term in g["terms"]:
            self.assertEqual(gloss[term["term"]], term["definition"])
            self.assertRegex(term["definition"], r"See chapters? .*\b1\b")

    def test_preview_export_includes_games_in_review(self):
        summary = W.export(preview=True, downloads=False, log=lambda *a: None)
        self.assertEqual(sorted(summary["games"]), ["fixture-in-review", "fixture-kitchen-sink"])

    def test_plan_warns_about_excluded_games(self):
        p = W.plan()
        self.assertEqual([g["id"] for g in p["games"]], ["fixture-kitchen-sink"])
        text = " ".join(p["warnings"])
        self.assertIn("fixture-in-review won't be published: not approved yet", text)
        self.assertIn("fixture-other-chapter won't be published: its chapter isn't published", text)
        self.assertIn("No publishing repository configured", text)

    def make_dist(self, extra: dict[str, str] | None = None):
        W.export(downloads=False, log=lambda *a: None)
        book = json.loads((W.GEN / "book.json").read_text())
        d = W.DIST
        files = {"index.html": '<a href="/read/">x</a>', "pagefind/pagefind.js": "",
                 "activities/fixture-kitchen-sink/index.html": "", "games/fixture-kitchen-sink/activity.json": "{}"}
        for e in book["entries"]:
            files[f"read/{e['slug']}/index.html"] = ('<div class="chapter-body" data-pagefind-body></div>' if e["published"]
                                                     else "<p>Coming soon</p>")
            if e["published"] and e["n"]:
                files[f"guides/{e['slug']}/index.html"] = "<p>Quick orientation</p>"
                files[f"read/{e['slug']}/index.html"] += "".join(f'<h2 id="{h["id"]}"></h2>' for h in e["toc"])
        files["read/glossary/index.html"] = "".join(f"<dd>{g['definition']}</dd>" for g in W.glossary_entries())
        files.update(extra or {})
        for name, text in files.items():
            (d / name).parent.mkdir(parents=True, exist_ok=True)
            (d / name).write_text(text)

    def test_validate_accepts_clean_output(self):
        self.make_dist()
        self.assertEqual(W.validate(log=lambda *a: None), [])

    def test_validate_catches_private_files_broken_links_and_leaks(self):
        self.make_dist({"research/notes.md": "x", "about/index.html": '<a href="/nowhere/">x</a>',
                        "games/fixture-in-review/game.json": "{}",
                        "read/02-unwritten/index.html": '<div class="chapter-body">This chapter will be written through the agent pipeline</div>'})
        problems = " ".join(W.validate(log=lambda *a: None))
        self.assertIn("Private or source file in output: research/notes.md", problems)
        self.assertIn("broken link /nowhere/", problems)
        self.assertIn("Unexpected game folder in output: games/fixture-in-review", problems)
        self.assertIn("Unpublished chapter /read/02-unwritten/ exposes content", problems)

    def test_activities_nav_follows_published_activities(self):
        # The fixture registry has one approved game, so the main nav must link Activities.
        self.make_dist({"index.html": '<nav aria-label="Main"><a href="/read/">Read</a></nav>'})
        self.assertIn("missing from the main navigation with 1 published activities", " ".join(W.validate(log=lambda *a: None)))
        self.make_dist({"index.html": '<nav aria-label="Main"><a href="/activities/">Activities</a></nav>'})
        self.assertNotIn("main navigation", " ".join(W.validate(log=lambda *a: None)))
        # With nothing published, the same link is an error.
        (W.GEN / "games.json").write_text("[]")
        self.assertIn("Activities is in the main navigation with 0", " ".join(W.validate(log=lambda *a: None)))

    def test_publish_requires_confirmation(self):
        (W.CONFIG).write_text("repo: someone/my-book\nurl: https://someone.github.io/my-book/\n")
        with self.assertRaisesRegex(RuntimeError, "Not confirmed"):
            W.publish(yes=False, log=lambda *a: None)

    def test_site_paths_from_config(self):
        self.assertEqual(W.site_paths({"url": "https://someone.github.io/my-book/"}),
                         ("https://someone.github.io", "/my-book/"))
        self.assertEqual(W.site_paths({}), ("http://localhost", "/"))


if __name__ == "__main__":
    unittest.main()
