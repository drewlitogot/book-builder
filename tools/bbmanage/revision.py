"""Deterministic source revision: SHA-256 over canonical relative paths and file contents.

The revision changes when any application source file changes and never when book data (chapters,
research, settings) changes, because only paths.source_files() are hashed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import paths as P


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def inventory(root: Path = P.APP) -> dict[str, str]:
    return {r: sha256_file(root / r) for r in P.source_files(root)}


def revision_of(inv: dict[str, str]) -> str:
    h = hashlib.sha256()
    for path in sorted(inv):
        h.update(path.encode("utf-8") + b"\0" + inv[path].encode("ascii") + b"\n")
    return h.hexdigest()


def current(root: Path = P.APP) -> dict:
    inv = inventory(root)
    return {"revision": revision_of(inv), "files": len(inv), "inventory": inv}


def short(rev: str) -> str:
    return rev[:12]


def write_inventory(root: Path, dest: Path) -> dict:
    cur = current(root)
    dest.write_text(json.dumps({"schema": 1, "project_id": P.PROJECT_ID, "version": P.version(),
                                "revision": cur["revision"], "files": cur["inventory"]}, indent=1, sort_keys=True),
                    encoding="utf-8")
    return cur
