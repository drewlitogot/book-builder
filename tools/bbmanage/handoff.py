"""AI development handoff: a self-contained ZIP a person gives to a new ChatGPT or Claude conversation.

It carries the exact source revision, the source inventory (paths + SHA-256), the module map,
architecture and contract docs, the selected source files and precise instructions for returning an
incremental update package. Manuscript content is excluded unless explicitly requested.
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

from . import paths as P
from . import revision as RV

HANDOFF_KIND = "bookbuilder-ai-handoff"
DOCS = ["docs/MODULAR_ARCHITECTURE.md", "docs/UPDATE_PACKAGE_CONTRACT.md", "docs/AI_DEVELOPMENT_HANDOFF.md",
        "docs/TESTING.md", "docs/BACKUP_AND_RECOVERY.md", "MODULES.json"]
BINARY = (".ttf", ".otf", ".woff", ".woff2", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".ico")
MAX_TEXT = 400_000


def modules() -> dict:
    try:
        return json.loads((P.APP / "MODULES.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"modules": []}


def files_for(module_ids: list[str] | None) -> list[str]:
    inv = P.source_files()
    if not module_ids:
        return inv
    import fnmatch  # noqa: PLC0415
    pats = [g for m in modules()["modules"] if m["id"] in module_ids for g in m["files"] + m.get("tests", [])]
    shared = [g for m in modules()["modules"] if m["id"] == "core" for g in m["files"]] if "core" not in module_ids else []
    return [f for f in inv if any(fnmatch.fnmatch(f, g) for g in pats + shared)]


def make(task: str = "", module_ids: list[str] | None = None, include_manuscript: bool = False,
         dest_dir: Path | None = None) -> dict:
    cur = RV.current()
    chosen = files_for(module_ids)
    rev = cur["revision"]
    instructions = f"""# Book Builder AI development handoff

You are continuing development of **Book Builder** (project id `{P.PROJECT_ID}`), version {P.version()}.

- Source revision: `{rev}`
- Source files in this handoff: {len(chosen)} of {cur['files']} (all files are listed in `source-inventory.json`)
- Modules in scope: {', '.join(module_ids) if module_ids else 'all'}
- Manuscript content included: {'YES (explicitly requested)' if include_manuscript else 'no'}

## Task
{task or '(The person giving you this handoff will describe the task.)'}

## Rules
1. Change only files in your assigned module(s); see `MODULES.json` and `docs/MODULAR_ARCHITECTURE.md`.
2. Keep the app's existing UI colors, fonts and icons. Never edit book data (book/, drafts/, research/, ...).
3. Python standard library plus requirements.txt only; no new frameworks.
4. Add or update tests under the module's test files.

## What to return: one update ZIP
Follow `docs/UPDATE_PACKAGE_CONTRACT.md` exactly:
- `forge-manifest.json` with `package_type` "bookbuilder-upgrade", `project_id` "{P.PROJECT_ID}",
  `base_revision` "{rev}", one operation per changed file, `sha256` of each new file and
  `original_sha256` (from `source-inventory.json`) for every replaced or deleted file.
- `payload/<path>`: the complete final contents of each added or replaced file. Nothing else.

If you can run Python, build it automatically: put your edited copy of `source/` next to this file and run
    python source/tools/manage.py make-update --base-inventory source-inventory.json --root source --out update.zip --id <short-id> --title "<what changed>"
Otherwise return the changed files in full and the person will build the package with that command.
Packages built on any other base revision are rejected as stale.
"""
    dest = (dest_dir or P.HOME / "handoffs") / f"bookbuilder-handoff-{RV.short(rev)}-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    skipped = []
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("HANDOFF.md", instructions)
        z.writestr("manifest.json", json.dumps({"kind": HANDOFF_KIND, "package_type": HANDOFF_KIND, "installable": False,
                                                "project_id": P.PROJECT_ID, "revision": rev, "modules": module_ids or "all",
                                                "include_manuscript": include_manuscript}, indent=1))
        z.writestr("source-inventory.json", json.dumps({"schema": 1, "project_id": P.PROJECT_ID, "revision": rev,
                                                        "files": cur["inventory"]}, indent=1, sort_keys=True))
        for d in DOCS:
            if (P.APP / d).exists():
                z.write(P.APP / d, d)
        # tools/manage.py and bbmanage are always included so the AI can build the return package.
        always = [f for f in cur["inventory"] if f == "tools/manage.py" or f.startswith("tools/bbmanage/")]
        for f in sorted(set(chosen) | set(always)):
            p = P.APP / f
            if f.endswith(BINARY) or p.stat().st_size > MAX_TEXT:
                skipped.append(f)
                continue
            z.write(p, "source/" + f)
        if include_manuscript:
            for f in P.data_files(P.APP):
                if f.startswith("book/") or f == "book.yml":
                    z.write(P.APP / f, "manuscript/" + f)
        if skipped:
            z.writestr("SKIPPED_FILES.md", "Binary or very large files left out (their hashes are in source-inventory.json):\n\n"
                       + "\n".join(f"- {f}" for f in skipped) + "\n")
    return {"ok": True, "path": str(dest), "revision": rev, "files": len(chosen), "skipped": len(skipped)}
