"""Delete and restore: books, saved prompts and revisions (drafts and checks) go to the Trash.
Registered through routes.py. Every delete needs `confirm: true`; approved chapters are never touched."""
from __future__ import annotations

import time
from pathlib import Path

import chapter as C
import registry as REG
import routes
import trash as T

ROOT = C.ROOT
APP = REG.APP
PROMPT_DIRS = ("prompts", "dist/prompt-packs")
REVISION_DIRS = ("drafts", "reviews")


def _inside(rel: str, dirs: tuple[str, ...]) -> Path | None:
    """The project file for `rel` if it's a file inside one of `dirs`, else None."""
    p = (ROOT / str(rel)).resolve()
    for d in dirs:
        base = (ROOT / d).resolve()
        if p != base and p.is_relative_to(base) and p.exists():
            return p
    return None


def _file(p: Path) -> dict:
    st = p.stat()
    return {"path": str(p.relative_to(ROOT)), "name": p.name, "bytes": st.st_size, "mtime": st.st_mtime}


def _delete_files(data: dict, dirs: tuple[str, ...], kind: str) -> dict:
    if data.get("confirm") is not True:
        return {"ok": False, "message": "Needs confirmation."}
    files = data.get("files") or []
    bad = [f for f in files if _inside(f, dirs) is None]
    if bad or not files:
        return {"ok": False, "message": f"Can't delete: {', '.join(map(str, bad)) or 'nothing chosen'}."}
    for f in files:
        T.put(_inside(f, dirs), kind, f, str(ROOT))
    n = len(files)
    return {"ok": True, "message": f"Moved {n} file{'s' if n != 1 else ''} to the Trash."}


# ---------------------------------------------------------------- books

@routes.post("/api/projects/delete")
def delete_book(data: dict) -> dict:
    if data.get("confirm") is not True:
        return {"ok": False, "message": "Needs confirmation."}
    target = Path(str(data.get("path", ""))).expanduser().resolve()
    if target in (ROOT.resolve(), APP.resolve()):
        return {"ok": False, "message": "This book is open. Open another book first, then delete this one."}
    if not REG.is_project(target):
        return {"ok": False, "message": "That folder isn't a book project (no book.yml), so it wasn't deleted."}
    title = next((b.get("title") for b in REG.library(ROOT) if Path(b["path"]) == target), None) or target.name
    T.put(target, "book", title, str(target))
    REG.forget(str(target))
    return {"ok": True, "message": f"Moved “{title}” to the Trash. You can restore it from Settings › Trash."}


# ---------------------------------------------------------------- prompts

@routes.get("/api/prompts/files")
def prompt_files(qs: dict) -> dict:
    out = []
    for d in PROMPT_DIRS:
        base = ROOT / d
        if base.is_dir():
            out += [_file(p) for p in base.rglob("*") if p.is_file() and p.name != ".DS_Store"]
    return {"files": sorted(out, key=lambda f: f["mtime"], reverse=True)}


@routes.post("/api/prompts/delete")
def delete_prompts(data: dict) -> dict:
    return _delete_files(data, PROMPT_DIRS, "prompt")


# ---------------------------------------------------------------- revisions

def _revision_kind(name: str) -> str:
    if name.endswith("-chapter.md"):
        return "draft"
    if "notes" in name:
        return "notes"
    return "other"


@routes.get("/api/revisions/files")
def revision_files(qs: dict) -> dict:
    out = []
    for ch in C.parse_outline()[0]:
        stem = C.chapter_path(ch).stem
        files = []
        for d in REVISION_DIRS:
            base = ROOT / d / stem
            if base.is_dir():
                for p in sorted(base.rglob("*")):
                    if p.is_file() and p.name != ".DS_Store":
                        f = _file(p)
                        f["kind"] = "check" if d == "reviews" else _revision_kind(p.name)
                        files.append(f)
        if files:
            meta = C.front_matter(C.chapter_path(ch))[0] if C.chapter_path(ch).exists() else {}
            out.append({"n": ch["n"], "title": ch["title"], "status": meta.get("status", "planned"),
                        "files": sorted(files, key=lambda f: f["mtime"], reverse=True)})
    return {"chapters": out}


@routes.post("/api/revisions/delete")
def delete_revisions(data: dict) -> dict:
    return _delete_files(data, REVISION_DIRS, "revision")


# ---------------------------------------------------------------- the Trash

@routes.get("/api/trash")
def trash_list(qs: dict) -> dict:
    return {"items": T.items(), "folder": str(T.TRASH), "now": time.time()}


@routes.post("/api/trash/restore")
def trash_restore(data: dict) -> dict:
    try:
        r = T.restore(str(data.get("id", "")))
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    if r["ok"] and r["item"]["kind"] == "book":
        REG.ensure(Path(r["item"]["original"]))
    return r


@routes.post("/api/trash/purge")
def trash_purge(data: dict) -> dict:
    if data.get("confirm") is not True:
        return {"ok": False, "message": "Needs confirmation."}
    if data.get("all"):
        return T.empty()
    try:
        return T.purge(str(data.get("id", "")))
    except ValueError as e:
        return {"ok": False, "message": str(e)}
