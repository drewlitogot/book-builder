"""Desktop app: the Electron shell, the packager's safety checks and the first-run Sample Book copy.
Building real packages downloads ~250 MB per system, so that isn't part of the test run."""
import io
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

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))


class DesktopTests(unittest.TestCase):
    def test_electron_shell_is_valid_and_keeps_the_window_local(self):
        js = (ROOT / "desktop" / "main.js").read_text()
        for must in ("contextIsolation: true", "nodeIntegration: false", "sandbox: true", "setWindowOpenHandler",
                     "will-navigate", "/api/quit", "requestSingleInstanceLock"):
            self.assertIn(must, js)
        pkg = json.loads((ROOT / "desktop" / "package.json").read_text())
        self.assertEqual(pkg["main"], "main.js")
        if shutil.which("node"):
            r = subprocess.run(["node", "--check", str(ROOT / "desktop" / "main.js")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_package_contents(self):
        import package_app as PA  # noqa: PLC0415
        app = PA.app_files()
        self.assertIn("tools/webapp.py", app)
        self.assertIn("tools/start_packaged.py", app)
        self.assertFalse(any(f.startswith(("tests/", "desktop/", "book/", "Build_App_")) for f in app))
        sample = PA.sample_files()
        self.assertIn("book.yml", sample)
        self.assertIn("assets/typst/callouts.typ", sample)
        self.assertNotIn("LICENSE", sample)
        self.assertFalse(any(f.startswith("tools/") for f in sample))
        self.assertEqual(set(PA.TARGETS), {"macos-arm64", "macos-x64", "windows-x64", "linux-x64"})

    def test_extract_refuses_paths_and_links_outside_the_folder(self):
        import package_app as PA  # noqa: PLC0415
        tmp = Path(tempfile.mkdtemp())
        try:
            for name, link in (("../evil.txt", None), ("ok/link", "../../outside")):
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as z:
                    info = zipfile.ZipInfo(name)
                    if link:
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    z.writestr(info, link or "x")
                (tmp / "a.zip").write_bytes(buf.getvalue())
                with self.assertRaises(SystemExit):
                    PA.extract(tmp / "a.zip", tmp / "out")
            self.assertFalse((tmp / "evil.txt").exists())
        finally:
            shutil.rmtree(tmp)

    def test_first_run_copies_a_writable_sample_book(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            sample = tmp / "bundle" / "sample-book"
            shutil.copytree(ROOT / "book", sample / "book")
            shutil.copy2(ROOT / "book.yml", sample / "book.yml")
            for p in [sample, *sample.rglob("*")]:
                p.chmod(p.stat().st_mode & ~0o222)          # app bundles can be read-only
            home = tmp / "data"
            home.mkdir()
            (home / "settings.json").write_text(json.dumps({"projectsDir": str(tmp / "Books")}))
            code = "import json, start_packaged as S; from pathlib import Path; print(S.choose_project(Path(%r)))" % str(sample)
            env = {**os.environ, "BOOK_BUILDER_HOME": str(home)}
            r = subprocess.run([sys.executable, "-c", code], cwd=TOOLS, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            dest = tmp / "Books" / "Sample Book"
            self.assertEqual(Path(r.stdout.strip().splitlines()[-1]).resolve(), dest.resolve())
            self.assertTrue(os.access(dest / "book.yml", os.W_OK) and os.access(dest / "book", os.W_OK))
            # The next start opens the book used last instead of copying again.
            r = subprocess.run([sys.executable, "-c", code], cwd=TOOLS, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(Path(r.stdout.strip().splitlines()[-1]).resolve(), dest.resolve())
        finally:
            for p in tmp.rglob("*"):
                p.chmod(p.stat().st_mode | 0o200)
            shutil.rmtree(tmp)

    def test_build_scripts_exist_for_each_system(self):
        mac = ROOT / "Build_App_macOS.command"
        linux = ROOT / "Build_App_Linux.sh"
        win = (ROOT / "Build_App_Windows.cmd").read_bytes()
        for f in (mac, linux):
            self.assertTrue(os.access(f, os.X_OK), f"{f.name} must be executable")
            self.assertIn("tools/package_app.py", f.read_text())
        self.assertIn(b"\r\n", win)
        self.assertNotIn(b"\n", win.replace(b"\r\n", b""))
        self.assertIn(b"tools\\package_app.py", win)


if __name__ == "__main__":
    unittest.main()
