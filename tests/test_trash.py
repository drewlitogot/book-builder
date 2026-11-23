"""Delete and restore: books, saved prompts and revision files go to the Trash and can come back."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


def make_book(path: Path, title: str) -> Path:
    (path / "book" / "01-part").mkdir(parents=True)
    (path / "research").mkdir()
    shutil.copy2(ROOT / "research" / "03-content-outline.md", path / "research" / "03-content-outline.md")
    (path / "book.yml").write_text(f"metadata:\n  title: {title}\nparts: []\n")
    return path


class TrashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.open_book = make_book(self.tmp / "open", "Open Book")
        self.other = make_book(self.tmp / "other", "Other Book")
        for d, name in (("prompts", "01-choosing-a-topic-write.md"), ("dist/prompt-packs", "pack.zip"),
                        ("drafts/01-choosing-a-topic", "v1-chapter.md"), ("drafts/01-choosing-a-topic", "v2-chapter.md"),
                        ("reviews/01-choosing-a-topic", "check-v1.md")):
            (self.open_book / d).mkdir(parents=True, exist_ok=True)
            (self.open_book / d / name).write_text("x")
        (self.open_book / "book" / "01-part" / "approved.md").write_text("approved text")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, code: str):
        env = {**os.environ, "BOOK_PROJECT": str(self.open_book), "BOOK_BUILDER_HOME": str(self.home)}
        prog = ("import json, routes, registry as REG; routes.load(); G = routes.GET; P = routes.POST\n"
                f"REG.ensure(__import__('pathlib').Path({str(self.other)!r}))\n" + code)
        r = subprocess.run([sys.executable, "-c", prog], cwd=TOOLS, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_prompts_and_revisions_go_to_the_trash_and_come_back(self):
        out = self.call(
            "a = G['/api/prompts/files']({})\n"
            "b = G['/api/revisions/files']({})\n"
            "c = P['/api/prompts/delete']({'files': ['prompts/01-choosing-a-topic-write.md']})\n"
            "d = P['/api/prompts/delete']({'files': ['prompts/01-choosing-a-topic-write.md'], 'confirm': True})\n"
            "e = P['/api/revisions/delete']({'files': ['drafts/01-choosing-a-topic/v2-chapter.md', 'reviews/01-choosing-a-topic/check-v1.md'], 'confirm': True})\n"
            "t = G['/api/trash']({})['items']\n"
            "f = P['/api/trash/restore']({'id': [i for i in t if i['kind'] == 'prompt'][0]['id']})\n"
            "print(json.dumps([len(a['files']), [x['kind'] for c in b['chapters'] for x in c['files']], c['ok'], d['ok'], e['ok'], len(t), f['ok']]))")
        n_prompts, kinds, unconfirmed, deleted, revs, in_trash, restored = out
        self.assertEqual(n_prompts, 2)
        self.assertEqual(sorted(kinds), ["check", "draft", "draft"])
        self.assertFalse(unconfirmed, "deleting needs confirm: true")
        self.assertTrue(deleted and revs and restored)
        self.assertEqual(in_trash, 3)
        self.assertTrue((self.open_book / "prompts" / "01-choosing-a-topic-write.md").exists(), "restored")
        self.assertFalse((self.open_book / "drafts" / "01-choosing-a-topic" / "v2-chapter.md").exists())
        self.assertTrue((self.open_book / "drafts" / "01-choosing-a-topic" / "v1-chapter.md").exists())

    def test_only_prompt_and_revision_files_can_be_deleted(self):
        out = self.call(
            "r = [P['/api/prompts/delete']({'files': [f], 'confirm': True})['ok'] for f in "
            "['book/01-part/approved.md', '../other/book.yml', 'prompts', 'prompts/missing.md', 'book.yml']]\n"
            "r += [P['/api/revisions/delete']({'files': ['book/01-part/approved.md'], 'confirm': True})['ok']]\n"
            "print(json.dumps(r))")
        self.assertEqual(out, [False] * 6)
        self.assertTrue((self.open_book / "book" / "01-part" / "approved.md").exists())
        self.assertTrue((self.other / "book.yml").exists())

    def test_books_go_to_the_trash_but_not_the_open_one(self):
        out = self.call(
            f"a = P['/api/projects/delete']({{'path': {str(self.open_book)!r}, 'confirm': True}})\n"
            f"b = P['/api/projects/delete']({{'path': {str(self.other)!r}}})\n"
            f"c = P['/api/projects/delete']({{'path': {str(self.other)!r}, 'confirm': True}})\n"
            "lib = [x['path'] for x in REG.registry()]\n"
            "print(json.dumps([a['ok'], b['ok'], c['ok'], lib]))")
        self.assertEqual(out[:3], [False, False, True])
        self.assertNotIn(str(self.other.resolve()), out[3], "a deleted book leaves the Library")
        self.assertFalse(self.other.exists())
        self.assertTrue(self.open_book.exists())
        out = self.call(
            "t = G['/api/trash']({})['items']\n"
            "r = P['/api/trash/restore']({'id': t[0]['id']})\n"
            "print(json.dumps([r['ok'], [x['path'] for x in REG.registry()]]))")
        self.assertTrue(out[0])
        self.assertTrue((self.other / "book.yml").exists())
        self.assertIn(str(self.other.resolve()), out[1], "a restored book is back in the Library")

    def test_restore_refuses_to_overwrite_and_purge_needs_confirmation(self):
        out = self.call(
            "P['/api/prompts/delete']({'files': ['prompts/01-choosing-a-topic-write.md'], 'confirm': True})\n"
            "open(%r, 'w').write('new')\n"
            "i = G['/api/trash']({})['items'][0]['id']\n"
            "a = P['/api/trash/restore']({'id': i})['ok']\n"
            "b = P['/api/trash/purge']({'id': i})['ok']\n"
            "c = P['/api/trash/purge']({'id': '../../etc', 'confirm': True})['ok']\n"
            "d = P['/api/trash/purge']({'all': True, 'confirm': True})['ok']\n"
            "print(json.dumps([a, b, c, d, len(G['/api/trash']({})['items'])]))" % str(self.open_book / "prompts" / "01-choosing-a-topic-write.md"))
        self.assertEqual(out, [False, False, False, True, 0])
        self.assertEqual((self.open_book / "prompts" / "01-choosing-a-topic-write.md").read_text(), "new")


if __name__ == "__main__":
    unittest.main()
