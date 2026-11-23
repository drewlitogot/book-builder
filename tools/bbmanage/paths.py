"""Where Book Builder's source, user data, backups and logs live, and which files count as source.

Source (the application) and book data (manuscripts, research, assets, settings) are kept apart by
these rules. Every management operation (revision, source backup/restore, ZIP updates) only ever
touches SOURCE paths; book-data backup/restore only ever touches DATA paths.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

APP = Path(__file__).resolve().parents[2]            # the Book Builder installation (this repository)
PROJECT_ID = "book-builder"
HOME = Path(os.environ.get("BOOK_BUILDER_HOME") or Path.home() / ".book-builder")   # app data, outside the source
BACKUPS = HOME / "backups"
LOGS = HOME / "logs"
QA_DIR = HOME / "qa"
PACKAGES = HOME / "packages"                         # immutable copies of applied/inspected update ZIPs
STATE = HOME / "manager-state.json"


def version() -> str:
    try:
        return (APP / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


# ---- application source: what revisions, source backups and update packages cover
SOURCE_FILES = [".gitignore", "README.md", "START_HERE.md", "VERSION", "CHANGELOG.md", "requirements.txt",
                "BookBuilder_Manager.cmd", "BookBuilder_Manager.command", "MODULES.json",
                "Build_App_macOS.command", "Build_App_Windows.cmd", "Build_App_Linux.sh"]
SOURCE_DIRS = ["tools", "tests", "run", "desktop", "assets/typst", "assets/filters", "assets/csl", "assets/css", "assets/fonts",
               "docs/book-manager", "docs/game-developer", "docs/architecture"]
SITE_SOURCE = ["site/package.json", "site/package-lock.json", "site/astro.config.mjs", "site/tsconfig.json",
               "site/vitest.config.ts", "site/runtime.vite.config.ts", "site/public/favicon.svg"]
SITE_SOURCE_DIRS = ["site/src", "site/tests"]
EXCLUDE = ["*/__pycache__/*", "*.pyc", "*/.DS_Store", ".DS_Store", "site/src/generated/*", "*/node_modules/*",
           "*.log", "*.tmp", "*/.pytest_cache/*", ".env", "*.env", "*.pem", "*.key"]

# ---- book data: what book-data backups cover (for the project in this folder)
DATA_FILES = ["book.yml", "references.bib", "website.yml", "workspace.yml", "PROJECT-BRIEF.md", "LICENSE"]
DATA_DIRS = ["book", "drafts", "reviews", "research", "research-library", "images", "prompts", "briefs", "sources", "sources-inbox", "games",
             "agents", "assets/branding", "docs/upgrade-audit"]
PRIVATE_DIRS = ["sources-private"]                   # copyrighted source copies: only with explicit opt-in


def rel(p: Path, base: Path = APP) -> str:
    return p.relative_to(base).as_posix()


def excluded(relpath: str) -> bool:
    return any(fnmatch.fnmatch(relpath, pat) or fnmatch.fnmatch("/" + relpath, "*/" + pat.lstrip("*/"))
               for pat in EXCLUDE) or "/__pycache__/" in f"/{relpath}" or "/node_modules/" in f"/{relpath}"


def is_source_path(relpath: str) -> bool:
    """True if a canonical relative path belongs to the application source (never book data)."""
    if not relpath or relpath.startswith(("/", "../")) or "\\" in relpath or "/../" in f"/{relpath}/" or excluded(relpath):
        return False
    if relpath in SOURCE_FILES or relpath in SITE_SOURCE:
        return True
    return any(relpath.startswith(d + "/") for d in SOURCE_DIRS + SITE_SOURCE_DIRS) or \
        (relpath.startswith("docs/") and relpath.count("/") == 1 and relpath.endswith(".md"))


def is_data_path(relpath: str) -> bool:
    if relpath in DATA_FILES:
        return True
    return any(relpath.startswith(d + "/") for d in DATA_DIRS + PRIVATE_DIRS)


def source_files(root: Path = APP) -> list[str]:
    """Every application source file under root, as sorted canonical relative paths."""
    out = set()
    for f in SOURCE_FILES + SITE_SOURCE:
        if (root / f).is_file():
            out.add(f)
    for d in SOURCE_DIRS + SITE_SOURCE_DIRS:
        for p in (root / d).rglob("*") if (root / d).is_dir() else []:
            if p.is_file() and not p.is_symlink():
                r = p.relative_to(root).as_posix()
                if not excluded(r):
                    out.add(r)
    for p in (root / "docs").glob("*.md") if (root / "docs").is_dir() else []:
        out.add(p.relative_to(root).as_posix())
    return sorted(out)


def data_files(root: Path = APP, include_private: bool = False) -> list[str]:
    out = set()
    for f in DATA_FILES:
        if (root / f).is_file():
            out.add(f)
    for d in DATA_DIRS + (PRIVATE_DIRS if include_private else []):
        for p in (root / d).rglob("*") if (root / d).is_dir() else []:
            if p.is_file() and not p.is_symlink() and p.name != ".DS_Store" and \
                    not p.name.endswith((".sqlite", ".sqlite-journal", ".sqlite-wal", ".sqlite-shm")):   # rebuildable index
                out.add(p.relative_to(root).as_posix())
    return sorted(out)


def ensure_dirs() -> None:
    for d in (HOME, BACKUPS / "source", BACKUPS / "data", LOGS, QA_DIR, PACKAGES):
        d.mkdir(parents=True, exist_ok=True)
