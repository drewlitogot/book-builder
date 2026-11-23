"""Tests for the Game Package Manager (tools/games.py). Run: .venv/bin/python -m unittest discover tests"""
from __future__ import annotations

import copy
import io
import json
import shutil
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import games as G  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "games" / "kitchen-sink"
CHAPTERS = {1: {"path": "x", "title": "One", "status": "approved", "part": "P"},
            2: {"path": "y", "title": "Two", "status": "planned", "part": "P"}}


def fixture_files() -> dict[str, bytes]:
    return {p.relative_to(FIXTURE).as_posix(): p.read_bytes() for p in FIXTURE.rglob("*") if p.is_file()}


def make_zip(files: dict[str, bytes], extra: list[zipfile.ZipInfo | tuple] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
        for item in extra or []:
            zf.writestr(*item)
    return buf.getvalue()


def edited(manifest=None, activity=None) -> dict[str, bytes]:
    files = fixture_files()
    m = json.loads(files["game.json"])
    a = json.loads(files["activity.json"])
    if manifest:
        manifest(m)
    if activity:
        activity(a)
    files["game.json"] = json.dumps(m).encode()
    files["activity.json"] = json.dumps(a).encode()
    return files


class TempRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        games = self.tmp / "games"
        self.patches = [mock.patch.object(G, "GAMES", games), mock.patch.object(G, "PACKAGES", games / "packages"),
                        mock.patch.object(G, "STAGING", games / ".staging"),
                        mock.patch.object(G, "REGISTRY", games / "registry.json"),
                        mock.patch.object(G, "book_chapters", lambda: copy.deepcopy(CHAPTERS))]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class ValidationTests(unittest.TestCase):
    def check(self, files, ok=False, contains=""):
        res = G.validate_package(files, CHAPTERS)
        self.assertEqual(res["ok"], ok, res["errors"])
        if contains:
            self.assertTrue(any(contains in e for e in res["errors"] + res["warnings"]), res)
        return res

    def test_fixture_is_valid(self):
        self.check(fixture_files(), ok=True)

    def test_schema_error_missing_field(self):
        self.check(edited(manifest=lambda m: m.pop("title")), contains="'title' is a required property")

    def test_unsupported_api_version(self):
        self.check(edited(manifest=lambda m: m.update(apiVersion="2.0")), contains="not supported")

    def test_unknown_chapter(self):
        self.check(edited(manifest=lambda m: m.update(chapter=9)), contains="does not exist")

    def test_unapproved_chapter_warns(self):
        res = self.check(edited(manifest=lambda m: m.update(chapter=2)), ok=True)
        self.assertTrue(any("not approved" in w for w in res["warnings"]))

    def test_broken_branch_target(self):
        self.check(edited(activity=lambda a: a["screens"][0].update(next="nowhere")), contains="unknown screen")

    def test_unknown_field_in_condition(self):
        def f(a):
            a["screens"][1]["next"]["rules"][0]["when"] = {"field": "ghost", "equals": "x"}
        self.check(edited(activity=f), contains="unknown field")

    def test_scoring_only_in_knowledge_checks(self):
        self.check(edited(manifest=lambda m: m.update(activityType="scenario")), contains="Only knowledge-check")

    def test_sensitive_must_be_ungraded(self):
        def m(m):
            m.update(sensitive=True, contentWarnings=["test"])
        self.check(edited(manifest=m), contains="must be ungraded")

    def test_no_reachable_completion(self):
        def f(a):
            a["screens"] = [s for s in a["screens"] if s["type"] != "completion"]
            a["screens"][-1]["next"] = "intro"
        self.check(edited(activity=f), contains="completion")

    def test_undeclared_asset(self):
        files = fixture_files()
        files["assets/extra.png"] = files["assets/dot.png"]
        self.check(files, contains="not listed in game.json")

    def test_fake_image_rejected(self):
        files = fixture_files()
        files["assets/dot.png"] = b"<script>alert(1)</script>"
        self.check(files, contains="not a real PNG")

    def test_html_in_text_rejected(self):
        self.check(edited(activity=lambda a: a["screens"][0].update(body="<script>x</script>")), contains="HTML")

    def test_manipulation_term_flags_for_review(self):
        res = self.check(edited(activity=lambda a: a["screens"][0].update(body="Never try negging anyone.")), ok=True)
        self.assertTrue(any("Editorial review" in w for w in res["warnings"]))


class ArchiveSafetyTests(unittest.TestCase):
    def test_path_traversal(self):
        with self.assertRaisesRegex(G.PackageError, "Unsafe"):
            G.read_archive(make_zip({**fixture_files(), "../evil.txt": b"x"}))

    def test_absolute_path(self):
        with self.assertRaisesRegex(G.PackageError, "Unsafe"):
            G.read_archive(make_zip({**fixture_files(), "/etc/passwd": b"x"}))

    def test_symlink(self):
        info = zipfile.ZipInfo("assets/link.png")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(G.PackageError, "Symbolic links"):
            G.read_archive(make_zip(fixture_files(), [(info, "/etc/passwd")]))

    def test_scripts_not_allowed(self):
        for name in ("game.js", "assets/run.js", "index.html", "assets/pic.svg"):
            with self.assertRaisesRegex(G.PackageError, "not allowed"):
                G.read_archive(make_zip({**fixture_files(), name: b"x"}))

    def test_archive_bomb(self):
        with self.assertRaisesRegex(G.PackageError, "compression ratio|larger than"):
            G.read_archive(make_zip({**fixture_files(), "assets/big.txt": b"0" * (4 * 1024 * 1024)}))

    def test_too_many_entries(self):
        files = {f"assets/f{i}.txt": b"x" for i in range(G.MAX_ENTRIES + 1)}
        with self.assertRaisesRegex(G.PackageError, "entries"):
            G.read_archive(make_zip(files))

    def test_not_a_zip(self):
        with self.assertRaisesRegex(G.PackageError, "Not a valid ZIP"):
            G.read_archive(b"hello")

    def test_wrapping_folder_and_mac_junk_accepted(self):
        files = {f"my-game/{k}": v for k, v in fixture_files().items()}
        files["__MACOSX/my-game/._game.json"] = b"junk"
        files["my-game/.DS_Store"] = b"junk"
        out = G.read_archive(make_zip(files))
        self.assertIn("game.json", out)
        self.assertNotIn(".DS_Store", out)


class ChatReplyTests(unittest.TestCase):
    def reply(self, label=lambda n: f"**{n}**"):
        f = fixture_files()
        return ("Here is your game.\n\n" + "\n\n".join(
            f"{label(n)}\n```{'json' if n.endswith('json') else 'markdown'}\n{f[n].decode()}\n```"
            for n in ("game.json", "activity.json", "README.md")) + "\n\nSummary: …")

    def test_reads_labeled_code_blocks(self):
        files = G.parse_reply(self.reply())
        self.assertEqual(sorted(files), ["README.md", "activity.json", "game.json"])
        self.assertEqual(json.loads(files["game.json"])["id"], "fixture-kitchen-sink")

    def test_other_label_styles_and_unlabeled_json(self):
        for label in (lambda n: f"### {n}", lambda n: f"`{n}`", lambda n: f"File: {n}", lambda n: ""):
            files = G.parse_reply(self.reply(label))
            self.assertIn("activity.json", files)
            self.assertIn("game.json", files)

    def test_missing_file_is_a_clear_error(self):
        with self.assertRaisesRegex(G.PackageError, "Couldn't find activity.json"):
            G.parse_reply("**game.json**\n```json\n{\"activityType\": \"scenario\"}\n```")

    def test_prompt_is_self_contained(self):
        p = G.creation_prompt(None)
        for needed in ("learningObjectives", "\"keyboard\": true", "screenReader", "authors", "API essentials"):
            self.assertIn(needed, p)
        md = G.docs_markdown()
        self.assertIn("game.schema.json", md)
        self.assertIn("component-reference.md", md)


class ImageAttachTests(TempRegistry):
    def reply_with_image(self, chapter=1):
        def m(m):
            m["chapter"] = chapter
            m["assets"].append({"path": "assets/cafe-scene.png", "type": "image", "alt": "Two people at a café."})
        def a(a):
            a["screens"][0]["image"] = {"asset": "assets/cafe-scene.png"}
        f = edited(manifest=m, activity=a)
        del f["README.md"]
        return f

    def big_jpeg(self) -> bytes:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (2400, 1600), (240, 238, 232)).save(buf, "JPEG", quality=95)
        return buf.getvalue()

    def test_missing_images_are_listed_by_declared_name(self):
        need = G.missing_assets(self.reply_with_image())
        self.assertEqual([n["path"] for n in need], ["assets/cafe-scene.png"])
        self.assertEqual(need[0]["alt"], "Two people at a café.")

    def test_attached_image_is_converted_resized_and_installs(self):
        files = G.attach_assets(self.reply_with_image(), {"assets/cafe-scene.png": self.big_jpeg()})
        from PIL import Image
        im = Image.open(io.BytesIO(files["assets/cafe-scene.png"]))
        self.assertEqual(im.format, "PNG")
        self.assertEqual(im.width, G.MAX_IMAGE_WIDTH)
        self.assertEqual(G.missing_assets(files), [])
        res = G.install(G.zip_files(files))
        self.assertEqual(res["entry"]["status"], "review")

    def test_non_image_and_undeclared_files_rejected(self):
        with self.assertRaisesRegex(G.PackageError, "isn't a readable image"):
            G.attach_assets(self.reply_with_image(), {"assets/cafe-scene.png": b"<svg onload=alert(1)>"})
        with self.assertRaisesRegex(G.PackageError, "isn't a missing asset"):
            G.attach_assets(self.reply_with_image(), {"assets/other.png": self.big_jpeg()})

    def test_images_in_sensitive_chapter_warn(self):
        files = G.attach_assets(self.reply_with_image(chapter=1), {"assets/cafe-scene.png": self.big_jpeg()})
        chapters = {1: {"path": "x", "title": "One", "status": "approved", "part": "P"},
                    35: {"path": "y", "title": "Assault", "status": "approved", "part": "P"}}
        self.assertFalse(any("sensitive topic" in w for w in G.validate_package(files, chapters)["warnings"]))
        m = json.loads(files["game.json"]); m["chapter"] = 35
        files["game.json"] = json.dumps(m).encode()
        self.assertTrue(any("sensitive topic" in w for w in G.validate_package(files, chapters)["warnings"]))

    def test_prompt_has_unified_image_style(self):
        p = G.creation_prompt(None)
        self.assertIn("## Images (required: 9 images in 3 files)", p)
        self.assertIn("## Image style for Book Builder games", p)
        self.assertIn("2×2 grid", p)
        self.assertIn("**Sheet 1**, **Sheet 2**, **Icon**", p)
        self.assertIn("make **only the\nicon**", p)
        # The same style text, word for word, as the standalone style prompt.
        self.assertIn(G.image_style(), p)


def sheet_png(w: int, h: int) -> bytes:
    from PIL import Image
    im = Image.new("RGB", (w, h))
    for i, c in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]):
        im.paste(c, ((i % 2) * w // 2, (i // 2) * h // 2, (i % 2 + 1) * w // 2, (i // 2 + 1) * h // 2))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def v11_reply(chapter: int = 1) -> dict[str, bytes]:
    """The 1.1 reflection template as a reply: 8 scene images + icon declared, none attached."""
    root = G.DOCS / "templates" / "reflection-package"
    files = {f.name: f.read_bytes() for f in root.iterdir() if f.is_file()}
    m = json.loads(files["game.json"])
    a = json.loads(files["activity.json"])
    m["chapter"] = chapter
    m["requiredCapabilities"].append("images")
    m["assets"] = [{"path": f"assets/img-0{i}-scene.webp", "type": "image", "alt": f"Scene {i}."} for i in range(1, 9)]
    m["assets"].append({"path": "assets/icon.png", "type": "image", "alt": "Two cups."})
    m["icon"] = "assets/icon.png"
    for i, s in enumerate(a["screens"]):
        s["image"] = {"asset": f"assets/img-0{i + 1}-scene.webp"}
    a["screens"].insert(1, {"id": "more", "type": "perspective", "title": "Two views", "next": "rank",
                            "perspectives": [{"id": f"p{i}", "label": f"View {i}", "body": "Text.",
                                              "image": {"asset": f"assets/img-0{i}-scene.webp"}} for i in (5, 6, 7, 8)]})
    a["screens"][0]["next"] = "more"
    m["requiredCapabilities"].append("perspective-switching")
    files["game.json"], files["activity.json"] = json.dumps(m).encode(), json.dumps(a).encode()
    return files


class SheetTests(TempRegistry):
    def test_slots_group_scene_images_into_two_sheets_and_an_icon(self):
        slots = G.image_slots(v11_reply())
        self.assertEqual([(s["slot"], len(s["assets"])) for s in slots], [("sheet-1", 4), ("sheet-2", 4), ("icon", 1)])
        self.assertEqual(slots[1]["assets"][0]["path"], "assets/img-05-scene.webp")

    def test_sheets_are_cut_in_panel_order_and_install(self):
        from PIL import Image
        files = G.attach_assets(v11_reply(), {"sheet-1": sheet_png(2048, 1365), "sheet-2": sheet_png(2048, 1365),
                                              "icon": sheet_png(1024, 1024)})
        colors = []
        for i in range(1, 5):
            im = Image.open(io.BytesIO(files[f"assets/img-0{i}-scene.webp"])).convert("RGB")
            colors.append(im.getpixel((im.width // 2, im.height // 2)))
        self.assertEqual([max(range(3), key=lambda k: c[k]) if c != (255, 255, 0) else "y" for c in colors][:3], [0, 1, 2])
        icon = Image.open(io.BytesIO(files["assets/icon.png"]))
        self.assertEqual(icon.size, (G.ICON_SIZE, G.ICON_SIZE))
        self.assertEqual(G.image_slots(files), [])
        res = G.validate_package(files, CHAPTERS)
        self.assertTrue(res["ok"], res["errors"])
        self.assertFalse([w for w in res["warnings"] if "House style" in w or "no screen" in w], res["warnings"])
        self.assertEqual(G.install(G.zip_files(files))["entry"]["status"], "review")

    def test_small_sheet_rejected(self):
        with self.assertRaisesRegex(G.PackageError, "too small"):
            G.attach_assets(v11_reply(), {"sheet-1": sheet_png(800, 533)})

    def test_icon_must_be_declared_image(self):
        files = v11_reply()
        m = json.loads(files["game.json"]); m["icon"] = "assets/nope.png"
        files["game.json"] = json.dumps(m).encode()
        res = G.validate_package(files, CHAPTERS)
        self.assertTrue(any("icon" in e for e in res["errors"]))


class Api11Tests(unittest.TestCase):
    def template(self, name):
        root = G.DOCS / "templates" / name
        return {f.name: f.read_bytes() for f in root.iterdir() if f.is_file()}

    def test_all_templates_valid(self):
        for name in ("minimal-package", "branching-package", "reflection-package"):
            res = G.validate_package(self.template(name), {**CHAPTERS, 7: CHAPTERS[1]})
            self.assertTrue(res["ok"], (name, res["errors"]))

    def test_11_features_in_a_10_package_rejected(self):
        files = self.template("reflection-package")
        for name in ("game.json", "activity.json"):
            d = json.loads(files[name]); d["apiVersion"] = "1.0"; files[name] = json.dumps(d).encode()
        res = G.validate_package(files, {7: CHAPTERS[1]})
        self.assertFalse(res["ok"])
        self.assertTrue(any("1.1" in e and "ranking" in e for e in res["errors"]), res["errors"])

    def test_placeholders_and_first_checked(self):
        files = self.template("reflection-package")
        a = json.loads(files["activity.json"])
        a["screens"][0]["body"] = "Hi {{answer:nope}} {{var:missing}} {{oops}}"
        a["screens"][2]["fields"][0]["options"][0]["feedback"] = "x"
        a["screens"][2]["feedback"][0]["when"] = {"field": "firmness", "first": "firm"}
        files["activity.json"] = json.dumps(a).encode()
        errs = " | ".join(G.validate_package(files, {7: CHAPTERS[1]})["errors"])
        for bit in ("unknown field 'nope'", "undeclared variable 'missing'", "{{oops}}", "only works on ranking"):
            self.assertIn(bit, errs)

    def test_save_notes_needs_capability(self):
        files = self.template("reflection-package")
        m = json.loads(files["game.json"]); m["requiredCapabilities"].remove("save-notes")
        files["game.json"] = json.dumps(m).encode()
        self.assertTrue(any("save-notes" in e for e in G.validate_package(files, {7: CHAPTERS[1]})["errors"]))

    def test_update_prompt_includes_package_style_and_next_version(self):
        with mock.patch.object(G, "get", lambda gid: {"id": gid, "version": "1.2.3"}), \
             mock.patch.object(G, "installed_files", lambda gid: fixture_files()), \
             mock.patch.object(G, "book_chapters", lambda: CHAPTERS):
            p = G.update_prompt("ch01-kitchen-sink")
        self.assertIn('"version": "1.3.0"', p)
        self.assertIn("**game.json**\n```json", p)
        self.assertIn(G.image_style(), p)
        self.assertIn("Game API 1.1", p)


class InstallTests(TempRegistry):
    def zip(self, version="1.0.0", **kw) -> bytes:
        return make_zip(edited(manifest=lambda m: m.update(version=version, **kw)))

    def test_import_registers_for_review(self):
        res = G.install(self.zip(), source="t.zip")
        self.assertEqual(res["entry"]["status"], "review")
        self.assertTrue((G.PACKAGES / "fixture-kitchen-sink" / "activity.json").exists())
        self.assertEqual(G.published_games(CHAPTERS), [])  # never auto-approved

    def test_duplicate_requires_replace(self):
        G.install(self.zip())
        with self.assertRaisesRegex(G.PackageError, "identical"):
            G.install(self.zip())
        with self.assertRaisesRegex(G.PackageError, "already installed"):
            G.install(self.zip("1.1.0"))

    def test_replace_newer_version_resets_review(self):
        G.install(self.zip())
        G.set_status("fixture-kitchen-sink", "approved")
        res = G.install(self.zip("1.1.0"), replace=True)
        self.assertEqual(res["entry"]["status"], "review")
        self.assertEqual(res["entry"]["history"][0]["version"], "1.0.0")

    def test_replace_older_or_same_version_refused(self):
        G.install(self.zip("1.2.0"))
        with self.assertRaisesRegex(G.PackageError, "older"):
            G.install(self.zip("1.1.0"), replace=True)
        with self.assertRaisesRegex(G.PackageError, "Raise the version"):
            G.install(self.zip("1.2.0", title="Changed title"), replace=True)

    def test_failed_install_rolls_back(self):
        G.install(self.zip())
        before = (G.PACKAGES / "fixture-kitchen-sink" / "game.json").read_bytes()
        with mock.patch.object(G, "save_registry", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                G.install(self.zip("2.0.0"), replace=True)
        self.assertEqual((G.PACKAGES / "fixture-kitchen-sink" / "game.json").read_bytes(), before)
        self.assertEqual(G.get("fixture-kitchen-sink")["version"], "1.0.0")
        self.assertEqual(list((G.STAGING).iterdir()), [])

    def test_approve_publish_filtering(self):
        G.install(self.zip())
        G.set_status("fixture-kitchen-sink", "approved")
        self.assertEqual([g["id"] for g in G.published_games(CHAPTERS)], ["fixture-kitchen-sink"])
        unapproved_chapter = copy.deepcopy(CHAPTERS)
        unapproved_chapter[1]["status"] = "draft"
        self.assertEqual(G.published_games(unapproved_chapter), [])
        # Files changed after approval: excluded until re-imported.
        (G.PACKAGES / "fixture-kitchen-sink" / "README.md").write_text("tampered")
        self.assertEqual(G.published_games(CHAPTERS), [])

    def test_assign_changes_chapter_and_resets(self):
        G.install(self.zip())
        G.set_status("fixture-kitchen-sink", "approved")
        g = G.assign("fixture-kitchen-sink", 2)
        self.assertEqual((g["chapter"], g["status"]), (2, "review"))
        self.assertEqual(json.loads((G.PACKAGES / "fixture-kitchen-sink" / "game.json").read_text())["chapter"], 2)

    def test_export_round_trip_and_remove(self):
        G.install(self.zip())
        out = G.export("fixture-kitchen-sink", self.tmp / "out")
        res = G.validate_package(G.read_archive(out.read_bytes()), CHAPTERS)
        self.assertTrue(res["ok"], res["errors"])
        G.remove("fixture-kitchen-sink")
        self.assertFalse((G.PACKAGES / "fixture-kitchen-sink").exists())
        self.assertEqual(G.load_registry()["games"], {})


if __name__ == "__main__":
    unittest.main()
