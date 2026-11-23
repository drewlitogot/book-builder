#!/usr/bin/env python3
"""Book Builder's application-level data: the project registry, global settings and book templates.

Book Builder is the application; each book is a *project* folder with its own book.yml, outline,
chapters, assets, research and outputs. Nothing here touches a project's manuscript.

App data lives outside every project, in BOOK_BUILDER_HOME (default ~/.book-builder):

    registry.json   known projects: path, when added and last opened, archived flag
    settings.json   global preferences (appearance, default fonts, AI assistants, privacy, ...)

If the folder the tools ship in also holds a book (book.yml), it is registered automatically as the
"home" project, so single-book setups keep working with no migration step.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import yaml

APP = Path(__file__).resolve().parent.parent          # the Book Builder engine (tools, fonts, templates)
HOME = Path(os.environ.get("BOOK_BUILDER_HOME") or Path.home() / ".book-builder")
REGISTRY = HOME / "registry.json"
SETTINGS = HOME / "settings.json"
APP_NAME = "Book Builder"
PROJECT_FILE = "project.json"

# Global settings: application preferences only. Book-specific choices live in each project.
SETTINGS_DEFAULTS = {
    "theme": "light",                       # light (default) | dark | system
    "density": "comfortable",               # comfortable | compact
    "projectsDir": str(Path.home() / "Books"),
    "defaultFonts": {"title": "Playfair Display", "body": "Source Serif 4", "ui": "Source Sans 3"},
    "writer": "ChatGPT",                    # the assistant that drafts (gets copied prompts)
    "checker": "Claude Code",               # the assistant that checks drafts
    "openLastProject": False,               # False: start in the Library
    "openIn": "window",                     # desktop app: "window" (its own window) | "browser"
    "guidance": True,                       # False = expert mode: hide tutorial invitations and Guide me links
    "privacy": {"fetchFontCatalog": True, "checkLiveSite": True},
    "defaultPromptKinds": ["research", "write", "revise"],
}


# ------------------------------------------------------------------ storage helpers

def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def settings() -> dict:
    saved = _read(SETTINGS, {})
    out = json.loads(json.dumps(SETTINGS_DEFAULTS))
    for k, v in saved.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def save_settings(data: dict) -> dict:
    """Merge known keys only, so a stray field can't end up in app settings."""
    cur = _read(SETTINGS, {})
    for k, v in data.items():
        if k not in SETTINGS_DEFAULTS:
            continue
        if isinstance(SETTINGS_DEFAULTS[k], dict) and isinstance(v, dict):
            cur[k] = {**cur.get(k, {}), **{kk: vv for kk, vv in v.items() if kk in SETTINGS_DEFAULTS[k]}}
        else:
            cur[k] = v
    _write(SETTINGS, cur)
    return settings()


# ------------------------------------------------------------------ registry

def is_project(path: Path) -> bool:
    return (path / "book.yml").is_file()


def registry() -> list[dict]:
    items = _read(REGISTRY, {}).get("projects", [])
    return [p for p in items if isinstance(p, dict) and p.get("path")]


def _save_registry(items: list[dict]) -> None:
    _write(REGISTRY, {"projects": items})


def project_file(path: Path) -> dict:
    """project.json of a Book Builder-created project (stable id, publishing switch, brand placeholder).
    Older single-book setups don't have one and are never given one automatically."""
    try:
        return json.loads((Path(path) / PROJECT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ensure(path: Path, opened: bool = False) -> dict:
    """Register a project folder (idempotent). Returns its registry entry (with a stable id)."""
    path = Path(path).expanduser().resolve()
    items = registry()
    entry = next((p for p in items if Path(p["path"]) == path), None)
    if entry is None:
        entry = {"path": str(path), "added": time.time(), "lastOpened": None, "archived": False}
        items.append(entry)
    # The id never depends on the title or folder name. Created projects carry theirs in project.json;
    # legacy projects get one in the registry only (their files aren't touched).
    entry["id"] = project_file(path).get("project_id") or entry.get("id") or f"bk-{uuid.uuid4().hex[:12]}"
    entry["legacy"] = not (path / PROJECT_FILE).exists()
    if opened:
        entry["lastOpened"] = time.time()
        entry["archived"] = False
    _save_registry(items)
    return entry


def update(path: str, **fields) -> bool:
    items = registry()
    for p in items:
        if Path(p["path"]) == Path(path).resolve():
            p.update({k: v for k, v in fields.items() if k in ("archived",)})
            _save_registry(items)
            return True
    return False


def forget(path: str) -> bool:
    """Remove a project from the Library. The folder itself is never touched."""
    items = registry()
    keep = [p for p in items if Path(p["path"]) != Path(path).resolve()]
    _save_registry(keep)
    return len(keep) != len(items)


# ------------------------------------------------------------------ project cards (Library)

COVER_NAMES = ("assets/branding/cover.jpg", "assets/branding/cover.png", "assets/cover.jpg", "assets/cover.png",
               "cover.jpg", "cover.png")


def cover_of(root: Path) -> str | None:
    return next((c for c in COVER_NAMES if (root / c).is_file()), None)


def manifest(root: Path) -> dict:
    try:
        return yaml.safe_load((root / "book.yml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def status_counts(root: Path, man: dict) -> dict:
    """Chapter statuses straight from each file's front matter (cheap; no workflow logic)."""
    counts = {"total": 0, "approved": 0, "drafted": 0, "planned": 0}
    for part in man.get("parts") or []:
        for rel in part.get("chapters") or []:
            p = root / rel
            if p.name == "references.md":
                continue
            counts["total"] += 1
            status = "planned"
            try:
                head = p.read_text(encoding="utf-8")[:600]
                m = re.search(r"^status:\s*(\S+)", head, re.M)
                status = m.group(1) if m else "planned"
            except OSError:
                pass
            counts["approved" if status == "approved" else "planned" if status == "planned" else "drafted"] += 1
    return counts


def last_modified(root: Path) -> float | None:
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%ct"], cwd=root, capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            git_t = float(r.stdout.strip())
        else:
            git_t = 0.0
    except (OSError, subprocess.SubprocessError):
        git_t = 0.0
    files = [p for p in (root / "book").rglob("*.md")] if (root / "book").exists() else []
    file_t = max((p.stat().st_mtime for p in files), default=0.0)
    t = max(git_t, file_t, (root / "book.yml").stat().st_mtime if (root / "book.yml").exists() else 0.0)
    return t or None


def project_status(c: dict) -> str:
    if not c["total"]:
        return "Planning"
    if c["approved"] == c["total"]:
        return "Manuscript complete"
    if c["approved"] or c["drafted"]:
        return "Writing"
    return "Planning"


def card(entry: dict) -> dict:
    root = Path(entry["path"])
    if not is_project(root):
        return {**entry, "missing": True, "title": root.name, "status": "Folder not found"}
    man = manifest(root)
    meta = man.get("metadata") or {}
    counts = status_counts(root, man)
    return {**entry, "missing": False, "title": str(meta.get("title") or root.name),
            "subtitle": str(meta.get("subtitle") or ""), "author": str(meta.get("author") or ""),
            "cover": cover_of(root), "counts": counts, "status": project_status(counts),
            "modified": last_modified(root), "home": root == APP}


def library(current: Path) -> list[dict]:
    if is_project(APP):              # a single-book setup keeps its book next to the tools
        ensure(APP)
    ensure(current)
    for e in registry():             # older entries get their stable id the first time they're listed
        if not e.get("id") and is_project(Path(e["path"])):
            ensure(Path(e["path"]))
    return [card(e) for e in registry()]


# ------------------------------------------------------------------ templates and new projects

# Starter configurations, not rules: they only decide the first outline, folders and settings.
TEMPLATES = {
    "nonfiction": {"name": "Nonfiction", "icon": "book-open",
                   "desc": "Parts and chapters with research, sources and citations.",
                   "parts": [("Foundations", ["Introduction", "Background", "Key ideas"]),
                             ("In practice", ["Getting started", "Common problems", "Next steps"])],
                   "research": True},
    "fiction": {"name": "Fiction", "icon": "feather",
                "desc": "Acts and chapters; no citations or research step.",
                "parts": [("Act one", ["Chapter one", "Chapter two", "Chapter three"]),
                          ("Act two", ["Chapter four", "Chapter five", "Chapter six"]),
                          ("Act three", ["Chapter seven", "Chapter eight"])],
                "research": False},
    "academic": {"name": "Academic", "icon": "graduation-cap",
                 "desc": "Literature review, methods and findings, with a full bibliography.",
                 "parts": [("Context", ["Introduction", "Literature review"]),
                           ("Study", ["Methods", "Findings", "Discussion"]),
                           ("Close", ["Conclusion"])],
                 "research": True},
    "children": {"name": "Children's book", "icon": "baby",
                 "desc": "Short sections meant to sit beside pictures.",
                 "parts": [("Story", ["Beginning", "Middle", "End"])], "research": False},
    "illustrated": {"name": "Illustrated book", "icon": "image",
                    "desc": "Chapters planned around images, with image prompts and alt text.",
                    "parts": [("Gallery", ["Opening", "Collection", "Closing"])], "research": False},
    "custom": {"name": "Custom", "icon": "sliders-horizontal",
               "desc": "One empty part. Shape the outline yourself.",
               "parts": [("Part one", ["First chapter"])], "research": False},
}

ENGINE_ASSETS = ["assets/typst", "assets/filters", "assets/csl", "assets/css", "assets/fonts"]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "book"


def outline_text(title: str, parts: list[tuple[str, list[str]]]) -> str:
    """An outline in the format tools/chapter.py parses."""
    lines = [f"# {title}: content outline", "",
             "Edit this outline, then use Chapters › Reorder to see the order. Each chapter line is",
             "`N. **Title**: one-line description`.", ""]
    n = 0
    for i, (name, chapters) in enumerate(parts, 1):
        lines += [f"## Part {i}: {name} (`{i:02d}-{slug(name)}`)", ""]
        for ch in chapters:
            n += 1
            lines.append(f"{n}. **{ch}**: ")
        lines.append("")
    return "\n".join(lines)


def _valid_folder(base: Path) -> str | None:
    """Reasons a folder can't hold a new book (None = fine)."""
    if base.exists() and any(base.iterdir()):
        return f"{base} already exists and isn't empty. Pick another folder."
    if base == APP or APP in base.parents:
        return "New books can't go inside the Book Builder folder (keep books in their own folders). Pick another folder."
    for e in registry():
        other = Path(e["path"])
        if other == base or other in base.parents or base in other.parents:
            return f"That folder overlaps another book in the Library ({other}). Pick a separate folder."
    return None


def _clean_parts(parts) -> list[tuple[str, list[str]]]:
    out = []
    for p in parts or []:
        name = " ".join(str(p.get("name", "") if isinstance(p, dict) else p[0]).split())[:80]
        chs = p.get("chapters", []) if isinstance(p, dict) else p[1]
        chs = [" ".join(str(c).split())[:120] for c in chs if str(c).strip()]
        if name and chs:
            out.append((name, chs))
    return out


def create(title: str, template: str = "custom", folder: str | None = None, author: str = "",
           subtitle: str = "", parts=None, meta: dict | None = None, brand: dict | None = None,
           cover: tuple[bytes, str] | None = None, formats: list[str] | None = None) -> dict:
    """Create a new, self-contained book project from the wizard. Refuses non-empty or overlapping folders.
    Publishing is OFF for every new project until its website is configured on purpose."""
    title = " ".join(title.split())
    if not title:
        return {"ok": False, "message": "Give the book a title."}
    tpl = TEMPLATES.get(template, TEMPLATES["custom"])
    base = Path(folder).expanduser() if folder else Path(settings()["projectsDir"]).expanduser() / slug(title)
    base = base.resolve()
    if (why := _valid_folder(base)):
        return {"ok": False, "message": why}
    parts = _clean_parts(parts) or tpl["parts"]
    if sum(len(c) for _, c in parts) > 300:
        return {"ok": False, "message": "That's more than 300 chapters; split the book or add chapters later."}
    meta = {k: " ".join(str(v).split()) for k, v in (meta or {}).items() if str(v).strip()}
    project_id = f"bk-{uuid.uuid4().hex[:12]}"
    try:
        base.mkdir(parents=True, exist_ok=True)
        for rel in ENGINE_ASSETS:               # build templates and fonts, so the project builds on its own
            if (APP / rel).exists():
                shutil.copytree(APP / rel, base / rel)
        (base / "assets/branding").mkdir(parents=True, exist_ok=True)
        (base / "research").mkdir(exist_ok=True)
        (base / "research/03-content-outline.md").write_text(outline_text(title, parts), encoding="utf-8")
        book_parts, n = [], 0
        for i, (name, chapters) in enumerate(parts, 1):
            files = []
            for ch in chapters:
                n += 1
                rel = f"book/{i:02d}-{slug(name)}/{n:02d}-{slug(ch)}.md"
                (base / rel).parent.mkdir(parents=True, exist_ok=True)
                (base / rel).write_text(f'---\nid: ch-{uuid.uuid4().hex[:8]}\ntitle: {json.dumps(ch)}\nstatus: planned\nsources: []\n---\n\n'
                                        f'# {ch}\n\n*Planned.*\n', encoding="utf-8")
                files.append(rel)
            book_parts.append({"title": f"Part {i}: {name}", "chapters": files})
        md = {"title": title, "subtitle": subtitle or "", "author": author or "Author name",
              "lang": meta.pop("lang", "en-US"), "rights": f"© {time.strftime('%Y')}. All rights reserved.", "date": "Draft",
              **{k: v for k, v in meta.items() if k in ("description", "subject", "intended-audience", "keywords", "publisher", "editor")},
              "papersize": "us-trade",
              "margin": {"inside": "0.875in", "outside": "0.625in", "top": "0.75in", "bottom": "0.75in"},
              "fontsize": "11pt"}
        if isinstance(md.get("keywords"), str):
            md["keywords"] = [k.strip() for k in md["keywords"].split(",") if k.strip()]
        if tpl["research"]:
            (base / "references.bib").write_text("% BibTeX entries for this book\n", encoding="utf-8")
            md["bibliography"] = "references.bib"
        header = (f"# Book manifest for {title}: metadata and chapter order.\n"
                  f"# Created by {APP_NAME} from the {tpl['name']} template.\n\n")
        (base / "book.yml").write_text(header + yaml.safe_dump({"metadata": md, "parts": book_parts},
                                                               sort_keys=False, allow_unicode=True), encoding="utf-8")
        if cover and cover[0]:
            data, ext = cover
            ext = ext.lower() if ext.lower() in (".jpg", ".jpeg", ".png") else None
            if not ext or not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
                raise ValueError("The cover must be a JPEG or PNG image.")
            (base / "assets/branding" / f"cover{'.jpg' if ext == '.jpeg' else ext}").write_bytes(data)
        b = brand or {}
        (base / PROJECT_FILE).write_text(json.dumps({
            "schema": 1, "project_id": project_id, "created": time.time(), "template": template,
            "publishing": {"enabled": False, "note": "Off until you set up this book's website on purpose."},
            "outputs": [f for f in (formats or ["pdf", "epub"]) if f in ("pdf", "epub", "docx", "html")],
            "brand": {"status": "placeholder", "accent": b.get("accent") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(b.get("accent", ""))) else None,
                      "titleFont": str(b.get("titleFont") or "")[:60] or None, "bodyFont": str(b.get("bodyFont") or "")[:60] or None,
                      "mood": str(b.get("mood") or "")[:200] or None},
        }, indent=1), encoding="utf-8")
        (base / "README.md").write_text(f"# {title}\n\nA {APP_NAME} project ({tpl['name']} template).\n", encoding="utf-8")
        (base / ".gitignore").write_text("dist/\nsources-private/\nresearch-library/\n.DS_Store\n", encoding="utf-8")
    except (OSError, ValueError) as e:
        return {"ok": False, "message": f"Couldn't create the project: {e}"}
    entry = ensure(base)
    return {"ok": True, "message": f"Created {title} in {base}.", "path": str(base), "id": entry["id"]}


def publishing_enabled(root: Path) -> tuple[bool, str]:
    """Legacy projects keep their existing website settings; created projects start with publishing off."""
    pf = project_file(root)
    if not pf:
        return True, ""
    if not pf.get("publishing", {}).get("enabled"):
        return False, "Publishing is off for this book. Turn it on in Overview › Book Details once its website is set up."
    return True, ""


def import_folder(folder: str) -> dict:
    path = Path(folder).expanduser().resolve()
    if not path.is_dir():
        return {"ok": False, "message": f"No folder at {path}."}
    if not is_project(path):
        return {"ok": False, "message": f"{path} has no book.yml, so it isn't a book project."}
    ensure(path)
    return {"ok": True, "message": f"Added {path.name} to the Library.", "path": str(path)}
