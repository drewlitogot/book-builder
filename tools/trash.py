"""Book Builder's Trash: deleted books, prompts and revisions are moved here, so they can be restored.

    BOOK_BUILDER_HOME/trash/<id>/info.json   what it was, where it came from, when it was deleted
    BOOK_BUILDER_HOME/trash/<id>/item        the file or folder itself

Nothing is erased until you delete it from the Trash page (or empty the Trash), which always asks
first. Approved chapters (book/) are never deleted by these tools.
Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path

HOME = Path(os.environ.get("BOOK_BUILDER_HOME") or Path.home() / ".book-builder")
TRASH = HOME / "trash"


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def put(path: Path, kind: str, label: str, project: str = "") -> dict:
    """Move a file or folder into the Trash. Returns its Trash record."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} doesn't exist")
    tid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    box = TRASH / tid
    box.mkdir(parents=True)
    info = {"id": tid, "kind": kind, "label": label, "original": str(path.resolve()), "project": project,
            "deletedAt": time.time(), "bytes": _size(path), "folder": path.is_dir()}
    (box / "info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    shutil.move(str(path), str(box / "item"))
    return info


def items() -> list[dict]:
    out = []
    for info in TRASH.glob("*/info.json") if TRASH.exists() else []:
        try:
            rec = json.loads(info.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (info.parent / "item").exists():
            out.append(rec)
    return sorted(out, key=lambda r: r.get("deletedAt", 0), reverse=True)


def _box(tid: str) -> Path:
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{6}", tid or ""):
        raise ValueError("Unknown Trash item.")
    box = TRASH / tid
    if not (box / "info.json").exists():
        raise ValueError("That item is no longer in the Trash.")
    return box


def restore(tid: str) -> dict:
    """Put an item back where it came from. Refuses if something new is in its place."""
    box = _box(tid)
    info = json.loads((box / "info.json").read_text(encoding="utf-8"))
    dest = Path(info["original"])
    if dest.exists():
        return {"ok": False, "message": f"Something else is already at {dest}. Move it first, then restore."}
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(box / "item"), str(dest))
    shutil.rmtree(box)
    return {"ok": True, "message": f"Restored to {dest}.", "item": info}


def purge(tid: str) -> dict:
    """Erase one item for good."""
    box = _box(tid)
    shutil.rmtree(box)
    return {"ok": True, "message": "Deleted permanently."}


def empty() -> dict:
    n = 0
    for rec in items():
        shutil.rmtree(TRASH / rec["id"], ignore_errors=True)
        n += 1
    return {"ok": True, "message": f"Emptied the Trash ({n} item{'s' if n != 1 else ''})."}
