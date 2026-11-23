"""Full-book export and import ("book package", kind bookbuilder-book).

Export: everything a book needs to be opened and rebuilt elsewhere (book.yml, chapters, drafts, reviews,
research, Research Library originals and records, prompts, games, branding, build templates and fonts,
project settings), with SHA-256 checksums. Left out: builds (dist/), git history, publish checkouts,
the rebuildable search index, Book Builder's own source and, unless asked, sources-private/.

Import: safe-ZIP checks, kind and checksum validation, a preview, then extraction into a NEW, empty folder
as a NEW book (new project id, publishing off). Nothing is ever merged into an existing book.
"""
from __future__ import annotations

import json
import time
import uuid
import zipfile
from pathlib import Path

import registry as REG
from bbmanage import paths as BP
from bbmanage import revision as RV
from bbmanage import zipsafe

KIND = "bookbuilder-book"
SKIP_DIRS = {"dist", ".git", ".publish", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
SKIP_NAMES = {".DS_Store", "index.sqlite", "index.sqlite-journal", "index.sqlite-wal", "index.sqlite-shm"}


def book_files(root: Path, include_private: bool = False) -> list[str]:
    root = root.resolve()
    if root == BP.APP:                       # the legacy book shares the app folder: take its data + build assets
        files = set(BP.data_files(root, include_private))
        files |= {f for f in BP.source_files(root) if f.startswith(tuple(f"{d}/" for d in REG.ENGINE_ASSETS))}
        files |= {f for f in ("README.md",) if (root / f).exists()}
        return sorted(f for f in files if Path(f).name not in SKIP_NAMES)
    out = []
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        if not p.is_file() or p.is_symlink() or p.name in SKIP_NAMES or SKIP_DIRS & set(parts[:-1]):
            continue
        if not include_private and parts[0] in BP.PRIVATE_DIRS:
            continue
        out.append(rel)
    return sorted(out)


def _title(root: Path) -> str:
    import yaml  # noqa: PLC0415
    try:
        return str((yaml.safe_load((root / "book.yml").read_text(encoding="utf-8")).get("metadata") or {}).get("title") or root.name)
    except (OSError, yaml.YAMLError, AttributeError):
        return root.name


def export(root: Path, dest_dir: Path, include_private: bool = False) -> dict:
    root = root.resolve()
    if not (root / "book.yml").exists():
        return {"ok": False, "message": "That folder isn't a book (no book.yml)."}
    files = book_files(root, include_private)
    title = _title(root)
    entry = REG.ensure(root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{REG.slug(title)}-book-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    hashes, chapters = {}, 0
    with zipfile.ZipFile(dest.with_suffix(".partial"), "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            hashes[f] = RV.sha256_file(root / f)
            z.write(root / f, "book/" + f)
            chapters += f.startswith("book/") and f.endswith(".md")
        z.writestr("manifest.json", json.dumps({
            "schema": 1, "kind": KIND, "installable": False, "title": title, "source_project_id": entry["id"],
            "exported": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "book_builder": BP.version(),
            "include_private": include_private, "chapter_files": chapters, "files": hashes}, indent=1, ensure_ascii=False))
        z.writestr("README.md", f"Book package: {title}. Import it in Book Builder › New Book › Import Project. "
                                "It opens as a new, separate book.\n")
    dest.with_suffix(".partial").replace(dest)
    return {"ok": True, "path": str(dest), "name": dest.name, "files": len(files), "title": title,
            "bytes": dest.stat().st_size, "private_included": include_private}


def inspect(zpath: Path) -> dict:
    """Validate a book package. Raises ValueError (or zipsafe.UnsafeArchive) with a plain reason."""
    entries = zipsafe.check(Path(zpath))
    names = {i.filename for i in entries}
    if "manifest.json" not in names:
        raise ValueError("Not a Book Builder book package (manifest.json is missing).")
    m = json.loads(zipsafe.read(zpath, "manifest.json"))
    if m.get("kind") != KIND:
        raise ValueError(f"This is a {m.get('kind') or 'different'} archive, not a book package. "
                         "(Book-data backups are restored with the manager; app updates use option 3.)")
    with zipfile.ZipFile(zpath) as z:
        for path, digest in m["files"].items():
            if not zipsafe.safe_name(path) or path.split("/")[0] in SKIP_DIRS:
                raise ValueError(f"Unsafe path in the package: {path}")
            member = "book/" + path
            if member not in names:
                raise ValueError(f"The package is incomplete: {path} is missing.")
            if RV.sha256_bytes(z.read(member)) != digest:
                raise ValueError(f"Checksum mismatch for {path}: the package is damaged or was edited.")
    extra = sorted(n for n in names if n.startswith("book/") and not n.endswith("/") and n[5:] not in m["files"])
    if extra:
        raise ValueError(f"The package contains undeclared files: {extra[:5]}")
    if "book.yml" not in m["files"]:
        raise ValueError("The package has no book.yml.")
    return {"title": m.get("title"), "files": len(m["files"]), "chapter_files": m.get("chapter_files"),
            "exported": m.get("exported"), "source_project_id": m.get("source_project_id"),
            "include_private": m.get("include_private"), "book_builder": m.get("book_builder"),
            "bytes": sum(i.file_size for i in entries)}


def import_book(zpath: Path, folder: str | None = None) -> dict:
    info = inspect(zpath)
    base = Path(folder).expanduser() if folder else Path(REG.settings()["projectsDir"]).expanduser() / REG.slug(info["title"] or "book")
    base = base.resolve()
    if base.exists() and not any(base.iterdir()):
        pass
    if (why := REG._valid_folder(base)):
        # pick a free sibling name automatically when the default folder is taken
        if folder:
            return {"ok": False, "message": why}
        for i in range(2, 50):
            alt = base.with_name(f"{base.name}-{i}")
            if not REG._valid_folder(alt):
                base = alt
                break
        else:
            return {"ok": False, "message": why}
    m = json.loads(zipsafe.read(zpath, "manifest.json"))
    base.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        for path in m["files"]:
            out = base / path
            if not out.resolve().is_relative_to(base):
                raise ValueError(f"Unsafe path: {path}")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read("book/" + path))
    pf = {}
    try:
        pf = json.loads((base / REG.PROJECT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    pf.update({"schema": 1, "project_id": f"bk-{uuid.uuid4().hex[:12]}", "created": time.time(),
               "imported_from": {"project_id": m.get("source_project_id"), "title": m.get("title"), "exported": m.get("exported")},
               "publishing": {"enabled": False, "note": "Off for imported books until you set up the website on purpose."}})
    pf.setdefault("brand", {"status": "placeholder"})
    (base / REG.PROJECT_FILE).write_text(json.dumps(pf, indent=1), encoding="utf-8")
    entry = REG.ensure(base)
    return {"ok": True, "path": str(base), "id": entry["id"], "title": info["title"], "files": info["files"],
            "message": f"Imported “{info['title']}” as a new book in {base}. Publishing is off until you turn it on."}
