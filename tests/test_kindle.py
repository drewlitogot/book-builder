"""Send to Kindle: opt-in, validation, password handling and honest status, with a fake mail server."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

FAKE = '''
import smtplib
SENT = []
class Fake:
    def __init__(self, refuse=False, fail=False): self.refuse, self.fail = refuse, fail
    def send_message(self, msg):
        if self.fail: raise smtplib.SMTPAuthenticationError(535, b"bad password hunter2")
        SENT.append(msg); return {"x@kindle.com": (550, b"no")} if self.refuse else {}
    def quit(self): pass
'''


class KindleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls.tmp.name) / "home"
        cls.book = Path(cls.tmp.name) / "book"
        (cls.book / "dist").mkdir(parents=True)
        (cls.book / "book.yml").write_text("metadata: {title: K}\nparts: []\n")
        (cls.book / "dist" / "k.epub").write_bytes(b"PK\x03\x04 fake epub")
        (cls.book / "dist" / "k.txt").write_text("not a book")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def py(self, code):
        env = {**os.environ, "BOOK_BUILDER_HOME": str(self.home), "PYTHONPATH": str(TOOLS), "BOOK_PROJECT": str(self.book),
               "BB_NO_KEYCHAIN": "1"}
        r = subprocess.run([sys.executable, "-c", FAKE + code], env=env, capture_output=True, text=True, timeout=60, cwd=TOOLS)
        if r.returncode:
            raise AssertionError(r.stderr[-3000:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_1_off_until_set_up_and_validated(self):
        out = self.py("import kindle as K, json; from pathlib import Path\n"
                      "a = K.send(Path(%r), confirm=True)\n"
                      "b = K.save({'kindle': 'me@gmail.com'})\n"
                      "c = K.save({'host': 'smtp evil;rm', 'kindle': 'me@kindle.com'})\n"
                      "print(json.dumps([a['status'], b['ok'], c['ok']]))" % str(self.book / "dist" / "k.epub"))
        self.assertEqual(out, ["not-sent", False, False])

    def test_2_password_never_leaves_the_backend(self):
        out = self.py("import kindle as K, json\n"
                      "r = K.save({'enabled': True, 'host': 'smtp.example.com', 'port': 587, 'user': 'me', 'sender': 'me@example.com', "
                      "'kindle': 'me_1@kindle.com', 'password': 'hunter2'})\n"
                      "print(json.dumps({'r': r, 's': K.settings()}))")
        self.assertNotIn("hunter2", json.dumps(out))
        self.assertTrue(out["s"]["passwordStored"])
        self.assertNotIn("hunter2", (self.home / "kindle.json").read_text())
        secret = self.home / "secrets" / "smtp-password"
        self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o600)

    def test_3_send_needs_confirmation_and_reports_honestly(self):
        epub = str(self.book / "dist" / "k.epub")
        out = self.py("import kindle as K, json; from pathlib import Path\n"
                      f"p = Path({epub!r})\n"
                      "a = K.send(p, confirm=False)\n"
                      "b = K.send(p, confirm=True, transport=lambda s, pw: Fake())\n"
                      "c = K.send(p, confirm=True, transport=lambda s, pw: Fake(refuse=True))\n"
                      "d = K.send(p, confirm=True, transport=lambda s, pw: Fake(fail=True))\n"
                      f"e = K.send(Path({str(self.book / 'dist' / 'k.txt')!r}), confirm=True, transport=lambda s, pw: Fake())\n"
                      "m = SENT[0]\n"
                      "print(json.dumps({'s': [x['status'] for x in (a, b, c, d, e)], 'msg': b['message'], 'err': d['message'], "
                      "'to': m['To'], 'att': [p.get_filename() for p in m.iter_attachments()], 'log': [h['status'] for h in K.history()]}))")
        self.assertEqual(out["s"], ["not-sent", "sent-to-server", "refused", "failed", "not-sent"])
        self.assertIn("can't see Amazon's side", out["msg"])
        self.assertNotIn("delivered", out["msg"].lower())
        self.assertNotIn("hunter2", out["err"], "the password is masked in error messages")
        self.assertEqual(out["to"], "me_1@kindle.com")
        self.assertEqual(out["att"], ["k.epub"])
        self.assertEqual(out["log"], ["sent-to-server", "refused", "failed"])


if __name__ == "__main__":
    unittest.main()
