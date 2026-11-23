"""Source backups and book-data backups: separate archives, separate restore paths.

Archive layout (both kinds): manifest.json + files/<canonical relative path>.
  - source backup: kind "bookbuilder-source-backup", every paths.source_files() file, plus the revision.
  - data backup:   kind "bookbuilder-data-backup", the project's book data (paths.data_files()), plus
                   Book Builder's app data (registry, settings) under appdata/.
A source restore never writes data paths; a data restore never writes source paths.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

from . import paths as P
from . import revision as RV
from . import zipsafe

SOURCE_KIND = "bookbuilder-source-backup"
DATA_KIND = "bookbuilder-data-backup"
APPDATA_FILES = ["registry.json", "settings.json"]


def stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _write_zip(dest: Path, root: Path, files: list[str], manifest: dict, extra: dict[str, Path] | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    hashes = {}
    tmp = dest.with_suffix(".partial")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for r in files:
            src = root / r
            hashes[r] = RV.sha256_file(src)
            z.write(src, "files/" + r)
        for name, src in (extra or {}).items():
            if src.is_file():
                hashes[name] = RV.sha256_file(src)
                z.write(src, name)
        manifest = {**manifest, "files": hashes, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        z.writestr("manifest.json", json.dumps(manifest, indent=1, sort_keys=True))
    tmp.replace(dest)
    return dest


def make_source_backup(root: Path = P.APP, label: str = "", dest_dir: Path | None = None) -> dict:
    P.ensure_dirs()
    cur = RV.current(root)
    name = f"bookbuilder-source-{stamp()}-{RV.short(cur['revision'])}{('-' + label) if label else ''}.zip"
    dest = (dest_dir or P.BACKUPS / "source") / name
    _write_zip(dest, root, sorted(cur["inventory"]), {"schema": 1, "kind": SOURCE_KIND, "project_id": P.PROJECT_ID,
                                                     "version": P.version(), "revision": cur["revision"], "label": label})
    return {"ok": True, "path": str(dest), "revision": cur["revision"], "files": cur["files"]}


def make_data_backup(project: Path = P.APP, include_private: bool = False, label: str = "",
                     dest_dir: Path | None = None) -> dict:
    """Book data is plain files (no database), so a copy is consistent unless files change mid-copy;
    each file is hashed as it's written and the manifest records exactly what was captured."""
    P.ensure_dirs()
    files = P.data_files(project, include_private)
    title = project.name
    try:
        import re  # noqa: PLC0415
        m = re.search(r"^\s*title:\s*(.+)$", (project / "book.yml").read_text(encoding="utf-8"), re.M)
        title = m.group(1).strip().strip("'\"") if m else title
    except OSError:
        pass
    extra = {f"appdata/{n}": P.HOME / n for n in APPDATA_FILES}
    skipped = [] if include_private else [d for d in P.PRIVATE_DIRS if (project / d).exists()]
    name = f"bookbuilder-data-{stamp()}{('-' + label) if label else ''}.zip"
    dest = (dest_dir or P.BACKUPS / "data") / name
    _write_zip(dest, project, files, {"schema": 1, "kind": DATA_KIND, "project_id": P.PROJECT_ID, "book_title": title,
                                      "project_path": str(project), "include_private": include_private,
                                      "not_included": skipped, "label": label})
    return {"ok": True, "path": str(dest), "files": len(files), "book": title, "not_included": skipped}


def list_backups(kind: str) -> list[dict]:
    d = P.BACKUPS / kind
    out = []
    for z in sorted(d.glob("*.zip"), reverse=True) if d.exists() else []:
        try:
            m = json.loads(zipsafe.read(z, "manifest.json"))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            m = {}
        out.append({"path": str(z), "name": z.name, "bytes": z.stat().st_size, "created": m.get("created"),
                    "revision": m.get("revision"), "files": len(m.get("files", {})), "book": m.get("book_title")})
    return out


def inspect(zpath: Path, kind: str) -> dict:
    """Validate archive safety, kind and every checksum. Raises UnsafeArchive / ValueError."""
    entries = zipsafe.check(zpath)
    names = {i.filename for i in entries}
    if "manifest.json" not in names:
        raise ValueError("Not a Book Builder backup: manifest.json is missing.")
    m = json.loads(zipsafe.read(zpath, "manifest.json"))
    if m.get("kind") != kind:
        raise ValueError(f"This is a {m.get('kind') or 'unknown'} archive, not a {kind}.")
    if m.get("project_id") != P.PROJECT_ID:
        raise ValueError("This backup belongs to a different application.")
    with zipfile.ZipFile(zpath) as z:
        for path, digest in m["files"].items():
            member = path if path.startswith("appdata/") else "files/" + path
            if member not in names:
                raise ValueError(f"Backup is incomplete: {path} is missing.")
            if RV.sha256_bytes(z.read(member)) != digest:
                raise ValueError(f"Checksum mismatch for {path}: the backup is damaged.")
    undeclared = sorted(n for n in names - {"manifest.json"} if not n.endswith("/")
                        and (n[6:] if n.startswith("files/") else n) not in m["files"])
    if undeclared:
        raise ValueError(f"Backup contains undeclared files: {undeclared[:5]}")
    return m


def restore_source(zpath: Path, root: Path = P.APP, confirm: str = "") -> dict:
    """Make root's source exactly match the backup. Book data is never touched."""
    m = inspect(zpath, SOURCE_KIND)
    bad = [p for p in m["files"] if not P.is_source_path(p)]
    if bad:
        raise ValueError(f"Backup lists non-source paths, refusing: {bad[:5]}")
    if confirm != "RESTORE":
        return {"ok": False, "needs": "RESTORE", "revision": m["revision"], "files": len(m["files"])}
    pre = make_source_backup(root, label="pre-restore")
    current = set(P.source_files(root))
    removed = sorted(current - set(m["files"]))
    with tempfile.TemporaryDirectory(dir=P.HOME) as stage:
        stage = Path(stage)
        with zipfile.ZipFile(zpath) as z:
            for path in m["files"]:
                out = stage / path
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read("files/" + path))
        try:
            for path in m["files"]:
                dest = root / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage / path, dest)
            for path in removed:
                (root / path).unlink(missing_ok=True)
        except OSError as e:
            restore_source(Path(pre["path"]), root, confirm="RESTORE") if not os.environ.get("BB_NO_ROLLBACK") else None
            raise RuntimeError(f"Restore failed and the previous source was put back: {e}") from e
    after = RV.current(root)["revision"]
    return {"ok": after == m["revision"], "revision": after, "expected": m["revision"], "removed": removed,
            "pre_restore_backup": pre["path"]}


def restore_data(zpath: Path, project: Path = P.APP, confirm: str = "", restore_appdata: bool = False) -> dict:
    """Write the backup's book-data files into project. Source files are never touched; files that
    exist now but not in the backup are listed, not deleted."""
    m = inspect(zpath, DATA_KIND)
    files = {p: d for p, d in m["files"].items() if not p.startswith("appdata/")}
    bad = [p for p in files if not P.is_data_path(p) or P.is_source_path(p)]
    if bad:
        raise ValueError(f"Backup lists non-data paths, refusing: {bad[:5]}")
    if confirm != "RESTORE":
        return {"ok": False, "needs": "RESTORE", "book": m.get("book_title"), "files": len(files)}
    pre = make_data_backup(project, include_private=bool(m.get("include_private")), label="pre-restore")
    extra_now = sorted(set(P.data_files(project, bool(m.get("include_private")))) - set(files))
    with zipfile.ZipFile(zpath) as z:
        for path in files:
            dest = project / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".bbrestore")
            tmp.write_bytes(z.read("files/" + path))
            os.replace(tmp, dest)
        if restore_appdata:
            for n in APPDATA_FILES:
                if f"appdata/{n}" in m["files"]:
                    P.HOME.mkdir(parents=True, exist_ok=True)
                    (P.HOME / n).write_bytes(z.read(f"appdata/{n}"))
    mismatched = [p for p, d in files.items() if RV.sha256_file(project / p) != d]
    return {"ok": not mismatched, "restored": len(files), "mismatched": mismatched, "not_in_backup": extra_now,
            "pre_restore_backup": pre["path"]}


def copy_tree_source(src_root: Path, dest_root: Path) -> None:
    """Copy just the application source (for tests and handoffs)."""
    for r in P.source_files(src_root):
        (dest_root / r).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_root / r, dest_root / r)
