"""Start Book Builder from a packaged app (the macOS .app, the Windows or Linux folder).

The launchers made by tools/package_app.py run this with the bundled Python. It:
- puts the bundled Pandoc and Typst first on PATH (BB_RUNTIME_BIN)
- on first run, copies the Sample Book (BB_SAMPLE_BOOK) into your books folder, so the app bundle
  itself is never written to
- opens the book you used last (or the Sample Book), then starts the normal web app.

Standard library only.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def choose_project(sample: Path | None) -> Path | None:
    sys.path.insert(0, str(TOOLS))
    import registry as R  # noqa: PLC0415

    books = [p for p in R.registry() if not p.get("archived") and R.is_project(Path(p["path"]))]
    if books:
        last = max(books, key=lambda p: p.get("lastOpened") or p.get("added") or 0)
        return Path(last["path"])
    if sample and R.is_project(sample):
        dest = Path(R.settings()["projectsDir"]).expanduser() / "Sample Book"
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(sample, dest)
            for p in [dest, *dest.rglob("*")]:              # the bundle may be read-only; the copy must not be
                p.chmod(p.stat().st_mode | 0o200)
        if R.is_project(dest):
            R.ensure(dest, opened=True)
            return dest
    return None


def main() -> None:
    env = dict(os.environ)
    bin_dir = env.get("BB_RUNTIME_BIN")
    if bin_dir:
        env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"                   # never write caches into the app bundle
    sample = Path(env["BB_SAMPLE_BOOK"]) if env.get("BB_SAMPLE_BOOK") else None
    if not env.get("BOOK_PROJECT"):
        project = choose_project(sample)
        if project:
            env["BOOK_PROJECT"] = str(project)
    os.environ.clear()
    os.environ.update(env)
    args = [sys.executable, str(TOOLS / "webapp.py"), *sys.argv[1:]]
    if os.name == "nt":                                    # execv on Windows doesn't keep the console attached
        import subprocess  # noqa: PLC0415
        sys.exit(subprocess.call(args, env=env))
    os.execve(sys.executable, args, env)


if __name__ == "__main__":
    main()
