"""Book Manager integration: Games view endpoints and the local game preview."""
from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import games as G  # noqa: E402
import webapp as A  # noqa: E402
from test_games import TempRegistry, fixture_files, make_zip  # noqa: E402


class WebappGameTests(TempRegistry):
    def b64(self) -> str:
        return base64.b64encode(make_zip(fixture_files())).decode()

    def test_validate_import_approve_remove_via_endpoints(self):
        r = A.game_action("validate", {"data": self.b64()})
        self.assertTrue(r["ok"], r)
        self.assertEqual(G.load_registry()["games"], {})  # validate never installs
        r = A.game_action("import", {"data": self.b64(), "name": "fixture.zip"})
        self.assertEqual(r["entry"]["status"], "review")
        again = A.game_action("import", {"data": self.b64()})
        self.assertFalse(again["ok"])
        st = A.games_state()
        self.assertEqual([g["id"] for g in st["games"]], ["fixture-kitchen-sink"])
        self.assertFalse(st["games"][0]["willPublish"])
        A.game_action("status", {"id": "fixture-kitchen-sink", "status": "approved"})
        self.assertTrue(A.games_state()["games"][0]["willPublish"])
        self.assertTrue(A.game_action("remove", {"id": "fixture-kitchen-sink"})["ok"])

    def test_unsafe_zip_reported_not_raised(self):
        bad = base64.b64encode(make_zip({**fixture_files(), "evil.js": b"alert(1)"})).decode()
        r = A.game_action("import", {"data": bad})
        self.assertFalse(r["ok"])
        self.assertIn("not allowed", r["message"])

    def test_preview_page_loads_runtime_and_package(self):
        G.install(make_zip(fixture_files()))
        page = A.preview_page("fixture-kitchen-sink")
        self.assertIn('/runtime/game-runtime.js', page)
        self.assertIn('/games/preview/fixture-kitchen-sink/', page)
        self.assertIn("Not published", page)
        self.assertTrue((A.RUNTIME / "game-runtime.js").exists(), "run `npm run build:runtime` in site/")


if __name__ == "__main__":
    unittest.main()
