"""Save Work git scenarios against throwaway repositories (a local bare repo stands in for GitHub)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import gitstatus as GS  # noqa: E402


def sh(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env={**GS.GIT_ENV, "GIT_AUTHOR_NAME": "t",
                   "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})


class GitScenarioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.remote, self.repo = base / "remote.git", base / "book"
        sh(base, "init", "-q", "--bare", "-b", "main", str(self.remote))
        sh(base, "init", "-q", "-b", "main", str(self.repo))
        for k, v in (("user.name", "t"), ("user.email", "t@example.com"), ("commit.gpgsign", "false")):
            sh(self.repo, "config", k, v)
        (self.repo / "book").mkdir()
        (self.repo / "book" / "01.md").write_text("one\n")
        (self.repo / "tools.py").write_text("x = 1\n")
        (self.repo / ".gitignore").write_text("dist/\n")
        sh(self.repo, "add", "-A")
        sh(self.repo, "commit", "-q", "-m", "start")
        sh(self.repo, "remote", "add", "origin", str(self.remote))
        sh(self.repo, "push", "-q", "-u", "origin", "main")

    def tearDown(self):
        self.tmp.cleanup()

    def test_1_clean_and_synced(self):
        st = GS.status(self.repo)
        self.assertEqual(st["state"], "clean")
        self.assertEqual((st["ahead"], st["behind"], st["saveCount"]), (0, 0, 0))
        self.assertEqual(st["lastCommit"]["subject"], "start")
        self.assertEqual(st["lastPush"]["hash"], st["lastCommit"]["hash"])

    def test_2_only_ignored_files(self):
        (self.repo / "dist").mkdir()
        (self.repo / "dist" / "book.pdf").write_text("pdf")
        st = GS.status(self.repo)
        self.assertEqual(st["state"], "clean")
        self.assertEqual(st["files"], [])
        self.assertGreaterEqual(st["ignored"], 1)

    def test_3_untracked_outside_book_is_not_a_failure_and_not_committable(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "launch.json").write_text("{}")
        st = GS.status(self.repo)
        self.assertEqual(st["state"], "other")                 # saved and synced; other files noted
        self.assertEqual(st["counts"]["untracked"], 1)
        self.assertEqual(st["saveCount"], 0)
        r = GS.commit(self.repo, "nothing")
        self.assertFalse(r["ok"])
        self.assertIn("no changes", r["message"].lower())

    def test_4_modified_tracked_files_commit_only_book_folders(self):
        (self.repo / "book" / "01.md").write_text("one, edited\n")
        (self.repo / "tools.py").write_text("x = 2\n")
        (self.repo / "book" / "02.md").write_text("two\n")
        st = GS.status(self.repo)
        self.assertEqual(st["state"], "changes")
        self.assertEqual((st["counts"]["modified"], st["counts"]["untracked"], st["saveCount"], st["otherCount"]), (2, 1, 2, 1))
        r = GS.commit(self.repo, "Edit chapter one")
        self.assertTrue(r["ok"], r)
        self.assertRegex(r["hash"], r"^[0-9a-f]{7,}$")
        after = GS.status(self.repo)
        self.assertEqual([f["path"] for f in after["files"]], ["tools.py"])   # not silently staged or committed
        self.assertEqual(after["ahead"], 1)
        self.assertEqual(after["state"], "ahead")

    def test_4b_files_staged_outside_book_are_left_out_of_the_commit(self):
        (self.repo / "tools.py").write_text("x = 3\n")
        sh(self.repo, "add", "tools.py")
        (self.repo / "book" / "01.md").write_text("changed\n")
        self.assertTrue(GS.commit(self.repo, "book only")["ok"])
        out = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertEqual(out.split(), ["book/01.md"])

    def test_5_and_6_local_commit_then_successful_push(self):
        (self.repo / "book" / "01.md").write_text("v2\n")
        self.assertTrue(GS.commit(self.repo, "v2")["ok"])
        self.assertEqual(GS.status(self.repo)["state"], "ahead")
        p = GS.push(self.repo)
        self.assertTrue(p["ok"], p)
        st = GS.status(self.repo)
        self.assertEqual((st["state"], st["ahead"]), ("clean", 0))
        self.assertTrue(GS.push(self.repo)["ok"])            # nothing to push is not an error

    def test_7_push_with_network_unavailable(self):
        (self.repo / "book" / "01.md").write_text("v3\n")
        GS.commit(self.repo, "v3")
        sh(self.repo, "remote", "set-url", "origin", "http://127.0.0.1:9/nowhere.git")
        p = GS.push(self.repo, timeout=20)
        self.assertFalse(p["ok"])
        self.assertEqual(p["kind"], "network")
        self.assertEqual(GS.status(self.repo)["ahead"], 1)    # the commit is still safe locally

    def test_8_auth_and_rejection_messages_are_classified(self):
        self.assertEqual(GS.classify_error("remote: Invalid username or password.\nfatal: Authentication failed for 'https://github.com/a/b.git/'"), "auth")
        self.assertEqual(GS.classify_error("fatal: could not read Username for 'https://github.com': terminal prompts disabled"), "auth")
        self.assertEqual(GS.classify_error("git@github.com: Permission denied (publickey)."), "auth")
        self.assertEqual(GS.classify_error("! [rejected] main -> main (fetch first)\nerror: failed to push some refs"), "rejected")
        self.assertEqual(GS.classify_error("fatal: unable to access 'https://github.com/a/b.git/': Could not resolve host: github.com"), "network")

    def test_no_upstream(self):
        sh(self.repo, "checkout", "-q", "-b", "local-only")
        st = GS.status(self.repo)
        self.assertEqual(st["state"], "noupstream")
        p = GS.push(self.repo)
        self.assertEqual(p["kind"], "noremote")

    def test_merge_conflict(self):
        sh(self.repo, "checkout", "-q", "-b", "other")
        (self.repo / "book" / "01.md").write_text("other side\n")
        sh(self.repo, "commit", "-q", "-am", "other")
        sh(self.repo, "checkout", "-q", "main")
        (self.repo / "book" / "01.md").write_text("main side\n")
        sh(self.repo, "commit", "-q", "-am", "main")
        subprocess.run(["git", "merge", "other"], cwd=self.repo, capture_output=True, env=GS.GIT_ENV)
        st = GS.status(self.repo)
        self.assertEqual(st["state"], "conflict")
        self.assertEqual(st["conflicts"], ["book/01.md"])
        self.assertFalse(GS.commit(self.repo, "x")["ok"])

    def test_not_a_repository(self):
        d = Path(self.tmp.name) / "plain"
        d.mkdir()
        self.assertEqual(GS.status(d)["state"], "norepo")


if __name__ == "__main__":
    unittest.main()
