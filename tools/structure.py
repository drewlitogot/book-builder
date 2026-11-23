"""Book structure editing (add, rename, reorder, remove parts and chapters) for Book Builder projects.

Safety rules:
- Only projects created by Book Builder (with project.json) can be edited. Older single-book
  setups are shown read-only, so none of their files are rewritten.
- A chapter that has any work (not 'planned', or drafts / research / reviews exist) keeps its number,
  part folder and title here; only planned placeholders move, get renamed or are removed.
- Removed placeholders go to book/.removed/, never deleted. A book-data backup is made first.
- book.yml is rewritten only from its `parts:` line down; metadata lines and comments stay as they are.
"""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path

import yaml

import chapter as C
import registry as REG

ROOT = C.ROOT


def editable() -> tuple[bool, str]:
    if not (ROOT / REG.PROJECT_FILE).exists():
        return False, ("This book was set up before Book Builder's structure editor, so its chapter files aren't "
                       "rewritten here. Change its order in research/03-content-outline.md instead.")
    return True, ""


def _has_work(ch: dict, meta: dict) -> bool:
    stem = C.chapter_path(ch).stem
    return (meta.get("status", "planned") != "planned"
            or (ROOT / "drafts" / stem).exists() or (ROOT / "reviews" / stem).exists()
            or C.research_path(ch).exists())


def current() -> dict:
    chapters, parts, _ = C.parse_outline()
    out = {}
    for ch in chapters:
        if C.is_special(ch):
            continue
        path = C.chapter_path(ch)
        meta, _ = C.front_matter(path)
        part = out.setdefault(ch["part"]["n"], {"n": ch["part"]["n"], "name": ch["part"]["name"], "chapters": []})
        part["chapters"].append({"id": meta.get("id") or f"file:{path.relative_to(ROOT).as_posix()}", "n": ch["n"],
                                 "title": ch["title"], "status": meta.get("status", "planned"),
                                 "file": path.relative_to(ROOT).as_posix(), "locked": _has_work(ch, meta)})
    ok, why = editable()
    return {"editable": ok, "reason": why, "parts": [out[k] for k in sorted(out)]}


def _fm_set_title(path: Path, title: str) -> None:
    t = path.read_text(encoding="utf-8")
    t = re.sub(r"(?m)^title:.*$", f"title: {json.dumps(title)}", t, count=1)
    t = re.sub(r"(?m)^# .*$", f"# {title}", t, count=1)
    path.write_text(t, encoding="utf-8")


def save(new_parts: list[dict]) -> dict:
    ok, why = editable()
    if not ok:
        return {"ok": False, "message": why}
    cur = current()
    old = {c["id"]: c for p in cur["parts"] for c in p["chapters"]}
    plan, n, seen = [], 0, set()
    for i, part in enumerate(new_parts, 1):
        name = " ".join(str(part.get("name", "")).split())[:80]
        chs = [c for c in part.get("chapters", []) if str(c.get("title", "")).strip()]
        if not name or not chs:
            return {"ok": False, "message": f"Part {i} needs a name and at least one chapter."}
        folder = f"{i:02d}-{REG.slug(name)}"
        for c in chs:
            n += 1
            title = " ".join(str(c["title"]).split())[:120]
            src = old.get(c.get("id")) if c.get("id") else None
            if c.get("id") and not src:
                return {"ok": False, "message": f"Unknown chapter id {c['id']}: reload the page and try again."}
            if src:
                if src["id"] in seen:
                    return {"ok": False, "message": f"“{src['title']}” appears twice."}
                seen.add(src["id"])
                if src["locked"]:
                    same_place = src["n"] == n and Path(src["file"]).parent.name == folder
                    if not same_place or title != src["title"]:
                        return {"ok": False, "message": f"“{src['title']}” already has drafts, research or a status, so it keeps "
                                                         f"its number ({src['n']}), part and title. Move the other chapters around it."}
            plan.append({"part": i, "partName": name, "folder": folder, "n": n, "title": title, "src": src,
                         "dest": f"book/{folder}/{n:02d}-{REG.slug(title)}.md" if not (src and src["locked"]) else src["file"]})
    removed = [c for c in old.values() if c["id"] not in seen]
    locked_removed = [c["title"] for c in removed if c["locked"]]
    if locked_removed:
        return {"ok": False, "message": f"Chapters with work can't be removed here: {', '.join(locked_removed)}."}

    import sys  # noqa: PLC0415
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from bbmanage import backups as B  # noqa: PLC0415
    backup = B.make_data_backup(ROOT, label="pre-structure")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    staging = ROOT / "book" / f".restructure-{stamp}"
    staging.mkdir(parents=True)
    trash = ROOT / "book" / ".removed" / stamp
    for c in removed:                                     # planned placeholders only
        trash.mkdir(parents=True, exist_ok=True)
        shutil.move(str(ROOT / c["file"]), trash / Path(c["file"]).name)
    for item in plan:                                     # move movable files out of the way first
        if item["src"] and not item["src"]["locked"]:
            tmp = staging / f"{item['src']['id'].replace(':', '_').replace('/', '_')}.md"
            shutil.move(str(ROOT / item["src"]["file"]), tmp)
            item["tmp"] = tmp
    for item in plan:
        dest = ROOT / item["dest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if item.get("tmp"):
            shutil.move(str(item["tmp"]), dest)
            if item["title"] != item["src"]["title"]:
                _fm_set_title(dest, item["title"])
        elif not item["src"]:
            dest.write_text(f'---\nid: ch-{uuid.uuid4().hex[:8]}\ntitle: {json.dumps(item["title"])}\nstatus: planned\nsources: []\n---\n\n'
                            f'# {item["title"]}\n\n*Planned.*\n', encoding="utf-8")
    shutil.rmtree(staging, ignore_errors=True)
    for d in sorted((ROOT / "book").glob("[0-9][0-9]-*"), reverse=True):   # tidy empty part folders
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()

    parts = []
    for item in plan:
        if not parts or parts[-1][0] != item["partName"]:
            parts.append((item["partName"], []))
        parts[-1][1].append(item["title"])
    title = (yaml.safe_load((ROOT / "book.yml").read_text(encoding="utf-8")).get("metadata") or {}).get("title", "Book")
    (ROOT / "research" / "03-content-outline.md").write_text(REG.outline_text(title, parts), encoding="utf-8")
    book_parts = []
    for i, (name, _) in enumerate(parts, 1):
        book_parts.append({"title": f"Part {i}: {name}", "chapters": [it["dest"] for it in plan if it["part"] == i]})
    text = (ROOT / "book.yml").read_text(encoding="utf-8")
    m = re.search(r"(?m)^parts:", text)
    head = text[:m.start()] if m else text.rstrip() + "\n"
    (ROOT / "book.yml").write_text(head + yaml.safe_dump({"parts": book_parts}, sort_keys=False, allow_unicode=True),
                                   encoding="utf-8")
    return {"ok": True, "message": f"Saved: {len(parts)} part(s), {n} chapter(s)"
                                   + (f"; {len(removed)} placeholder(s) moved to book/.removed/" if removed else "") + ".",
            "backup": backup["path"], "structure": current()}
