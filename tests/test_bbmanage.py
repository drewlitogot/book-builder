"""Application management: source revision, backups, update packages, QA evidence and handoffs.

Everything runs on a throwaway copy of the application in a folder whose name contains spaces, with
BOOK_BUILDER_HOME in a temporary folder. The real installation, books and backups are never touched.
"""
import importlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REAL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REAL / "tools"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.home = base / "app data"
        os.environ["BOOK_BUILDER_HOME"] = str(self.home)
        import bbmanage.paths as P
        importlib.reload(P)
        from bbmanage import backups, packages, qa, revision, handoff
        for m in (revision, backups, packages, qa, handoff):
            importlib.reload(m)
        self.P, self.RV, self.B, self.PK, self.Q, self.H = P, revision, backups, packages, qa, handoff
        self.root = base / "Book Builder Test Copy"          # spaces on purpose
        self.root.mkdir()
        backups.copy_tree_source(REAL, self.root)
        (self.root / "book" / "01-part").mkdir(parents=True)
        self.chapter = self.root / "book" / "01-part" / "01-ch.md"
        self.chapter.write_text("---\ntitle: One\nstatus: approved\n---\n# One\nApproved text.\n")
        (self.root / "book.yml").write_text("metadata:\n  title: Test\nparts: []\n")
        (self.root / "research").mkdir()
        (self.root / "research" / "notes.md").write_text("notes\n")

    def tearDown(self):
        os.environ.pop("BOOK_BUILDER_HOME", None)
        self.tmp.cleanup()

    # helpers
    def edit_source(self, rel="tools/routes.py", extra="\n# changed\n"):
        p = self.root / rel
        p.write_text(p.read_text() + extra)

    def make_package(self, edit=True, **kw):
        bk = self.B.make_source_backup(self.root)
        base_inv, base_rev = self.PK.inventory_from_backup(Path(bk["path"]))
        work = Path(self.tmp.name) / "work"
        if work.exists():
            shutil.rmtree(work)
        self.B.copy_tree_source(self.root, work)
        if edit:
            (work / "tools" / "routes.py").write_text((work / "tools" / "routes.py").read_text() + "\n# v2\n")
            (work / "tools" / "new_module.py").write_text("X = 1\n")
            (work / "tests" / "test_builder.py").unlink()
        out = Path(self.tmp.name) / "update.zip"
        r = self.PK.make(base_inv, base_rev, work, out, "pkg-1", "Test update", **kw)
        return out, r, work


class RevisionTests(Base):
    def test_revision_is_deterministic_and_ignores_book_data(self):
        a = self.RV.current(self.root)["revision"]
        self.assertEqual(a, self.RV.current(self.root)["revision"])
        self.chapter.write_text("edited chapter\n")
        (self.root / "research" / "notes.md").write_text("more\n")
        self.assertEqual(a, self.RV.current(self.root)["revision"], "editing a chapter must not change the source revision")
        self.edit_source()
        self.assertNotEqual(a, self.RV.current(self.root)["revision"])

    def test_source_and_data_sets_never_overlap(self):
        src = set(self.P.source_files(self.root))
        self.assertTrue(src)
        self.assertFalse(any(self.P.is_data_path(f) for f in src))
        self.assertFalse(any(f.startswith(("book/", "research/", "dist/", ".venv/")) for f in src))
        self.assertFalse(any("__pycache__" in f for f in src))


class SourceBackupTests(Base):
    def test_backup_and_restore_leave_books_alone(self):
        bk = self.B.make_source_backup(self.root)
        rev = bk["revision"]
        self.edit_source()
        (self.root / "tools" / "added_later.py").write_text("x = 1\n")
        before_chapter = self.chapter.read_bytes()
        self.assertEqual(self.B.restore_source(Path(bk["path"]), self.root)["needs"], "RESTORE")   # no word, no change
        r = self.B.restore_source(Path(bk["path"]), self.root, confirm="RESTORE")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.RV.current(self.root)["revision"], rev)
        self.assertFalse((self.root / "tools" / "added_later.py").exists(), "files added after the backup are removed")
        self.assertIn("tools/added_later.py", r["removed"])
        self.assertEqual(self.chapter.read_bytes(), before_chapter)
        self.assertTrue(Path(r["pre_restore_backup"]).exists())

    def test_damaged_backup_is_refused(self):
        bk = Path(self.B.make_source_backup(self.root)["path"])
        bad = bk.with_name("bad.zip")
        with zipfile.ZipFile(bk) as zin, zipfile.ZipFile(bad, "w") as zout:
            for i in zin.infolist():
                data = zin.read(i.filename)
                zout.writestr(i, data + b"!" if i.filename == "files/tools/routes.py" else data)
        with self.assertRaises(ValueError):
            self.B.inspect(bad, self.B.SOURCE_KIND)

    def test_data_backup_is_not_a_source_backup(self):
        d = Path(self.B.make_data_backup(self.root)["path"])
        with self.assertRaises(ValueError):
            self.B.restore_source(d, self.root, confirm="RESTORE")


class DataBackupTests(Base):
    def test_backup_and_restore_book_data_without_touching_source(self):
        (self.home).mkdir(parents=True, exist_ok=True)
        (self.home / "registry.json").write_text('{"projects": []}')
        bk = self.B.make_data_backup(self.root)
        self.assertGreaterEqual(bk["files"], 3)
        rev = self.RV.current(self.root)["revision"]
        self.chapter.write_text("accidentally destroyed\n")
        (self.root / "research" / "notes.md").unlink()
        self.assertEqual(self.B.restore_data(Path(bk["path"]), self.root)["needs"], "RESTORE")
        r = self.B.restore_data(Path(bk["path"]), self.root, confirm="RESTORE")
        self.assertTrue(r["ok"], r)
        self.assertIn("Approved text.", self.chapter.read_text())
        self.assertTrue((self.root / "research" / "notes.md").exists())
        self.assertEqual(self.RV.current(self.root)["revision"], rev)
        self.assertTrue(Path(r["pre_restore_backup"]).exists())

    def test_private_sources_need_opt_in(self):
        (self.root / "sources-private").mkdir()
        (self.root / "sources-private" / "paper.pdf").write_bytes(b"%PDF")
        no = self.B.make_data_backup(self.root)
        self.assertEqual(no["not_included"], ["sources-private"])
        yes = self.B.make_data_backup(self.root, include_private=True)
        self.assertEqual(yes["files"], no["files"] + 1)


class UpdatePackageTests(Base):
    def test_valid_package_inspects_and_applies_exactly(self):
        z, made, work = self.make_package()
        plan = self.PK.inspect(z, self.root)
        self.assertEqual(plan["counts"], {"add": 1, "replace": 1, "delete": 1})
        chapter = self.chapter.read_bytes()
        self.assertEqual(self.PK.apply(z, self.root)["needs"], "APPLY")
        r = self.PK.apply(z, self.root, confirm="APPLY", check_server=False)
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.RV.current(self.root)["revision"], made["target_revision"])
        self.assertEqual(self.RV.current(self.root)["revision"], self.RV.current(work)["revision"])
        self.assertFalse((self.root / "tests" / "test_builder.py").exists())
        self.assertTrue((self.root / "tools" / "new_module.py").exists())
        self.assertEqual(self.chapter.read_bytes(), chapter, "updates never touch manuscripts")
        self.assertTrue(Path(r["source_backup"]).exists() and Path(r["data_backup"]).exists())
        self.assertTrue(Path(r["kept_package"]).exists())

    def test_stale_package_is_rejected(self):
        z, _, _ = self.make_package()
        self.edit_source("tools/jobs.py")
        with self.assertRaisesRegex(self.PK.PackageError, "Stale package"):
            self.PK.inspect(z, self.root)

    def _rewrite(self, z, fn):
        out = z.with_name("tampered.zip")
        with zipfile.ZipFile(z) as zin:
            entries = {i.filename: zin.read(i.filename) for i in zin.infolist()}
        fn(entries)
        with zipfile.ZipFile(out, "w") as zout:
            for n, d in entries.items():
                zout.writestr(n, d)
        return out

    def _manifest_edit(self, z, fn):
        def edit(e):
            m = json.loads(e["forge-manifest.json"]); fn(m); e["forge-manifest.json"] = json.dumps(m).encode()
        return self._rewrite(z, edit)

    def test_wrong_project_and_type_are_rejected(self):
        z, _, _ = self.make_package()
        with self.assertRaisesRegex(self.PK.PackageError, "not 'book-builder'"):
            self.PK.inspect(self._manifest_edit(z, lambda m: m.update(project_id="vibecode-studio")), self.root)
        with self.assertRaisesRegex(self.PK.PackageError, "Wrong package type"):
            self.PK.inspect(self._manifest_edit(z, lambda m: m.update(package_type="something")), self.root)

    def test_modified_missing_and_undeclared_payloads_are_rejected(self):
        z, _, _ = self.make_package()
        with self.assertRaisesRegex(self.PK.PackageError, "hash mismatch"):
            self.PK.inspect(self._rewrite(z, lambda e: e.__setitem__("payload/tools/routes.py", b"evil")), self.root)
        with self.assertRaisesRegex(self.PK.PackageError, "Payload missing"):
            self.PK.inspect(self._rewrite(z, lambda e: e.pop("payload/tools/new_module.py")), self.root)
        with self.assertRaisesRegex(self.PK.PackageError, "Undeclared payload"):
            self.PK.inspect(self._rewrite(z, lambda e: e.__setitem__("payload/tools/extra.py", b"x")), self.root)

    def test_paths_outside_source_traversal_and_symlinks_are_rejected(self):
        z, _, _ = self.make_package()
        def to_book(m):
            m["operations"].append({"op": "add", "path": "book/01-part/evil.md", "sha256": "0" * 64})
        with self.assertRaisesRegex(self.PK.PackageError, "outside the application source"):
            self.PK.inspect(self._manifest_edit(z, to_book), self.root)
        with self.assertRaisesRegex(self.PK.PackageError, "Unsafe path"):
            self.PK.inspect(self._rewrite(z, lambda e: e.__setitem__("payload/../../escape.py", b"x")), self.root)
        link = z.with_name("link.zip")
        with zipfile.ZipFile(z) as zin, zipfile.ZipFile(link, "w") as zout:
            for i in zin.infolist():
                zout.writestr(i, zin.read(i.filename))
            info = zipfile.ZipInfo("payload/tools/link.py")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zout.writestr(info, "/etc/passwd")
        with self.assertRaisesRegex(self.PK.PackageError, "Symbolic link"):
            self.PK.inspect(link, self.root)

    def test_original_hash_mismatch_is_rejected(self):
        z, _, _ = self.make_package()
        def wrong(m):
            for op in m["operations"]:
                if op["op"] == "replace":
                    op["original_sha256"] = "f" * 64
        with self.assertRaises(self.PK.PackageError):
            self.PK.inspect(self._manifest_edit(z, wrong), self.root)

    def test_failed_apply_rolls_back(self):
        z, _, _ = self.make_package()
        rev = self.RV.current(self.root)["revision"]
        with self.assertRaisesRegex(self.PK.PackageError, "previous source was restored"):
            self.PK.apply(z, self.root, confirm="APPLY", check_server=False, data_backup=False, fail_after=1)
        self.assertEqual(self.RV.current(self.root)["revision"], rev)

    def test_backups_qa_and_handoffs_are_never_installable(self):
        bk = Path(self.B.make_source_backup(self.root)["path"])
        with self.assertRaisesRegex(self.PK.PackageError, "isn't an update"):
            self.PK.inspect(bk, self.root)
        qa_dir = Path(self.tmp.name) / "qa"
        record = {"run_id": "r1", "revision": "a" * 64, "version": "t", "status": "passed", "finished": 0, "dir": str(qa_dir),
                  "suites": [{"name": "python-unittest", "status": "passed", "summary": {"passed": 1}, "tests": [{"id": "t", "outcome": "passed"}]}],
                  "totals": {"passed": 1}}
        qa_dir.mkdir()
        qz = Path(self.Q.review_zip(record, dest_dir=qa_dir)["path"])
        with zipfile.ZipFile(qz) as z:
            names = set(z.namelist())
            self.assertTrue({"QA_REPORT.md", "qa-manifest.json", "test-results.json", "environment.json",
                             "KNOWN_ISSUES.md", "NEXT_STEPS.md"} <= names)
            self.assertFalse(json.loads(z.read("qa-manifest.json"))["installable"])
        with self.assertRaisesRegex(self.PK.PackageError, "isn't an update"):
            self.PK.inspect(qz, self.root)


class HandoffTests(Base):
    def test_handoff_excludes_manuscripts_and_round_trips_to_a_package(self):
        r = self.H.make("Add a feature", ["app-management"], dest_dir=Path(self.tmp.name))
        with zipfile.ZipFile(r["path"]) as z:
            names = z.namelist()
            self.assertIn("HANDOFF.md", names)
            self.assertIn("source-inventory.json", names)
            self.assertFalse(any(n.startswith(("manuscript/", "source/book/")) for n in names))
            self.assertIn("source/tools/manage.py", names)
            inv = json.loads(z.read("source-inventory.json"))
            ex = Path(self.tmp.name) / "ai"
            z.extractall(ex)
        # The handoff carries the REAL installation's revision, so build the return package against it.
        (ex / "source" / "tools" / "bbmanage" / "paths.py").write_text(
            (ex / "source" / "tools" / "bbmanage" / "paths.py").read_text() + "\n# AI change\n")
        out = Path(self.tmp.name) / "return.zip"
        made = self.PK.make(inv["files"], inv["revision"], ex / "source", out, "ai-1", "AI change", partial=True)
        with zipfile.ZipFile(out) as z:
            m = json.loads(z.read("forge-manifest.json"))
        self.assertEqual([o["path"] for o in m["operations"]], ["tools/bbmanage/paths.py"])
        self.assertEqual(m["base_revision"], inv["revision"])
        self.assertEqual(made["operations"], 1)


class CliTests(Base):
    def run_cli(self, *args):
        env = {**os.environ, "BOOK_BUILDER_HOME": str(self.home)}
        return subprocess.run([sys.executable, str(REAL / "tools" / "manage.py"), *args], capture_output=True, text=True,
                              env=env, stdin=subprocess.DEVNULL, timeout=120)

    def test_status_revision_and_refusals_without_confirmation(self):
        r = self.run_cli("status", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("revision", json.loads(r.stdout))
        self.assertEqual(self.run_cli("revision").returncode, 0)
        self.edit_source("tools/jobs.py")                         # make the copy differ from the real app
        z, _, _ = self.make_package()
        r = self.run_cli("update", str(z))                       # built for the test copy: stale for the real app
        self.assertEqual(r.returncode, 1)
        self.assertIn("Stale package", r.stdout)

    def test_windows_launcher_is_well_formed(self):
        cmd = (REAL / "BookBuilder_Manager.cmd").read_bytes()
        self.assertIn(b"\r\n", cmd)
        self.assertNotIn(b"\n", cmd.replace(b"\r\n", b""), "CRLF line endings only")
        text = cmd.decode("ascii")
        self.assertIn('cd /d "%~dp0"', text)
        self.assertIn('"%BB_PY%" %BB_PYARG% "%~dp0tools\\manage.py"', text)   # quoted: works with spaces


if __name__ == "__main__":
    unittest.main()
