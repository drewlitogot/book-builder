"""Token-free UI inventory: every server endpoint the page calls exists, and every page in the menus has a renderer.

A button wired to a missing endpoint, or a menu entry without a page, fails here instead of in front of a reader.
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
WEB = TOOLS / "web"


def ui_calls() -> set[str]:
    text = (WEB / "index.html").read_text() + (WEB / "builder.js").read_text()
    calls = set(re.findall(r"""(?:api|fetch)\(\s*[`"'](/api/[A-Za-z0-9/_.-]*)""", text))
    calls |= set(re.findall(r"""href="(/api/[A-Za-z0-9/_.-]+)""", text))
    return {c.rstrip("/") if not c.endswith("/") else c for c in calls}


def server_routes() -> tuple[set[str], set[str]]:
    code = "import json, routes; routes.load(); print(json.dumps(sorted(set(routes.GET) | set(routes.POST))))"
    r = subprocess.run([sys.executable, "-c", code], cwd=TOOLS, capture_output=True, text=True, timeout=60)
    registered = set(json.loads(r.stdout.strip().splitlines()[-1]))
    src = (TOOLS / "webapp.py").read_text()
    exact = set(re.findall(r'(?:u\.path|p) == "(/api/[^"]+)"', src)) | {p for p in registered if not p.endswith("*")}
    exact |= set(re.findall(r'(?:u\.path|p) in \(([^)]*)\)', src) and
                 re.findall(r'"(/api/[^"]+)"', " ".join(re.findall(r'(?:u\.path|p) in \(([^)]*)\)', src))))
    prefixes = set(re.findall(r'(?:u\.path|p)\.startswith\("(/api/[^"]+)"\)', src)) | {p[:-1] for p in registered if p.endswith("*")}
    return exact, prefixes


class InventoryTests(unittest.TestCase):
    def test_every_endpoint_the_page_calls_exists(self):
        exact, prefixes = server_routes()
        missing = []
        for call in sorted(ui_calls()):
            base = call.split("?")[0]
            if base in exact or any(base.startswith(p) for p in prefixes):
                continue
            if base.endswith("/") and any(e.startswith(base) for e in exact):   # built in code, e.g. `/api/insights/${name}`
                continue
            missing.append(call)
        self.assertGreater(len(ui_calls()), 60, "the inventory should find the page's calls")
        self.assertEqual(missing, [], "the page calls endpoints the server doesn't have")

    def test_every_menu_page_has_a_renderer_or_view(self):
        js = (WEB / "builder.js").read_text()
        html = (WEB / "index.html").read_text()
        navs = js[js.index("const APP_NAV"):js.index("const LEGACY")]
        problems = []
        for sec, subs in re.findall(r'\{ id: "([\w-]+)", label: "[^"]+", icon: "[\w-]+"[^\[]*subs: \[(.*?)\] \}', navs, re.S):
            for key, view in re.findall(r'\["([\w-]+)", "[^"]+", "[\w-]+"(?:, "(\w+)")?\]', subs):
                if view:
                    if f'id="v-{view}"' not in html:
                        problems.append(f"{sec}/{key}: view v-{view} missing")
                elif f'PAGES["{sec}/{key}"]' not in js:
                    problems.append(f"{sec}/{key}: no page renderer")
        self.assertEqual(problems, [])

    def test_no_page_still_says_not_available_for_built_features(self):
        js = (WEB / "builder.js").read_text()
        built = ["Website ZIP", "Custom hosting", "Image licensing", "Emailing the EPUB", "Uploading files from this page"]
        stale = [b for b in built if re.search(rf'planned\(\s*"[^"]*{re.escape(b)}', js)]
        self.assertEqual(stale, [], "these features exist now; their pages shouldn't say 'not available yet'")


if __name__ == "__main__":
    unittest.main()
