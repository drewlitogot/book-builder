"""Incremental ZIP upgrades for Book Builder's application source.

Package layout:
    forge-manifest.json          the contract (docs/UPDATE_PACKAGE_CONTRACT.md)
    payload/<relative path>      complete final contents of every added or replaced file

Inspection never executes anything from the archive. Applying requires: correct package type and
project, the exact base source revision, valid hashes for every payload and every original file,
only source paths, the server stopped, the word APPLY, and fresh source + data backups. Files are
staged, then swapped in with os.replace; any failure restores the source backup.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

from . import backups as B
from . import paths as P
from . import revision as RV
from . import zipsafe

PACKAGE_TYPE = "bookbuilder-upgrade"
MANIFEST = "forge-manifest.json"
NOT_UPDATES = {  # archives people might confuse with updates, and what they actually are
    B.SOURCE_KIND: "a source backup (restore it with option 6)",
    B.DATA_KIND: "a book-data backup (restore it with option 9)",
    "bookbuilder-qa-review": "a QA review package (evidence only, never installable)",
    "bookbuilder-ai-handoff": "an AI development handoff (context for an AI, not an update)",
    "bookbuilder-diagnostics": "a diagnostics package",
    "bookbuilder-book": "a book package (import it with New Book › Import Project)",
}


class PackageError(Exception):
    pass


def _manifest(zpath: Path, names: set[str]) -> dict:
    if MANIFEST not in names:
        if "manifest.json" in names:
            try:
                kind = json.loads(zipsafe.read(zpath, "manifest.json")).get("kind", "")
            except ValueError:
                kind = ""
            if kind in NOT_UPDATES:
                raise PackageError(f"This isn't an update: it's {NOT_UPDATES[kind]}.")
        raise PackageError(f"Not a Book Builder update package: {MANIFEST} is missing.")
    try:
        return json.loads(zipsafe.read(zpath, MANIFEST))
    except ValueError as e:
        raise PackageError(f"{MANIFEST} isn't valid JSON: {e}") from e


def inspect(zpath: Path, root: Path = P.APP) -> dict:
    """Full validation against root's current source. Returns the plan; raises PackageError."""
    try:
        entries = zipsafe.check(Path(zpath), max_total=512 * 1024 ** 2)
    except zipsafe.UnsafeArchive as e:
        raise PackageError(str(e)) from e
    names = {i.filename for i in entries}
    m = _manifest(Path(zpath), names)
    if m.get("package_type") in NOT_UPDATES:
        raise PackageError(f"This isn't an update: it's {NOT_UPDATES[m['package_type']]}.")
    if m.get("package_type") != PACKAGE_TYPE:
        raise PackageError(f"Wrong package type {m.get('package_type')!r}; expected {PACKAGE_TYPE!r}.")
    if m.get("project_id") != P.PROJECT_ID:
        raise PackageError(f"This package is for {m.get('project_id')!r}, not {P.PROJECT_ID!r}.")
    if m.get("schema_version") != 1:
        raise PackageError(f"Unsupported manifest schema {m.get('schema_version')!r}.")
    for k in ("package_id", "base_revision", "title", "operations"):
        if not m.get(k):
            raise PackageError(f"Manifest is missing {k!r}.")
    cur = RV.current(root)
    if m["base_revision"] != cur["revision"]:
        raise PackageError(f"Stale package: it was made for source revision {RV.short(m['base_revision'])}, "
                           f"but this installation is at {RV.short(cur['revision'])}. Ask for a package built on the current source.")
    ops, declared, seen = [], set(), set()
    with zipfile.ZipFile(zpath) as z:
        for op in m["operations"]:
            kind, path = op.get("op"), op.get("path", "")
            if kind not in ("add", "replace", "delete"):
                raise PackageError(f"Unknown operation {kind!r} for {path}.")
            if not zipsafe.safe_name(path) or not P.is_source_path(path):
                raise PackageError(f"Refusing to write outside the application source: {path!r}")
            if path.lower() in seen:
                raise PackageError(f"{path} appears in more than one operation.")
            seen.add(path.lower())
            target = root / path
            exists = target.is_file()
            if kind == "add" and exists:
                raise PackageError(f"Add would overwrite an existing file: {path}")
            if kind in ("replace", "delete"):
                if not exists:
                    raise PackageError(f"{kind.capitalize()} target doesn't exist: {path}")
                if not op.get("original_sha256"):
                    raise PackageError(f"{kind.capitalize()} of {path} has no original_sha256.")
                if cur["inventory"].get(path) != op["original_sha256"]:
                    raise PackageError(f"{path} has changed since the package was made (original hash mismatch).")
            if kind in ("add", "replace"):
                member = "payload/" + path
                if member not in names:
                    raise PackageError(f"Payload missing for {path}.")
                if not op.get("sha256") or RV.sha256_bytes(z.read(member)) != op["sha256"]:
                    raise PackageError(f"Payload hash mismatch for {path}: the package was modified or damaged.")
                declared.add(member)
            ops.append({"op": kind, "path": path, "bytes": z.getinfo("payload/" + path).file_size if kind != "delete" else 0})
    undeclared = sorted(n for n in names if n.startswith("payload/") and not n.endswith("/") and n not in declared)
    stray = sorted(n for n in names if not n.startswith("payload/") and n != MANIFEST and not n.endswith("/"))
    if undeclared:
        raise PackageError(f"Undeclared payload files: {undeclared[:5]}")
    if stray:
        raise PackageError(f"Unexpected files outside payload/: {stray[:5]}")
    return {"manifest": {k: m.get(k) for k in ("package_id", "title", "description", "base_revision",
                                               "assignment_id", "created", "author")},
            "operations": ops, "counts": {k: sum(1 for o in ops if o["op"] == k) for k in ("add", "replace", "delete")},
            "current_revision": cur["revision"]}


def server_running() -> list[int]:
    import urllib.request  # noqa: PLC0415
    up = []
    for port in range(8765, 8785):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=0.3) as r:  # noqa: S310
                if json.loads(r.read()).get("app") == "book-manager":
                    up.append(port)
        except (OSError, ValueError):
            continue
    return up


def apply(zpath: Path, root: Path = P.APP, confirm: str = "", check_server: bool = True,
          data_backup: bool = True, fail_after: int | None = None) -> dict:
    """Apply a validated package. `fail_after` exists for rollback tests only."""
    plan = inspect(zpath, root)
    if confirm != "APPLY":
        return {"ok": False, "needs": "APPLY", "plan": plan}
    if check_server and root == P.APP and (ports := server_running()):
        raise PackageError(f"Book Builder is running (port {ports[0]}). Quit it first; the source can't be replaced while it runs.")
    P.ensure_dirs()
    kept = P.PACKAGES / f"{time.strftime('%Y%m%d-%H%M%S')}-{plan['manifest']['package_id']}.zip"
    shutil.copy2(zpath, kept)                     # immutable original, for audit and later three-way merges
    src_backup = B.make_source_backup(root, label="pre-update")
    data_bk = B.make_data_backup(root, label="pre-update") if data_backup else None
    done = 0
    try:
        with tempfile.TemporaryDirectory(dir=P.HOME) as stage, zipfile.ZipFile(zpath) as z:
            stage = Path(stage)
            for op in plan["operations"]:
                if op["op"] != "delete":
                    out = stage / op["path"]
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(z.read("payload/" + op["path"]))
            for op in plan["operations"]:
                if fail_after is not None and done >= fail_after:
                    raise OSError("simulated failure during apply")
                dest = root / op["path"]
                if op["op"] == "delete":
                    dest.unlink()
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(stage / op["path"], dest)
                done += 1
    except Exception as e:  # noqa: BLE001
        B.restore_source(Path(src_backup["path"]), root, confirm="RESTORE")
        raise PackageError(f"Update failed after {done} change(s); the previous source was restored. ({e})") from e
    checks = post_checks(root, [o["path"] for o in plan["operations"] if o["op"] != "delete"])
    rev = RV.current(root)["revision"]
    record = {"time": time.time(), "package_id": plan["manifest"]["package_id"], "title": plan["manifest"]["title"],
              "from": plan["current_revision"], "to": rev, "source_backup": src_backup["path"],
              "data_backup": data_bk and data_bk["path"], "kept_package": str(kept), "checks": checks}
    _remember("updates", record)
    return {"ok": checks["ok"], **record}


def post_checks(root: Path, changed: list[str]) -> dict:
    """Syntax checks of changed Python/JS files and dependency declaration sanity (no imported code runs)."""
    import subprocess  # noqa: PLC0415
    problems = []
    for path in changed:
        f = root / path
        if path.endswith(".py"):
            try:
                compile(f.read_text(encoding="utf-8"), str(f), "exec")   # syntax only; nothing is run
            except SyntaxError as e:
                problems.append(f"{path}: line {e.lineno}: {e.msg}")
        elif path.endswith(".js") and shutil.which("node"):
            r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
            if r.returncode:
                problems.append(f"{path}: {r.stderr.strip()[:300]}")
        elif path.endswith(".json"):
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except ValueError as e:
                problems.append(f"{path}: invalid JSON ({e})")
    if "requirements.txt" in changed:
        for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and not __import__("re").match(r"^[A-Za-z0-9_.\-\[\]]+([<>=!~]=?[\w.*]+)?(,[<>=!~]=?[\w.*]+)*$", line.strip()):
                problems.append(f"requirements.txt: can't parse {line!r}")
    return {"ok": not problems, "problems": problems,
            "note": "Run option 4 (QA) to test the updated source; new dependencies need option 1 (Install)."}


def make(base_inventory: dict[str, str], base_revision: str, root: Path, dest: Path, package_id: str, title: str,
         description: str = "", assignment_id: str = "", partial: bool = False, deletes: list[str] | None = None) -> dict:
    """Build an update package from base_inventory (an older source) to root's source.

    partial=True is for handoffs, whose source/ copy holds only some files: files missing from root are
    treated as unchanged, and only paths listed in `deletes` are deleted."""
    cur = RV.current(root)["inventory"]
    if partial:
        for d in deletes or []:
            cur.pop(d, None)
        cur = {**{k: v for k, v in base_inventory.items() if k not in cur and k not in (deletes or [])}, **cur}
    ops = []
    for path in sorted(set(base_inventory) | set(cur)):
        if path in cur and path not in base_inventory:
            ops.append({"op": "add", "path": path, "sha256": cur[path]})
        elif path in base_inventory and path not in cur:
            ops.append({"op": "delete", "path": path, "original_sha256": base_inventory[path]})
        elif base_inventory[path] != cur[path]:
            ops.append({"op": "replace", "path": path, "sha256": cur[path], "original_sha256": base_inventory[path]})
    if not ops:
        raise PackageError("No source differences: nothing to package.")
    manifest = {"schema_version": 1, "project_id": P.PROJECT_ID, "package_id": package_id, "package_type": PACKAGE_TYPE,
                "base_revision": base_revision, "target_revision": RV.revision_of(cur), "title": title,
                "description": description, "assignment_id": assignment_id or None,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "operations": ops}
    dest.parent.mkdir(parents=True, exist_ok=True)
    if partial:
        manifest["target_revision"] = None   # unknown: the handoff copy didn't contain every file
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(MANIFEST, json.dumps(manifest, indent=1))
        for op in ops:
            if op["op"] != "delete":
                z.write(root / op["path"], "payload/" + op["path"])
    return {"ok": True, "path": str(dest), "operations": len(ops), "base_revision": base_revision,
            "target_revision": manifest["target_revision"]}


def inventory_from_backup(zpath: Path) -> tuple[dict[str, str], str]:
    m = B.inspect(Path(zpath), B.SOURCE_KIND)
    return m["files"], m["revision"]


def _remember(key: str, record: dict) -> None:
    try:
        state = json.loads(P.STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    state.setdefault(key, []).append(record)
    state[key] = state[key][-50:]
    P.STATE.parent.mkdir(parents=True, exist_ok=True)
    P.STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def state() -> dict:
    try:
        return json.loads(P.STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
